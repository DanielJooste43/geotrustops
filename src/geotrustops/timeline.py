# ruff: noqa: S608 - f-strings insert only internal SQL fragments (the distance formula, AOI tests); every value is a
# named parameter.
"""Release timeline from Overture places changelogs (data contract §12).

Purpose: show the study area's change history release by release, and follow a record's position over time.
Inputs: one places changelog extract per release in config/timeline.json (downloaded for the extraction bbox,
with the same manifest checks as the pinned extracts), plus the AOI from config/study_area.json.
Output: out_timeline/timeline.json with per-release counts and one event per added record, removed record or
position change in the AOI.

Facts this relies on (checked 2026-11-25):
- A changelog row's `bbox` is the record's position in that release; for `removed` rows it is the position in the
  release before (November 2026: 398/398 geometry changes matched curr, 327/327 removals matched prev).
- Changelogs before 2026-03-18.0 have no `columns_changed` and store `bbox` as 32-bit floats (about 0.2 m here);
  later ones store doubles. A position change is therefore detected from positions, not from change labels:
  the record's position differs from its last-seen position by at least `min_step_m`.
- Overture does not publish every change set for every release, so the partitions published are recorded.
Limits: timing is per release only (the data has no per-change timestamp); "from" positions are the last position
seen in an earlier changelog, and that release is named.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb

from geotrustops.config import Config, ConfigError
from geotrustops.extract import (
    CHANGELOG_SELECT,
    ExtractError,
    changelog_path,
    download,
    s3_connection,
    verify_manifest,
)

SCHEMA_VERSION = 1
RELEASE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}\.\d+$")
CHANGE_SETS = ("added", "data_changed", "removed", "unchanged")
KINDS = ("added", "removed", "position_changed")
EVENT_FIELDS = (
    "release_index", "kind_index", "id_index", "lon", "lat",
    "from_release_index", "from_lon", "from_lat", "distance_m",
)  # fmt: skip
LICENCES = ("CDLA-Permissive-2.0", "Apache-2.0", "CC0-1.0")
ATTRIBUTION = (
    "© Overture Maps Foundation, overturemaps.org. Places data from Meta, Microsoft, Foursquare "
    "(Copyright 2024 Foursquare Labs, Inc. All rights reserved.), AllThePlaces and other Overture sources."
)
# Changelogs before 2026-03-18.0 lack columns_changed. Extracts share their path with the build's changelog
# extract, so a release whose changelog has the column keeps the build's exact column set (contract §10).
LEGACY_SELECT = "id, change_type, bbox"
EARTH_RADIUS_M = 6_371_008.8


class TimelineError(RuntimeError):
    """A timeline input is missing or inconsistent."""


@dataclass(frozen=True)
class TimelineConfig:
    releases: tuple[str, ...]
    min_step_m: float
    out_dir: str


@dataclass(frozen=True)
class TimelineInput:
    release: str
    path: Path
    sha256: str
    change_type_partitions: tuple[str, ...]


def load_timeline_config(path: Path) -> TimelineConfig:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8-sig"))
        releases = tuple(str(r) for r in raw["releases"])
        min_step_m = float(raw["min_step_m"])
        out_dir = str(raw.get("out_dir", "out_timeline"))
    except (KeyError, TypeError, ValueError, OSError) as exc:
        raise ConfigError(f"invalid timeline config {path}: {exc}") from exc
    bad = [r for r in releases if not RELEASE_RE.match(r)]
    if bad:
        raise ConfigError(f"timeline releases not in YYYY-MM-DD.N form: {bad}")
    if len(releases) < 2 or list(releases) != sorted(set(releases)):
        raise ConfigError("timeline releases must be at least two, unique and oldest first")
    if not min_step_m > 0:
        raise ConfigError("timeline min_step_m must be positive")
    return TimelineConfig(releases, min_step_m, out_dir)


def _partitions(con: duckdb.DuckDBPyConnection, uri: str) -> list[str]:
    rows = con.execute(
        "SELECT DISTINCT regexp_extract(file, 'change_type=([a-z_]+)', 1) AS t FROM glob($uri) ORDER BY t",
        {"uri": uri},
    ).fetchall()
    found = [str(r[0]) for r in rows if r[0]]
    if not found:
        # An empty listing usually means the release is no longer on S3 (kept at most 60 days), not that Overture
        # published nothing; recording it would label the release "no change sets published".
        raise TimelineError(
            f"{uri}: no change_type partitions found; refusing to record an empty listing"
        )
    unknown = sorted(set(found) - set(CHANGE_SETS))
    if unknown:
        raise ExtractError(f"{uri}: unexpected change_type partitions {unknown}")
    return found


def changelog_select(columns: list[str]) -> str:
    """The columns to extract: the build's set when the changelog has columns_changed, else the legacy set."""
    return CHANGELOG_SELECT if "columns_changed" in columns else LEGACY_SELECT


