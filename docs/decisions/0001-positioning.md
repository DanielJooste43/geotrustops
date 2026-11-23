# ADR 0001 — Positioning: Overture-first material-change review, with a source-adapter boundary


**Status:** accepted · **Date:** 2026-11-23

## Question
Build GeoTrustOps as an Overture-specific tool, or as a general change-detection tool for any recurring source?

## What already exists (checked 2026-11-23)
- **Generic two-version comparison:** ArcGIS *Detect Feature Changes* / *Change Detector*, FME *ChangeDetector*,
  QGIS *Change Describer* plugin. Mature; matching without stable ids (conflation) is their hard part.
- **Overture official:** GERS changelog per release (`change_type` + `columns_changed`, no values, no
  distances, no materiality); release notes (aggregate counts only).
- **Overture third-party:** `overture_compare_releases` in koizumikento/overture-maps-mcp (MIT, 1 star,
  ≤5,000 records/snapshot; "modified" = any property or exact geometry difference, no metre threshold;
  warns about scope-crossing but does not correct it). Apify "Chain Location Network Monitor"
  (brand/chain places only, paid, 2 total users).

## Decision
1. Build **Overture places first**: a *material-change review* with thresholds, old/new values, QA exclusions,
   buffered boundary handling and reconciliation, **validated against Overture's own changelog**.
2. Keep a clean **source-adapter boundary**: contract Stage A (read + flatten) is the only Overture-specific
   code; the engine consumes `id, lon, lat, name, category, basic_category`. Another source with stable ids
   = a new adapter. **Corrected by ADR 0003:** the source profile also covers lifecycle-field meanings and the
   changelog oracle, and a separate locale profile (ZA) covers region/phone normalisation.
3. Do **not** claim general-purpose change detection, a product, or that no Overture comparison tool exists.

## Why
- Generic sources lack stable ids, so they need conflation: a different, harder problem, already served by
  Esri/FME, and not credible within one week.
- Simple Overture diffs already exist; the defensible contribution is **rigour**: materiality, boundary
  correctness, QA and external validation.
- Evidence of outside demand is weak (2 users / 1 star); the project's purpose is a verifiable,
  reproducible case study, which this serves directly.

## Consequences
- No scope change to the remaining work. README states "adapter design; only Overture implemented".
- Possible follow-ups (outside the current scope): a second stable-id adapter (e.g. OpenStreetMap)
  to *prove* generality; packaging as a small CLI to test whether anyone wants it.
