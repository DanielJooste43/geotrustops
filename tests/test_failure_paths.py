"""Failure paths and published-field guards (data contract §3, §5, §6; AGENTS.md privacy rule).

Expected values are written from the contract text, not imported from the implementation, so a change to the
code's own field lists cannot make these tests agree with it.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import duckdb
import pytest

from geotrustops import export
from geotrustops.export import ExportError
from geotrustops.timeline import TimelineError, _partitions

_spec = importlib.util.spec_from_file_location(
    "contract_tests", Path(__file__).parent / "contract" / "test_contract.py"
)
assert _spec and _spec.loader
_contract = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_contract)
Run, place = _contract.Run, _contract.place

# Contract §5 (properties) with the §3 flags, typed from the document.
PUBLISHED_PROPERTIES = {
    "id",
    "change_type",
    "distance_m",
    "move_band",
    *(
        f"{side}_{field}"
        for side in ("prev", "curr")
        for field in (
            "name",
            "category",
            "basic_category",
            "lon",
            "lat",
            "operating_status",
            "confidence",
        )
    ),
    "name_changed",
    "category_changed",
    "basic_category_changed",
    "name_change_kind",
    "name_matches_brand",
    "status_changed",
    "confidence_to_zero",
    "enrichment_changed",
    "format_only_changed",
    "crossed_aoi_boundary",
    "source_datasets",
    "source_licences",
}
# Contract §6: required input columns.
REQUIRED = ["id", "geometry", "names", "taxonomy", "basic_category", "confidence", "sources"]

CONTACT = {
    "phones": ["+27 12 345 6789"],
    "websites": ["https://contact.example.org"],
    "emails": ["info@contact.example.org"],
    "socials": ["https://social.example.org/cafe"],
}


def _contact_run(tmp_path: Path) -> Run:
    prev = [place(id="a", **CONTACT), place(id="b", **CONTACT)]
    curr = [place(id="a", name="Cafe Two", **CONTACT), place(id="c", **CONTACT)]
    return Run(tmp_path, prev, curr)


def test_published_properties_are_exactly_the_contract_fields(tmp_path: Path) -> None:
    run = _contact_run(tmp_path)
    assert run.build() == 0
    features = json.loads((run.out / "changes.geojson").read_text(encoding="utf-8"))["features"]
    assert features, "fixture should produce changed records"
    for f in features:
        assert set(f["properties"]) == PUBLISHED_PROPERTIES


def test_no_output_contains_contact_values(tmp_path: Path) -> None:
    run = _contact_run(tmp_path)
    assert run.build() == 0
    for path in run.out.iterdir():
        text = path.read_text(encoding="utf-8")
        for values in CONTACT.values():
            for value in values:
                assert value not in text, f"{value!r} published in {path.name}"


@pytest.mark.parametrize("column", REQUIRED)
def test_a_missing_required_column_fails_and_writes_nothing(tmp_path: Path, column: str) -> None:
    run = Run(tmp_path, [place(id="a")], [place(id="a")])
    con = duckdb.connect()
    stripped = tmp_path / "curr_stripped.parquet"
    con.execute(
        f"COPY (SELECT * EXCLUDE ({column}) FROM read_parquet($source)) "  # noqa: S608 - column from REQUIRED
        "TO $dest (FORMAT parquet)",
        {"source": run.curr.as_posix(), "dest": stripped.as_posix()},
    )
    run.args[run.args.index(str(run.curr))] = str(stripped)
    assert run.build() == 2
    assert not run.out.exists()


def test_a_failed_swap_keeps_the_previous_outputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out = tmp_path / "out"
    out.mkdir()
    (out / "summary.json").write_text("previous", encoding="utf-8")
    staging = tmp_path / "out.staging"
    staging.mkdir()
    (staging / "summary.json").write_text("new", encoding="utf-8")
    real_rename = Path.rename

    def rename(self: Path, target: Path) -> Path:
        if self == staging:
            raise OSError("simulated: file locked")
        return real_rename(self, target)

    monkeypatch.setattr(Path, "rename", rename)
    with pytest.raises(ExportError, match="previous outputs kept"):
        export._swap_into_place(staging, out, tmp_path / "out.previous")
    assert (out / "summary.json").read_text(encoding="utf-8") == "previous"


def test_a_failed_restore_names_the_previous_outputs_and_later_runs_keep_them(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out, staging, previous = tmp_path / "out", tmp_path / "out.staging", tmp_path / "out.previous"
    out.mkdir()
    (out / "summary.json").write_text("previous", encoding="utf-8")
    staging.mkdir()
    real_rename = Path.rename

    def rename(self: Path, target: Path) -> Path:
        if self in (staging, previous):  # neither the new outputs nor the restore can move
            raise OSError("simulated: file locked")
        return real_rename(self, target)

    monkeypatch.setattr(Path, "rename", rename)
    with pytest.raises(ExportError, match="out.previous"):
        export._swap_into_place(staging, out, previous)
    assert (previous / "summary.json").read_text(encoding="utf-8") == "previous"
    monkeypatch.setattr(Path, "rename", real_rename)
    # The next run must not delete the only copy: it refuses until the outputs are restored.
    with pytest.raises(ExportError, match="move out.previous back"):
        export._swap_into_place(staging, out, previous)
    assert (previous / "summary.json").read_text(encoding="utf-8") == "previous"


def test_a_corrupt_history_line_is_reported_with_its_location(tmp_path: Path) -> None:
    run = Run(tmp_path, [place(id="a")], [place(id="a", name="Cafe Two")])
    history = tmp_path / "history.jsonl"
    history.write_text('{"key": "x"}\nnot json\n', encoding="utf-8")
    run.args[run.args.index("--no-history")] = "--history"
    run.args.insert(run.args.index("--history") + 1, str(history))
    assert run.build() == 2
    assert history.read_text(encoding="utf-8") == '{"key": "x"}\nnot json\n'  # untouched
    # Contract §6 exception: the new outputs passed every check and stay in place.
    assert run.summary["change_counts"]["attribute_changed"] == 1


def test_an_empty_change_set_listing_is_refused(tmp_path: Path) -> None:
    con = duckdb.connect()
    with pytest.raises(TimelineError, match="no change_type partitions"):
        _partitions(con, (tmp_path / "type=change" / "*" / "*.parquet").as_posix())


def test_an_unreadable_input_file_exits_2_without_a_traceback(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run = Run(tmp_path, [place(id="a")], [place(id="a")])
    run.prev.write_bytes(b"not a parquet file")
    assert run.build() == 2
    assert "geotrustops: FAILED:" in capsys.readouterr().err
    assert not run.out.exists()


def test_a_row_lost_before_stage_b_fails_the_row_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from geotrustops import pipeline

    run = Run(tmp_path, [place(id="a"), place(id="b")], [place(id="a"), place(id="b")])
    anchor = "SELECT row_number() OVER () AS src_row, * FROM read_parquet($path)"
    assert anchor in pipeline._NORMALIZE, "fault-injection anchor not found; update this test"
    # Stage A silently drops the first source row: R must still be the file's row count (contract §4, identity 1).
    dropping = f"SELECT * FROM ({anchor}) WHERE src_row > 1"
    monkeypatch.setattr(pipeline, "_NORMALIZE", pipeline._NORMALIZE.replace(anchor, dropping))
    assert run.build() == 2
    assert not run.out.exists()


def test_name_matches_brand_is_false_not_null_when_the_brand_is_missing(tmp_path: Path) -> None:
    # Contract §3: flags are true/false for every matched id; a renamed record without a brand is "no match".
    run = Run(tmp_path, [place(id="a", name="Cafe")], [place(id="a", name="Cafe Two")])
    assert run.build() == 0
    assert run.prop("a")["name_matches_brand"] is False