def _columns(con: duckdb.DuckDBPyConnection, uri: str) -> list[str]:
    rows = con.execute(
        "DESCRIBE SELECT * FROM read_parquet($uri, hive_partitioning = true)", {"uri": uri}
    ).fetchall()
    return [str(r[0]) for r in rows]


def fetch_timeline(cfg: Config, tcfg: TimelineConfig, raw_dir: Path, force: bool = False) -> None:
    """Download each release's changelog extract unless present; record which change sets Overture published."""
    con: duckdb.DuckDBPyConnection | None = None
    try:
        for rel in tcfg.releases:
            out = changelog_path(raw_dir, rel)
            uri = cfg.changelog_uri.format(release=rel)
            if out.exists() and not force:
                m = verify_manifest(out, cfg, "changelog", rel)
                if (
                    "change_type_partitions" not in m
                ):  # extract made by `fetch`: add the listing once
                    con = con or s3_connection(cfg)
                    m["change_type_partitions"] = _partitions(con, uri)
                    mpath = out.parent / "manifest.json"
                    mpath.write_text(json.dumps(m, indent=2) + "\n", encoding="utf-8")
                print(f"skip: changelog {rel} present ({m['row_count']} rows)")
                continue
            con = con or s3_connection(cfg)
            parts = _partitions(con, uri)
            meta = {"kind": "changelog", "release": rel, "change_type_partitions": parts}
            select = changelog_select(_columns(con, uri))
            m = download(con, uri, select, cfg.extraction_bbox, out, meta)
            print(f"changelog {rel}: {m['row_count']} rows, change sets {', '.join(parts)}")
    finally:
        if con is not None:
            con.close()


def load_inputs(cfg: Config, tcfg: TimelineConfig, raw_dir: Path) -> list[TimelineInput]:
    """Verify every extract against its manifest (release, bbox, SHA-256) before it is used."""
    inputs = []
    for rel in tcfg.releases:
        path = changelog_path(raw_dir, rel)
        m = verify_manifest(path, cfg, "changelog", rel)
        if "change_type_partitions" not in m:
            raise TimelineError(
                f"{path}: manifest lacks change_type_partitions (run `geotrustops timeline --fetch`)"
            )
        inputs.append(
            TimelineInput(rel, path, str(m["sha256"]), tuple(m["change_type_partitions"]))
        )
    return inputs


# Haversine distance in metres between the row (lon, lat) and its prior position (plon, plat).
_DIST = (
    f"2 * {EARTH_RADIUS_M} * asin(sqrt(pow(sin(radians(lat - plat) / 2), 2) "
    "+ cos(radians(plat)) * cos(radians(lat)) * pow(sin(radians(lon - plon) / 2), 2)))"
)


