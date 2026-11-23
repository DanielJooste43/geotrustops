# GeoTrustOps

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

## Outputs

| File | For |
|---|---|
| `out/changes.geojson` | one point per changed place with before/after values, distance and flags (RFC 7946) |
| `out/summary.json` | counts, flags, reconciliation results, changelog cross-check, input hashes |
| `out/qa_report.md` | the same for a human reviewer: largest moves, renames by kind, exclusions, mismatches |

These are **map-record** changes: `added` ≠ a business opened, `removed` ≠ closed, `moved` ≠ the old position was
wrong.

## How the results are verified

| Check | Independent because |
|---|---|
| Unit and pipeline tests (`tests/`) | include fault injection: deliberately broken classifications must fail reconciliation |
| Contract tests (`tests/contract/`) | written from the specification alone, without reading the implementation |
| Golden records (`tests/golden/`) | real places classified by hand from raw data before the pipeline's answers were seen (11/11 agree) |
| Overture changelog oracle | produced by Overture, not by this project (0 mismatches on both release pairs) |

What each of these caught is in [`docs/engineering_review_log.md`](docs/engineering_review_log.md).

## Documentation

- [Methodology](docs/methodology.md): the logic stage by stage, with real examples
- [Data contract](docs/data_contract.md): the exact rules, tagged as generic, Overture-specific or South Africa-specific
- [Decision records](docs/decisions/): positioning, rule review, rule layers, engine/interface separation, naming
- [Source manifest](docs/source_manifest.md) · [Calibration log](docs/calibration_log.md) · [Investigation backlog](docs/investigation_backlog.md)

## Stack

Python 3.12 · DuckDB 1.4.2 (SQL, `spatial`, `httpfs`) · GeoParquet on S3 · pytest · GitHub Actions

## Data and licence

Code: MIT ([LICENSE](LICENSE)). Data: © Overture Maps Foundation and its sources; place records are licensed per
source (CDLA-Permissive-2.0, Apache-2.0, CC0-1.0), carried in each output feature's `source_licences`.
See [Overture attribution](https://docs.overturemaps.org/attribution/).
