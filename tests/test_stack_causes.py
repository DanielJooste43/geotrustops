"""Regression tests for the stacked-coordinates likely-cause cascade (investigation I-1, stage C).

The cascade's order and thresholds are pre-registered in docs/investigation_backlog.md; these tests pin them so the
recorded results stay reproducible if the script changes.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "investigate"))

from stack_causes import clusters, decimals, likely_cause  # noqa: E402
from stacked_coordinates import classify  # noqa: E402

# A cluster that matches no step at all; each test switches on exactly the evidence it needs.
NOTHING: dict[str, Any] = {
    "size": 5,
    "dup_share": 0.0,
    "base_share": 0.0,
    "unit_share": 0.0,
    "postal_share": 0.0,
    "box_share": 0.0,
    "town_only_share": 0.0,
    "rounded_share": 0.0,
    "town_point_m": math.inf,
    "building_area_m2": None,
    "connector_m": math.inf,
    "road_m": math.inf,
    "corner": False,
}


def cause(**evidence: Any) -> str:
    return likely_cause(**{**NOTHING, **evidence})


def test_no_evidence_defaults_to_manual_inspection():
    assert cause() == "unknown: manual inspection"


@pytest.mark.parametrize(
    ("evidence", "expected"),
    [
        ({"dup_share": 0.5}, "duplicate records"),
        ({"base_share": 0.5}, "shared address point"),
        ({"base_share": 0.5, "unit_share": 0.5}, "shared address point (unit numbers recorded)"),
        ({"postal_share": 0.5}, "postal address, no street"),
        ({"postal_share": 0.5, "box_share": 0.5}, "one institution, shared postal box"),
        ({"size": 10, "town_point_m": 50.0}, "near a town point (likely town-level geocode)"),
        ({"town_only_share": 0.5}, "town-only address"),
        ({"rounded_share": 0.5}, "rounded coordinates"),
        ({"building_area_m2": 10_000.0}, "large building (mall-like)"),
        ({"building_area_m2": 9_999.0}, "one compact building"),
        ({"connector_m": 2.0}, "intersection geocode"),
        ({"connector_m": 2.0, "corner": True}, "intersection geocode (address says corner)"),
        ({"road_m": 2.0}, "street-centreline geocode"),
    ],
)
def test_each_step_fires_at_its_threshold(evidence: dict[str, Any], expected: str):
    assert cause(**evidence) == expected


@pytest.mark.parametrize(
    "evidence",
    [
        {"dup_share": 0.49},
        {"base_share": 0.49},
        {"postal_share": 0.49},
        {"size": 9, "town_point_m": 0.0},  # too few places for a town fallback
        {"size": 10, "town_point_m": 50.1},
        {"town_only_share": 0.49},
        {"rounded_share": 0.49},
        {"connector_m": 2.01},
        {"road_m": 2.01},
    ],
)
def test_just_below_a_threshold_does_not_fire(evidence: dict[str, Any]):
    assert cause(**evidence) == "unknown: manual inspection"


def test_first_matching_step_wins():
    everything = {
        "size": 50,
        "dup_share": 0.6,
        "base_share": 0.6,
        "postal_share": 0.6,
        "town_point_m": 1.0,
        "town_only_share": 0.6,
        "rounded_share": 1.0,
        "building_area_m2": 20_000.0,
        "connector_m": 0.0,
        "road_m": 0.0,
    }
    order = [
        ("dup_share", 0.0, "duplicate records"),
        ("base_share", 0.0, "shared address point"),
        ("postal_share", 0.0, "postal address, no street"),
        ("town_point_m", math.inf, "near a town point (likely town-level geocode)"),
        ("town_only_share", 0.0, "town-only address"),
        ("rounded_share", 0.0, "rounded coordinates"),
        ("building_area_m2", None, "large building (mall-like)"),
        ("connector_m", math.inf, "intersection geocode"),
        ("road_m", math.inf, "street-centreline geocode"),
    ]
    for key, off, expected in order:
        assert cause(**everything) == expected
        everything[key] = off  # remove this step's evidence; the next step must take over
    assert cause(**everything) == "unknown: manual inspection"


def test_decimals_counts_stored_digits():
    assert decimals(28.1869) == 4
    assert decimals(-25.7533) == 4
    assert decimals(28.188321) == 6
    assert decimals(28.0) == 1


def test_clusters_link_points_within_two_metres_in_a_chain():
    # 1.5 m apart in a chain: a-b and b-c link, so a and c share a cluster although they are 3 m apart.
    step = 1.5 / 110_574.0
    pts = [("a", 28.18, -25.74), ("b", 28.18, -25.74 + step), ("c", 28.18, -25.74 + 2 * step)]
    far = [("d", 28.19, -25.74)]
    cid = clusters(pts + far)
    assert cid["a"] == cid["b"] == cid["c"]
    assert cid["d"] != cid["a"]


def test_stage_a_unfit_share_is_never_null():
    # Missing categories are coalesced to "not unfit", so the share is always a number.
    row = {"base_share": 0.0, "unit_share": 0.0, "strong_anchor": True, "unfit_share": 0.0}
    assert classify(row) == "H1"
