# GeoTrustOps QA report

Releases: `2026-09-23.1` → `2026-10-21.0` · shifted > 5.0 m · moved > 25.0 m · major > 100.0 m · contract v0.4

> Map-record changes between two Overture releases. added != opened, removed != closed, moved/shifted != the earlier position was wrong, a rename kind != better or worse.

## Provenance

- Pipeline `1.0.0` · contract `v0.4`
- AOI: {'west': 28.168, 'south': -25.758, 'east': 28.205, 'north': -25.732}
- Extraction bbox (AOI + buffer): {'west': 28.157999999999998, 'south': -25.768, 'east': 28.215, 'north': -25.721999999999998}
- Input sha256: prev `a309a92a031dfa1162f556a18dcf02cfa87123c234a47949d943f68a2c86f746` · curr `f69ec5ca48f04a6564952f76eb0ea78c1c6a85086da7f440e863862c076fe1c8`
- Changelog sha256: `7e2e0287af00bec74d0d486d1b07fe7a168b3d6f19c471a653b6abd7af8a9873`

## Inputs

| | prev | curr |
|---|---|---|
| rows in extraction (AOI + buffer) | 7811 | 8209 |
| valid rows | 7811 | 8209 |
| excluded: `missing_id` | 0 | 0 |
| excluded: `duplicate_id` | 0 | 0 |
| excluded: `missing_geometry` | 0 | 0 |
| excluded: `non_point_geometry` | 0 | 0 |
| excluded: `invalid_coordinates` | 0 | 0 |

Ids: 8209 in extraction, 5733 in study, 2476 buffer-only (ignored).

## Change types (ids in study)

| type | count |
|---|---|
| excluded | 0 |
| added | 289 |
| removed | 0 |
| moved | 111 |
| attribute_changed | 72 |
| shifted | 74 |
| unchanged | 5187 |

| move band (matched ids) | count |
|---|---|
| stable | 5238 |
| minor | 95 |
| material | 74 |
| major | 37 |

| flag | count |
|---|---|
| name_changed | 47 |
| name_matches_brand | 3 |
| category_changed | 71 |
| basic_category_changed | 56 |
| status_changed | 6 |
| confidence_to_zero | 0 |
| crossed_aoi_boundary | 4 |

| enrichment field changed (addresses after region normalisation) | count |
|---|---|
| addresses | 177 |
| brand | 54 |
| emails | 42 |
| phones | 44 |
| socials | 46 |
| websites | 52 |

| format-only change (raw differs, normalised equal; not counted above) | count |
|---|---|
| addresses | 0 |
| phones | 6 |

## Renames by kind (kind describes the edit, not its quality)

| kind | count |
|---|---|
| added | 0 |
| removed | 0 |
| case_or_spacing | 3 |
| punctuation | 2 |
| expanded_or_trimmed | 26 |
| different | 16 |

