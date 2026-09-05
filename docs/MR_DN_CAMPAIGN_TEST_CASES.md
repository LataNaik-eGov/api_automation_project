# MR-DN Campaign Flow — API Notes & Test Cases

Scope: **MR-DN only** (`CONSOLE_CAMPAIGN_TYPES=MR-DN`).
Environment: `hcm-demo.digit.org`, tenant `demo`, hierarchy `MICROPLAN`,
locale `en_DEMO`.
Verified against the campaign **`MR-DN_september_20260501`**, created through
the UI on 2026-09-05.

Automation: `tests/console/`, helpers in `utils/console.py` and
`utils/template_filler.py`.

```bash
pytest tests/console -v                       # whole console suite (MR-DN only)
pytest tests/console/test_upload_file.py -v   # template download -> fill -> upload
```

---

## 1. The campaign under test

Read back from `POST /project-factory/v1/project-type/search`:

| Field | Value |
|---|---|
| `campaignName` | `MR-DN_september_20260501` |
| `projectType` | `MR-DN` (Seasonal Malaria Chemoprevention) |
| `status` | `created` |
| `hierarchyType` | `MICROPLAN` |
| `boundaryCode` | `MICROPLAN_TC` (Tchad) |
| `beneficiaryType` | `INDIVIDUAL` |
| Dates | 06 Sep 2026 → 04 Oct 2026 (29 days) |
| Cycles (UI) | 3, multi-round |
| Resources (UI) | SP-250mg, AQ-75mg, SP-500mg, AQ-150mg |
| `boundaries` | 6 |
| `deliveryRules` | 1 |

**Discrepancy worth raising:** the UI shows *3 cycles*, but searching this
**created** campaign returns an empty
`additionalDetails.cycleData.cycleData` array (`deliveryRules` is present, with
its own `cycles`).

Note this is *not* the write bug in §3.5: on a **drafted** campaign, search
returns `cycleData` with all 3 entries intact. So cycleData survives the draft
steps and is absent once the campaign reaches `created` — it appears to be
dropped or migrated during finalization. Worth confirming with the platform
team whether that is intended.

Attached resource — the file downloaded and supplied as the sample:

```
type        unified-console-resources
filename    MR-DN_september_20260501_Microplan Template.xlsx
fileStoreId 6e366343-f73d-4ca3-a646-76cd2455543b
status      completed
```

Because that file is the *accepted* resource of a successfully created
campaign, it is now both:

- the fill pattern → `data/console/templates/MR-DN_sample.xlsx`
- the known-good end-to-end input → `CONSOLE_PREFILLED_FILESTORE_ID` in `.env`
  (previously blank, which silently skipped the E2E tests)

## 2. Template structure

`MR-DN_..._Microplan Template.xlsx` — 6 sheets:

| Sheet | Rows × Cols | Role |
|---|---|---|
| `Facilities List` | 1008 × 14 | facility master |
| `User List` | 1008 × 26 | field users + roles |
| `Boundary List` | 1003 × 12 | per-village SMC targets |
| `_h_SimpleLookup_h_` | 13 × 5 | hidden — cascading boundary lookup |
| `_h_Dropdowns_h_` | 15 × 5 | hidden — role/type dropdown sources |
| `_h_Meta_h_` | 1 × 1 | hidden — per-generation meta uuid |

Every data sheet uses a **two-row header band**:

```
row 1   MICROPLAN_PAYS   MICROPLAN_PROVINCE   HCM_ADMIN_CONSOLE_FACILITY_NAME   ...   <- localization codes
row 2   Pays             Province             Facility Name                     ...   <- display labels (localised)
row 3+  Tchad            LAC                  Chez chef village Kosserie F      ...   <- data
```

MR-DN-specific data columns:

