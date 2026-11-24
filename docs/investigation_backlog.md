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
- **Original hypothesis (superseded 2026-11-24 before any analysis):** fallback geocodes at suburb, street or
  postcode centroids. Revised because businesses are rarely geocoded to an area centroid; shared buildings and
  shared address points are far more likely, and can be tested with fields already in the records.
- **Why it matters:** a person navigating to any of those 91 places is sent to the same spot; positional quality is
  worse than the release-to-release "unchanged" suggests. Also the trigger of a geometry-handling crash fixed earlier (engineering review log).
- **Hypotheses (pre-registered 2026-11-24):** **H1 shared complex**: the places are tenants of one building or
  complex. **H2 shared address point**: the places share one street address and so geocode to one point.
  **H0 unexplained**: neither; goes to stage B.
- **Data:** November release (`2026-11-18.0`), places inside the study AOI. A *stack* is 2 or more places on an
  identical coordinate; a *large stack* has 10 or more. Script: `scripts/investigate/stacked_coordinates.py`.
- **Stage A (place records only):**
  1. *Unit designators* in the freeform address or the name ("Shop 3", "Unit 12", "Suite 4", "Office 2", "Shop G14",
     "Stall", "Kiosk", "Floor"/"Level", "Block"). Removing them gives a *base address* (lowercase, punctuation
     removed, spaces collapsed). Per stack: share of places with a unit designator; share of places on the
     stack's most common base address.
  2. *Complex anchor* in the name **or** the freeform address. Strong: mall, shopping centre/center, shopping
     complex, retail park/centre/block, plaza, arcade, business park, office park, complex, tower(s). Weak
     (ambiguous, reported separately): centre/center, building, house, court, square.
  3. *Category fit*: share of the stack's places whose category would not fit inside a complex (natural features
     such as river, lake, mountain, forest, nature reserve; whole-area features such as neighbourhood or city;
     large transport infrastructure such as airport or train station; farms; campgrounds).
- **Per-stack classification:** **H2** if ≥ 50% of places share the most common base address. Otherwise **H1** if
  ≥ 50% carry a unit designator, or a strong anchor is present and ≤ 10% of categories do not fit. Otherwise **H0**.
  A missing address counts as no evidence, not as a different address.
- **Outcome rule:** *explained* (lead rejected as fallback geocodes) if H1 + H2 cover ≥ 80% of stacked places
  **and** ≥ 8 of the 10 largest stacks. Otherwise *inconclusive*, and the H0 stacks go to stage B.
- **Stage B (only if needed; licence review first):** test H0 stacks against Overture building footprints (point
  inside one building; building name) and address points (structured number/street/unit). Both themes may be
  partly ODbL-licensed.
- **Descriptive only:** source-dataset mix per stack.
- **Result (2026-11-24, stage A): `inconclusive`** under the pre-registered rule.
  - Reproduced the observation exactly: 5,736 places in the AOI; 960 (16.7%) on 196 stacks; 14 large stacks.
  - H2 153 stacks / 503 places (52.4%); H1 11 / 254 (26.5%); H0 32 / 203 (21.1%). H1 + H2 = **78.9%** (rule:
    ≥ 80%); top 10 explained **8** (rule: ≥ 8). Coverage misses by 1.1 points, so the rule says inconclusive.
  - **Measurement caveats found when checking what the measures captured** (thresholds not changed):
    - *H2 overcounts for the largest stacks.* The 91-place stack counts as H2 because its most common base address
      is just `pretoria` (48 places; 51 of 91 have a city-only address). That is a shared *town*, not a shared
      address point. Small stacks look different: 153 of 193 stacks with an address have a street number in their
      most common base address, consistent with genuine shared address points.
    - *H1 anchors are thin and contradictory in the large stacks.* 2–4 of 27–67 places carry an anchor, and one
      stack mixes "Shopping Centre", "Office Park" and "Retail Park": several complexes on one point, which fits a
      coarse fallback point better than one building.
    - *Exact equality splits clusters.* Four "stacks" of 48, 45, 36 and 13 places lie within about 1 m of each
      other (around 28.18763, −25.74587), i.e. one cluster of 142 places.
    - *A likely city-level fallback point.* The 91-place stack (28.18832, −25.74579) lies about 80 m from the
      `Church Square` plaza point in the same extract (28.188068, −25.746466), in the historic centre of Pretoria,
      and over half its places carry only "Pretoria" as address. Suggestive of a "Pretoria" geocode, not proof.
  - **Reading:** small stacks are mostly shared address points (the revised hypothesis holds there); the largest
    stacks look like coarse, city-level fallback points (the original hypothesis may hold there after all).
  - **Next (decision needed):** (1) pre-register a refined rule (H2 needs a street number; H1 needs one consistent
    anchor; points within 2 m form one stack; H3 = ≥ 50% city-only addresses) and test it on the **October**
    release as held-out data, since this release has now been seen; and/or (2) stage B with building footprints and
    address points after a licence review. Publish nothing until `verified`.


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
