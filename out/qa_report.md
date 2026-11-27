# GeoTrustOps QA report

Releases: `2026-10-21.0` → `2026-11-18.0` · shifted > 5.0 m · moved > 25.0 m · major > 100.0 m · contract v0.4

> Map-record changes between two Overture releases. added != opened, removed != closed, moved/shifted != the earlier position was wrong, a rename kind != better or worse.

## Provenance

- Pipeline `1.0.0` · contract `v0.4`
- AOI: {'west': 28.168, 'south': -25.758, 'east': 28.205, 'north': -25.732}
- Extraction bbox (AOI + buffer): {'west': 28.157999999999998, 'south': -25.768, 'east': 28.215, 'north': -25.721999999999998}
- Input sha256: prev `f69ec5ca48f04a6564952f76eb0ea78c1c6a85086da7f440e863862c076fe1c8` · curr `ea1a5c837dde146147db6540c60c617c68b6b2d0817a02953646f43e7055358e`
- Changelog sha256: `a6f6f00fd5767b4e412b53525fe85d7274b68251e9ddd518bbdf4d70e7c51fb5`

## Inputs

| | prev | curr |
|---|---|---|
| rows in extraction (AOI + buffer) | 8209 | 8189 |
| valid rows | 8209 | 8189 |
| excluded: `missing_id` | 0 | 0 |
| excluded: `duplicate_id` | 0 | 0 |
| excluded: `missing_geometry` | 0 | 0 |
| excluded: `non_point_geometry` | 0 | 0 |
| excluded: `invalid_coordinates` | 0 | 0 |

Ids: 8517 in extraction, 5967 in study, 2550 buffer-only (ignored).

## Change types (ids in study)

| type | count |
|---|---|
| excluded | 0 |
| added | 232 |
| removed | 228 |
| moved | 178 |
| attribute_changed | 49 |
| shifted | 109 |
| unchanged | 5171 |

| move band (matched ids) | count |
|---|---|
| stable | 5211 |
| minor | 118 |
| material | 108 |
| major | 70 |

| flag | count |
|---|---|
| name_changed | 41 |
| name_matches_brand | 4 |
| category_changed | 50 |
| basic_category_changed | 38 |
| status_changed | 1 |
| confidence_to_zero | 0 |
| crossed_aoi_boundary | 7 |

| enrichment field changed (addresses after region normalisation) | count |
|---|---|
| addresses | 259 |
| brand | 80 |
| emails | 41 |
| phones | 49 |
| socials | 47 |
| websites | 437 |

| format-only change (raw differs, normalised equal; not counted above) | count |
|---|---|
| addresses | 4450 |
| phones | 314 |

## Renames by kind (kind describes the edit, not its quality)

| kind | count |
|---|---|
| added | 0 |
| removed | 0 |
| case_or_spacing | 3 |
| punctuation | 0 |
| expanded_or_trimmed | 24 |
| different | 14 |

