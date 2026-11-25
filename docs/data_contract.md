# GeoTrustOps data contract — v0.4 (2026-11-23)

**History.** v0.1 first draft. v0.2: buffered extraction + study-membership rule after the changelog
cross-check exposed 7 boundary crossers; changelog oracle added. **v0.3** (ADR 0002): `shifted` change
type and move bands; `name_change_kind` replaces `name_cosmetic_only`; purpose-based field tiers with
lifecycle and enrichment flags; address region-code normalisation; run calibration log; second release pair.
**v0.4** (ADR 0005): project renamed MapPulse → GeoTrustOps; CLI `geotrustops`, GeoJSON foreign member `geotrustops`. No rule changes.

This contract is the single definition that the implementation, the independent contract tests and the
golden records are all checked against. If the code and this contract disagree, the code is wrong, or the contract is
changed first and re-approved.

Scope: Overture `places/place`. Primary pair `2026-10-21.0` (**prev**) → `2026-11-18.0` (**curr**)
(`config/study_area.json`); second pair `2026-09-23.1` → `2026-10-21.0` (`config/pair_sep_oct.json`).
AOI (WGS84): west `28.168`, south `-25.758`, east `28.205`, north `-25.732`.
**Extraction bbox** = AOI + `buffer_deg` (`0.01°`, ~1 km) on every side, so places crossing the AOI edge
between releases are in both extracts. All parameters live in config; nothing is hardcoded elsewhere.

---

## 0. Rule layers (ADR 0003)

Every rule in this contract belongs to exactly one layer and is tagged where it appears:

| Tag | Layer | Holds for | Changes when |
|---|---|---|---|
| `[generic]` | data-product-agnostic | any two snapshots of point features with stable ids | rarely; a contract version change |
| `[source: overture]` | source profile | Overture Maps places | the data source changes |
| `[locale: ZA]` | locale profile | records in South Africa | the country changes, even with the same source |

**Where each rule lives** (v0.3):

| Contract section | Rule | Layer |
|---|---|---|
| §1 | normalized field set and purpose tiers (key/locate/identify/classify/lifecycle/enrich) | `[generic]` |
| §1 | mapping to Overture fields (`names.primary`, `taxonomy.primary`, `basic_category`, `sources[]`, WKB geometry) | `[source: overture]` |
| §1 | `confidence` semantics: existence only, not comparable across providers, never classified on; `version` not compared | `[source: overture]` |
| §1 | which columns are required vs optional inputs | `[source: overture]` |
| §1 | region-code normalisation (`GP` → `ZA-GP` …) | `[locale: ZA]` |
| §1 | phone normalisation (`0…` → `+27…`) | `[locale: ZA]` |
| §2 | exclusion reasons and order; AOI membership; buffered study population | `[generic]` |
| §3 | change types and priority; haversine distance; move bands and thresholds; rename kinds; flags as computations | `[generic]` |
| §3 | *meaning* of `operating_status` values and of `confidence = 0` (= permanently closed) | `[source: overture]` |
| §4 | reconciliation identities | `[generic]` |
| §5–§8, §10 | outputs, run behaviour, interpretation limits, golden records, CLI/test interface | `[generic]` |
| §6, §10 | the *list* of required input columns, the input and changelog parquet shapes | `[source: overture]` |
| §5, §7 | literal attribution/release wording; changelog-specific fields in outputs and history | `[source: overture]` |
| §3 | which flag inputs come from profiles (confidence-0 signal: source; address/phone normalisation: locale) | profile, as marked |
| §8 | `lookup_id.py` reads Overture-shaped files (the golden-record process itself is generic) | `[source: overture]` |
| §9 | changelog oracle: its existence, its schema, and the "never compares `confidence`/`sources`" exception in rule 4 | `[source: overture]` |

**Correction to ADR 0001:** the earlier claim that "Stage A is the only Overture-specific stage" was too strong.
The source profile also covers the §3 lifecycle *meanings* and the whole §9 oracle; the locale profile covers
two §1 normalisations. The generic engine (§2–§4 logic) is unchanged by any of them.

**Checklist: what a new source or locale must define before it can be compared**
- *New source profile:* field mapping to the §1 normalized set; geometry encoding; which inputs are required;
  what its confidence/status fields mean (or that it has none); whether it publishes a changelog or other
  independent oracle, and which columns that oracle compares; licence and attribution; release identifiers.
