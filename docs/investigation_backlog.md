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

## I-1 Stacked coordinates (**verified as a triage method (2026-11-24)**)
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
  - **Quality framing (2026-11-24):** a stack is a positional defect whatever its cause. Forty shops in one mall
    on one point are "explained" but still send every visitor to the same spot, so a user must correct or accept
    the error. The aim is to **diagnose the cause** of each stack, not to excuse it.
  - **Exploratory profile** (`scripts/investigate/stacked_profile.py`; descriptive, no thresholds depend on it).
    Candidate causes seen in the data, none verified:
    - *Postal-box addresses:* 57 stacked places have a "Private Bag"/"PO Box" address (singles: 4 of 4,776). 75 of
      the 78 stacked "libraries" come from AllThePlaces and are organisations with postal addresses (e.g. "Private
      Bag x680"); the 51-place stack is 84% postal. A postal box cannot be geocoded to a street.
    - *Town-only addresses:* the 91-place stack is 93% "Pretoria"-only addresses (meta), about 80 m from Church
      Square: a likely town-level fallback point.
    - *Reduced coordinate precision:* stacked places have ≤ 5 decimals far more often (54–76%) than single places
      (11%; median 8 decimals). The 66-place stack is entirely at 4 decimals (about 11 m), so truncation merges
      places with different street addresses.
    - *Shared street address:* small stacks (median 3 places) mostly share a numbered street address (e.g. 15
      places at one Madiba Street number): a building or address point without unit-level positions.
    - *Split clusters:* 142 places within about 1 m form four "exact" stacks.
  - **Indicators that do not separate stacks:** confidence (median 0.51–0.57 in every group, so filtering on
    confidence will not remove stacked places); source update year (all 2026); website/phone completeness.
    **Weak indicators:** missing category (7–13% stacked vs 3% single), brand present (3–4% vs 11%).
  - **Persistence:** 93–96% of stacked places were at the same point in the October release; stacks persist
    between releases rather than appearing and disappearing.
  - **Measurement note:** "has a number" also counts postal numbers ("Private Bag x680"); a check for place
    words in names failed validation and was dropped.
- **Review fix (2026-11-24):** missing categories are now coalesced to "not unfit" (a missing category is no
  evidence, the same policy as a missing address). Re-running stage A gives the same counts and outcome (111 stacked
  places have no category; no stack crossed the 10% threshold).
- **Stage C: likely-cause cascade (pre-registered 2026-11-24, before any of its data was downloaded).**
  Purpose: assign each cluster a *likely cause* from simple checks on Overture data only; every cluster, explained
  or not, is flagged for **manual inspection**. The label is a guide for reviewers, not a verdict.
  Script: `scripts/investigate/stack_causes.py`. Run on November (`2026-11-18.0`) and repeated on October
  (`2026-10-21.0`) for comparison. Extra Overture layers from the same release as the places, extraction bbox only:
  divisions (`division` points), buildings (`building`), transportation (`connector`, `segment`); ODbL, used for
  internal analysis only.
  0. *Cluster*: places within 2 m of each other (single-linkage) form one cluster; clusters of 2+ places are tested.
  1. *Duplicate records*: places in the cluster with the same normalised name or the same phone number as another
     place in it. If duplicates are ≥ 50% of the cluster: **duplicate records**, stop. Otherwise attach the flag
     "contains duplicates" and continue.
  2. *Shared street address*: ≥ 50% share one base address (unit designators removed) that contains a street number
     → **shared address point**; if ≥ 50% also carry a unit designator → **multi-tenant address**.
  3. *Address quality*: ≥ 50% have a postal-box address. If ≥ 50% of the cluster share the **same** box (e.g.
     "Private Bag X680", compared on the box type and number) → **one institution, shared postal box**; otherwise
     → **postal address, no street**. (Amended 2026-11-24 before the cascade was run: a shared private bag marks one
     institution, such as a university, while different boxes on one point suggest a fallback point. The earlier
     stage A profile had shown that the 51-place stack is mostly postal with few repeated boxes.) ≥ 50% have a town-only
     address (no digit) → **town-only address**, and continue to step 4 (step 4's label replaces it if it matches).
  4. *Town point*: cluster centre within 2 m of a division point (locality, localadmin, borough, macrohood,
     neighborhood, microhood) → **town-level geocode**.
  5. *Rounded coordinates*: every point in the cluster has ≤ 4 decimals in both lon and lat → **rounded coordinates**.
  6. *Building*: cluster centre inside a building footprint. Footprint ≥ 10,000 m² and (floors ≤ 3 or floors
     unknown) → **large building (mall-like)**; otherwise → **one compact building**. Report how often floors are
     unknown.
  7. *Street geometry*: centre within 2 m of a connector → **intersection geocode** (noted when the address says
     "Cnr"/"Corner"); else within 2 m of a road segment → **street-centreline geocode**.
  - Otherwise → **unknown: manual inspection**.
  - Output: clusters and places per likely cause, per release; the 10 largest clusters with their cause.
  - Out of scope (scope guard): external datasets, unlikely-feature overlaps, severity scores, position fixes.
  - **Result on November under the registered cascade** (exploration release, seen before): 503 clusters holding
    1,951 places (2 m clustering; 960 on exact stacks). Shared address point 911 (46.7%), one compact building 286,
    street-centreline geocode 205, town-only address 196, unknown 133, multi-tenant address 109, postal address 52,
    duplicate records 39, intersection 11, large building 9. Floors unknown for 40 of 47 building matches.
    The three largest city-centre clusters (143, 106, 36 places) lie 28, 44 and 24 m from Overture's "Pretoria"
    locality point; no cluster was within 2 m of any division point. 66 of 105 places in the cluster labelled
    "one compact building" are at exactly 4 decimals.
- **Stage C amendment (2026-11-24, recorded before the October run; October is the confirmation release).**
  Each change is judged by whether it changes what an evaluator does next, not by counts alone:
  - *Town point*: the 2 m match is dropped (it needs a supplier to use exactly Overture's coordinates, which
    never happened). New step after the postal step: **10+ places and centre within 50 m** of a division point →
    **near a town point (likely town-level geocode)**. Suppliers' town points differ by tens of metres; a fallback
    point gathers many unrelated places, so small clusters (genuine neighbours in a dense centre) are excluded.
  - *Rounded coordinates*: **≥ 50%** of the cluster's points at ≤ 4 decimals (was: every point; 2 m clustering
    pulls in neighbouring points with more decimals).
  - *Multi-tenant address* is merged into **shared address point**, with the note "unit numbers recorded": same
    cause, same action.
  - *Building*: footprint area alone decides **large building (mall-like)** (≥ 10,000 m²) versus **compact
    building**; floor counts are missing for most buildings.
  - Dropped from the cascade: complex anchor words (thin and contradictory in large stacks), category fit
    (ingestion pipeline's job), source mix (does not separate stacked from single places).
  - Kept as headline findings: confidence does not separate stacked places; stacks persist between releases.
  - New order: duplicates → shared address → postal → near a town point → town-only address → rounded coordinates →
    building → intersection → street centreline → unknown. Every cluster: manual inspection recommended.
- **Stage C result (amended cascade, 2026-11-24).**

  | Likely cause | October (confirmation): clusters / places | November: clusters / places |
  |---|---|---|
  | shared address point | 319 / 934 (47.2%) | 315 / 911 (46.7%) |
  | near a town point (likely town-level geocode) | 3 / 271 (13.7%) | 3 / 285 (14.6%) |
  | one compact building | 42 / 185 | 43 / 181 |
  | unknown: manual inspection | 28 / 127 (6.4%) | 29 / 133 (6.8%) |
  | shared address point (unit numbers recorded) | 52 / 116 | 49 / 109 |
  | rounded coordinates | 1 / 107 | 1 / 105 |
  | town-only address | 36 / 90 | 34 / 90 |
  | postal address, no street | 1 / 53 | 1 / 52 |
  | duplicate records | 16 / 40 | 16 / 39 |
  | street-centreline geocode | 9 / 35 | 7 / 26 |
  | intersection geocode (address says corner) | 2 / 13 | 2 / 11 |
  | large building (mall-like) | 2 / 6 | 3 / 9 |

  - Clusters: October 511 holding 1,977 places; November 503 holding 1,951. A likely cause other than "unknown"
    for 93.6% (October) and 93.2% (November) of clustered places. Clusters that also contain duplicates: 7 / 6.
  - The 10 largest clusters get the same cause in both releases (three city-centre clusters near the "Pretoria"
    point; one rounded-coordinates cluster; one postal cluster; five shared address points).
  - **What October shows, and what it does not:** 93–96% of stacked places sit on the same point in both
    releases, so October is mostly the same records. It shows the labels are stable on a release that was not used
    to tune the rule; it is not an independent validation on new places.
  - **Outcome:** stage C registered no pass mark of its own, so the stage A outcome rule is the yardstick (a cause
    for ≥ 80% of clustered places and for ≥ 8 of the 10 largest). October meets it: 93.6% and 10 of 10.
    `verified` as a *triage method* (likely causes from simple checks, reproducible across releases);
    no individual cause is verified without manual inspection. Headline findings for evaluators: about a third of
    places in central Pretoria share a point within 2 m with another place; confidence does not separate them;
    the largest stacks are likely town-level fallback points; stacks persist between releases.
  - **Not yet decided:** whether and how to publish per-place likely causes (ODbL share-alike applies to data
    derived from the context layers; counts and summaries are fine with attribution).
  - **Next (decision needed):** (1) pre-register a refined rule (H2 needs a street number; H1 needs one consistent
    anchor; points within 2 m form one stack; H3 = ≥ 50% city-only addresses) and test it on the **October**
    release as held-out data, since this release has now been seen; and/or (2) stage B with building footprints and
    address points after a licence review. Publish nothing until `verified`.


## I-2 Wrong-province region recode (open, small)
- **Observed:** 1 place (`Bushbuck Group`) changed region `GP` → `ZA-MP` (Gauteng → Mpumalanga) inside central Pretoria.
- **Hypothesis:** an error in the November region migration, not a real relocation.
- **Confirm if:** its coordinates are unchanged and inside Gauteng. **Result:** _(pending)_

## I-3 Website removals in November (open)
- **Observed:** 552 of 625 website changes were complete removals; 458 of those places had only `http://` links.
- **Hypothesis:** Overture dropped insecure or unverifiable websites in the November release.
- **Confirm if:** removal rate for `http://`-only places is far higher than for `https://`; check Overture release notes.
- **Result:** _(pending)_

## I-4 October had 0 removals (open, small)
- **Observed:** the Oct changelog (vs Sep.1) shows 289 added and **0 removed** in the AOI; GeoTrustOps agrees.
- **Hypothesis:** a pipeline/process difference in that release (e.g. removals deferred), not zero closures.
- **Confirm if:** 0 removals also holds for a larger area or nationally. **Result:** _(pending)_

## I-6 What drives large confidence drops? (open)
- **Observed:** confidence changes on 38–66% of matched places per release, mostly small (mean |Δ| 0.014–0.018),
  but some drops are large (e.g. 0.517 → 0.068, 0.718 → 0.117) with no `operating_status` change. 96–97% of
  changes coincide with the provider's source-level confidence changing.
- **Hypothesis:** large drops are passed through from one provider's own scoring, not Overture re-verification.
- **Confirm if:** large drops (> 0.3) concentrate in one source dataset and match that source's confidence change.
- **Why it matters:** if users filter on confidence (Overture's example uses `> 0.95`), a provider re-score can
  silently remove places from a map. **Result:** _(pending)_

## I-5 Lower-confidence places churn more (open)
- **Observed (Oct→Nov):** median confidence 0.48 (added) and 0.43 (removed) vs 0.56 (matched).
- **Hypothesis:** low-confidence records are less stable between releases. Correlation only.
- **Confirm if:** the pattern holds in Sep.1→Oct as well. **Result:** _(pending)_

## I-7 Organisations categorised as libraries (open, small (logged 2026-11-24))
- **Observed:** 75 places from one AllThePlaces directory are categorised `library` but are government
  departments, institutes and companies with postal-box addresses (found during I-1).
- **Hypothesis:** a library-directory source whose members are organisations, not libraries; a category defect,
  separate from stacking.
- **Confirm if:** most of these records come from one source and few names contain "library". **Result:** _(pending)_
