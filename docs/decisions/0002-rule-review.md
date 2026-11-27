# ADR 0002: Rule review: thresholds, renames, fields, boundary, failure rate, date range


**Status:** accepted and implemented in contract v0.3 / pipeline 0.3.0 (2026-11-23).
Follow-on under the same principle (format ≠ content), on new evidence: phone E.164 normalisation, and
`address_format_only` generalised to `format_only_changed` (see contract §1, §3).; **Date:** 2026-11-23
Evidence: real pinned extracts (AOI ids), Overture changelogs 2026-06 → 2026-11, Overture schema docs.
Each section gives the proposed change, the evidence, a verdict (agree / partly / disagree) and a proposal.

---

## 1. Move threshold, possibly per category / per feature type

**Suggestion:** thresholds per feature (POIs > 5 m worth knowing; roads more sensitive because of width).

**Evidence**
- Scope: GeoTrustOps compares **places only**. Roads are out of scope for this project.
- Overture defines places as "point geometries" but does **not** state what the point represents
  (entrance, centroid, geocode) or any positional accuracy (schema + Places guide, read 2026-11-23).
- No POI positional-accuracy standard was found. ISO 19157 defines positional accuracy as *fitness for
  use* against a reference, not a universal metre value.
- Real distances, 5,507 matched ids: ≤1 m 5,188; 1–5 m 23; 5–10 m 34; 10–25 m 84; 25–100 m 108; >100 m 70.
- By top-level category, share of matched places moving >5 m ranges 2.8%–13.7%, but the moving
  groups are small (14–56 places), too few to set per-category thresholds.

**Verdict: partly agree.**
- *Agree* that 5 m is a defensible floor: below it, moves are within typical consumer-GPS error
  (GPS.gov quotes ~4.9 m for smartphones in open sky), and 118 places moved 5–25 m that are currently
  hidden as `unchanged` / `attribute_changed`.
- *Disagree* with per-category thresholds now: there is no authoritative basis, Overture does not define
  the point's meaning, and the data are too sparse to calibrate. A threshold without a basis is not defensible.
- *Disagree* with researching road thresholds now: out of scope. Recorded in the backlog: for lines,
  displacement should be judged relative to carriageway width (e.g. half a lane), not a point threshold.
- *Disagree* that a >5 m move "improves" the dataset: without ground truth we can say it **moved**,
  not that it got better.

**Proposal (v0.3):** keep one *material* threshold (25 m) for `moved`; add a reported **move band** on every
matched id: `stable ≤5 m`, `minor 5–25 m`, `material 25–100 m`, `major >100 m`; add change type
**`shifted`** (5–25 m, no attribute change) so minor moves are visible and filterable. Thresholds stay in config.

## 2. Cosmetic renames

**Suggestion:** renames count, but "cosmetic" must be defined more clearly; brand alignment and capitalisation
are improvements.

**Evidence:** 41 renames in AOI: **24** one name contains the other ("Mr Price Cellular Pta" → "Mr Price"),
**14** different text, **3** case/spacing only. Examples that are *not* clearly improvements:
"Topaz Disco CC" → "Topaz Disco PRETORIA, Gauteng" (location stuffed into the name);
"Guleti mncube" → "Guleti kibooko bigoondo khumalo".

**Verdict: agree that the definition must be sharper; disagree that the tool should label renames as
improvements.** The data show renames that look worse as often as better; judging quality needs a reference.

**Proposal:** replace `name_cosmetic_only` with **`name_change_kind`**, defined by edit type, not quality:
`case_or_spacing`; `punctuation` (equal after removing non-alphanumerics); `expanded_or_trimmed` (one contains
the other); `different`; `added` / `removed` (NULL ↔ value). All still count as `attribute_changed`.
Optional flag `name_matches_brand` (new name equals `brand.names.primary`) to support the brand-alignment reading.

## 3. Which fields are compared; mandatory vs optional; confidence, basic_category

**Suggestion:** mandatory-field changes matter most; optional fields are enrichment; decide by purpose.

**Evidence (Overture place schema v2.0.0):** only `id`, `geometry`, `theme`, `type`, `version` are required.
`names`, `taxonomy`, `basic_category`, `confidence`, `addresses`, `operating_status`… are all **optional**.
`basic_category` is "recommended … for map iconography". `confidence` "measures existence only", is "not
calibrated to be strictly comparable across providers", and the changelog **never compares it**.
`operating_status` ∈ open / temporarily_closed / permanently_closed; permanently_closed ⇒ confidence 0.

