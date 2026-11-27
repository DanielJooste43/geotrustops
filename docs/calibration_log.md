# Calibration log: thresholds and the evidence behind them

Machine record: `runs/history.jsonl` (one line per distinct inputs + config + version; written by
`geotrustops build`). This file records **decisions**. It is not machine learning: thresholds are set
from observed run history (statistical process control) once enough runs exist.

| Parameter | Value | Basis | Review when |
|---|---|---|---|
| `max_excluded_share` | 5% | initial guard against broken extracts; observed exclusion rate 0.0% in all 4 extractions (Sep.1, Oct, Oct, Nov) | ≥ 6 runs: set to max observed + margin |
| `minor_move_m` | 5 m | ≈ consumer-GPS error; below it, moves are not reportable (ADR 0002 §1) | a reference dataset becomes available |
| `move_threshold_m` | 25 m | illustrative material threshold, inherited; 108 + 70 matched moves above it (Oct→Nov) | reviewer feedback on false alarms |
| `major_move_m` | 100 m | display band for the largest moves | same |
| `buffer_deg` | 0.01° (~1 km) | largest observed AOI-edge crossing 404 m (Oct→Nov) | any oracle add/remove mismatch |

## Entries
- **2026-11-23**: initial values (contract v0.3). Two pairs run: Sep.1→Oct and Oct→Nov, 0 exclusions, 0 changelog
  mismatches. Format migrations observed in Oct→Nov only: 4,450 address region recodes (`GP` → `ZA-GP`), 314 phone
  E.164 reformats; normalisation added so they are reported as format-only, not as content changes.
