# Source manifest — GeoTrustOps

All values below were **observed on 2026-11-23** by running the scripts named; none are assumed.

## Releases (pinned)

| | Previous | Current |
|---|---|---|
| Overture release ID | `2026-10-21.0` | `2026-11-18.0` |
| Source URI | `s3://overturemaps-us-west-2/release/2026-10-21.0/theme=places/type=place/*.parquet` | `s3://overturemaps-us-west-2/release/2026-11-18.0/theme=places/type=place/*.parquet` |
| Files in theme (S3 listing) | 16 parquet, ~11.3 GB total | 16 parquet, ~11.5 GB total |
| S3 LastModified of part-00000 | 2026-10-21T17:43Z | 2026-11-18T17:03Z |
| Records in study bbox | **5,733** | **5,738** |
| Local extract | `data/raw/places_2026-10-21.0.parquet` (709,349 B) | `data/raw/places_2026-11-18.0.parquet` (705,509 B) |
| SHA-256 | `338d87e6…a24beb` | `8f9d8516…42e171e5` |
| Extracted (UTC) | 2026-11-23T07:26:31 | 2026-11-23T07:27:06 |

Other releases visible in the bucket listing on 2026-11-23: `2026-09-23.0`, `2026-09-23.1`.
Full hashes are in `data/raw/*.manifest.json` (local, not committed).

**How releases were discovered:** anonymous S3 ListObjectsV2:
`https://overturemaps-us-west-2.s3.amazonaws.com/?list-type=2&prefix=release/&delimiter=/`

## Validation source: Overture GERS changelog (not a pipeline input)
- `s3://overturemaps-us-west-2/changelog/2026-11-18.0/theme=places/type=place/change_type=*/*.parquet` (64 files; listed 2026-11-23)
- Schema: `id, bbox, columns_changed (VARCHAR[]), change_type, theme, type`
- Used only to cross-check GeoTrustOps classes (contract §9). Changelogs exist for every release back to `2024-06-13-beta.0`.

## Study area
WGS84 lon/lat bbox: west `28.168`, south `-25.758`, east `28.205`, north `-25.732` (central Pretoria). Not expanded.
Filter: Overture `bbox` struct overlaps the AOI (identical rule for both releases).
Observed: 2 records per release have point coordinates marginally outside the AOI (Overture's bbox struct is rounded outward) → handled by the study-membership rule: a place is in the study only if it lies inside the exact AOI in at least one release (contract §2).

## Schema (identical in both releases — 18 columns, 0 added/removed/retyped)
`id, geometry (WKB BLOB), confidence, websites[], emails[], socials[], phones[], brand, addresses[], names, sources[], operating_status, basic_category, taxonomy, version, bbox, theme, type`

### Field mapping to the comparison record

| GeoTrustOps field | Overture source | Observed notes |
|---|---|---|
| `id` | `id` | GERS id; 0 null, 0 duplicate in both releases |
| `lon`, `lat` | `ST_X/ST_Y(ST_GeomFromWKB(geometry))` | 100% POINT; 0 null coords |
| `name` | `names.primary` | 0 empty in both |
| `category` | `taxonomy.primary` | 283 / 270 NULL. No legacy `categories` column exists |
| `basic_category` | `basic_category` | 282 / 270 NULL |
| `operating_status` | `operating_status` | almost all NULL (8 / 7 'open') → informational only |
| *(not compared)* | `version` | changed on 4,716 of 5,502 matched ids → not a meaningful change signal |

## Licence and attribution
- Overture Places guide: theme published under **CDLA-Permissive-2.0 and Apache-2.0, depending on source**; contains no OpenStreetMap data. https://docs.overturemaps.org/guides/places/
- Observed per-record `sources[].license` in extract: CDLA-Permissive-2.0, CC0-1.0 (AllThePlaces), Apache-2.0 (Foursquare).
- Source datasets observed: meta, AllThePlaces, Microsoft, Foursquare, Uberall, PinMeTo.
- Attribution, licence texts and the Foursquare NOTICE are in `DATA_LICENSE.md`, `NOTICE` and `LICENSES/`.