**Verdict: disagree with "mandatory = most important"; agree with "decide by purpose".** By the schema's
own rules a place without a name is valid, yet a nameless POI is close to useless to a person finding it.
Schema-requiredness tells us what is *valid*, not what *matters*.

**Proposal (purpose tiers for a place):**

| Tier | Purpose | Fields | Treatment |
|---|---|---|---|
| Locate | can you find it | geometry | classification (`moved` / `shifted`) |
| Identify | is it the right place | names.primary | classification + `name_change_kind` |
| Classify | what is it, which icon | taxonomy.primary, basic_category | classification (keep both: basic_category drives icons) |
| Lifecycle | does it still exist | operating_status, confidence | **flags**: `status_changed`, `confidence_to_zero`; confidence shown, never classified (uncalibrated; mean change 0.012 on 3,635 places = noise) |
| Enrich | contact / context | addresses, phones, websites, emails, socials, brand | **`enrichment_changed`** list + counts; not a material change |

**Addresses, a real finding:** 4,706 places changed addresses, and **4,047 of those changed only the region code
`GP` → `ZA-GP`** (ISO 3166-2 style). Variants: `Gauteng` → `ZA-GP`, and anomalies `GP` → `Gauteng` and
`GP` → `ZA-MP` (1 place, Gauteng → Mpumalanga, wrong for central Pretoria). Proposal: compare addresses with
region codes normalised; report `address_format_only` separately from real address edits (121 freeform,
83 locality, 61 postcode changes).

## 4. Boundary rule

**Suggestion:** check industry practice.

**Evidence:** osmium (the standard OpenStreetMap extract tool) never clips objects, and its default
`complete_ways` strategy keeps whole objects that touch the region. Spatial statistics handles edge effects with a
guard zone (buffer). Our crossers moved 44–404 m; the buffer is ~1 km.

**Verdict: the current v0.2 design already follows practice.** Extract larger, match on complete records,
decide membership on the exact AOI. No change. The changelog oracle detects any mover beyond the buffer.

## 5. 5% exclusion failure threshold and an "ML learning doc"

**Verdict: disagree with ML; agree with learning from runs.** There is nothing to train on: 4 extractions,
0% exclusions observed. Calling a threshold rule "ML" would be an overclaim.

**Proposal:** a **calibration log**: each build upserts one row (keyed by input hashes, so reruns don't duplicate)
into `runs/history.jsonl` with exclusion rates per reason, change counts and changelog mismatches.
`docs/calibration_log.md` records threshold decisions. Rule: keep 5% until ≥6 runs exist, then set the gate
from the observed baseline (statistical process control, not ML).

## 6. Date range

**Suggestion:** design on the range with most changes; the latest release is the most relevant to present.

**Evidence: changelogs for the AOI, each vs its previous release:**

| Release | added | removed | data_changed | dominated by |
|---|---|---|---|---|
| 2026-06-17 | 7 | 21 | 242 | taxonomy (233) |
| 2026-07-22 | 870 | 850 | 1,321 | geometry 511 (largest real churn) |
| 2026-08-19 | 424 | 653 | 2,311 | addresses (1,154) |
| 2026-09-23.0 / .1 | 313 | 108 | 4,924 | `categories` removal (4,557): a schema migration |
| 2026-10-21 | 289 | **0** | 603 | geometry (352) |
| 2026-11-18 | 232 | 228 | 4,720 | addresses (3,493): region recode |

Only **Sep, Oct and Nov** release data are still on S3; July/August exist only as changelogs.

**Verdict: disagree with "design on the range with most changes".**
1. The tool is config-driven: it must work on *any* pair; no range is designed in.
2. "Most changes" mostly measures *schema migrations* (Sep: categories removal; Nov: region recode), not
   map updates. More rows of noise do not mean more issues found.
3. The richest real churn (July) can't be compared: its release data are gone.
4. Sep→Nov would merge two changelogs, losing the one-to-one oracle check.

**Proposal:** keep **Oct→Nov** as the headline pair (latest, oracle valid, most current, includes the
region-recode finding). Add **Sep.1→Oct** as a second configured pair, run through the same pipeline, so the
calibration log has more than one data point and the method is shown to work on another release pair.

---

## Scope check
Additions are flags, one change type (`shifted`), address normalisation, a run log and a second config. No new
infrastructure, no roads, no ML. Implemented before the independent contract tests and golden records
were written, so neither had to be redone.
