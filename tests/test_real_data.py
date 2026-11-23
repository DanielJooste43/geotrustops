"""Regression tests on the pinned real extracts (skipped when data/raw is absent, e.g. in CI).

The inputs are pinned and hash-checked by their manifests, so exact counts are a legitimate
*regression* baseline: if they change, the inputs or the rules changed. They are not evidence of
correctness by themselves; that comes from the changelog oracle, reconciliation and golden records.
Baseline observed 2026-11-23 (data contract v0.3 rules, unchanged since).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from geotrustops.cli import main
from tests.conftest import RAW, REAL_CONFIG, ROOT

SEP_OCT_CONFIG = ROOT / "config" / "pair_sep_oct.json"

pytestmark = [
    pytest.mark.realdata,
    pytest.mark.skipif(not (RAW / "releases").exists(), reason="pinned extracts not downloaded"),
]


def _build(config: Path, out: Path) -> dict:
    assert (
        main(
            [
                "build",
                "--config",
                str(config),
                "--raw-dir",
                str(RAW),
                "--out",
                str(out),
                "--no-history",
            ]
        )
        == 0
    )
    return json.loads((out / "summary.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def oct_nov(tmp_path_factory: pytest.TempPathFactory) -> dict:
    return _build(REAL_CONFIG, tmp_path_factory.mktemp("oct_nov") / "out")


@pytest.fixture(scope="module")
def sep_oct(tmp_path_factory: pytest.TempPathFactory) -> dict:
    if not (RAW / "releases" / "2026-09-23.1").exists():
        pytest.skip("second-pair extract not downloaded")
    return _build(SEP_OCT_CONFIG, tmp_path_factory.mktemp("sep_oct") / "out")


def test_oct_nov_counts_match_baseline(oct_nov: dict):
    assert oct_nov["change_counts"] == {
        "excluded": 0,
        "added": 232,
        "removed": 228,
        "moved": 178,
        "attribute_changed": 49,
        "shifted": 109,
        "unchanged": 5171,
    }


def test_sep_oct_counts_match_baseline(sep_oct: dict):
    assert sep_oct["change_counts"] == {
        "excluded": 0,
        "added": 289,
        "removed": 0,
        "moved": 111,
        "attribute_changed": 72,
        "shifted": 74,
        "unchanged": 5187,
    }


@pytest.mark.parametrize("pair", ["oct_nov", "sep_oct"])
def test_reconciliation_and_changelog_oracle_hold(pair: str, request: pytest.FixtureRequest):
    s = request.getfixturevalue(pair)
    assert all(r["holds"] for r in s["reconciliation"].values())
    assert s["changelog_check"]["total_mismatches"] == 0
    assert s["changelog_check"]["duplicate_ids_in_changelog"] == 0


def test_region_and_phone_recode_is_a_november_event(oct_nov: dict, sep_oct: dict):
    assert oct_nov["format_only_field_counts"] == {"addresses": 4450, "phones": 314}
    assert sep_oct["format_only_field_counts"] == {"addresses": 0, "phones": 6}


def test_real_boundary_crossers_are_moves(oct_nov: dict):
    assert oct_nov["flag_counts"]["crossed_aoi_boundary"] == 7


def test_real_geojson_is_small_enough_for_the_web(tmp_path: Path):
    _build(REAL_CONFIG, tmp_path / "out")
    assert (tmp_path / "out" / "changes.geojson").stat().st_size < 2_000_000
