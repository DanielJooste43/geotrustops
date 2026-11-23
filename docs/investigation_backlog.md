# Investigation backlog

**Purpose:** issues noticed along the way that may indicate data-quality problems in the source. They are
**leads, not findings**: nothing here may be published (README, map, write-ups) until its status is `verified`.

**Rules**
- Each investigation is **time-boxed**; the leads with most value are taken first.
- Each investigation: a hypothesis, a reproducible query/script committed under `scripts/investigate/`,
  a stated confirm/reject criterion *written before running it*, and a result entry below.
- Outcome is one of `verified`, `rejected`, `inconclusive`. Rejected leads stay listed (negative results count).
- A verified lead may become: a QA flag in the pipeline (via a contract change), a map layer,
  or a published finding.

---

## I-1 Stacked coordinates — **open, highest value**
- **Observed (2026-11-23, Nov release, AOI):** 960 of 5,736 places (≈17%) share an exact coordinate with at
  least one other place, on 196 distinct points. Largest stacks: 91, 66, 51, 46, 44 places, each with all
  **different** names (e.g. a music studio, tutors, motor dealer, coffee shop on one point).
- **Hypothesis:** these are fallback geocodes (suburb, street, postcode or building centroids), not real positions.
- **Why it matters:** a person navigating to any of those 91 places is sent to the same spot; positional quality is
  worse than the release-to-release "unchanged" suggests. Also the trigger of a geometry-handling crash fixed earlier (engineering review log).
- **Method:** (a) for the top 10 stacks, compare the point to suburb/postcode centroids (Overture `divisions` or
  addresses' `postcode`/`locality`); (b) share of stacked places by source dataset; (c) do stacked places
  move more or less between releases?
- **Confirm if:** most large stacks coincide (≤ 50 m) with an administrative or postcode centroid, or are
  dominated by one source. **Reject if:** stacks are single buildings with plausibly co-located tenants
  (e.g. an office tower or mall: check names and categories).
- **Result:** _(pending)_

## I-2 Wrong-province region recode — open, small
- **Observed:** 1 place (`Bushbuck Group`) changed region `GP` → `ZA-MP` (Gauteng → Mpumalanga) inside central Pretoria.
- **Hypothesis:** an error in the November region migration, not a real relocation.
- **Confirm if:** its coordinates are unchanged and inside Gauteng. **Result:** _(pending)_

## I-3 Website removals in November — open
- **Observed:** 552 of 625 website changes were complete removals; 458 of those places had only `http://` links.
- **Hypothesis:** Overture dropped insecure or unverifiable websites in the November release.
- **Confirm if:** removal rate for `http://`-only places is far higher than for `https://`; check Overture release notes.
- **Result:** _(pending)_

## I-4 October had 0 removals — open, small
- **Observed:** the Oct changelog (vs Sep.1) shows 289 added and **0 removed** in the AOI; GeoTrustOps agrees.
- **Hypothesis:** a pipeline/process difference in that release (e.g. removals deferred), not zero closures.
- **Confirm if:** 0 removals also holds for a larger area or nationally. **Result:** _(pending)_

## I-6 What drives large confidence drops? — open
- **Observed:** confidence changes on 38–66% of matched places per release, mostly small (mean |Δ| 0.014–0.018),
  but some drops are large (e.g. 0.517 → 0.068, 0.718 → 0.117) with no `operating_status` change. 96–97% of
  changes coincide with the provider's source-level confidence changing.
- **Hypothesis:** large drops are passed through from one provider's own scoring, not Overture re-verification.
- **Confirm if:** large drops (> 0.3) concentrate in one source dataset and match that source's confidence change.
- **Why it matters:** if users filter on confidence (Overture's example uses `> 0.95`), a provider re-score can
  silently remove places from a map. **Result:** _(pending)_

## I-5 Lower-confidence places churn more — open
- **Observed (Oct→Nov):** median confidence 0.48 (added) and 0.43 (removed) vs 0.56 (matched).
- **Hypothesis:** low-confidence records are less stable between releases. Correlation only.
- **Confirm if:** the pattern holds in Sep.1→Oct as well. **Result:** _(pending)_
