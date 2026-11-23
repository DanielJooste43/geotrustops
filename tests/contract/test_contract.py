"""Independent contract checks using synthetic Overture inputs and public CLI.

Inputs: plain dictionaries via the shared fixture writer. Outputs: CLI exit status,
GeoJSON, summary and QA text. Assumptions: WGS84, 6,371,000 m spherical radius;
written from docs/data_contract.md alone, independently of the implementation and its unit tests.
"""

import importlib.util
import json
import math
from pathlib import Path

import pytest

from geotrustops.cli import main

_spec = importlib.util.spec_from_file_location(
    "contract_fixture", Path(__file__).parents[1] / "fixtures" / "make_fixture.py"
)
_fixture = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_fixture)
write_places = _fixture.write_places
write_changelog = _fixture.write_changelog


def place(id="subject", **kwargs):
    if kwargs.get("addresses"):
        kwargs["addresses"] = [dict.fromkeys(
            ["freeform", "locality", "postcode", "region", "country"]
        ) | address for address in kwargs["addresses"]]
    return {"id": id, "lon": 28.18, "lat": -25.745,
            "name": "Cafe", "category": "cafe", "basic_category": "eat", **kwargs}


def north(metres):
    return -25.745 + math.degrees(metres / 6371000)


class Run:
    def __init__(self, root, prev, curr, *, minimal=False, oracle=None, **config):
        self.root = root
        self.out = root / "out"
        self.cfg = root / "config.json"
        self.cfg.write_text(json.dumps({
            "releases": {"prev": "2026-10-21.0", "curr": "2026-11-18.0"},
            "aoi": {"west": 28.168, "south": -25.758, "east": 28.205, "north": -25.732},
            "buffer_deg": 0.01, "move_threshold_m": 25.0, "minor_move_m": 5.0,
            "major_move_m": 100.0, "max_excluded_share": 0.05, **config,
        }), encoding="utf-8")
        self.prev = write_places(root / "prev.parquet", prev, minimal=minimal)
        self.curr = write_places(root / "curr.parquet", curr, minimal=minimal)
        self.args = ["build", "--config", str(self.cfg), "--prev", str(self.prev),
                     "--curr", str(self.curr), "--out", str(self.out), "--no-history"]
        if oracle is not None:
            cl = write_changelog(root / "changelog.parquet", oracle)
            self.args += ["--changelog", str(cl)]

    def build(self):
        return main(self.args)

    @property
    def summary(self):
        return json.loads((self.out / "summary.json").read_text(encoding="utf-8"))

    @property
    def features(self):
        features = json.loads((self.out / "changes.geojson").read_text(encoding="utf-8"))["features"]
        return {f["properties"]["id"]: f for f in features}

    def prop(self, id="subject"):
        return self.features[id]["properties"]

    def snapshot(self):
        return {p.relative_to(self.out).as_posix(): p.read_bytes()
                for p in self.out.rglob("*") if p.is_file()}


@pytest.mark.parametrize("distance,kind,band", [
    (0, "unchanged", "stable"), (4.999, "unchanged", "stable"),
    (5.001, "shifted", "minor"), (24.999, "shifted", "minor"),
    (25.001, "moved", "material"), (99.999, "moved", "material"),
    (100.001, "moved", "major"),
])
def test_thresholds_and_move_bands(tmp_path, distance, kind, band):
    run = Run(tmp_path, [place()], [place(lat=north(distance))])
    assert run.build() == 0
    assert run.summary["change_counts"][kind] == 1
    assert run.summary["move_band_counts"][band] == 1
    if kind != "unchanged":
        assert run.prop()["move_band"] == band
        assert run.prop()["distance_m"] == round(distance, 1)
    else:
        assert not run.features


@pytest.mark.parametrize("field", ["name", "category", "basic_category"])
@pytest.mark.parametrize("distance,kind", [(0, "attribute_changed"), (10, "attribute_changed"), (30, "moved")])
def test_null_to_value_and_priority(tmp_path, field, distance, kind):
    run = Run(tmp_path, [place(**{field: None})], [place(lat=north(distance))])
    assert run.build() == 0
    assert run.prop()["change_type"] == kind
    assert run.prop()[field + "_changed"] is True


@pytest.mark.parametrize("old,new,kind", [
    (None, "Cafe", "added"), ("Cafe", None, "removed"),
    (" Cafe   North ", "cafe north", "case_or_spacing"),
    ("Cafe-North!", "Cafe North", "punctuation"),
    ("Cafe", "Cafe North", "expanded_or_trimmed"),
    ("Cafe North", "Cafe", "expanded_or_trimmed"),
    ("Cafe", "Bakery", "different"), ("", "Cafe", "added"),
])
def test_name_change_kinds(tmp_path, old, new, kind):
    run = Run(tmp_path, [place(name=old)], [place(name=new)])
    assert run.build() == 0
    assert run.prop()["name_change_kind"] == kind
    assert run.summary["name_change_kind_counts"][kind] == 1


