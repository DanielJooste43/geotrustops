"""Golden records: the pipeline must agree with places classified by hand (contract §8).

`tests/golden/golden_records.csv` was classified manually from raw data and the contract only,
before the pipeline's answers were seen. A disagreement is investigated; the golden file is never
edited to match the code. Skipped when the file or the pinned extracts are absent.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from geotrustops.config import load_config
from geotrustops.extract import changelog_path, release_path
from geotrustops.pipeline import run
from tests.conftest import RAW, REAL_CONFIG

GOLDEN = Path(__file__).parent / "golden" / "golden_records.csv"
VALID = {"excluded", "added", "removed", "moved", "attribute_changed", "shifted", "unchanged",
         "not_in_study"}


@pytest.mark.realdata
@pytest.mark.skipif(not GOLDEN.exists(), reason="golden_records.csv not present")
@pytest.mark.skipif(not (RAW / "releases").exists(), reason="pinned extracts not downloaded")
def test_pipeline_agrees_with_every_golden_record():
    with GOLDEN.open(encoding="utf-8-sig", newline="") as f:
        golden = [r for r in csv.DictReader(f) if r.get("id")]
    assert golden, "golden_records.csv has no rows"
    bad = [r["id"] for r in golden if r["manual_class"].strip() not in VALID]
    assert not bad, f"invalid manual_class for {bad}; allowed: {sorted(VALID)}"

    cfg = load_config(REAL_CONFIG)
    result = run(release_path(RAW, cfg.prev_release), release_path(RAW, cfg.curr_release),
                 changelog_path(RAW, cfg.curr_release), cfg)
    disagreements = [
        f"{r['id']}: manual={r['manual_class'].strip()} "
        f"pipeline={result.classification.get(r['id'], 'not_in_extract')} ({r.get('manual_notes', '')})"
        for r in golden
        if result.classification.get(r["id"], "not_in_extract") != r["manual_class"].strip()
    ]
    assert not disagreements, "investigate; do not edit the golden file:\n" + "\n".join(disagreements)