| kind | id | previous | current | = brand |
|---|---|---|---|---|
| case_or_spacing | `09127cce-cef3-4e64-b8a2-849a52ae7a8c` | Pretoria School for Cerebral Palsied Learners | Pretoria School For Cerebral Palsied Learners | False |
| case_or_spacing | `7859fe37-37fe-4efc-be44-0d64317eb769` | Mkoni Printers | Mkoni printers | False |
| case_or_spacing | `dd792f22-e2ff-4e6f-be33-639af11b8f60` | Dazzling Smile Dental | Dazzling smile dental | False |
| different | `080d5470-42ec-4897-a026-4d09715ddecc` | Topaz Disco CC | Topaz Disco PRETORIA, Gauteng | False |
| different | `28d1c2d4-6120-4b2b-a298-adad47117130` | Police Clearance Certificate | Police Clearance South Africa | False |
| different | `458a07a2-b4a5-4492-a5db-aa86c3de0412` | Mo_nails | Mo nails and beauty bar | False |
| different | `48deb8a6-4660-4808-bcfb-24f01b1840fa` | Eduflex Online Tutors | Eduflex College | False |
| different | `5db26b3a-5d27-40cb-89e7-75a790b098e7` | Guleti mncube | Guleti kibooko bigoondo khumalo | False |
| different | `7a4a5790-4527-4941-be93-4d132e16c42d` | Wilfred Heinrich Optometrist | Wilfred S Heinrich Optometrist | False |
| different | `89494bd8-1e95-4e45-ac11-7ec90203d2f2` | GoTyme Bank Customer Kiosk Pretoria Local Office | GoTyme Bank Kiosk | False |
| different | `8e0b261a-b24f-4802-8988-da321557a34d` | SAPS Pretoria Central Police Station | SAPS Central Pretoria | False |
| different | `99ab3847-9176-4f99-ae22-d056bf276898` | Shabhac Construction (pty) Ltd | Shabhac Construction & Development | False |
| different | `b99e7a65-0aa2-4ac7-a494-fd936a86dc00` | Tshwane Hub of Arts - THOA | Tshwane Arts and Craft Hub | False |
| different | `c2a653a9-6002-4a83-9dac-de0e8931167e` | Department of Environmental Affairs | Department of Forestry, Fisheries and the Environment | False |
| different | `d4ebe049-0747-47b2-84f8-9c8c3af0f835` | Sefike Attorneys Incoporated | Sefike Attorneys Incorporated | False |
| different | `ebc972a0-0170-4faf-94f9-dde17bbba746` | LEO's PLACE | Leos Place Apartments - Arcadia. | False |
| different | `fe3575b7-ad5c-4c02-8df4-f51031005b24` | Lebzsecurity academy school474 | LEBZ Security | False |
| expanded_or_trimmed | `025a06e8-b713-4b9d-89d0-3b94f7302fbc` | Kfc Pretoria (Pretorius Street) | KFC | True |
| expanded_or_trimmed | `19b598de-b91b-47e0-b831-327533f589e4` | Mr Price Cellular Pta | Mr Price | True |
| expanded_or_trimmed | `2022708f-1e93-4c61-8e09-9b1c09eaabdf` | PG Glass | PG Glass Pretoria CBD | False |
| expanded_or_trimmed | `28fc0aff-1719-42e2-8202-58bbf1e4abdc` | McDonald's Sammy Marks | McDonald's | True |
| expanded_or_trimmed | `3031f185-58e2-4ce6-b866-70b8714a0256` | Old Mutual Finance | Old Mutual | False |
| expanded_or_trimmed | `44646daa-883c-49e5-96a8-e339ea87e179` | Oriental Palace | Oriental palace restaurant | False |
| expanded_or_trimmed | `51b3d327-1fe2-4c3e-8c4e-b09d15d669c5` | Kingdom Blue Funeral Service | Kingdom Blue | False |
| expanded_or_trimmed | `53336e30-6dcc-4e34-bd88-72f9265d07be` | Pharmacy at SPAR | Pharmacy at SPAR Louis Pasteur | False |
| expanded_or_trimmed | `54616ab0-5d7c-4d98-9630-3582bbb7e716` | Shoprite Van Der Walt Street | Shoprite | False |
| expanded_or_trimmed | `5b709d63-321c-45f2-a160-8b848b23d110` | AVBOB | AVBOB South Africa | False |
| expanded_or_trimmed | `6ace4889-d283-46e8-8b1d-2b4f4ea3eccb` | Mugg & Bean On The Move | Mugg & Bean On The Move One on Mutual | False |
| expanded_or_trimmed | `72b9dda4-08ee-4019-9884-c8f5df1ccf00` | LEGiT | Legit - Pretoria Church | False |
| expanded_or_trimmed | `8e582afe-9ce5-4128-9ad3-f4b6d4571a4a` | Zonefitness Gym- Sancardia | Zonefitness | False |
| expanded_or_trimmed | `8f45a3da-803f-4958-a6e3-6b584a0a1b41` | Clicks Pharmacy Sharon's Place | Clicks | True |
| expanded_or_trimmed | `a59b7770-5c7d-461e-b8c1-93c2d7d63b43` | Nu Metro | Nu Metro Sunnypark | False |
| expanded_or_trimmed | `af94dbda-def3-4d24-8b06-15412a45f453` | adidas Outlet Store JHB, Festival Mall | Adidas Outlet | False |
| expanded_or_trimmed | `b353b605-daf2-4c73-8a2a-40637df1b827` | Fabiani | Fabiani - Sammy Marks | False |
| expanded_or_trimmed | `baf792a6-3e54-4f44-bf1d-df13f5d3a967` | Pavilion | Pavilion Parkade | False |
| expanded_or_trimmed | `bd0c910b-a0e7-4d64-8d4c-42bd65c2de5f` | Highbury College | Highbury College – Main Campus | False |
| expanded_or_trimmed | `ccb9ce8e-acfe-4d29-9f8b-f51bfe46cd20` | Triple Hand Auto | Triple Hand Auto - Mobile | False |
| expanded_or_trimmed | `d800a79c-d892-4501-9e0d-ed3beddfd180` | Steers Pretoria Central | Steers | False |
| expanded_or_trimmed | `e9d40e52-f94e-4bfe-82fd-1b428e632035` | Tip N Tip Store | Tip N Tip | False |
| expanded_or_trimmed | `f1cb9f53-7cc8-4c83-a147-1f8753472553` | Silent Night Guest House Sunnyside Pretoria - Superior Queen Room | Silent Night Guest House Sunnyside Pretoria | False |
| expanded_or_trimmed | `f7a26bf6-ac47-4f13-96d2-faaded3949b8` | Dr Ifeanyi Wosu | Dr Ifeanyi Wosu Inc | False |

