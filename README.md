# GeoTrustOps

[![ci](https://github.com/DanielJooste43/geotrustops/actions/workflows/tests.yml/badge.svg?branch=main)](https://github.com/DanielJooste43/geotrustops/actions/workflows/tests.yml)

**Material-change review for map-data releases.** GeoTrustOps compares two pinned releases of
[Overture Maps](https://overturemaps.org/) places for a study area, classifies every record's change, proves the
counts reconcile, and cross-checks its result against Overture's own changelog.

> **Status:** the validation pipeline is complete and tested. A web map that reads its outputs is in progress.

## Why

Overture publishes a changelog with every release. For central Pretoria (Oct → Nov 2026) it marks **79% of places
as `data_changed`**. Most of that is not a change anyone needs to review:

| | Places (study area) |
|---|---|
| Changelog says `data_changed` | 4,721 |
| **Material changes** found by GeoTrustOps (moved > 25 m, or renamed / recategorised) | **227 (3.8%)** |
| Minor moves (5–25 m), reported separately | 109 |
| Address changes that were only a region-code migration (`GP` → ISO `ZA-GP`) | 4,450 |
| Phone changes that were only a format migration (local → E.164 `+27…`) | 314 |

The changelog answers *"did any column change?"*; GeoTrustOps answers *"which changes matter, by how much, from
what to what?"*, and works for any two snapshots, including sources that publish no changelog.

## What it does

```
Overture S3 (2 pinned releases) ─► extract AOI + 1 km buffer ─► normalise ─► validate (exclusion reasons)
   ─► match by stable id ─► classify ─► reconcile (10 identities) ─► changelog cross-check ─► export
```

- **7 change types**, one per record, first match wins: `excluded`, `added`, `removed`, `moved` (> 25 m),
  `attribute_changed`, `shifted` (5–25 m), `unchanged`.
- **Flags** for what else changed: rename kind (case/spacing, punctuation, expanded/trimmed, different), category,
  operating status, enrichment fields, format-only migrations, AOI-boundary crossing.
- **Fails safe:** a run that excludes more than 5% of a release, or where any reconciliation identity fails, writes
  nothing and keeps the previous outputs. Same inputs → byte-identical outputs.

## Quick start

```powershell
python -m venv .venv
.venv\Scripts\pip install -e ".[dev]"
.venv\Scripts\geotrustops fetch      # pinned extracts from Overture S3 -> data/raw (not committed), ~2 min
.venv\Scripts\geotrustops build      # -> out/changes.geojson, out/summary.json, out/qa_report.md
.venv\Scripts\python -m pytest       # real-data tests are skipped if data/raw is absent
```

A second release pair: `geotrustops build --config config/pair_sep_oct.json`.
Inspect any record against the raw data: `python scripts/lookup_id.py <overture-id>`.

## Reproducibility

Overture keeps each release on S3 for at most 60 days, partly to honour data-protection removal requests, so the
pinned releases used here will disappear from the public bucket. Their extracts are therefore **not** republished:
they include business contact fields (phones, emails, websites, social links) that the outputs leave out.

- Every pinned extract is listed with its size and SHA-256 in [`data/archive.json`](data/archive.json).
- The files themselves are kept in a private archive. While S3 still serves a release, `geotrustops fetch` reads S3;
  when it no longer does, `fetch` restores the file from the archive (`GEOTRUSTOPS_ARCHIVE_REPO`,
  `GEOTRUSTOPS_ARCHIVE_TOKEN`) and accepts it only if size and SHA-256 match the committed manifest.
  `fetch --source s3` or `--source archive` forces one source.
- Restoring all five extracts from the archive and rebuilding both release pairs reproduces the committed `out/` and
  `out_pairs/` files byte for byte.
- **Access for verification is available on request** (open an issue). The archive is kept only to verify the
  published results: it is deleted 12 months after the v1.0 release, and any record is removed from it on request.

## Outputs

| File | For |
|---|---|
| `out/changes.geojson` | one point per changed place with before/after values, distance and flags (RFC 7946) |
| `out/summary.json` | counts, flags, reconciliation results, changelog cross-check, input hashes |
| `out/qa_report.md` | the same for a human reviewer: largest moves, renames by kind, exclusions, mismatches |
| `out_triage/stack_causes.json` | quality triage: places stacked within 2 m, each group with a likely cause from simple checks and a manual-inspection flag (separate ODbL database; see [DATA_LICENSE.md](DATA_LICENSE.md)) |

These are **map-record** changes: `added` ≠ a business opened, `removed` ≠ closed, `moved` ≠ the old position was
wrong.

## Web map

`web/` is a one-screen map of the exported files: change records by type (shape and colour), an overall-change view
(one glow per changed record, with an optional smoothed density layer), quality flags for stacked places, a record
inspector with previous and current values and positions, a keyboard-accessible records list, and a provenance panel
with release ids, input checksums, reconciliation and the changelog cross-check.

It reads `out/changes.geojson`, `out/summary.json` and `out_triage/stack_causes.json` only, and every number it shows
comes from `summary.json` (or, for quality flags, from the triage file): it never recomputes a classification or a
count ([ADR 0004](docs/decisions/0004-engine-interface-separation.md)). A typed adapter validates the files against
the data contract and refuses to draw data that does not match.

```powershell
cd web
npm ci
npm run dev        # local map at the address it prints
npm test           # adapter tests, including checks against the committed exports
npm run licenses   # declared licence of every package; shipped code must be permissive
npm run build      # type check and production build into web/dist
```

The basemap is OpenFreeMap's Dark style (no key); if it cannot be loaded, the records are shown on a plain
background. Attribution stays visible on every screen size.

## How the results are verified

| Check | Independent because |
|---|---|
| Unit and pipeline tests (`tests/`) | include fault injection: deliberately broken classifications must fail reconciliation |
| Contract tests (`tests/contract/`) | written from the specification alone, without reading the implementation |
| Golden records (`tests/golden/`) | real places classified by hand from raw data before the pipeline's answers were seen (11/11 agree) |
| Overture changelog oracle | produced by Overture, not by this project (0 mismatches on both release pairs) |
| Weekly real-data run (`.github/workflows/real-data.yml`) | restores the hash-pinned inputs, runs the real-data tests and requires the rebuilt outputs to match the committed ones byte for byte |

Every pull request also runs the `lint`, `types` and `pytest` checks and receives an AI-assisted code review (Codex)
before merge, guided by the project's review rules in [`AGENTS.md`](AGENTS.md). Findings are verified before they are
acted on; review complements the checks above and does not replace them.

What each of these caught is in [`docs/engineering_review_log.md`](docs/engineering_review_log.md).

## Documentation

- [Methodology](docs/methodology.md): the logic stage by stage, with real examples
- [Data contract](docs/data_contract.md): the exact rules, tagged as generic, Overture-specific or South Africa-specific
- [Decision records](docs/decisions/): positioning, rule review, rule layers, engine/interface separation, naming
- [Source manifest](docs/source_manifest.md) · [Calibration log](docs/calibration_log.md) · [Investigation backlog](docs/investigation_backlog.md)

## Stack

Python 3.12 · DuckDB 1.4.2 (SQL, `spatial`, `httpfs`) · GeoParquet on S3 · pytest · ruff · mypy (strict) · GitHub Actions

## Third-party tools and services

Each was checked against its own licence before use. Only MapLibre GL JS is shipped to visitors of the web map,
with its licence.

| Component | Used for | Licence |
|---|---|---|
| DuckDB 1.4.2 and its `spatial` / `httpfs` extensions | SQL engine, geometry, S3 reads | MIT |
| Python 3.12 | runtime | PSF-2.0 |
| hatchling | build backend | MIT |
| pytest 9.2.0, pytest-cov 7.1.0 | tests, coverage | MIT |
| ruff 0.17.6 | lint and formatting | MIT |
| mypy 2.4.1 | static type checking | MIT (some bundled files PSF-2.0) |
| GitHub Actions: `actions/checkout` v7.0.1, `actions/setup-python` v7.1.0, `actions/upload-artifact` v7.0.2 | CI (pinned to commit SHAs) | MIT |
| Overture Maps data via AWS Open Data | source data | see [DATA_LICENSE.md](DATA_LICENSE.md) |
| Overture divisions, buildings and transportation themes | context layers for the quality-triage checks; layers not redistributed, derived results in `out_triage/` | ODbL 1.0; see [DATA_LICENSE.md](DATA_LICENSE.md) |
| MapLibre GL JS 6.17.0 | web map rendering (shipped) | BSD-3-Clause |
| TypeScript 7.0.2, Vite 8.3.8, Vitest 5.1.1, Node.js 26 LTS | web map build and tests (not shipped) | Apache-2.0 / MIT / MIT / MIT; Vite's CSS minifier `lightningcss` is MPL-2.0, used at build time only |
| OpenFreeMap (Dark style, hosted tiles) | basemap | free service, no key; style BSD-3-Clause code and CC BY 4.0 design; map data © OpenStreetMap contributors (ODbL), © OpenMapTiles |
| GitHub Releases (private repository) | archive of the pinned extracts | GitHub Terms of Service; data licences as above |

## Data and licence

Code: MIT ([LICENSE](LICENSE)). Data is **not** MIT: it is derived from Overture Maps Foundation releases and keeps
each source's licence (CDLA-Permissive-2.0, Apache-2.0, CC0-1.0), named in every output feature's `source_licences`.
Licence texts, the Foursquare notice and how to attribute: [DATA_LICENSE.md](DATA_LICENSE.md), [NOTICE](NOTICE), [LICENSES/](LICENSES/).
