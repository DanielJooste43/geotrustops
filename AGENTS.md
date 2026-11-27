# Contributor and review guidelines

Guidance for anyone changing this repository, and for the automated code review that runs on pull requests.

## Project rules

- **The data contract is the source of truth.** `docs/data_contract.md` defines every classification rule, field
  and output. If code and contract disagree, the code is wrong, or the contract is changed first in the same PR.
- **Work arrives through pull requests** linked to an issue (`Closes #N`). `main` is protected; the `lint`, `types`,
  `pytest` and `web` checks must pass.
- **Each module starts with its purpose, inputs, outputs and assumptions;** SQL states the row grain of each table.
- **Raw extracts stay local** (`data/raw/` is ignored and rebuilt with `geotrustops fetch`). Never commit keys,
  credentials or absolute local paths.

## Code Review Rules

### Correctness
- Any change to classification, exclusion, reconciliation or exports must update `docs/data_contract.md` and include
  a test that fails without the change.
- Reconciliation baselines must be computed independently of the table they check (contract §4). Flag any identity
  that could pass by construction.
- NULL handling must be explicit: comparisons use `IS DISTINCT FROM`; flags that can be NULL are coalesced where
  counted.
- Thresholds are strict where the contract says so (`> 25.0`, `> 5.0`); flag `>=` used by mistake.
- Coordinates that are missing, NaN or outside WGS84 are an unknown location, never "outside the study area".

### SQL and security
- DuckDB values are bound as **named parameters** (`$name`). Flag any value pasted into SQL text and any positional
  `?`. Interpolating internal constants is acceptable only with a `noqa: S608` comment stating why, placed outside
  the SQL string.
- No credentials, tokens or absolute local paths in code, tests, docs or outputs.

### Reproducibility
- Outputs must stay deterministic: sorted rows, rounded coordinates, no timestamps in `out/`. A change that alters
  output bytes for unchanged inputs needs an explanation in the PR.
- A failed run must not replace previous outputs.
- Dependencies are pinned exactly; GitHub Actions are pinned to commit SHAs.

### Licensing and data
- A new tool, library, Action, dataset, map tiles, fonts or external API needs its licence checked and recorded
  (README "Third-party tools and services" or `DATA_LICENSE.md`) in the same PR.
- Published outputs never include the source `phones`, `emails`, `websites` or `socials` fields.
  `DATA_LICENSE.md`, `NOTICE` and `LICENSES/` must stay consistent with the data that is published.

### Scope
- Prefer the smallest change that closes the linked issue; flag unrelated refactoring mixed into a PR.
