"""Checks the committed quality-triage file against data contract §11.

The file is produced by scripts/investigate/stack_causes.py --export from local extracts and context layers; these
tests pin its published shape, provenance and licence notice so a change to the exporter cannot drift silently.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
TRIAGE = ROOT / "out_triage" / "stack_causes.json"
CLUSTER_KEYS = {"size", "lon", "lat", "likely_cause", "also_duplicates", "manual_inspection", "ids"}
CAUSES = {
    "duplicate records",
    "shared address point",
    "shared address point (unit numbers recorded)",
    "one institution, shared postal box",
    "postal address, no street",
    "near a town point (likely town-level geocode)",
    "town-only address",
    "rounded coordinates",
    "large building (mall-like)",
    "one compact building",
    "intersection geocode",
    "intersection geocode (address says corner)",
    "street-centreline geocode",
    "unknown: manual inspection",
}


@pytest.fixture(scope="module")
def doc() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(TRIAGE.read_text(encoding="utf-8"))
    return data


def test_top_level_fields_and_odbl_notice(doc: dict[str, Any]) -> None:
    assert doc["schema_version"] == 1
    assert doc["licence"] == "ODbL-1.0"
    assert doc["licence_uri"] == "https://opendatacommons.org/licenses/odbl/1-0/"
    assert "OpenStreetMap" in doc["attribution"]
    assert set(doc["inputs_sha256"]) == {"places", "building", "connector", "division", "segment"}


def test_release_and_places_input_match_the_change_run(doc: dict[str, Any]) -> None:
    summary = json.loads((ROOT / "out" / "summary.json").read_text(encoding="utf-8"))
    assert doc["release"] == summary["releases"]["curr"]
    assert doc["inputs_sha256"]["places"] == summary["inputs_sha256"]["curr"]


def test_clusters_hold_ids_and_positions_only(doc: dict[str, Any]) -> None:
    for c in doc["clusters"]:
        assert set(c) == CLUSTER_KEYS  # no names or other place attributes (§11)
        assert c["manual_inspection"] is True
        assert c["likely_cause"] in CAUSES
        assert c["size"] >= 2 and c["size"] == len(c["ids"])
        assert c["ids"] == sorted(c["ids"])
        assert round(c["lon"], 6) == c["lon"] and round(c["lat"], 6) == c["lat"]


def test_totals_reconcile_and_places_are_unique(doc: dict[str, Any]) -> None:
    ids = [i for c in doc["clusters"] for i in c["ids"]]
    assert doc["cluster_count"] == len(doc["clusters"])
    assert doc["clustered_places"] == len(ids) == len(set(ids))
    assert doc["clustered_places"] <= doc["places_in_aoi"]


def test_order_is_deterministic(doc: dict[str, Any]) -> None:
    keys = [(-c["size"], c["lon"], c["lat"]) for c in doc["clusters"]]
    assert keys == sorted(keys)


def test_bytes_are_canonical(doc: dict[str, Any]) -> None:
    raw = TRIAGE.read_bytes()
    assert b"\r\n" not in raw
    assert raw.decode("utf-8") == json.dumps(doc, ensure_ascii=False, indent=1) + "\n"
