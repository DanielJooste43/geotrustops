# ADR 0005 — Rename the project to GeoTrustOps

**Status:** accepted · 2026-11-23

## Context
The original working name, "MapPulse", is already used by other products. The project needed a distinct name
before any public release. "GeoTrustOps" was checked for conflicts in package and repository namespaces
(no PyPI package or GitHub repository of that name as of 2026-11-23).

## Decision
Rename between the pipeline milestone and the web-map milestone, while no interface or public release depends on
the old name:
- Python package `src/mappulse` → `src/geotrustops`; CLI `mappulse` → `geotrustops`; version 0.4.0.
- GeoJSON foreign member `mappulse` → `geotrustops`; data contract v0.4 (**no rule changes**). The tool-name column
  in `summary.json` `changelog_check.crosstab` and in the QA mismatch list is renamed the same way (values identical).
- Documentation updated to the new name; historical records keep the old name, with a note at the top.
- Repository renamed to `geotrustops` (the previous URL redirects).

## Verification
- Full test suite passes.
- Both configured release pairs reproduce identical `change_counts` and reconciliation results, with 0 changelog
  mismatches.
- Every feature in `changes.geojson` is identical; only the metadata member key changed.