def test_brand_match_and_unchanged_name_kind(tmp_path):
    run = Run(tmp_path, [place(), place("same")],
              [place(name="Brand", brand_name="BRAND"), place("same", lat=north(30))])
    assert run.build() == 0
    assert run.prop()["name_matches_brand"] is True
    assert run.prop("same")["name_change_kind"] is None
    assert run.prop("same")["name_matches_brand"] is False


def test_study_membership_and_boundary_crossers(tmp_path):
    run = Run(tmp_path,
              [place("outside", lon=28.16), place("cross", lon=28.1679), place("edge", lon=28.168)],
              [place("outside", lon=28.161), place("cross", lon=28.169)])
    assert run.build() == 0
    assert set(run.features) == {"cross", "edge"}
    assert run.prop("cross")["change_type"] == "moved"
    assert run.prop("cross")["crossed_aoi_boundary"] is True
    assert run.prop("edge")["change_type"] == "removed"
    assert run.features["edge"]["geometry"]["coordinates"] == [28.168, -25.745]
    assert run.summary["change_counts"]["added"] == 0


@pytest.mark.parametrize("minimal", [False, True])
def test_confidence_alone_is_unchanged_and_optional_columns(tmp_path, minimal):
    run = Run(tmp_path, [place(confidence=0.8)], [place(confidence=0.4)], minimal=minimal)
    assert run.build() == 0
    assert run.summary["change_counts"]["unchanged"] == 1
    assert not run.features


def test_lifecycle_flags_do_not_classify(tmp_path):
    run = Run(tmp_path, [place(operating_status="open", confidence=None)],
              [place(operating_status="permanently_closed", confidence=0)])
    assert run.build() == 0
    assert run.summary["change_counts"]["unchanged"] == 1
    assert run.summary["flag_counts"]["status_changed"] == 1
    assert run.summary["flag_counts"]["confidence_to_zero"] == 1


@pytest.mark.parametrize("region,code", [("GP", "ZA-GP"), ("gauteng", "ZA-GP"),
    ("WC", "ZA-WC"), ("KwaZulu Natal", "ZA-KZN"), ("KwaZulu-Natal", "ZA-KZN"),
    ("North West", "ZA-NW"), ("Mpumalanga", "ZA-MP"), ("Limpopo", "ZA-LP"),
    ("Eastern Cape", "ZA-EC"), ("Free State", "ZA-FS"), ("Northern Cape", "ZA-NC")])
def test_address_and_phone_format_only(tmp_path, region, code):
    run = Run(tmp_path,
              [place(addresses=[{"region": region, "country": "ZA"}], phones=["012 345-6789"])],
              [place(addresses=[{"region": code, "country": "ZA"}], phones=["+27123456789"])])
    assert run.build() == 0
    summary = run.summary
    assert summary["change_counts"]["unchanged"] == 1
    assert summary["format_only_field_counts"]["addresses"] == 1
    assert summary["format_only_field_counts"]["phones"] == 1
    assert summary["enrichment_field_counts"].get("addresses", 0) == 0
    assert summary["enrichment_field_counts"].get("phones", 0) == 0


def test_phone_without_country_is_real_enrichment(tmp_path):
    run = Run(tmp_path, [place(phones=["0123456789"])], [place(phones=["+27123456789"])])
    assert run.build() == 0
    assert run.summary["enrichment_field_counts"]["phones"] == 1
    assert run.summary["format_only_field_counts"].get("phones", 0) == 0


@pytest.mark.parametrize("bad,reason", [
    (place(id=None), "missing_id"), (place(id=""), "missing_id"),
    (place(geometry=None), "missing_geometry"),
    (place(wkt="LINESTRING (28.18 -25.745, 28.181 -25.745)"), "non_point_geometry"),
    (place(lon=181), "invalid_coordinates"),
])
def test_exclusion_reasons(tmp_path, bad, reason):
    good = [place(str(i)) for i in range(20)]
    run = Run(tmp_path, good + [bad], good)
    assert run.build() == 0  # 1/21 < 5%; exclusion must be audited, not fatal
    assert reason in (run.out / "qa_report.md").read_text(encoding="utf-8")
    assert run.summary["excluded_rows_by_reason"]["prev"][reason] == 1
    assert not run.features
    assert run.summary["change_counts"]["unchanged"] == 20


def test_duplicate_copies_excluded_even_if_other_side_valid(tmp_path):
    good = [place(str(i)) for i in range(40)]
    run = Run(tmp_path, good + [place(), place(geometry=None)], good + [place()])
    assert run.build() == 0
    assert run.summary["change_counts"]["excluded"] == 1
    assert run.summary["excluded_rows_by_reason"]["prev"]["duplicate_id"] == 2
    assert run.summary["excluded_rows_by_reason"]["prev"]["missing_geometry"] == 0
    assert run.summary["change_counts"]["removed"] == 0
    assert run.summary["change_counts"]["added"] == 0
    assert "duplicate_id" in (run.out / "qa_report.md").read_text(encoding="utf-8")


