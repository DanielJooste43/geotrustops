# Case study: what changed in a map-data release, and which records need a look

**In one paragraph.** Overture's changelog marks 79% of the places in central Pretoria as changed between the
October and November 2026 releases. GeoTrustOps classified every record and found 227 material changes (3.8%):
178 places moved more than 25 m and 49 were renamed or recategorised. Most of the rest was two format migrations
(4,450 region codes, 314 phone numbers). Every count reconciles, the classification agrees with Overture's own
changelog on every record it can be checked against, and the outputs rebuild byte for byte from pinned inputs.
Separately, 503 groups of places stacked on one point (1,951 places) are flagged for a manual look.

[Live map](https://danieljooste43.github.io/geotrustops/) · [README](../README.md) ·
[Methodology](methodology.md) · [Data contract](data_contract.md) · [Engineering review log](engineering_review_log.md)

## The problem

Someone evaluating Overture Maps places for an area (a GIS analyst, a data team deciding whether to adopt a new
release) needs two answers before trusting it:

1. **What really changed between two releases?** Overture's changelog answers "did any column change?". For this
   area it says `data_changed` for 4,721 places, which is too many to review and mostly not worth reviewing.
2. **Which records show warning signs?** Some problems are not changes at all: hundreds of places sharing one
   coordinate, or a record that jumps back and forth between two positions from release to release.

## Data and scope

- **Area:** central Pretoria, about 3.7 × 2.9 km, extracted with a ~1 km buffer so records crossing the edge are
  seen on both sides.
- **Releases:** places `2026-10-21.0` → `2026-11-18.0` (main pair) and `2026-09-23.1` → `2026-10-21.0` (second pair),
  each pinned by SHA-256; the changelogs of 29 releases since July 2024 for record history; Overture buildings, roads
  and boundaries as context for the stacked-place checks.
- **Out of scope:** other themes and areas, fuzzy matching of records that change id, and any claim about the real
  world. A removed record is not a closed business.

## Approach

**One class per record, with flags for the rest.** Records are matched by Overture's stable id. Each gets exactly
one change type, first match wins: excluded, added, removed, moved (> 25 m), attribute changed (renamed or
recategorised), shifted (5–25 m), unchanged. What else changed is a flag: the kind of rename, operating status,
contact fields, and format-only migrations. The thresholds are illustrative configuration for an urban street grid,
not a statement about Overture's accuracy ([ADR 0002](decisions/0002-rule-review.md)).

**Format migrations separated from content.** Addresses and phone numbers are normalised before comparison. A region
code that went from `GP` to `ZA-GP` is reported as a format-only change, not an address change.

**Fail safe, and the same result every time.** Ten count identities must hold, or the run writes nothing and keeps
the previous outputs. So must a cap on excluded rows. Each side of an identity is counted from a different source:
the source file or the row-level table against the classification, so an identity cannot agree with itself. Same
inputs give byte-identical outputs.

**An engine and a map with a contract between them.** The pipeline (Python and DuckDB) writes three files defined by
the [data contract](data_contract.md). The web map (MapLibre) validates those files and never computes a count or a
classification ([ADR 0004](decisions/0004-engine-interface-separation.md)). If the files do not match the contract,
or do not come from the same run, the map refuses to draw them and says why.

## Results (Oct → Nov 2026)

| | Places |
|---|---|
| In the study area | 5,967 |
| Changelog says `data_changed` | 4,721 |
| **Moved more than 25 m** | **178** |
| **Renamed or recategorised** | **49** |
| Shifted 5–25 m (reported, not counted as material) | 109 |
| Added / removed | 232 / 228 |
| Address change that was only the region-code migration | 4,450 |
| Phone change that was only the format migration | 314 |

The second pair (Sep → Oct) shows 111 moved, 72 renamed or recategorised, 74 shifted, 289 added and 0 removed, with
almost no format migrations (0 region codes, 6 phones). The November spike is a format change, not a burst of edits.

**Warning signs** (current release):
- **503 groups of stacked places** (1,951 places within 2 m of each other), each with a likely cause from simple
  checks against buildings, roads and boundaries. Most share one address point (315 groups) or sit in one compact
  building (43); 29 have no simple explanation. There is no severity score: the flag means "worth a manual look".
- **Unstable records:** Pretoria Zoo's record alternates between two positions 62.7 m apart in most releases since
  September 2025. The record history makes this visible for every record.

## Verification

The question behind every check: *would this catch the pipeline being wrong in a way its own tests share?*

| Check | What it guards against | Result |
|---|---|---|
| Overture's changelog as an independent oracle (5 rules) | a classification that agrees with its own tests but not with the source | 0 mismatches on both pairs |
| Contract tests written from the specification only | tests that copy the implementation's mistakes | in CI on every change |
| Fault injection: dropped, misrouted, substituted and lost rows | identities that pass by construction | every injected fault fails the run |
| Golden records: 11 real places classified by hand before the pipeline's answer was seen | errors shared by code and tests | 11/11 agree |
| Byte-identical rebuilds, weekly against the real releases | silent drift | identical |
| The map's numbers against the files (swipe sides, counts) | a display that disagrees with the data | 564 / 568 records per side = summary |
| Failure paths: locked outputs, corrupt input, stalled network, broken files for the map | a failure that looks like a result | exit code 2 and previous outputs kept; the map shows a notice |

The [engineering review log](engineering_review_log.md) lists the real defects found while building this and which
kind of check found each one. Most were missed by the implementation's own tests and caught by an
independent check: the external oracle, a specification-only test, fault injection, or a review of the whole
codebase against the contract.

## Limitations

- One area, one theme (places), two release pairs. The pipeline is generic; the evidence is for this area.
- Matching by stable id only: a place that gets a new id appears as one removal and one addition.
- Changelog gaps (no June 2025 changelog; some releases publish only unchanged records) are marked in the history,
  not filled in.
- Reproducing the outputs after Overture removes a release from S3 needs the private archive of the pinned extracts,
  which is available for verification on request and deleted 12 months after v1.0.

## Next steps

- Investigate the leads already recorded in the [investigation backlog](investigation_backlog.md): website removals
  in November, large confidence drops, and a region recode in the wrong province.
- Run the same pipeline on a second area to test whether the thresholds and the stacked-place causes travel.
- Smaller hardening: config range checks, timeline rows without a position counted rather than dropped, and the
  source licence of each record shown on the map.