- *New locale profile:* region/admin-code normalisation; phone normalisation; any address format rules.
- Until a profile exists, its rules must not be borrowed from Overture/ZA by default.

**Implementation status:** this layering is documented, **not yet separated in code** (both profiles are inline in
`src/geotrustops/pipeline.py`). Extraction into code profiles is deferred until a second source or locale is added
(ADR 0001 and ADR 0003 follow-up).

---

## 1. Stage A — normalized record (grain: one row per source row, per release)

**Adapter boundary (ADR 0001, corrected by ADR 0003):** Stage A holds the source mapping and the locale
normalisations; the source profile also defines §3 lifecycle meanings and the §9 oracle (see §0).

**Field tiers by purpose `[generic]` (ADR 0002 §3); column mapping `[source: overture]`.** Overture's schema requires only `id`, `geometry`, `theme`, `type`,
`version`; requiredness says what is *valid*, not what *matters*, so fields are tiered by purpose:

| Tier | Purpose | Normalized field(s) | Source | Used for |
|---|---|---|---|---|
| Key | match | `id` | `id` | matching |
| Locate | find it | `lon`, `lat`, `geom_type` | `ST_X/ST_Y(geometry)` | classification |
| Identify | right place? | `name` | `names.primary` (`''` → NULL) | classification |
| Classify | what / which icon | `category`, `basic_category` | `taxonomy.primary`, `basic_category` | classification |
| Lifecycle | still exists? | `operating_status`, `confidence` | same | flags only |
| Enrich | contact/context | `addresses_raw`, `addresses_norm`, `phones`, `websites`, `emails`, `socials`, `brand` | same (as JSON text); `brand_name` = `brand.names.primary` | `enrichment_changed` only |
| Attribution | licence | `source_datasets`, `source_licences` | sorted distinct `sources[].dataset/.license`, `;`-joined | display |

**Input requiredness `[source: overture]` (clarified 2026-11-23):** `confidence` is a **required column**
(§6, §10), but its *values* may be NULL. `operating_status` and all enrichment columns are **optional
inputs**: if a column is absent, it is treated as NULL.

**`confidence` is never classified on `[source: overture]`:** Overture states it measures existence only and is "not calibrated to be
strictly comparable across providers"; the changelog never compares it. **`version`** is not compared (bookkeeping).

**Address normalisation (`addresses_norm`) `[locale: ZA]`:** each address's `region` is mapped to its ISO 3166-2 code when it is a
known South African province code or name, case-insensitively (`GP`/`Gauteng` → `ZA-GP`, `WC` → `ZA-WC`,
`KZN`/`KwaZulu Natal`/`KwaZulu-Natal` → `ZA-KZN`, `NW`/`North West` → `ZA-NW`, `MP`/`Mpumalanga` → `ZA-MP`,
`LP`/`Limpopo` → `ZA-LP`, `EC`/`Eastern Cape` → `ZA-EC`, `FS`/`Free State` → `ZA-FS`,
`NC`/`Northern Cape` → `ZA-NC`; an existing `ZA-xx` is kept). Other parts are unchanged.

**Phone normalisation (`phones_norm`) `[locale: ZA]` (added 2026-11-23 on evidence: 424 of 492 Oct→Nov phone changes were
local → E.164 only):** empty values dropped; keep digits and `+`; a number starting `0` on a record whose first
address has `country = 'ZA'` becomes `+27` + the rest. Without a ZA address, no country prefix is assumed.

## 2. Stage B — row-level exclusion (grain: one row per source row) `[generic]`

First failing rule wins: 1 `missing_id` (NULL/`''`) · 2 `duplicate_id` (id occurs >1 in that release: **all**
copies excluded) · 3 `missing_geometry` (NULL/unparsable) · 4 `non_point_geometry` · 5 `invalid_coordinates`
(lon ∉ [-180,180], lat ∉ [-90,90] or NaN). Rows with no reason are **valid**; each valid row gets
`in_aoi` = `west ≤ lon ≤ east AND south ≤ lat ≤ north` (inclusive). For *any* row, AOI membership is
**unknown** (not "outside") when its coordinates are not a valid WGS84 position: missing, NaN or out of range,
whatever its exclusion reason.

**Study population:** an id is *in study* if it has a valid `in_aoi` row in **at least one** release, or has an
excluded row located in (or not locatable relative to) the AOI. Others are `buffer_only_ids` (counted, ignored).

