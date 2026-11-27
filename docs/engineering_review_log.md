# Engineering review log

Real defects found while building GeoTrustOps, and **which kind of check found each one**. The point of recording
them: every defect below passed at least one other check first. Confidence comes from checks that are independent of
each other, not from any single suite being green.

## Summary

| # | Defect | Found by | Would the implementation's own tests have caught it? |
|---|---|---|---|
| 1 | The earlier prototype's "13 tests pass" was not reproducible (6 failed) | re-running the prototype's claims | n/a |
| 2 | Places crossing the study-area edge reported as 4 openings + 3 closures | **external oracle** (Overture changelog) | **no**: code and tests agreed with each other |
| 3 | Crash on one non-point geometry among identically located points | **independent contract test** | **no**: the unit fixture happened not to trigger it |
| 4 | Contradiction in the specification (`confidence` optional vs required) | **independent contract test** authoring | no |
| 5 | Reconciliation identities partly counted the table they checked | **code review + fault injection** | **no**: every identity was green |
| 6 | Paths containing a quote character broke the extraction SQL | **code review** | no |
| 7 | Oracle rule required a check the oracle cannot support | **code review** against source documentation | no |
| 8 | Invalid coordinates (NaN, lon 181) treated as a known location outside the area | **code review** (second round) | **no** |
| 9 | A substituted id kept every count equal | **fault injection** | **no** |
| 10 | An implementation comment asserted a DuckDB limitation that does not exist | **testing the claim** on the pinned version | no |
| 11 | Inspection tool compared the wrong release pair | **manual check** of output against intent | no |
| 12 | `count_if` returned NULL; a config file with a UTF-8 BOM was rejected | unit tests | yes |
| 13 | "79% of places changed" was mostly format migrations | **investigating the oracle's own numbers** | n/a (a finding, not a defect) |

## Details

### 1. The prototype's test claims
The earlier, unpublished prototype this project started from documented 13 passing tests. Re-running gave **6 failures on both DuckDB 1.1.3 and
1.4.2**: positional `?` parameters (`COPY … TO ?` does not parse on 1.1.3; parameters bound in the wrong order on
1.4.2), with an unpinned `duckdb>=1.1` dependency.
**Fix:** named parameters throughout; DuckDB pinned to 1.4.2.

### 2. Boundary crossers looked like openings and closures (external oracle)
The first rule set excluded points outside the study box per release. A place just outside in October was never
extracted, so moving inside by November made it look **added**. Comparing against Overture's changelog gave exactly
7 disagreements; a buffered re-query showed all 7 had moved 44–404 m across the edge.
**Fix:** extract the AOI plus a ~1 km buffer and decide membership on the exact AOI (contract §2). The changelog
became a permanent oracle (contract §9): 0 mismatches since, on both release pairs.

### 3. A crash a unit test missed by chance (independent contract test)
One LINESTRING among 20 **identically located** points crashed the run (`ST_X only supports POINT geometries`)
despite a `CASE WHEN geom_type = 'POINT'` guard: DuckDB still evaluated `ST_X` on the line (likely
dictionary-encoded vectors). The unit test used spread-out points and never triggered it. Real data often stacks many
places on one coordinate, so a single bad geometry in a future release would have crashed the pipeline.
**Fix:** guard moved inside the call, `ST_X(CASE WHEN … THEN geom END)`.
**Test:** `test_one_line_among_many_points_is_excluded_not_a_crash` (identical/spread × prev/curr): 2 of 4 failed
before the fix.

### 4. A self-contradicting specification
One section called `confidence` optional; two others required it. Found while writing tests from the specification
alone. **Fix:** required column, NULL values allowed (contract §1).

### 5. Reconciliation that partly checked itself (code review + fault injection)
Identities such as "union = considered + buffer-only" were computed from the classified table they were meant to
validate. Removing one id from the classification left **all identities true**.
**Fix:** every left-hand side is counted independently from row-level data with set operations (contract §4).
**Test:** `test_injected_classification_fault_fails_and_keeps_outputs` breaks the classification four ways; the
earlier code missed both dropped-id cases.

### 6. Values pasted into SQL
Paths were interpolated into SQL text; `o'brien/places.parquet` caused a parse error.
**Fix:** bound parameters for both the source URI and the COPY target.
**Test:** `test_fetch_handles_apostrophes_in_paths`.

### 7. A rule that was right on paper, wrong for the data
The oracle required "changelog `unchanged` ⇒ no lifecycle flag", but Overture's changelog states that `sources` and
`confidence` are never compared. Research before deciding: Overture documents confidence as existence likelihood from
provider signals, with 0 always paired with `permanently_closed`; in the data, 96–97% of confidence changes coincided
with the provider's own source-level confidence changing, in both directions, and none reached 0.
**Fix:** the rule checks `status_changed` only; real closures are still caught via status (contract §9 rule 4).

### 8. Invalid coordinates treated as "outside" (second review round)
`NaN` or longitude 181 made the in-AOI test return *false*, so an invalid record silently became buffer-only instead
of an excluded, reported record. **Fix:** AOI membership is *unknown* when the position is not a valid WGS84 point.
**Test:** `test_unlocatable_invalid_point_is_in_study_as_excluded`: 3 of 4 failed before the fix.

### 9. Counts can hide substitution (fault injection)
Replacing one classified id with a duplicate of another kept every count equal. **Fix:** compare *distinct* ids and
assert one row per id (contract §4, identity `ids_unique`).

### 10. An untested assumption in a comment
A code comment stated that DuckDB cannot bind a COPY destination, and the code worked around it. Testing on the
pinned DuckDB 1.4.2 showed binding works; the original failure (item 1) was positional parameters on 1.1.3.
**Fix:** single statement with `$uri` and `$dest`. The lesson repeats item 1: re-run remembered results.

### 11. An inspection tool showing the wrong pair (manual check)
After a second release pair was downloaded, `scripts/lookup_id.py` read every release folder and showed
September/October instead of October/November. Caught because the output did not fit the task being done.
**Fix:** the tool reads only the configured pair and states when a record is absent.

### 12. Defects the unit tests did catch
`count_if` returns NULL (not 0) when nothing is matched; a config saved by a Windows editor (UTF-8 BOM) was rejected.
Necessary but not sufficient: unit tests catch what their author anticipated (12) and miss what they didn't (3, 5, 8, 9).

### 13. "79% changed" was mostly format migrations (a finding)
Investigating why the changelog marks most places as changed: in Oct → Nov, 4,450 places changed only their region
code (`GP` → `ZA-GP`) and 314 only their phone format (local → E.164); Sep → Oct had 0 and 6. After normalisation,
real address and phone change rates are similar in both pairs; the one genuine November spike is website removals.
**Change:** normalisation plus `format_only_changed`, so migrations are reported separately from content changes.

## Practices this supports
1. Re-run inherited and remembered claims in the current environment (1, 10).
2. Validate against an independent external source (2).
3. Write some tests from the specification alone, without reading the implementation (3, 4).
4. Compute reconciliation baselines independently and prove them by injecting faults (5, 9).
5. Bind values; never paste them into SQL (6).
6. Research how the source produces a field before writing a rule about it (7).
7. Check every "failed as expected" against the actual error message (a fixture that could not write NaN once
   produced a misleading failure; the real assertion was confirmed before the fix in item 8).
8. Separate format migrations from content changes (13).

Design decisions and rejected alternatives are recorded in [`decisions/`](decisions/).