| kind | id | previous | current | = brand |
|---|---|---|---|---|
| case_or_spacing | `0fcca0ef-5420-46d8-86a7-d124c76d5dd4` | sportscene | Sportscene | True |
| case_or_spacing | `1780ba1b-607a-49cb-9fc1-e0e8c36d6709` | AudioStyling | Audiostyling | False |
| case_or_spacing | `61b5005a-1473-4727-9b29-5cf031e58c12` | Magampa & Associates  Attorneys Inc | Magampa & Associates Attorneys Inc | False |
| different | `22d7ca0c-4c82-4fdc-abf5-37264fa08587` | Stevovo's Fast Food and Takeaways | Stevovo'S Fast Food & Take Aways | False |
| different | `38058c2e-575e-4157-959f-136b5e617399` | Colosseum Hotel | Colosseum Executive Suite Hotel | False |
| different | `3a64cf5d-9177-4918-acb6-a01b7be9ccfd` | Unfpa - United Nations Population Fund Library | UNFPA Library | False |
| different | `48038267-3758-4203-8277-9ecc29ad3147` | Marivate P M | Mashiapata M J | False |
| different | `73238018-e160-4665-8bf9-b45b15e8f625` | Sterkinekor Sterland | Brooklyn Sterkinekor Classic | False |
| different | `808a15f5-8d37-421f-b376-eb7da5398973` | Old Mutual Finance | Old Mutual South Africa | True |
| different | `905df28d-73f9-4ddd-82d1-0bb578d694bf` | Brightsky Homeware and Kitchenware | Brightsky Homeware & Kitchenware | False |
| different | `9ca3e0f9-6539-4159-8093-1b78a0caef00` | Shermitex Academy | shermitex and smt security | False |
| different | `a3b20a95-b39c-4588-8dc1-80ed4496a43b` | Sol-Ant Travel and Tours | Sol-Ant Travel & Tours | False |
| different | `aced0705-77ca-429e-99be-048125066e91` | S.MAB Aviation Academy | S.MAB Training Academy | False |
| different | `c4f9b99e-b54a-49cd-bdeb-0c2f804536b7` | Leticon Branding | Leticon Flooring Solutions | False |
| different | `cbfc9f34-9482-4759-8f7a-73078b65a684` | Bloed Street Shopping Centre | BloedStreet Mall Shopping Center | False |
| different | `e8076ce7-e423-4a53-8b52-9eae9521098a` | Best-One | Best One SA | False |
| different | `ed2a3ffb-73ee-45b0-be2b-c6a4ef5e5deb` | TotalEnergies Wf Nkomo | TotalEnergies Hansa Auto Services | False |
| different | `f1cb9f53-7cc8-4c83-a147-1f8753472553` | Silent Night Guest House Sunnyside, Pretoria | Silent Night Guest House Sunnyside Pretoria - Superior Queen Room | False |
| different | `fb8e9bf7-1304-4476-b020-54afc9d42cf1` | Selah Jewellery | Selah Fine Jewellery | False |
| expanded_or_trimmed | `0aa7f715-1ae6-4ff3-b375-d564a347099f` | Ithreesixty mobile | ithreesixty mobile phone | False |
| expanded_or_trimmed | `17c51ee8-810e-49d3-a434-315ea5908ce2` | Bidvest Bank | Bidvest Bank - Sanlam Centre | False |
| expanded_or_trimmed | `1c5b163f-e5b6-4a73-b9e8-de68a8184b29` | Attorneys | Matshona Attorneys | False |
| expanded_or_trimmed | `1d1f853a-92ba-4c5f-8c18-b6abf533ace7` | Adidas Outlet | adidas Outlet Store Pretoria, Pretoria CBD | False |
| expanded_or_trimmed | `33851b53-87ef-45b6-8d5d-d7b0c32049b5` | Genpower Solar | Genpower | False |
| expanded_or_trimmed | `35d8f4b8-a980-4641-9024-81ca0fe3490c` | Laomai Medical Centre | Pretoria Dentist - Laomai Medical Centre | False |
| expanded_or_trimmed | `4eff5ab0-3041-4bcb-b6a1-4455bfb687a7` | Sportscene | sportscene - Sunny Park | False |
| expanded_or_trimmed | `516b7fa6-a24a-44e8-92c3-8a721418ed6a` | Enzo's Lounge | Enzo's Lounge Paul Kruger Street 501  | False |
| expanded_or_trimmed | `51b3d327-1fe2-4c3e-8c4e-b09d15d669c5` | Kingdom Blue | Kingdom Blue Funeral Service | False |
| expanded_or_trimmed | `57f3da12-837d-42c2-abc9-ac63128f30b0` | Peermed Dentist In Pretoria | Dentist in Pretoria | False |
| expanded_or_trimmed | `5e4b0a8c-726c-41a4-bd4d-5c81481fe897` | Post Office South Africa | Pretoria | Post Office South Africa | False |
| expanded_or_trimmed | `77570fc0-456d-485e-9bd3-0c385f49033a` | Van der Stel Building | 179 Van Der Stel Building South Point | False |
| expanded_or_trimmed | `8337e910-8cff-447b-b03b-ce0fd7d3aa72` | Auto Pedigree | Auto Pedigree Pretoria Central | False |
| expanded_or_trimmed | `835b1387-23ab-452a-8fa4-62bdff3dc62b` | Lesmed | Lesmed Products CC | False |
| expanded_or_trimmed | `9b453b69-c281-4f70-84f8-9f0212b66d62` | TAPE Pretoria CBD | TAPE | True |
| expanded_or_trimmed | `a6e0a50f-1a28-4df3-9efb-ac67400ae0f1` | Limparts Africa | Limparts | False |
| expanded_or_trimmed | `aa58a503-6047-4296-821b-f1001fb81357` | Stunts Photography Pretoria  | Stunts Photography | False |
| expanded_or_trimmed | `ab6a6183-4834-4550-815f-0b3b414535e9` | Phyllis Robertson Home | Phyllis Robertson Home / Tehuis | False |
| expanded_or_trimmed | `af94dbda-def3-4d24-8b06-15412a45f453` | Adidas Outlet | adidas Outlet Store JHB, Festival Mall | False |
| expanded_or_trimmed | `d348a9c1-7503-437d-8601-ba813849b756` | Patrone Baloyi Trading and Project | Patrone Baloyi Trading and projects | False |
| expanded_or_trimmed | `d3e64722-9d7e-4f85-b78c-514b429bbbc9` | Sisonke Global Systems | Sisonke Global System | False |
| expanded_or_trimmed | `d800a79c-d892-4501-9e0d-ed3beddfd180` | Steers | Steers Pretoria Central | False |
| expanded_or_trimmed | `d802c210-6c06-4379-aef1-15bfc4397ddf` | Regus | Regus - Pretoria, Central | False |
| expanded_or_trimmed | `e7f335d2-9cd5-431c-814a-3a76a3baa7f1` | Standard Bank Pretoria Central | Standard Bank | False |
| expanded_or_trimmed | `e9d40e52-f94e-4bfe-82fd-1b428e632035` | Tip N Tip | Tip N Tip Store | False |
| expanded_or_trimmed | `f39e35ba-f246-41da-96c7-5653be97f98c` | Reuben's Place, Pretoria | Reuben'S Place | False |
| punctuation | `ab0f66a1-ce7c-4333-9d05-458e03b97868` | Smiletech computers | SMILE TECH computers | False |
| punctuation | `c64aa9bc-9d50-40ba-8c37-76b179b6838a` | Swaleh's Secondhand Wheels and Tyres Centre | Swaleh’s second hand wheels and tyres centre | False |