## 3. Stage C — id-level classification (grain: one row per distinct non-empty id) `[generic]`

(Comparisons of *normalized* inputs are generic. Three inputs to them come from profiles:
the choice of `confidence = 0` as a lifecycle signal and the meaning of `operating_status` values are
`[source: overture]` (confidence 0 is always paired with `permanently_closed`); the address and phone
normalisations that feed `enrichment_changed` / `format_only_changed` are `[locale: ZA]`.)

Matching uses all extraction rows, so edge crossers are compared, not called added/removed.
`distance_m` = haversine, radius `6371000` m, unrounded coordinates.

Exactly one `change_type`, **first match wins**:

| Priority | `change_type` | Rule |
|---|---|---|
| 1 | `excluded` | an excluded row in either release |
| 2 | `added` | valid in curr, absent from prev **extraction** |
| 3 | `removed` | valid in prev, absent from curr **extraction** |
| 4 | `moved` | matched and `distance_m > move_threshold_m` (25.0, strictly greater) |
| 5 | `attribute_changed` | matched, not moved, and `name`, `category` or `basic_category` IS DISTINCT FROM |
| 6 | `shifted` | matched, no attribute change, `minor_move_m < distance_m ≤ move_threshold_m` (5.0 < d ≤ 25.0) |
| 7 | `unchanged` | matched, none of the above (it may still have lifecycle/enrichment flags) |

`matched` = valid in both releases. Thresholds are illustrative and configurable: 25 m is not an Overture
accuracy spec; 5 m approximates consumer-GPS error (ADR 0002 §1). A move does **not** mean the data improved.

**`move_band`** (every matched id): `stable` d ≤ 5 · `minor` 5 < d ≤ 25 · `material` 25 < d ≤ 100 · `major` d > 100
(bounds from config `minor_move_m`, `move_threshold_m`, `major_move_m`).

**Flags** (matched ids only; NULL otherwise):

| Flag | Rule |
|---|---|
| `name_changed`, `category_changed`, `basic_category_changed` | the field IS DISTINCT FROM |
| `name_change_kind` | NULL if not `name_changed`; else first match: `added` (NULL→value) · `removed` (value→NULL) · `case_or_spacing` (equal after lower-case + trim + collapse spaces) · `punctuation` (equal after lower-case and removing non-alphanumerics) · `expanded_or_trimmed` (one lower-cased name contains the other) · `different` |
| `name_matches_brand` | `name_changed` AND lower(curr `name`) = lower(curr `brand_name`) |
| `status_changed` | `operating_status` IS DISTINCT FROM |
| `confidence_to_zero` | curr `confidence` = 0 AND prev `confidence` IS DISTINCT FROM 0 |
| `enrichment_changed` | sorted `;`-joined list of enrich fields that differ (`addresses`, `phones` compare their normalised forms); `''` if none |
| `format_only_changed` | sorted `;`-joined list of `addresses` / `phones` whose raw value differs but normalised value is equal; `''` if none |
| `crossed_aoi_boundary` | `in_aoi` differs between releases |

Kinds describe the **edit**, not its quality. A `moved` record keeps its rename flags: priority is a display
choice, not a claim that nothing else changed.

## 4. Reconciliation identities (all must hold, or the run fails) `[generic]`

**Left-hand sides are counted independently from Stage B rows** with plain set operations, never from the
Stage C classification they check (identities counted from the classified table would pass even when an id
is dropped; proven by fault-injection tests). Grain of every set: one distinct id.

1. `R_side = V_side + X_side` per release (rows = valid + excluded).
2. distinct non-empty source ids (B) = **distinct** classified ids (C), and classified rows = distinct classified
   ids (one row per id; catches a substituted id that keeps the row count).
3. study population (B: ids with a valid in-AOI row, ∪ excluded ids located in or unlocatable relative to the AOI)
   = considered ids (C) = `excluded + added + removed + moved + attribute_changed + shifted + unchanged`.
4. excluded ids in the study population (B) = `excluded`.
5. ids valid in both releases, in study, not excluded (B) = `matched` = `moved + attribute_changed + shifted + unchanged`.
6. `C_curr` (B) = `added + matched`; `C_prev` (B) = `removed + matched`
   (`C_side` = valid ids in that release, in study, not excluded).

## 5. Outputs (deterministic: sorted by id, coords 6 dp, no timestamps) `[generic]`