- `Boundary List`: `TARGET_SMC_AGE_3_TO_11`, `TARGET_SMC_AGE_12_TO_59`,
  `TARGET_SMC_COLUUM_HOUSEHOLD`, `TARGET_SMC_COLUUM_PRODUCT`
  (the `COLUUM` spelling is the server's, not a typo here)
- `User List`: `USER_ROLE_MULTISELECT_1..5`, `EMPLOYMENT_TYPE`, plus
  server-minted `Username` / `Password` / `UserService Uuids`
- `Facilities List`: `FACILITY_CODE/NAME/TYPE/STATUS/CAPACITY/USAGE`

## 3. Bugs found and fixed

### 3.1 Filler read the label row as data — `utils/template_filler.py`

`_header_row()` picked the row with the most distinct strings. Rows 1 and 2
both have 26 distinct strings on `User List`, so row 1 won and `_fill_pattern`
then read **row 2 — the display-label row — as the first data row.**

The learned pattern was therefore the literal header text:

```
{'hcm_admin_console_user_name': 'Name', 'password': 'Password', ...}
```

Every generated template would have been filled with the word `"Name"` in the
name column and `"Password"` in the password column, then uploaded.

**Fix:** detect the header band explicitly. `_is_code_row()` recognises the
localization-code row (≥60% of cells matching `^[A-Z0-9][A-Z0-9_/#.\-]*$`);
the following non-code text row is recognised as labels and skipped.
`_header_row()` now returns `(header_row, headers, data_start)`.

Matching is keyed on **row 1 codes, not row 2 labels** — codes are locale-
stable, so one sample fills an `en_DEMO` and an `fr_DEMO` template alike.

### 3.2 Boundary columns were overwritten — `utils/template_filler.py`

`PRESERVED_HEADER_FRAGMENTS` matched on English words (`province`, `district`,
`village`, `country`). The MICROPLAN hierarchy is **French**: `Pays`,
`Centre De Santé`, `SPP/SFD`. Those three matched nothing and were copied from
the sample into every row, overwriting the generated file's real boundaries.

`__ROW_ID` (per-row uuid) and `Username`/`Password`/`UserService Uuids`
(minted by the user service on ingestion) were also being copied.

**Fix:** preserve any header starting with the hierarchy prefix
(`MICROPLAN_`), since boundary labels are localised and no word list can catch
them; added `__row_id`, `uuid(s)`, `username`, `password` to the fragments.

Preserved on `Facilities List` before → after the fix:

```
before  boundary_code, facility_code, district, province, village/quartier          (5)
after   + pays, centredesanté, spp/sfd, __row_id                                     (9)
```

### 3.3 Hidden sheets were being filled — `utils/template_filler.py`

`fill_template()` looped over every sheet, so `_h_Dropdowns_h_` and
`_h_SimpleLookup_h_` were treated as data and overwritten with a learned
pattern — corrupting the dropdown sources and the cascading boundary lookup.

**Fix:** `HIDDEN_SHEET_PATTERN = ^_h_.*_h_$`; those sheets are skipped.

### 3.4 `APIClient.upload_file()` did not exist — `utils/api_client.py`

`utils/console.py:664` called `client.upload_file(...)`, which was never
implemented. Every test touching the filestore died with
`AttributeError: 'APIClient' object has no attribute 'upload_file'` — 5 of 9
`test_upload_file.py` tests.

**Fix:** implemented multipart upload. The class-level
`Content-Type: application/json` header must be dropped so `requests` can set
`multipart/form-data` with its own boundary; sending the JSON header returns
400 from the filestore. Verified live: `201` with a real `fileStoreId`.

### 3.5 `/update` returns a CampaignDetails that omits what it just wrote — **product issue**

`POST /project-factory/v1/project-type/update` answers **200 `successful`**
with a `CampaignDetails` that drops `deliveryRules`,
`additionalDetails.cycleData` **and** `resources` — even though all three are
persisted correctly. Only `/project-type/search` reflects the written state.

Measured on a single MR-DN draft:

| Field | Sent | In the *update response* | On *search* |
|---|---|---|---|
| `deliveryRules` | 1 | **0** | 1 |
| `cycleData` | 3 | **0** | 3 |
| `resources` | 1 | **0** (after a generation) | 1 |

For `resources` the omission was reproduced with the generated file, a
re-uploaded copy, the generation's own `fileStoreId`, and a freshly re-read
campaign object — all four give `[]` in the response and the correct resource
on search.

**Impact:** any client trusting the update response concludes the write failed.
A retry would double-attach the resource. This single defect accounted for
**3 of the 18** failures in the MR-DN run — they were test-side trust in the
write response, not broken functionality.

**Test-side fix:** `test_upload_template_and_attach_to_campaign`,
`test_create_campaign_end_to_end`, `test_configure_delivery_rules` and
`test_delivery_rules_cycle_data_matches_cycles` now assert against the read
model, and report what the update returned when they fail.

### 3.6 project-factory accepts invalid input — **product issue, pre-existing**

A cluster of negative tests fail because
`POST /project-factory/v1/project-type/update` answers **`200 successful`**
for input the console UI refuses. Confirmed on the MR-DN run:

| Test | Input that was accepted |
|---|---|
| `test_boundary_selection_without_any_selection` | no boundaries at all |
| `test_boundary_selection_with_partial_selection` | partial hierarchy path |
| `test_boundary_selection_missing_lowest_level` | path stopping above the leaf |
| `test_boundary_selection_with_unknown_code` | a boundary code that does not exist |
| `test_delivery_rules_with_invalid_input` | non-numeric quantity |
| `test_delivery_rules_with_zero_input` | zero quantity |
| `test_delivery_rules_with_empty_input` | blank quantity |
| `test_delivery_rules_without_any_dates` | no cycle dates |
| `test_delivery_rules_with_first_start_date_only` | only the first start date |

These are **pre-existing** — the corresponding files were already in
`output/failed_requests/` before any change in this session. Validation lives
only in the UI; the API accepts the same payloads. Anything driving the API
directly (this suite, a bulk import, a script) can create malformed campaigns.

Worth raising with the platform team as a single item: *server-side validation
is missing on the campaign update endpoint.*

### 3.7 App config master is cross-tenant — **environment issue**

`HCM.APP_CONFIG` has exactly one record on hcm-demo, stored under
`tenantId: demo` but carrying `uniqueIdentifier: "mz"` and `data.TENANT_ID:
"mz"`. Writing it back returns **401 "You are not authorized to access this
resource"**, so `test_app_configuration_toggle_off` cannot pass. The record
appears to be a leftover from the `mz` tenant. Also pre-existing.

### 3.8 Filled template produced a functionally empty campaign — **automation bug**

The E2E passed while creating a campaign with **zero project facilities and
zero staff**. It was only visible by comparing against a UI-created campaign:

| Campaign | Projects | Facilities | Staff |
|---|---|---|---|
| UI-created `CMP-2026-09-05-004696` | 6 | 6 | 6 |
| Automation, before fix `CMP-2026-09-05-004766` | 6 | **0** | **0** |
| Automation, after fix `CMP-2026-09-05-004779` | 6 | **6** | **6** |

Two causes in `utils/template_filler.py`:

1. **Facilities arrived `Inactive`.** The generated template pre-populates
   `HCM_ADMIN_CONSOLE_FACILITY_USAGE = "Inactive"`; the sample says `Active`.
   The filler only wrote into *empty* cells, so it never flipped them and no
   facility was attached to the campaign. Fixed with
   `OVERWRITE_HEADER_FRAGMENTS = ("usage",)` — the columns where the sample's
   value must replace a populated one, mirroring the choice a user makes in the
   UI.

2. **`User List` is generated empty** — two header rows and nothing else
   (`max_row == 2`). The filler only fills rows that already exist, so the
   sample's users were never carried over. `_copy_rows()` now copies the
   sample's rows wholesale into a sheet that has none; with no generated data
   present there is nothing to preserve, so every column is copied.

A third issue surfaced while fixing these: on a two-row sheet the
display-label row was being detected as data. The target's first data row is
now derived from the sample's header-band offset
(`target_header_row + (source_data_start - source_header_row)`) instead of
being re-detected — both files come from the same generator, so the band shape
is identical, and an empty sheet gives detection nothing to work with.

Net effect on a real generated template: **13 rows filled, up from 1.**

**Lesson for the suite:** "campaign reaches `created`" is too weak an
assertion. `test_search_project_facilities` and `test_search_project_staff`
are what actually catch an empty campaign — they are the real end-to-end
guard.

## 4. Test cases

### Template generation & download

| ID | Type | Case | Expected |
|---|---|---|---|
| MRDN-01 | P | Generate template for MR-DN | `/excel-ingestion` generation reaches `completed` |
| MRDN-02 | P | Download generated template | 200; non-empty `.xlsx`; opens with openpyxl |
| MRDN-03 | P | Generated template has the expected sheets | `Facilities List`, `User List`, `Boundary List` present |

### Template filling (`utils/template_filler.py`)

| ID | Type | Case | Expected |
|---|---|---|---|
| MRDN-10 | P | Header band detected | header row = 1 (codes), data starts row 3 |
| MRDN-11 | P | Pattern is real data, not labels | learns `WHM1` / `9009000001`, never `"Name"` / `"Password"` |
| MRDN-12 | P | Boundary columns preserved | `Pays`, `Centre De Santé`, `SPP/SFD`, `MICROPLAN_*` keep the generated values |
| MRDN-13 | P | Identifiers preserved | `__ROW_ID`, `UserService Uuids`, `Username`, `Password` untouched |
| MRDN-14 | P | Hidden sheets untouched | `_h_*_h_` byte-identical after fill |
| MRDN-15 | P | SMC target columns filled | all four `TARGET_SMC_*` populated on every boundary row |
| MRDN-16 | P | Round trip | blank a generated template → fill → all data columns populated, preserved columns unchanged |

### Filestore upload

| ID | Type | Case | Expected |
|---|---|---|---|
| MRDN-20 | P | Upload filled template | 201; `files[0].fileStoreId` returned |
| MRDN-21 | N | Upload non-xlsx | rejected by validation |
| MRDN-22 | N | Upload corrupt workbook | rejected by validation |
| MRDN-23 | N | Upload template with invalid data | validation reports row-level errors |

### Validation & campaign attach

| ID | Type | Case | Expected |
|---|---|---|---|
| MRDN-30 | P | Filled template passes validation | process status `completed`, no errors |
| MRDN-31 | P | Attach resource to campaign | resource appears with `status: completed` |
| MRDN-32 | P | Campaign reaches `created` | search returns `status=created` |

## 5. Open items

- **Cycle data does not persist** (§1). Raise with the platform team — the
  UI reports 3 cycles, the API returns an empty `cycleData` array.
- **`/update` omits persisted resources** (§3.5). Raise with the platform team.
  Treat the update response as write-only; read state back via search.
- **No server-side validation on campaign update** (§3.6). Nine negative tests
  document it. Raise as one platform item.
- **Cross-tenant app config record** (§3.7). Needs an env fix before
  `test_app_configuration_toggle_off` can pass.
- The sample carries only one filled row per sheet, which is all the filler
  needs. If MR-DN later requires *varying* targets per village, the
  one-pattern-for-all-rows approach will need per-boundary values.
- `TARGET_SMC_COLUUM_*` is misspelled server-side; if that is ever corrected,
  the fill still works (it matches on whatever code the template carries) but
  these notes will be stale.