## Lifecycle changes (6)

- `1d1f853a-92ba-4c5f-8c18-b6abf533ace7` adidas Outlet Store Pretoria, Pretoria CBD: status None → open, confidence 0.8 → 0.99
- `656ba032-4ef8-4b67-9fd9-a5075b3eebad` Shell: status None → open, confidence 0.9997621375203133 → 0.9999881068760157
- `af94dbda-def3-4d24-8b06-15412a45f453` adidas Outlet Store JHB, Festival Mall: status None → open, confidence 0.8 → 0.99
- `d802c210-6c06-4379-aef1-15bfc4397ddf` Regus - Pretoria, Central: status None → open, confidence 0.9222823366522789 → 0.9959436754137277
- `e7e60093-50d2-4ce3-9193-8021b0172d54` Shell: status None → open, confidence 0.9997351062536239 → 0.9999866808313131
- `ed2a3ffb-73ee-45b0-be2b-c6a4ef5e5deb` TotalEnergies Hansa Auto Services: status None → open, confidence 0.9912530857324601 → 0.9995716899335384

## Reconciliation

- ✔ `R_prev = V_prev + X_prev`: 7811 = 7811
- ✔ `R_curr = V_curr + X_curr`: 8209 = 8209
- ✔ `distinct source ids (Stage B) = distinct classified ids (Stage C)`: 8209 = 8209
- ✔ `classified rows (Stage C) = distinct classified ids (one row per id)`: 8209 = 8209
- ✔ `study population (Stage B) = considered ids (Stage C)`: 5733 = 5733
- ✔ `study population (Stage B) = sum of change types`: 5733 = 5733
- ✔ `excluded ids in study (Stage B) = excluded`: 0 = 0
- ✔ `valid in both, in study, not excluded (Stage B) = moved + attribute_changed + shifted + unchanged`: 5444 = 5444
- ✔ `C_curr (Stage B) = added + matched`: 5733 = 5733
- ✔ `C_prev (Stage B) = removed + matched`: 5444 = 5444

## Changelog cross-check (contract §9)

| rule | checked | mismatches |
|---|---|---|
| added_is_changelog_added | 289 | 0 |
| removed_is_changelog_removed | 0 | 0 |
| moved_or_shifted_has_geometry_change | 185 | 0 |
| attribute_changed_has_attribute_change | 72 | 0 |
| changelog_unchanged_is_unchanged | 4839 | 0 |

Changelog type of ids in study: added 289, data_changed 605, unchanged 4839

## 10 largest moves

| id | previous name | current name | m | crossed AOI edge |
|---|---|---|---|---|
| `3b9e94f5-151c-4cf0-a7cd-d49e33bebca1` | African Bank - Shop L1/11 Sancardia | African Bank - Shop L1/11 Sancardia | 392.9 | False |
| `56a3cde7-6b7d-4e57-876c-3937f5dbb7f7` | Witbank Dam | Witbank Dam | 390.9 | True |
| `6fcd30f1-aa57-4457-a141-2be053dee912` | Gauteng Business Forum | Gauteng Business Forum | 342.6 | True |
| `82bdf66b-1246-4fad-9b74-b93b187884cd` | Tshwane Municipality | Tshwane Municipality | 341.1 | False |
| `5cacad8f-453b-43f9-9cce-186dbfa26bb1` | SACE Registration South Africa | SACE Registration South Africa | 316.6 | False |
| `72319b46-b6c9-4dff-813e-998821640af4` | Marie Stopes South Africa | Marie Stopes South Africa | 301.2 | False |
| `ece0ffde-a34f-4b79-8f00-cb151d25140c` | Shop N Save Online | Shop N Save Online | 292.7 | False |
| `7a3a6667-fb53-479e-9d04-b3751322b72c` | Opel | Opel | 287.3 | False |
| `1d97c139-ce58-4a26-ad5b-5613ae5f2e81` | National Agricultural Marketing Council | National Agricultural Marketing Council | 254.0 | True |
| `5c3d3abc-48b0-479d-abad-9fb155a34841` | Topflo | Topflo | 252.7 | False |

## Excluded rows (0)

None.