**`<out>/changes.geojson`**: RFC 7946; one Point Feature per id with `change_type` ∈ {added, removed, moved,
attribute_changed, shifted}; at **prev** position for `removed`, else **curr**. Properties: `id`, `change_type`,
`distance_m` (1 dp), `move_band`, `prev_/curr_` × {`name`, `category`, `basic_category`, `lon`, `lat`,
`operating_status`, `confidence`}, the §3 flags, `source_datasets`, `source_licences`. Top-level foreign member
`geotrustops` (RFC 7946 §6.1): interpretation limits, releases, pipeline/contract version, input sha256s, changelog
sha256 (or null), attribution. *Generic requirement:* outputs carry provenance and interpretation limits.
`[source: overture]`: the literal attribution text, release-id format and `source_datasets/licences` fields.

**`<out>/summary.json`**: releases, aoi, extraction bbox, thresholds, input sha256s, input/valid rows, excluded rows by
reason, union/considered/buffer-only ids, `change_counts` (7 types), `move_band_counts`, `name_change_kind_counts`,
`flag_counts`, `enrichment_field_counts`, `format_only_field_counts`, `reconciliation`, `changelog_check`,
pipeline + contract version.

**`<out>/qa_report.md`**: the same in readable form, plus 10 largest moves, renames by kind, address-format and
lifecycle changes, all excluded rows, all changelog mismatches.

**`runs/history.jsonl`** (calibration log, ADR 0002 §5): one JSON line per distinct (input sha256s, changelog sha256
or none, config, pipeline version), upserted (an identical rerun replaces its own line; a different or absent
changelog is separate evidence), sorted by key: releases, input/changelog hashes, rows,
exclusion share per reason, change counts, changelog mismatches. Threshold changes are recorded in
`docs/calibration_log.md`. The changelog-specific fields (here, in `summary.json` and `qa_report.md`) are
`[source: overture]`: a source without an oracle leaves them null.

## 6. Run behaviour and failure rules `[generic]`
- `geotrustops build` (config → raw → out). Exit `2` and **nothing written** on: missing input file; 0 rows;
  required column missing (the list is `[source: overture]`: `id`, `geometry`, `names`, `taxonomy`,
  `basic_category`, `confidence`, `sources`);
  excluded rows > `max_excluded_share` (5%) of a release; any reconciliation identity false.
- Outputs are staged and swapped in only after all checks pass. Rerun with same inputs/config → byte-identical outputs.

## 7. Interpretation limits (in every output and the UI) `[generic]`
(The principle is generic; the wording names Overture because that is the implemented `[source: overture]` profile.)
Map-record changes between two Overture releases: `added` ≠ opened, `removed` ≠ closed, `moved`/`shifted` ≠ the earlier
position was wrong, a rename kind ≠ better or worse. Causes include source updates, conflation, de-duplication,
taxonomy or format migrations, and the AOI boundary.

## 8. Golden records `[generic]`
`tests/golden/golden_candidates.csv` holds real ids selected **blind** (one per case, `md5(id)` order, excluding
every id shown in any doc or tool output; labels never printed). `manual_class` is filled by hand using only
`scripts/lookup_id.py` and this contract, **without running the pipeline**. Allowed: the 7 change types or
`not_in_study`. Saved as `tests/golden/golden_records.csv`; `tests/test_golden.py` asserts agreement.
A disagreement is investigated, never fixed by editing the golden file. (The process is generic; `lookup_id.py`'s
query reads Overture-shaped files, `[source: overture]`.)

## 9. Independent cross-check: Overture GERS changelog `[source: overture]`
Per-release changelog `s3://overturemaps-us-west-2/changelog/<curr>/theme=places/type=place/` (`id`, `change_type`
∈ added/removed/data_changed/unchanged, `columns_changed`; relative to the release immediately before `curr`, which
must be `prev`). A **validation oracle**, never an input. Rules (mismatches listed in `qa_report.md`; a test asserts 0):
1. `added` ⇒ changelog `added`; `removed` ⇒ changelog `removed`.
2. `moved` or `shifted` ⇒ changelog `data_changed` with `geometry` in `columns_changed`.
3. `attribute_changed` ⇒ changelog `data_changed` with `names`, `taxonomy` or `basic_category` in `columns_changed`.
4. Changelog `unchanged` (and not GeoTrustOps `excluded`) ⇒ GeoTrustOps `unchanged` with `enrichment_changed = ''` and
   `status_changed = false`. **`confidence_to_zero` is deliberately not checked** (decided 2026-11-23): Overture's changelog states "`sources` and `confidence` are never compared", so a confidence-only
   change is legitimately `unchanged` there. A genuine closure is still caught: the schema pairs confidence 0 with
   `operating_status = permanently_closed`, and `operating_status` *is* compared (observed in `columns_changed`).
   Evidence: in both pairs 96–97% of place-confidence changes coincide with a change in the provider's own
   source-level confidence, changes go both up and down (mean |Δ| 0.014–0.018), and no place went to 0.
