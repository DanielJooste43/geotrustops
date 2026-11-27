Closes #

## What and why
<!-- What changes, and the reason (link the issue). -->

## Checks run
| Check | Result |
|---|---|
| `ruff check .` and `ruff format --check .` | |
| `mypy src` | |
| `pytest` | |
| `web`: `npm test`, `npm run build`, `npm run licenses` | |
| Other (rebuild compared with the committed outputs, browser check, …) | |

## Data and licence impact
- [ ] No change to classification rules, fields or outputs, **or** `docs/data_contract.md` is updated in this pull
      request with a test that fails without the change.
- [ ] Committed outputs unchanged, **or** the changed values are listed above and explained.
- [ ] No new library, data source, font, icon or service, **or** its licence is checked and recorded.
