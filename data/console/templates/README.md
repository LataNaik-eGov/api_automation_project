# Sample campaign templates

Drop a filled-in unified template here, one per campaign type:

    data/console/templates/BEDNET_sample.xlsx
    data/console/templates/MR-DN_sample.xlsx

Fall back for any type not listed:

    data/console/templates/sample.xlsx

Override the location entirely with `CONSOLE_SAMPLE_TEMPLATE` in `.env`.

## How the sample is used

The console generates an empty template per campaign: boundary rows are
pre-populated, data columns are blank. `utils/template_filler.py` reads the
sample, learns which value belongs in which column (matching on **header text**,
not column position), and writes that pattern into every data row of the
freshly generated template.

Boundary and code columns are never overwritten — the generated template's own
values are kept. See `PRESERVED_HEADER_FRAGMENTS` in `utils/template_filler.py`.

So the sample only needs **one** correctly filled data row. Everything else is
read from the generated file.

## Template layout (learned from the MR-DN unified template)

The generated workbook is **not** a flat header + data sheet. Structure:

    row 1   localization codes   MICROPLAN_PAYS, HCM_ADMIN_CONSOLE_FACILITY_NAME, ...
    row 2   display labels       Pays, Facility Name, ...   (localised)
    row 3+  data

`_header_row()` keys off **row 1 (the codes)**, not row 2. Codes are stable
across locales, so the same sample fills an `en_DEMO` and an `fr_DEMO`
template identically. Row 2 is detected and skipped — treating it as data was
a bug that made the filler learn the literal header text (writing `"Password"`
into every password cell).

Data sheets: `Facilities List`, `User List`, `Boundary List`.
Hidden sheets — `_h_SimpleLookup_h_`, `_h_Dropdowns_h_`, `_h_Meta_h_` — hold
dropdown sources and a per-generation meta id. They are skipped entirely
(`HIDDEN_SHEET_PATTERN`); filling them corrupts the workbook.

## What is never copied from the sample

Beyond `PRESERVED_HEADER_FRAGMENTS`, any column whose header starts with the
hierarchy prefix (`MICROPLAN_`) is preserved. Boundary level names are
localised — *Pays*, *Centre De Santé*, *SPP/SFD* — so no fixed word list
catches them; the prefix does.

Also preserved: `__ROW_ID` (per-generation row identifiers), `UserService
Uuids`, and `Username` / `Password`, which the user service mints on ingestion.