@pytest.mark.parametrize("failure", ["empty_prev", "empty_curr", "missing_prev", "missing_curr", "exclusion_gate"])
def test_failed_run_preserves_previous_outputs(tmp_path, failure):
    run = Run(tmp_path, [place()], [place(name="New")])
    assert run.build() == 0
    before = run.snapshot()
    if failure.startswith("empty"):
        write_places(getattr(run, failure.split("_")[1]), [])
    elif failure.startswith("missing"):
        getattr(run, failure.split("_")[1]).unlink()
    else:
        write_places(run.curr, [place(geometry=None)])
    assert run.build() == 2
    assert run.snapshot() == before


def test_reconciliation_and_byte_identical_rerun(tmp_path):
    prev = [place("removed"), place("moved"), place("renamed"), place("shifted"), place("same")]
    curr = [place("added"), place("moved", lat=north(40)), place("renamed", name="New"),
            place("shifted", lat=north(10)), place("same")]
    run = Run(tmp_path, prev, curr)
    assert run.build() == 0
    assert run.summary["change_counts"] == {"excluded": 0, "added": 1, "removed": 1,
        "moved": 1, "attribute_changed": 1, "shifted": 1, "unchanged": 1}
    summary = run.summary
    assert summary["considered_ids"] == sum(summary["change_counts"].values()) == 6
    assert summary["union_ids"] == summary["considered_ids"] + summary["buffer_only_ids"] == 6
    for side in ("prev", "curr"):
        assert summary["input_rows"][side] == summary["valid_rows"][side] + sum(
            summary["excluded_rows_by_reason"][side].values()) == 5
    for identity in summary["reconciliation"].values():
        assert identity["holds"] is True
        assert identity["lhs"] == identity["rhs"]
    ids = list(run.features)
    assert ids == sorted(ids)
    before = run.snapshot()
    assert run.build() == 0
    assert run.snapshot() == before
    assert not (tmp_path / "runs").exists()


@pytest.mark.parametrize("scenario", ["added", "removed", "moved", "shifted", "attribute_changed",
                                      "unchanged", "reverse_not_required"])
@pytest.mark.parametrize("mismatch", [False, True])
def test_changelog_rules(tmp_path, scenario, mismatch):
    prev, curr = [place("anchor"), place()], [place("anchor"), place()]
    columns, cl_type = [], "unchanged"
    if scenario == "added":
        prev.pop()
        cl_type = "added"
    elif scenario == "removed":
        curr.pop()
        cl_type = "removed"
    elif scenario in ("moved", "shifted"):
        curr[-1] = place(lat=north(40 if scenario == "moved" else 10))
        columns, cl_type = ["geometry"], "data_changed"
    elif scenario == "attribute_changed":
        curr[-1] = place(name="New")
        columns, cl_type = ["names"], "data_changed"
    elif scenario == "reverse_not_required":
        curr[-1] = place(lat=north(1))
        columns, cl_type = ["geometry"], "data_changed"
    if mismatch:
        if scenario in ("unchanged", "reverse_not_required"):
            curr[-1] = place(operating_status="closed")
            cl_type, columns = "unchanged", []
        elif scenario in ("moved", "shifted", "attribute_changed"):
            columns = []
        else:
            cl_type = "unchanged"
    oracle = [{"id": "anchor", "change_type": "unchanged", "columns_changed": []},
              {"id": "subject", "change_type": cl_type, "columns_changed": columns}]
    run = Run(tmp_path, prev, curr, oracle=oracle)
    assert run.build() == 0  # oracle disagreement is reported, not a §6 fatal gate
    check = run.summary["changelog_check"]
    assert (check["total_mismatches"] > 0) is mismatch
    if mismatch:
        assert "subject" in (run.out / "qa_report.md").read_text(encoding="utf-8")


def test_configurable_thresholds(tmp_path):
    run = Run(tmp_path, [place()], [place(lat=north(12))],
              minor_move_m=2, move_threshold_m=10, major_move_m=11)
    assert run.build() == 0
    assert run.prop()["change_type"] == "moved"
    assert run.prop()["move_band"] == "major"


def test_changelog_unchanged_rejects_enrichment(tmp_path):
    run = Run(tmp_path, [place(websites=None)], [place(websites=["https://example.org"])],
              oracle=[{"id": "subject", "change_type": "unchanged", "columns_changed": []}])
    assert run.build() == 0
    assert run.summary["change_counts"]["unchanged"] == 1
    assert run.summary["changelog_check"]["total_mismatches"] == 1


def test_exclusion_gate_exactly_five_percent(tmp_path):
    good = [place(str(i)) for i in range(19)]
    run = Run(tmp_path, good + [place(geometry=None)], good)
    assert run.build() == 0
    assert run.summary["change_counts"]["excluded"] == 1


def test_failure_without_previous_output_writes_nothing(tmp_path):
    run = Run(tmp_path, [], [place()])
    assert run.build() == 2
    assert not run.out.exists()