## Lifecycle changes (1)

- `af94dbda-def3-4d24-8b06-15412a45f453` Adidas Outlet: status open → None, confidence 0.99 → 0.8

## Reconciliation

- ✔ `R_prev = V_prev + X_prev`: 8209 = 8209
- ✔ `R_curr = V_curr + X_curr`: 8189 = 8189
- ✔ `distinct source ids (Stage B) = distinct classified ids (Stage C)`: 8517 = 8517
- ✔ `classified rows (Stage C) = distinct classified ids (one row per id)`: 8517 = 8517
- ✔ `study population (Stage B) = considered ids (Stage C)`: 5967 = 5967
- ✔ `study population (Stage B) = sum of change types`: 5967 = 5967
- ✔ `excluded ids in study (Stage B) = excluded`: 0 = 0
- ✔ `valid in both, in study, not excluded (Stage B) = moved + attribute_changed + shifted + unchanged`: 5507 = 5507
- ✔ `C_curr (Stage B) = added + matched`: 5739 = 5739
- ✔ `C_prev (Stage B) = removed + matched`: 5735 = 5735

## Changelog cross-check (contract §9)

| rule | checked | mismatches |
|---|---|---|
| added_is_changelog_added | 232 | 0 |
| removed_is_changelog_removed | 228 | 0 |
| moved_or_shifted_has_geometry_change | 287 | 0 |
| attribute_changed_has_attribute_change | 49 | 0 |
| changelog_unchanged_is_unchanged | 786 | 0 |

Changelog type of ids in study: added 232, data_changed 4721, removed 228, unchanged 786

## 10 largest moves

| id | previous name | current name | m | crossed AOI edge |
|---|---|---|---|---|
| `58f10dd9-dc2d-4f8e-bf0a-ef4b8f7d93f3` | Video Galore Nedbank Plaza | Video Galore Nedbank Plaza | 418.4 | False |
| `56a3cde7-6b7d-4e57-876c-3937f5dbb7f7` | Witbank Dam | Witbank Dam | 404.1 | True |
| `ded56f61-90cf-4b29-a4c0-428964258058` | Dansa International College | Dansa International College | 388.4 | False |
| `0317c89d-83eb-4b38-95cc-b044cfc89840` | Downtown-Amaros | Downtown-Amaros | 388.3 | False |
| `9955d5eb-fef2-42d3-9e3b-4544b372179c` | Ever Increasing Word Pre School & Creche | Ever Increasing Word Pre School & Creche | 386.5 | True |
| `3f2214d1-3928-456a-a8cc-aee52722e26a` | SA Automotors | SA Automotors | 375.4 | False |
| `76ab0c05-cc76-45be-ab8a-c31099712988` | Central Business District | Central Business District | 372.3 | False |
| `65a88302-476b-46fc-b08c-a9986823e084` | Chwayi Beauty Salon & Accessories | Chwayi Beauty Salon & Accessories | 370.8 | False |
| `d640789d-6bd8-4001-90f8-e6d8a8f6e1b2` | QuickFix Tech Solutions | QuickFix Tech Solutions | 362.7 | False |
| `33d21ab2-870c-4ae2-a542-41b1ffcb1ba5` | CBD Pretoria Central | CBD Pretoria Central | 359.4 | False |

## Excluded rows (0)

None.
