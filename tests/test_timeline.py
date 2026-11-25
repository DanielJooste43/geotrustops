"""Release timeline (contract §12): event rules, from positions, label checks, determinism and config checks.

Synthetic changelogs are written as small Parquet files with the columns every changelog schema has
(id, change_type, bbox).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import duckdb
import pytest

from geotrustops.config import Config, ConfigError, load_config
from geotrustops.timeline import (
    KINDS,
    TimelineError,
    TimelineInput,
    build_timeline,
    load_timeline_config,
    write_timeline,
)

ROOT = Path(__file__).resolve().parents[1]
IN_A = (28.18, -25.74)  # inside the AOI
IN_B = (28.1805, -25.74)  # ~50 m east of IN_A, inside
IN_A_JITTER = (28.180004, -25.74)  # ~0.4 m from IN_A: below the minimum step
OUT = (28.30, -25.74)  # outside the AOI
STEP = 1.0
ALL = ("added", "data_changed", "removed", "unchanged")

Row = tuple[str, str, tuple[float, float]]


@pytest.fixture(scope="module")
def cfg() -> Config:
    return load_config(ROOT / "config" / "study_area.json")


def _changelog(path: Path, rows: list[Row]) -> Path:
    con = duckdb.connect()
    con.execute(
        "CREATE TABLE t (id VARCHAR, change_type VARCHAR, bbox STRUCT(xmin FLOAT, xmax FLOAT, ymin FLOAT, ymax FLOAT))"
    )
    for rid, ct, (lon, lat) in rows:
        con.execute(
            "INSERT INTO t VALUES ($i, $c, {'xmin': $x, 'xmax': $x, 'ymin': $y, 'ymax': $y})",
            {"i": rid, "c": ct, "x": lon, "y": lat},
        )
    con.execute("COPY t TO $p (FORMAT parquet)", {"p": path.as_posix()})
    con.close()
    return path


def _inputs(
    tmp: Path, releases: list[tuple[str, list[Row], tuple[str, ...]]]
) -> list[TimelineInput]:
    return [
        TimelineInput(rel, _changelog(tmp / f"{rel}.parquet", rows), f"sha-{rel}", parts)
        for rel, rows, parts in releases
    ]


def _events(doc: dict[str, Any]) -> dict[tuple[int, str, str], dict[str, Any]]:
    out = {}
    for raw in doc["events"]:
        e = dict(zip(doc["event_fields"], raw, strict=True))
        out[(e["release_index"], KINDS[e["kind_index"]], doc["ids"][e["id_index"]])] = e
    return out


def test_event_rules_and_from_positions(cfg: Config, tmp_path: Path) -> None:
    inputs = _inputs(
        tmp_path,
        [
            (
                "2026-01-01.0",
                [
                    ("a", "added", IN_A),
                    ("o", "added", OUT),
                    ("m", "unchanged", IN_A),
                    ("j", "unchanged", IN_A),
                ],
                ALL,
            ),
            (
                "2026-02-01.0",
                [
                    ("a", "data_changed", IN_A),
                    ("x", "added", IN_A),
                    ("j", "data_changed", IN_A_JITTER),
                ],
                ALL,
            ),
            (
                "2026-03-01.0",
                [
                    ("a", "data_changed", IN_B),  # last seen in release 1
                    ("m", "data_changed", OUT),  # moves out of the AOI: kept
                    ("x", "removed", IN_A),
                ],
                ALL,
            ),
        ],
    )
    ev = _events(build_timeline(cfg, inputs, STEP))
    assert set(ev) == {
        (0, "added", "a"),
        (1, "added", "x"),
        (2, "position_changed", "a"),
        (2, "position_changed", "m"),
        (2, "removed", "x"),
    }  # outside-AOI add, edits without a move, and the sub-step jitter are not events
    a = ev[(2, "position_changed", "a")]
    assert a["from_release_index"] == 1 and (a["from_lon"], a["from_lat"]) == pytest.approx(
        IN_A, abs=1e-5
    )
    assert a["distance_m"] == pytest.approx(50.2, abs=1.0)
    assert ev[(0, "added", "a")]["from_release_index"] is None
    assert ev[(2, "removed", "x")]["from_release_index"] is None
    assert (ev[(2, "removed", "x")]["lon"], ev[(2, "removed", "x")]["lat"]) == pytest.approx(
        IN_A, abs=1e-5
    )


def test_counts_reconcile_and_label_checks(cfg: Config, tmp_path: Path) -> None:
    inputs = _inputs(
        tmp_path,
        [
            ("2026-01-01.0", [("a", "added", IN_A), ("b", "added", IN_B)], ALL),
            # Only `unchanged` published, yet a moved and n is new: both are counted as label checks.
            (
                "2026-02-01.0",
                [("a", "unchanged", IN_B), ("b", "unchanged", IN_B), ("n", "unchanged", IN_A)],
                ("unchanged",),
            ),
            ("2026-03-01.0", [("b", "removed", IN_B)], ("removed",)),
        ],
    )
    doc = build_timeline(cfg, inputs, STEP)
    rel = doc["releases"]
    assert [r["changes_published"] for r in rel] == [True, False, True]
    assert rel[1]["position_changed"] == 1 and rel[1]["position_changed_labelled_unchanged"] == 1
    assert rel[1]["first_seen_without_added"] == 1
    assert rel[0]["first_seen_without_added"] == 0  # the first release has no earlier changelog
    assert sum(r[k] for r in rel for k in KINDS) == doc["event_count"] == len(doc["events"]) == 4
    assert doc["inputs_sha256"] == {i.release: i.sha256 for i in inputs}


def test_output_is_deterministic_json(cfg: Config, tmp_path: Path) -> None:
    inputs = _inputs(
        tmp_path,
        [
            ("2026-01-01.0", [("a", "added", IN_A)], ALL),
            ("2026-02-01.0", [("a", "unchanged", IN_B)], ALL),
        ],
    )
    doc = build_timeline(cfg, inputs, STEP)
    p1 = write_timeline(doc, tmp_path / "o1")
    p2 = write_timeline(build_timeline(cfg, inputs, STEP), tmp_path / "o2")
    assert p1.read_bytes() == p2.read_bytes() and b"\r\n" not in p1.read_bytes()
    assert json.loads(p1.read_text(encoding="utf-8")) == json.loads(json.dumps(doc))


def test_rejects_duplicates_and_disorder(cfg: Config, tmp_path: Path) -> None:
    dup = _inputs(
        tmp_path, [("2026-01-01.0", [("a", "added", IN_A), ("a", "unchanged", IN_A)], ALL)]
    )
    with pytest.raises(TimelineError, match="appears twice"):
        build_timeline(cfg, dup, STEP)
    # Same SHA-256 (as a republished patch changelog has): refused when it holds changes...
    rows: list[Row] = [("a", "added", IN_A)]
    same = _inputs(tmp_path, [("2026-04-01.0", rows, ALL), ("2026-04-01.1", rows, ALL)])
    same[1] = TimelineInput(same[1].release, same[1].path, same[0].sha256, ALL)
    with pytest.raises(TimelineError, match="identical"):
        build_timeline(cfg, same, STEP)
    # ...and allowed when it holds only `unchanged` rows (two quiet releases in a row).
    quiet_rows: list[Row] = [("a", "unchanged", IN_A)]
    quiet = _inputs(
        tmp_path, [("2026-05-01.0", quiet_rows, ALL), ("2026-06-01.0", quiet_rows, ALL)]
    )
    quiet[1] = TimelineInput(quiet[1].release, quiet[1].path, quiet[0].sha256, ALL)
    assert build_timeline(cfg, quiet, STEP)["event_count"] == 0
    disorder = _inputs(
        tmp_path,
        [
            ("2026-02-01.0", [("a", "added", IN_A)], ALL),
            ("2026-01-01.0", [("b", "added", IN_A)], ALL),
        ],
    )
    with pytest.raises(TimelineError, match="oldest first"):
        build_timeline(cfg, disorder, STEP)


@pytest.mark.parametrize(
    "raw",
    [
        {"releases": ["2026-02-01.0", "2026-01-01.0"], "min_step_m": 1},
        {"releases": ["2026-01-01.0", "2026-01-01.0"], "min_step_m": 1},
        {"releases": ["2024-06-13-beta.0", "2026-01-01.0"], "min_step_m": 1},
        {"releases": ["2026-01-01.0", "2026-02-01.0"], "min_step_m": 0},
        {"releases": ["2026-01-01.0", "2026-02-01.0"]},
    ],
)
def test_timeline_config_validation(tmp_path: Path, raw: dict[str, Any]) -> None:
    p = tmp_path / "t.json"
    p.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ConfigError):
        load_timeline_config(p)


def test_committed_config_is_valid() -> None:
    tcfg = load_timeline_config(ROOT / "config" / "timeline.json")
    assert tcfg.releases[-1] == load_config(ROOT / "config" / "study_area.json").curr_release
    assert tcfg.out_dir == "out_timeline" and tcfg.min_step_m == 1.0


# --- The committed file (contract §12) -------------------------------------------------------------------------

TIMELINE = ROOT / "out_timeline" / "timeline.json"
TOP_KEYS = {
    "schema_version", "aoi", "min_step_m", "method", "interpretation", "kinds", "event_fields", "releases",
    "ids", "events", "event_count", "inputs_sha256", "licences", "attribution",
}  # fmt: skip


@pytest.fixture(scope="module")
def committed() -> dict[str, Any]:
    doc: dict[str, Any] = json.loads(TIMELINE.read_text(encoding="utf-8"))
    return doc


def test_committed_shape_licences_and_releases(committed: dict[str, Any]) -> None:
    assert set(committed) == TOP_KEYS  # no names or other place attributes
    assert committed["schema_version"] == 1
    assert committed["licences"] == ["CDLA-Permissive-2.0", "Apache-2.0", "CC0-1.0"]
    assert "Overture Maps Foundation" in committed["attribution"]
    tcfg = load_timeline_config(ROOT / "config" / "timeline.json")
    assert [r["release"] for r in committed["releases"]] == list(tcfg.releases)
    assert list(committed["inputs_sha256"]) == list(tcfg.releases)
    assert (
        committed["event_count"]
        == len(committed["events"])
        == sum(r[k] for r in committed["releases"] for k in KINDS)
    )


def test_committed_file_is_written_deterministically(
    committed: dict[str, Any], tmp_path: Path
) -> None:
    assert write_timeline(committed, tmp_path).read_bytes() == TIMELINE.read_bytes()


def test_committed_curr_release_reconciles_with_the_change_run(committed: dict[str, Any]) -> None:
    summary = json.loads((ROOT / "out" / "summary.json").read_text(encoding="utf-8"))
    curr = summary["releases"]["curr"]
    i = [r["release"] for r in committed["releases"]].index(curr)
    rel = committed["releases"][i]
    assert committed["inputs_sha256"][curr] == summary["changelog_check"]["changelog_sha256"]
    assert (rel["added"], rel["removed"]) == (
        summary["change_counts"]["added"],
        summary["change_counts"]["removed"],
    )
    moves = {
        committed["ids"][e[2]]: e[8]
        for e in committed["events"]
        if e[0] == i and committed["kinds"][e[1]] == "position_changed"
    }
    changes = json.loads((ROOT / "out" / "changes.geojson").read_text(encoding="utf-8"))
    for f in changes["features"]:
        p = f["properties"]
        if p["change_type"] in ("moved", "shifted"):
            assert p["id"] in moves, p["id"]
            assert moves[p["id"]] == pytest.approx(p["distance_m"], abs=0.5)
