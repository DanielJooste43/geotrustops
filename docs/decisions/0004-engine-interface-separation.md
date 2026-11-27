# ADR 0004: The validation engine is independent of the map interface

**Status:** accepted (2026-11-23); applies to the web interface

## Context
The project must stand as data engineering in its own right: running checks and producing QA
reports with no web map involved. The pipeline already works this way (the CLI writes `changes.geojson`, `summary.json`,
`qa_report.md`). This ADR makes the separation an enforced rule before a web interface is added.

## Decision
1. **One-way dependency.** `web/` depends on the engine's *exported files* only (contract §5 is the interface).
   It never imports Python, never reads `data/raw/`, never re-computes a classification or a count.
   The engine has no web dependencies and does not know the map exists.
2. **Same repository, separate folders** (`src/` engine, `web/` interface). The boundary is the file contract,
   not the repo; one repo keeps provenance and review in one place.
3. **The engine is complete on its own.** CI runs and tests the engine (fetch-free synthetic tests, contract tests,
   determinism) without building the web app. The README presents the CLI and QA report first and the map second.
4. **Numbers shown in the UI come only from `summary.json`**, so map metrics can never drift from the QA report.
   A web-interface smoke test checks that the UI's displayed counts equal `summary.json`.

## Consequences
- The web-interface brief must include: "read only `out/*.json|geojson`; no new metrics computed in the browser".
- A reviewer can run `geotrustops build` (after the rename) and read `qa_report.md` without Node.js installed.
- In short: a data product with a CLI and a documented output contract; the map is one consumer of it.
