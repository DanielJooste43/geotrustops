"""Unit tests on small synthetic releases. Each test name states the rule it protects
(contract section in brackets)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from tests.conftest import INSIDE, METRES_PER_DEG_LAT, OUTSIDE, features, place, summary


def _north(metres: float) -> float:
    """Latitude of a point `metres` north of INSIDE (haversine sphere, exact for pure N-S)."""
    return INSIDE[1] + metres / METRES_PER_DEG_LAT


# --- §3 classification -------------------------------------------------------------------

def test_every_change_type_is_assigned_once(build):
    prev = [place("same"), place("gone"), place("mover"), place("renamed", name="Old")]
    curr = [place("same"), place("new"), place("mover", lat=_north(100)), place("renamed", name="New")]
    code, out = build(prev, curr)
    assert code == 0
    s = summary(out)
    assert s["change_counts"] == {"excluded": 0, "added": 1, "removed": 1, "moved": 1,
                                  "attribute_changed": 1, "shifted": 0, "unchanged": 1}
    assert {k: f["properties"]["change_type"] for k, f in features(out).items()} == {
        "new": "added", "gone": "removed", "mover": "moved", "renamed": "attribute_changed"}


def test_move_threshold_is_strictly_greater_than_25m(build):
    prev = [place("under"), place("over")]
    curr = [place("under", lat=_north(24.9)), place("over", lat=_north(25.1))]
    code, out = build(prev, curr)
    assert code == 0
    f = features(out)
    assert f["under"]["properties"]["change_type"] == "shifted"
    assert f["over"]["properties"]["change_type"] == "moved"
    assert abs(f["over"]["properties"]["distance_m"] - 25.1) < 0.05


def test_minor_moves_are_shifted_and_stable_moves_unchanged(build):
    prev = [place("stable"), place("minor"), place("minor_renamed", name="A")]
    curr = [place("stable", lat=_north(4.9)), place("minor", lat=_north(5.1)),
            place("minor_renamed", lat=_north(10), name="B")]
    code, out = build(prev, curr)
    f = features(out)
    assert "stable" not in f  # <= 5 m is unchanged and not exported
    assert (f["minor"]["properties"]["change_type"], f["minor"]["properties"]["move_band"]) == (
        "shifted", "minor")
    # an attribute change outranks a minor move; the band still records the move
    assert (f["minor_renamed"]["properties"]["change_type"],
            f["minor_renamed"]["properties"]["move_band"]) == ("attribute_changed", "minor")
    assert summary(out)["move_band_counts"] == {"stable": 1, "minor": 2, "material": 0, "major": 0}


def test_move_bands_material_and_major(build):
    code, out = build([place("m"), place("M")], [place("m", lat=_north(99)), place("M", lat=_north(101))])
    f = features(out)
    assert (f["m"]["properties"]["move_band"], f["M"]["properties"]["move_band"]) == ("material", "major")


def test_null_to_value_category_is_a_change(build):
    code, out = build([place("a", category=None)], [place("a", category="grocery_store")])
    p = features(out)["a"]["properties"]
    assert (p["change_type"], p["category_changed"], p["prev_category"]) == (
        "attribute_changed", True, None)


def test_name_change_kinds(build):
    pairs = {
        "case": ("School  for", "school For"),
        "punct": ("Mo_nails", "Mo-Nails"),
        "trim": ("Mr Price Cellular Pta", "Mr Price"),
        "diff": ("Eduflex Online Tutors", "Eduflex College"),
        "added": (None, "New Name"),
        "accent": ("Café Rouge", "Cafe Rouge"),  # é vs e is a real letter difference
    }
    prev = [place(k, name=a) for k, (a, _) in pairs.items()]
    curr = [place(k, name=b) for k, (_, b) in pairs.items()]
    code, out = build(prev, curr)
    kinds = {k: f["properties"]["name_change_kind"] for k, f in features(out).items()}
    assert kinds == {"case": "case_or_spacing", "punct": "punctuation", "trim": "expanded_or_trimmed",
                     "diff": "different", "added": "added", "accent": "different"}
    assert all(f["properties"]["change_type"] == "attribute_changed" for f in features(out).values())


def test_name_matches_brand(build):
    code, out = build([place("a", name="Kfc Pretoria", brand_name="KFC")],
                      [place("a", name="KFC", brand_name="KFC")])
    assert features(out)["a"]["properties"]["name_matches_brand"] is True


def test_moved_outranks_rename_but_keeps_the_flag(build):
    code, out = build([place("a", name="Mr Price Cellular")], [place("a", lat=_north(40), name="Mr Price")])
    p = features(out)["a"]["properties"]
    assert (p["change_type"], p["name_changed"], p["name_change_kind"]) == (
        "moved", True, "expanded_or_trimmed")


# --- §1/§3 lifecycle and enrichment tiers ---------------------------------------------------

def test_confidence_change_alone_is_unchanged(build):
    code, out = build([place("a", confidence=0.9)], [place("a", confidence=0.4)])
    assert summary(out)["change_counts"]["unchanged"] == 1
    assert "a" not in features(out)


def test_permanent_closure_sets_lifecycle_flags_not_a_change_type(build):
    code, out = build([place("a", operating_status="open", confidence=0.8)],
                      [place("a", operating_status="permanently_closed", confidence=0.0)])
    s = summary(out)
    assert s["change_counts"]["unchanged"] == 1
    assert (s["flag_counts"]["status_changed"], s["flag_counts"]["confidence_to_zero"]) == (1, 1)
    assert "permanently_closed" in (out / "qa_report.md").read_text(encoding="utf-8")


def test_region_recode_is_format_only_not_enrichment(build):
    addr = {"freeform": "65 Pretorius St", "locality": "Pretoria", "postcode": None, "country": "ZA"}
    code, out = build([place("fmt", addresses=[{**addr, "region": "GP"}]),
                       place("real", addresses=[{**addr, "region": "GP"}]),
                       place("wrongprov", addresses=[{**addr, "region": "GP"}])],
                      [place("fmt", addresses=[{**addr, "region": "ZA-GP"}]),
                       place("real", addresses=[{**addr, "region": "ZA-GP", "freeform": "66 Pretorius St"}]),
                       place("wrongprov", addresses=[{**addr, "region": "ZA-MP"}])])
    s = summary(out)
    assert s["format_only_field_counts"]["addresses"] == 1       # fmt only
    assert s["enrichment_field_counts"]["addresses"] == 2        # real + wrongprov
    assert s["change_counts"]["unchanged"] == 3                  # enrichment is never a change type


def test_phone_e164_reformat_is_format_only_but_new_number_is_enrichment(build):
    za = [{"freeform": None, "locality": "Pretoria", "postcode": None, "region": "ZA-GP", "country": "ZA"}]
    code, out = build([place("fmt", phones=["012 440 3311"], addresses=za),
                       place("new", phones=["0124403311"], addresses=za),
                       place("noza", phones=["0124403311"])],
                      [place("fmt", phones=["+27124403311"], addresses=za),
                       place("new", phones=["+27129999999"], addresses=za),
                       place("noza", phones=["+27124403311"])])  # no ZA address: not normalised
    s = summary(out)
    assert s["format_only_field_counts"]["phones"] == 1
    assert s["enrichment_field_counts"]["phones"] == 2


def test_optional_columns_may_be_absent(tmp_path):
    from geotrustops.cli import main
    from tests.conftest import write_config
    from tests.fixtures.make_fixture import write_places
    prev = write_places(tmp_path / "p.parquet", [place("a")], minimal=True)
    curr = write_places(tmp_path / "c.parquet", [place("a", name="renamed")], minimal=True)
    code = main(["build", "--config", str(write_config(tmp_path / "cfg.json")), "--prev", str(prev),
                 "--curr", str(curr), "--out", str(tmp_path / "out"), "--no-history"])
    assert code == 0
    assert summary(tmp_path / "out")["change_counts"]["attribute_changed"] == 1


def test_removed_is_drawn_at_previous_position_added_at_current(build):
    code, out = build([place("gone", lon=28.17, lat=-25.75)], [place("new", lon=28.19, lat=-25.74)])
    f = features(out)
    assert f["gone"]["geometry"]["coordinates"] == [28.17, -25.75]
    assert f["new"]["geometry"]["coordinates"] == [28.19, -25.74]


# --- §2 exclusions -------------------------------------------------------------------------

def test_duplicate_ids_exclude_every_copy(build):
    code, out = build([place("a")], [place("a"), place("a", name="copy")])
    s = summary(out)
    assert s["excluded_rows_by_reason"]["curr"]["duplicate_id"] == 2
    assert s["change_counts"]["excluded"] == 1
    assert "a" not in features(out)


def test_missing_id_rows_are_counted_not_matched(build):
    code, out = build([place("a")], [place("a"), {"id": "", "lon": INSIDE[0], "lat": INSIDE[1]}])
    s = summary(out)
    assert s["excluded_rows_by_reason"]["curr"]["missing_id"] == 1
    assert s["change_counts"]["unchanged"] == 1
    assert all(r["holds"] for r in s["reconciliation"].values())


@pytest.mark.parametrize("side", ["prev", "curr"])
@pytest.mark.parametrize("spread", [False, True])
def test_one_line_among_many_points_is_excluded_not_a_crash(build, side, spread):
    # Regression: with many points at IDENTICAL coordinates (common in real data: many shops in one
    # mall), DuckDB evaluated ST_X on the LINESTRING despite a CASE guard and the run crashed.
    # A fixture with spread-out points does not trigger it, so both layouts are tested.
    points = [place(f"p{i}", lon=28.17 + i * 0.001 if spread else 28.18) for i in range(20)]
    line = {"id": "line", "wkt": "LINESTRING (28.18 -25.74, 28.181 -25.741)"}
    prev, curr = ([*points, line], points) if side == "prev" else (points, [*points, line])
    code, out = build(prev, curr, max_excluded_share=0.05)
    assert code == 0
    assert summary(out)["excluded_rows_by_reason"][side]["non_point_geometry"] == 1


def test_bad_geometries_get_their_own_reasons(build):
    curr = [
        {"id": "nogeom", "geometry": None},
        {"id": "line", "wkt": "LINESTRING (28.18 -25.74, 28.181 -25.741)"},
        place("far", lon=500.0),
    ]
    code, out = build([place("ok")], [place("ok"), *curr])
    assert code == 0
    reasons = summary(out)["excluded_rows_by_reason"]["curr"]
    assert (reasons["missing_geometry"], reasons["non_point_geometry"], reasons["invalid_coordinates"]) == (1, 1, 1)


# --- §2-3 study population and boundary ----------------------------------------------------

@pytest.mark.parametrize("bad_rows,expected_excluded,expected_buffer_only", [
    ([place("x", lat=float("nan"))], 1, 0),                              # NaN: unlocatable -> in study
    ([place("x", lon=181.0)], 1, 0),                                     # out of WGS84 range: unlocatable
    ([place("x", lon=181.0), place("x", lon=181.0)], 1, 0),              # duplicate with invalid location
    ([place("x", *OUTSIDE)], 0, 1),                                      # control: valid but outside AOI
])
def test_unlocatable_invalid_point_is_in_study_as_excluded(build, bad_rows, expected_excluded,
                                                          expected_buffer_only):
    # Regression: invalid coordinates must count as "unknown location" (in study, excluded),
    # not as a known location outside the AOI (silently buffer-only).
    good = [place(f"g{i}") for i in range(20)]
    code, out = build([*good, *bad_rows], good)
    assert code == 0
    s = summary(out)
    assert s["change_counts"]["excluded"] == expected_excluded
    assert s["buffer_only_ids"] == expected_buffer_only
    assert all(r["holds"] for r in s["reconciliation"].values())


def test_place_outside_aoi_in_both_releases_is_not_in_study(build):
    code, out = build([place("edge", *OUTSIDE)], [place("edge", *OUTSIDE)])
    s = summary(out)
    assert (s["considered_ids"], s["buffer_only_ids"]) == (0, 1)


def test_boundary_crosser_is_moved_not_added(build):
    # Starts just west of the AOI (inside the buffer), ends inside the AOI.
    code, out = build([place("x", lon=28.165)], [place("x", lon=28.170)])
    p = features(out)["x"]["properties"]
    assert (p["change_type"], p["crossed_aoi_boundary"]) == ("moved", True)


# --- §4 reconciliation must catch classification faults (fault injection) ---------------------

@pytest.mark.parametrize("fault", [
    ("FROM flags\n", "FROM flags WHERE id <> 'p3'\n"),            # drop an in-study id
    ("FROM flags\n", "FROM flags WHERE id <> 'far'\n"),           # drop a buffer-only id
    ("WHEN curr_valid AND NOT prev_valid THEN 'added'",           # misroute added -> unchanged
     "WHEN curr_valid AND NOT prev_valid THEN 'unchanged'"),
    ("FROM flags\n",                                              # substitute p0 by a 2nd p1
     "FROM (SELECT * REPLACE (CASE WHEN id = 'p0' THEN 'p1' ELSE id END AS id) FROM flags) flags\n"),
])
def test_injected_classification_fault_fails_and_keeps_outputs(build, monkeypatch, fault):
    from geotrustops import pipeline
    prev = [place(f"p{i}") for i in range(5)] + [place("far", *OUTSIDE)]
    curr = [*prev, place("new")]
    code, out = build(prev, curr)
    assert code == 0
    before = (out / "summary.json").read_bytes()
    old, new = fault
    assert old in pipeline._CLASSIFY, "fault-injection anchor not found; update this test"
    monkeypatch.setattr(pipeline, "_CLASSIFY", pipeline._CLASSIFY.replace(old, new))
    code, out = build(prev, curr)
    assert code == 2
    assert (out / "summary.json").read_bytes() == before


# --- §6 gates and run behaviour ----------------------------------------------------------

def test_too_many_exclusions_fails_and_keeps_previous_outputs(build):
    code, out = build([place("a")], [place("a")])
    assert code == 0
    before = (out / "summary.json").read_bytes()
    code, out = build([place("a")], [place("a"), {"id": "b", "geometry": None}], max_excluded_share=0.05)
    assert code == 2
    assert (out / "summary.json").read_bytes() == before


def test_empty_release_fails(build):
    code, _ = build([place("a")], [])
    assert code == 2


def test_missing_input_file_fails(tmp_path: Path):
    from geotrustops.cli import main
    from tests.conftest import REAL_CONFIG
    code = main(["build", "--config", str(REAL_CONFIG), "--prev", str(tmp_path / "nope.parquet"),
                 "--curr", str(tmp_path / "nope2.parquet"), "--out", str(tmp_path / "out"),
                 "--no-history"])
    assert code == 2
    assert not (tmp_path / "out").exists()


def test_rerun_is_byte_identical(build):
    prev = [place("a"), place("b"), place("c", name="x")]
    curr = [place("a", lat=_north(60)), place("d"), place("c", name="y")]

    def digest(out: Path) -> dict[str, str]:
        return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.iterdir())}

    _, out = build(prev, curr)
    first = digest(out)
    _, out = build(prev, curr)
    assert digest(out) == first


# --- §9 changelog oracle -------------------------------------------------------------------

def test_changelog_agreement_and_a_planted_mismatch(build):
    prev = [place("same"), place("mover")]
    curr = [place("same"), place("mover", lat=_north(100)), place("new")]
    agree = [{"id": "same", "change_type": "unchanged"},
             {"id": "mover", "change_type": "data_changed", "columns_changed": ["geometry"]},
             {"id": "new", "change_type": "added"}]
    _, out = build(prev, curr, changelog=agree)
    assert summary(out)["changelog_check"]["total_mismatches"] == 0

    planted = [{**r, "columns_changed": ["addresses"]} if r["id"] == "mover" else r for r in agree]
    _, out = build(prev, curr, changelog=planted)
    cc = summary(out)["changelog_check"]
    assert cc["rules"]["moved_or_shifted_has_geometry_change"] == {"checked": 1, "mismatches": 1}
    assert "mover" in (out / "qa_report.md").read_text(encoding="utf-8")


@pytest.mark.parametrize("prev_conf,prev_status,curr_status,expected", [
    (0.9, None, None, 0),                       # confidence-only drop to 0: changelog ignores confidence
    (None, None, None, 0),                      # NULL -> 0: same reasoning
    (0.9, "open", "permanently_closed", 1),     # a real closure: status is compared -> mismatch
])
def test_oracle_rule4_checks_status_not_confidence(build, prev_conf, prev_status, curr_status, expected):
    # Contract §9 rule 4: Overture's changelog never compares confidence, so only status is checked.
    code, out = build([place("a", confidence=prev_conf, operating_status=prev_status)],
                      [place("a", confidence=0.0, operating_status=curr_status)],
                      changelog=[{"id": "a", "change_type": "unchanged"}])
    s = summary(out)
    assert s["flag_counts"]["confidence_to_zero"] == 1
    assert s["changelog_check"]["rules"]["changelog_unchanged_is_unchanged"]["mismatches"] == expected


def test_changelog_unchanged_but_enrichment_changed_is_a_mismatch(build):
    _, out = build([place("a", phones=["1"])], [place("a", phones=["2"])],
                   changelog=[{"id": "a", "change_type": "unchanged"}])
    assert summary(out)["changelog_check"]["rules"]["changelog_unchanged_is_unchanged"]["mismatches"] == 1


# --- calibration log -------------------------------------------------------------------------

def test_history_is_upserted_not_duplicated(tmp_path):
    from geotrustops.cli import main
    from tests.conftest import write_config
    from tests.fixtures.make_fixture import write_places
    prev = write_places(tmp_path / "p.parquet", [place("a")])
    curr = write_places(tmp_path / "c.parquet", [place("a"), place("b")])
    hist = tmp_path / "history.jsonl"
    args = ["build", "--config", str(write_config(tmp_path / "cfg.json")), "--prev", str(prev),
            "--curr", str(curr), "--out", str(tmp_path / "out"), "--history", str(hist)]
    assert main(args) == 0
    first = hist.read_bytes()
    assert main(args) == 0
    assert hist.read_bytes() == first
    assert len(first.decode().splitlines()) == 1
    # Same snapshots checked against a changelog are separate evidence: a second line
    from tests.fixtures.make_fixture import write_changelog
    cl = write_changelog(tmp_path / "cl.parquet", [{"id": "b", "change_type": "added"}])
    assert main([*args, "--changelog", str(cl)]) == 0
    lines = hist.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert {json.loads(x)["changelog_sha256"] is None for x in lines} == {True, False}
    assert main([*args, "--changelog", str(cl)]) == 0          # identical rerun still upserts
    assert len(hist.read_text(encoding="utf-8").splitlines()) == 2


# --- extract: paths with quotes must not break the SQL --------------------------------------

def test_fetch_handles_apostrophes_in_paths(tmp_path: Path):
    import duckdb

    from geotrustops.config import load_config
    from geotrustops.extract import changelog_path, fetch, release_path, sha256, verify_manifest
    from tests.conftest import write_config

    src = tmp_path / "o'brien source"
    src.mkdir()
    con = duckdb.connect()
    for name, extra in (("rel.parquet", "'x' AS payload"),
                        ("cl.parquet", "'added' AS change_type, ['geometry'] AS columns_changed")):
        con.execute(f"""COPY (SELECT 'a' AS id, {extra},
            struct_pack(xmin := 28.18, xmax := 28.18, ymin := -25.74, ymax := -25.74) AS bbox)
            TO '{(src / name).as_posix().replace("'", "''")}' (FORMAT parquet)""")
    cfg = load_config(write_config(tmp_path / "cfg.json", source={
        "release_uri": (src / "rel.parquet").as_posix(),
        "changelog_uri": (src / "cl.parquet").as_posix()}))
    raw = tmp_path / "o'brien raw"
    manifests = fetch(cfg, raw)
    assert [m["row_count"] for m in manifests] == [1, 1, 1]
    for kind, path, rel in (("release", release_path(raw, cfg.prev_release), cfg.prev_release),
                            ("changelog", changelog_path(raw, cfg.curr_release), cfg.curr_release)):
        assert verify_manifest(path, cfg, kind, rel)["sha256"] == sha256(path)


# --- extract manifest ---------------------------------------------------------------------

def test_manifest_detects_an_altered_input(tmp_path: Path):
    import json

    import pytest

    from geotrustops.config import load_config
    from geotrustops.extract import ExtractError, sha256, verify_manifest
    from tests.conftest import REAL_CONFIG

    cfg = load_config(REAL_CONFIG)
    f = tmp_path / "places.parquet"
    f.write_bytes(b"original")
    (tmp_path / "manifest.json").write_text(json.dumps({
        "kind": "release", "release": cfg.prev_release,
        "extraction_bbox": cfg.extraction_bbox.as_dict(), "sha256": sha256(f)}))
    verify_manifest(f, cfg, "release", cfg.prev_release)  # passes
    f.write_bytes(b"tampered")
    with pytest.raises(ExtractError, match="sha256"):
        verify_manifest(f, cfg, "release", cfg.prev_release)
