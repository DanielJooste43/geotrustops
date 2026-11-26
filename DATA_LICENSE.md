# Data licensing and attribution

**Code** in this repository is licensed under the MIT License ([LICENSE](LICENSE)).
**Data** is not covered by the MIT License. It is derived from [Overture Maps Foundation](https://overturemaps.org)
releases and keeps the licence of each source record.

## Which files are data

| Path | Contents |
|---|---|
| `out/`, `out_pairs/` | change outputs (GeoJSON, JSON, Markdown) containing place names, coordinates and categories |
| `out_timeline/timeline.json` | record ids, positions and change kinds per release, from Overture's places changelogs (no names or other attributes) |
| `runs/history.jsonl` | aggregate run statistics |
| `tests/golden/` | place ids used as hand-classified test cases |
| `docs/history/feasibility_probe.json` | sample counts and records from the initial feasibility probe |

Raw extracts (`data/raw/`) are not committed or republished; `geotrustops fetch` downloads them from Overture's public
bucket, or from a private archive once Overture has removed a release. `data/archive.json` holds only their checksums.

### Raw extracts supplied for verification

The archived extracts are unmodified Overture records clipped to the extraction area (study area plus 0.01°); the
changelog extracts keep only `id`, `change_type`, `columns_changed` and `bbox`. Unlike the outputs they include the
source `phones`, `emails`, `websites` and `socials` fields. They are shared only on request for verification, together
with `LICENSES/` and `NOTICE`, are deleted 12 months after the v1.0 release, and any record is removed on request.
Licence review (2026-11-24): the extracts contain only the three licences below, and Overture's
[attribution page](https://docs.overturemaps.org/attribution/) states no further restriction on redistribution.
Overture states no licence for the GERS changelog; only identifiers and change codes are kept from it.
Licence review (2026-11-25), for `out_timeline/timeline.json`: Overture's attribution, changelog and data-access
pages and its site terms state no licence for the changelog. Its content is Places data, and for records from past
releases the source cannot be identified, so the timeline is shared under all three Places licences below, with
their texts in `LICENSES/`, the Foursquare `NOTICE`, and the attribution in the file. The timeline extracts keep only
`id`, `change_type` and `bbox`.

## Source licences

Overture's Places theme is "published under the CDLA Permissive 2.0 and Apache 2.0 licenses, depending on the
source" and "contains no OpenStreetMap data" ([Places guide](https://docs.overturemaps.org/guides/places/)).
Each output feature names its sources and licences in `source_datasets` and `source_licences`.

| Licence | Sources present in these outputs | Obligation when sharing | Text |
|---|---|---|---|
| CDLA-Permissive-2.0 | Meta, Microsoft, Uberall, PinMeTo, and other Overture sources | make the agreement text available with the shared data (§2.1) | [LICENSES/CDLA-Permissive-2.0.txt](LICENSES/CDLA-Permissive-2.0.txt) |
| Apache-2.0 | Foursquare OS Places | include the licence, a notice of changes, and the full Foursquare NOTICE (§4) | [LICENSES/Apache-2.0.txt](LICENSES/Apache-2.0.txt), [NOTICE](NOTICE) |
| CC0-1.0 | AllThePlaces | none (public-domain dedication) | [LICENSES/CC0-1.0.txt](LICENSES/CC0-1.0.txt) |

Per-source details: [Overture attribution and licensing](https://docs.overturemaps.org/attribution/).

## Context layers and the quality-flag file (ODbL)

The stacked-coordinates investigation (`scripts/investigate/`, `docs/investigation_backlog.md` I-1) reads three more
Overture themes for the extraction area: **divisions** (town and suburb points), **buildings** (footprints) and
**transportation** (road connectors and segments). Overture publishes these themes under the
[Open Database License (ODbL)](https://opendatacommons.org/licenses/odbl/1-0/); their main source is OpenStreetMap
([Overture attribution](https://docs.overturemaps.org/attribution/)).

| Theme | Licence | How it is used here | Shared? |
|---|---|---|---|
| divisions, buildings, transportation | ODbL 1.0 (© OpenStreetMap contributors, Overture Maps Foundation) | downloaded to `data/raw/context/` (git-ignored) by `scripts/investigate/fetch_context_layers.py`; read by `scripts/investigate/stack_causes.py` | the layers themselves: no. Results derived from them: yes, see below |

**`out_triage/stack_causes.json`** is a derivative database of these layers: for each group of places stacked
within 2 m in release 2026-11-18.0, its centre, size, the likely cause from the pre-registered checks
(`docs/investigation_backlog.md`, I-1), a manual-inspection flag and the place ids. It is published under the
[Open Database License 1.0](https://opendatacommons.org/licenses/odbl/1-0/) (text in
[LICENSES/ODbL-1.0.txt](LICENSES/ODbL-1.0.txt)), with the attribution "© OpenStreetMap contributors, Overture Maps
Foundation". It is a separate database: it holds no place names or other place attributes and is never merged into
the change outputs above, which keep their own licences. The method that creates it is
`scripts/investigate/stack_causes.py --export`; its inputs are listed by SHA-256 inside the file.

## Attribution

If you reuse these outputs, please cite:

> Overture Maps Foundation, overturemaps.org. Releases 2026-09-23.1, 2026-10-21.0 and 2026-11-18.0,
> accessed 2026-11-23 from https://registry.opendata.aws/overture. Includes Foursquare OS Places data
> (© Foursquare Labs, Inc., Apache-2.0); see NOTICE.

## Modifications

The outputs are modified from the source records: fields were extracted and normalised (including region-code and
phone-number normalisation), records were clipped to a study area around central Pretoria, compared between
releases and classified, and change attributes were added. See [docs/methodology.md](docs/methodology.md).

## Records about you

The outputs contain business listings as published by Overture, which states that the Places theme includes only
places without personally identifiable information. The source `phones`, `emails`, `websites` and `socials` fields
are not exported. Place names are reproduced as published, and a small number of source names include contact
details (for example a phone number typed into the name). If a record concerns you and you would like it removed
from this repository, please open an issue.