The reverse is not required: the changelog flags any compared-column difference (e.g. sub-5 m moves, address format).

## 10. Test interface `[generic]`
```
geotrustops build --config <cfg.json> --prev <prev.parquet> --curr <curr.parquet> [--changelog <cl.parquet>] --out <dir>
```
Exit `0` ok, `2` gate failed. Explicit `--prev/--curr` skip manifest checks; without them, pinned extracts under
`data/raw/` are read and their manifests (sha256, release, bbox) verified. Python: `geotrustops.cli.main([...]) -> int`.
`--no-history` skips the calibration log (tests use it). `--out` defaults to config `out_dir`, else `out/`.

**Config:** `releases.prev/.curr`, `aoi.{west,south,east,north}`, `buffer_deg`, `move_threshold_m`, `minor_move_m`,
`major_move_m`, `max_excluded_share`; optional `out_dir`, `source`.

**Input parquet `[source: overture]`:** required `id VARCHAR`, `geometry` (WKB BLOB or GEOMETRY), `names STRUCT("primary")`,
`taxonomy STRUCT("primary")`, `basic_category`, `confidence DOUBLE`, `sources STRUCT(dataset, license)[]`;
optional `operating_status VARCHAR`, `addresses STRUCT(freeform, locality, postcode, region, country)[]`,
`phones/websites/emails/socials VARCHAR[]`, `brand STRUCT(names STRUCT("primary"))`.
**Changelog parquet `[source: overture]`:** `id`, `change_type`, `columns_changed VARCHAR[]`.
`tests/fixtures/make_fixture.py` writes all of these from plain Python dicts.

## 11. Quality-triage output (separate database) `[source: overture]`
**`out_triage/stack_causes.json`**, written by `scripts/investigate/stack_causes.py --export` for one release (default:
config `releases.curr`). It is versioned by its own `schema_version` (currently `1`) and does not change the
change-output contract above: the classification, reconciliation and `out/` files are unaffected. It lives outside
`out/` because `geotrustops build` replaces that folder as a whole.

- **Grain:** one entry per cluster of **2 or more** places whose points lie within `cluster_rule_m` (`2.0` m) of each
  other (single linkage), among the release's valid points inside the AOI. A place belongs to at most one cluster.
- **Cluster fields:** `size` (= number of `ids`), `lon`/`lat` (cluster centre, mean of member points, 6 dp),
  `likely_cause` (first matching step of the pre-registered cascade in `docs/investigation_backlog.md`, I-1 stage C),
  `also_duplicates` (the cluster contains duplicate records although another cause matched first),
  `manual_inspection` (always `true`), `ids` (sorted). **No names or other place attributes.**
- **Top level:** `schema_version`, `release`, `method`, `cluster_rule_m`, `places_in_aoi`, `cluster_count`
  (= number of clusters), `clustered_places` (= sum of `size`), `inputs_sha256` (places extract and the four context
  layers: `building`, `connector`, `division`, `segment`), `licence` (`ODbL-1.0`), `licence_uri`, `attribution`,
  `interpretation`, `clusters`.
- **Determinism:** clusters sorted by `size` descending, then `lon`, then `lat`; UTF-8, `\n` line endings, no
  timestamps. The same inputs give byte-identical output.
- **Licence:** the likely causes are derived from Overture's ODbL themes, so the file is a separate database under
  ODbL 1.0 (licence URI and attribution inside the file; text in `LICENSES/ODbL-1.0.txt`). It is never merged into
  the change outputs.
- **Consumers** must check that `release` and `inputs_sha256.places` equal `releases.curr` and `inputs_sha256.curr`
  of the change run they are shown with, and must not show the flags otherwise.
- **Interpretation:** a likely cause from simple checks, not a verified defect; every cluster needs manual inspection.