def build_timeline(cfg: Config, inputs: list[TimelineInput], min_step_m: float) -> dict[str, Any]:
    if [i.release for i in inputs] != sorted({i.release for i in inputs}):
        raise TimelineError("timeline inputs must be unique releases, oldest first")
    con = duckdb.connect()
    try:
        con.execute(
            "CREATE TABLE r (idx INTEGER, id VARCHAR, change_type VARCHAR, lon DOUBLE, lat DOUBLE)"
        )
        for idx, inp in enumerate(inputs):
            con.execute(
                """INSERT INTO r SELECT $idx, id, change_type,
                       ((bbox.xmin + bbox.xmax) / 2)::DOUBLE, ((bbox.ymin + bbox.ymax) / 2)::DOUBLE
                   FROM read_parquet($p)""",
                {"idx": idx, "p": inp.path.as_posix()},
            )
        # A patch release can republish its .0 changelog unchanged; counting both would double every
        # change. Identical changelogs holding only `unchanged` rows (nothing changed twice) are harmless.
        seen: dict[str, int] = {}
        for idx, inp in enumerate(inputs):
            first = seen.setdefault(inp.sha256, idx)
            if first != idx:
                changes = con.execute(
                    "SELECT count(*) FROM r WHERE idx = $i AND change_type <> 'unchanged'",
                    {"i": idx},
                ).fetchone()
                if changes and changes[0]:
                    raise TimelineError(
                        f"changelogs of {inputs[first].release} and {inp.release} are identical; "
                        "keep one"
                    )
        dup = con.execute(
            "SELECT idx, id FROM r GROUP BY ALL HAVING count(*) > 1 LIMIT 1"
        ).fetchone()
        if dup:
            raise TimelineError(
                f"record {dup[1]} appears twice in the changelog of {inputs[dup[0]].release}"
            )
        a = cfg.aoi
        in_aoi = "({x} BETWEEN $w AND $e AND {y} BETWEEN $s AND $n)"
        here, before = in_aoi.format(x="lon", y="lat"), in_aoi.format(x="plon", y="plat")
        con.execute(
            """CREATE TABLE j AS
                SELECT r.*, p.idx AS pidx, p.change_type AS pchange, p.lon AS plon, p.lat AS plat
                FROM r ASOF LEFT JOIN r AS p ON r.id = p.id AND r.idx > p.idx"""
        )
        con.execute(
            f"""CREATE TABLE e AS
                SELECT *, CASE WHEN change_type = 'added' THEN 'added'
                               WHEN change_type = 'removed' THEN 'removed'
                               WHEN pidx IS NOT NULL AND pchange <> 'removed' AND {_DIST} >= $step
                                 THEN 'position_changed' END AS kind,
                          CASE WHEN pidx IS NOT NULL THEN {_DIST} END AS dist
                FROM j""",
            {"step": min_step_m},
        )
        params = {"w": a.west, "e": a.east, "s": a.south, "n": a.north}
        rows = con.execute(
            f"""SELECT idx, kind, id, lon, lat, pidx, plon, plat, dist FROM e
                WHERE kind IS NOT NULL AND ({here} OR (kind = 'position_changed' AND {before}))
                ORDER BY idx, kind, id""",
            params,
        ).fetchall()
        # Label checks: position changes Overture labelled `unchanged`, and records first seen without `added`.
        checks = dict.fromkeys(range(len(inputs)), (0, 0))
        for idx, unlabelled_moves, new_without_added in con.execute(
            f"""SELECT idx,
                    count(*) FILTER (WHERE kind = 'position_changed' AND change_type = 'unchanged'),
                    count(*) FILTER (WHERE pidx IS NULL AND idx > 0 AND change_type <> 'added' AND {here})
                FROM e WHERE {here} OR (kind = 'position_changed' AND {before}) GROUP BY idx""",
            params,
        ).fetchall():
            checks[idx] = (int(unlabelled_moves), int(new_without_added))
    finally:
        con.close()

    ids = sorted({r[2] for r in rows})
    id_index = {v: i for i, v in enumerate(ids)}
    counts = [dict.fromkeys(KINDS, 0) for _ in inputs]
    events = []
    for idx, kind, rid, lon, lat, pidx, plon, plat, dist in rows:
        counts[idx][kind] += 1
        moved = kind == "position_changed"
        events.append([
            idx, KINDS.index(kind), id_index[rid], round(lon, 6), round(lat, 6),
            pidx if moved else None,
            round(plon, 6) if moved else None,
            round(plat, 6) if moved else None,
            round(dist, 1) if moved else None,
        ])  # fmt: skip

    releases = [
        {
            "release": inp.release,
            "change_type_partitions": list(inp.change_type_partitions),
            "changes_published": any(
                t in inp.change_type_partitions for t in ("added", "removed", "data_changed")
            ),
            **counts[i],
            "position_changed_labelled_unchanged": checks[i][0],
            "first_seen_without_added": checks[i][1],
        }
        for i, inp in enumerate(inputs)
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "aoi": cfg.aoi.as_dict(),
        "min_step_m": min_step_m,
        "method": (
            "Overture places changelogs, one per release, filtered to the AOI. Added and removed come from the "
            "changelog's change type. A position change is a record whose changelog position differs from its "
            "last-seen position (latest earlier changelog that lists it) by at least min_step_m, whatever its "
            "change type. Position is the changelog bbox centre; for removed records, the last position."
        ),
        "interpretation": [
            "Timing is per release: the data does not say when within a release interval a change happened.",
            "Trails join release positions in order; the lines between them are not observed paths.",
            "Releases with changes_published false had no added, removed or data_changed rows published by "
            "Overture; their added and removed counts are not evidence of no change.",
            "A spike can reflect a source or schema change rather than real-world change.",
            "Where a release's changelog is missing (June 2025), the next changelog is relative to a release not "
            "listed here: records first seen there without an added row are counted in first_seen_without_added.",
            "Positions before 2026-03-18.0 are stored as 32-bit floats (about 0.2 m here); min_step_m is set "
            "above that.",
        ],
        "kinds": list(KINDS),
        "event_fields": list(EVENT_FIELDS),
        "releases": releases,
        "ids": ids,
        "events": events,
        "event_count": len(events),
        "inputs_sha256": {inp.release: inp.sha256 for inp in inputs},
        "licences": list(LICENCES),
        "attribution": ATTRIBUTION,
    }


def write_timeline(doc: dict[str, Any], out_dir: Path) -> Path:
    """Write deterministically: sorted top-level keys, one id and one event per line, LF newlines."""
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "timeline.json"
    head = {k: v for k, v in doc.items() if k not in ("events", "ids")}
    parts = [
        json.dumps(k) + ": " + json.dumps(head[k], ensure_ascii=False, sort_keys=True)
        for k in sorted(head)
    ]
    parts.append('"ids": [\n' + ",\n".join(json.dumps(i) for i in doc["ids"]) + "\n]")
    parts.append(
        '"events": [\n'
        + ",\n".join(json.dumps(e, separators=(",", ":")) for e in doc["events"])
        + "\n]"
    )
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text("{\n" + ",\n".join(parts) + "\n}\n", encoding="utf-8", newline="\n")
    tmp.replace(path)
    return path
