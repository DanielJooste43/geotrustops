# Contributing

Thank you for looking at GeoTrustOps. Issues and pull requests are welcome: bug reports, questions about a record or
a rule, and fixes. The rules that every change follows are in [`AGENTS.md`](AGENTS.md); the data contract in
[`docs/data_contract.md`](docs/data_contract.md) is the source of truth for what the pipeline does.

## Set up

Tested on Windows 10 with Python 3.12; CI runs the same steps on Ubuntu. On Linux or macOS use `.venv/bin/`.

```powershell
python -m venv .venv
.venv\Scripts\pip install -e ".[dev]"
cd web; npm ci; cd ..
```

Real-data tests are skipped when `data/raw/` is absent. `geotrustops fetch` downloads the pinned extracts while
Overture still serves them on S3; after that, see "Reproducing the published results" below.

## Checks to run before a pull request

| Check | Command |
|---|---|
| Lint and format | `.venv\Scripts\ruff check .` and `.venv\Scripts\ruff format --check .` |
| Types (strict) | `.venv\Scripts\mypy src` |
| Tests | `.venv\Scripts\python -m pytest` |
| Web map | `cd web; npm test; npm run build; npm run licenses` |

CI runs the same four checks (`lint`, `types`, `pytest`, `web`); all must pass before a merge.

## Making a change

1. **Open or pick an issue first**, so the reason for the change is written down.
2. **Branch from `main`** with a name by type: `feat/…`, `fix/…`, `docs/…`, `ci/…`, `data/…` or `investigate/…`.
3. **Change the contract first** if a rule, field or output changes, and add a test that fails without the change
   (`AGENTS.md`, "Correctness").
4. **Commit** with a short imperative message that says what changed (for example "Bind the extraction box as named
   parameters"). Keep history: changes are merged, not squashed.
5. **Open a pull request** that starts with `Closes #N` and fills in the template: what and why, the checks you ran
   with their results, and any data or licence impact.

## Review

Every pull request is reviewed against `AGENTS.md` and the data contract, including an automated review by Codex.
Findings are answered in the pull request: fixed (with the commit), or not fixed with the reason. A pull request is
merged when the checks pass and the review is resolved.

## Reproducing the published results

The committed outputs rebuild byte for byte from the pinned extracts listed in [`data/archive.json`](data/archive.json).
Overture keeps each release on S3 for at most 60 days, so the extracts are also kept in a private archive, which is
not republished because it contains business contact fields. To verify the results after a release has left S3,
open an issue asking for access; `.env.example` lists the two environment variables `geotrustops fetch` then needs.

## Data, licences and records about you

Outputs are derived from Overture Maps data under the licences in [`DATA_LICENSE.md`](DATA_LICENSE.md) and
[`NOTICE`](NOTICE). A new library, data source, font or service needs its licence checked before it is added. If a
published record concerns you, use the "Data question or record removal" issue form.

## Conduct

Participation is covered by the [Code of Conduct](CODE_OF_CONDUCT.md).
