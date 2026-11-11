"""Fill a freshly generated campaign template using a sample as the pattern.

The console generates an empty unified template per campaign: the boundary rows
are pre-populated, the data columns are blank. Validation only passes once those
columns are filled in.

Rather than pinning a single pre-uploaded filestoreId — which rots the moment
the boundary data or template version changes — this module takes a sample
template that a human filled in once, learns which value goes in which column,
and applies that pattern to whatever the environment just generated.

Columns are matched by header text, not position, so the fill survives column
reordering and additions.
"""

import os
import random
import re
import shutil
import uuid

from utils.config import consoleHierarchyType, consoleSampleTemplate, tenantId

# Identifiers minted per generation. Copying these across templates makes the
# upload collide with itself, so the generated file's own value always wins.
# Matched on the header's last underscore-segment, or exactly — a substring
# test on "code" also swallows USER_BANK_CODE and USER_BENEFICIARY_CODE, which
# are ordinary data columns a human may fill in the sample.
PRESERVED_HEADER_SUFFIXES = (
    "boundary_code",
    "facility_code",
    "____row_id",
    "row_id",
)

# Columns regenerated fresh on every fill rather than taken from the sample.
# The user's phone number is their identity in the user service: reusing the
# sample's numbers across runs collides with the users a previous run already
# created. Matched on the header's last segment — deliberately NOT the payee
# phone, which is a payment recipient rather than a login identity.
GENERATED_PHONE_SUFFIXES = ("user_phone_number",)

# Credentials and service ids the user service mints on ingestion.
PRESERVED_HEADER_EXACT = (
    "username",
    "password",
    "userservice uuids",
)

# Boundary-level columns are prefixed with the hierarchy code
# (e.g. MICROPLAN_PAYS, MICROPLAN_CENTREDESANTE). Their names are localised —
# "Pays", "Centre De Santé", "SPP/SFD" — so no fixed fragment list can catch
# them. Match on the hierarchy prefix instead.
_HIERARCHY_PREFIX = f"{(consoleHierarchyType or '').strip().lower()}_" if consoleHierarchyType else ""

# Columns where the sample's value must REPLACE the generated one rather than
# only fill a blank. The console pre-populates facility/user rows with
# "Inactive"; marking them active for the campaign is exactly the decision the
# sample encodes. Without this the campaign is created with zero project
# facilities and zero staff.
OVERWRITE_HEADER_FRAGMENTS = ("usage",)

# A header row of localization codes: ALL-CAPS tokens, no lower-case letters.
# The unified template stacks two header rows — codes on the first, the
# localised display labels on the second — with data starting on the third.
_CODE_HEADER = re.compile(r"^[A-Z0-9][A-Z0-9_/#.\-]*$")


def _is_generated_phone(header):
    return header.endswith(GENERATED_PHONE_SUFFIXES)


def _unique_phone(used):
    """A 10-digit number starting with 9, unique within this fill.

    Drawn from 9_000_000_000-9_999_999_999 rather than counting up from the
    sample, so two runs do not hand the user service the same numbers.
    """
    while True:
        candidate = random.randint(9_000_000_000, 9_999_999_999)
        if candidate not in used:
            used.add(candidate)
            return candidate


def _openpyxl():
    try:
        import openpyxl
    except ImportError as exc:  # pragma: no cover - dependency guard
        raise RuntimeError(
            "openpyxl is required to fill campaign templates. "
            "Install it with: pip install -r requirements.txt"
        ) from exc
    return openpyxl


def sample_template_path(campaign_type):
    """Locate the sample template for a campaign type.

    Looks for, in order:
      1. CONSOLE_SAMPLE_TEMPLATE (exact path, if set)
      2. data/console/templates/<CAMPAIGN_TYPE>_sample.xlsx
      3. data/console/templates/sample.xlsx
    """
    if consoleSampleTemplate and os.path.exists(consoleSampleTemplate):
        return os.path.abspath(consoleSampleTemplate)

    base = os.path.join(os.path.dirname(__file__), "..", "data", "console", "templates")
    candidates = [
        os.path.join(base, f"{campaign_type}_sample.xlsx"),
        os.path.join(base, f"{campaign_type.replace('-', '_')}_sample.xlsx"),
        os.path.join(base, "sample.xlsx"),
    ]
    for candidate in candidates:
        if os.path.exists(candidate):
            return os.path.abspath(candidate)
    return None


def _row_headers(sheet, row_index):
    """{header text (lower-cased): column index} for one row."""
    headers = {}
    for column_index in range(1, sheet.max_column + 1):
        value = sheet.cell(row=row_index, column=column_index).value
        if isinstance(value, str) and value.strip():
            headers[value.strip().lower()] = column_index
    return headers


def _is_code_row(sheet, row_index):
    """True when a row holds localization codes rather than display labels."""
    values = [
        sheet.cell(row=row_index, column=c).value.strip()
        for c in range(1, sheet.max_column + 1)
        if isinstance(sheet.cell(row=row_index, column=c).value, str)
        and sheet.cell(row=row_index, column=c).value.strip()
    ]
    if not values:
        return False
    matches = sum(1 for v in values if _CODE_HEADER.match(v))
    return matches >= len(values) * 0.6


def _header_row(sheet, max_scan=10):
    """(header row index, header map), or (None, {}) if there is no header.

    The unified template uses a two-row header band: localization codes on the
    first row, localised display labels on the second, data from the third.
    Codes are matched on rather than labels because they are stable across
    locales — the same template in fr_DEMO carries identical codes.
    """
    for row_index in range(1, min(sheet.max_row, max_scan) + 1):
        if not _is_code_row(sheet, row_index):
            continue
        headers = _row_headers(sheet, row_index)
        if headers:
            return row_index, headers
    return None, {}


def _band_height(sheet, header_row):
    """Rows occupied by the header band: 1 for codes only, 2 with labels.

    Only ever measured on the sample, which is guaranteed to have data rows.
    A generated sheet can be entirely empty (the User List is two header rows
    and nothing else), which gives detection nothing to go on — hence the
    sample's band is applied to both files. Both come from the same generator,
    so the shape is identical.
    """
    label_row = header_row + 1
    if label_row <= sheet.max_row and not _is_code_row(sheet, label_row):
        if _row_headers(sheet, label_row):
            return 2
    return 1


def _is_overwritable(header):
    """True when the sample's value should win over a populated generated cell."""
    return any(fragment in header for fragment in OVERWRITE_HEADER_FRAGMENTS)


def _is_preserved(header):
    """True when the generated template's own value must win.

    Covers boundary hierarchy columns (matched on the hierarchy prefix, since
    their labels are localised), generated row identifiers and credentials.
    """
    if _HIERARCHY_PREFIX and header.startswith(_HIERARCHY_PREFIX):
        return True
    if header in PRESERVED_HEADER_EXACT:
        return True
    return header.endswith(PRESERVED_HEADER_SUFFIXES)


def _fill_pattern(sheet, data_start, headers):
    """The first filled-in data row, as {header: value}.

    Preserved columns are excluded, so only user-entered values are learnt.
    """
    for row_index in range(data_start, sheet.max_row + 1):
        pattern = {}
        for header, column_index in headers.items():
            if _is_preserved(header):
                continue
            value = sheet.cell(row=row_index, column=column_index).value
            if value not in (None, ""):
                pattern[header] = value
        if pattern:
            return pattern
    return {}


def _data_rows(sheet, data_start, headers):
    """Row indices that carry any value in a header column."""
    return [
        r for r in range(data_start, sheet.max_row + 1)
        if any(sheet.cell(row=r, column=c).value not in (None, "") for c in headers.values())
    ]


def _copy_rows(target, target_headers, target_data_start,
               source, source_headers, source_rows, used_phones):
    """Append the sample's rows wholesale to an empty generated sheet.

    Used when the console generates a sheet with no rows at all (the User List
    is empty on a fresh template). Boundary columns ARE copied here — unlike
    the fill path there is no generated value to preserve — but per-generation
    row ids and the credentials the user service mints are still skipped, or
    the upload collides with itself.
    """
    written = 0
    for offset, source_row in enumerate(source_rows):
        target_row = target_data_start + offset
        wrote_any = False
        for header, source_col in source_headers.items():
            target_col = target_headers.get(header)
            if target_col is None:
                continue
            if header in PRESERVED_HEADER_EXACT or header.endswith(PRESERVED_HEADER_SUFFIXES):
                continue
            value = source.cell(row=source_row, column=source_col).value
            if value in (None, ""):
                continue
            if _is_generated_phone(header):
                value = _unique_phone(used_phones)
            target.cell(row=target_row, column=target_col).value = value
            wrote_any = True
        if wrote_any:
            written += 1
    return written


def fill_template(generated_path, sample_path, output_path=None):
    """Apply the sample's values to every data row of the generated template.

    Returns (output_path, rows_filled). Only cells that are empty in the
    generated template are written, so pre-populated boundary data is untouched.
    """
    openpyxl = _openpyxl()

    if output_path is None:
        directory = os.path.dirname(generated_path)
        stem = os.path.splitext(os.path.basename(generated_path))[0]
        output_path = os.path.join(directory, f"{stem}_filled_{uuid.uuid4().hex[:6]}.xlsx")

    shutil.copyfile(generated_path, output_path)

    generated = openpyxl.load_workbook(output_path)
    sample = openpyxl.load_workbook(sample_path, data_only=True)

    sample_sheets = {name.strip().lower(): name for name in sample.sheetnames}
    rows_filled = 0
    # Which OVERWRITE_HEADER_FRAGMENTS actually matched a column. A fragment
    # that matches nothing means the console renamed the column and the
    # overwrite silently became a no-op — which is exactly how the
    # zero-facilities/zero-staff bug looked: rows_filled stays > 0, validation
    # still passes, and the campaign is created empty. Fail loudly instead.
    matched_overwrites = set()
    # Phone numbers are unique per fill, so the set spans every sheet.
    used_phones = set()

    for sheet_name in generated.sheetnames:
        # Hidden sheets hold dropdown sources and a per-generation meta id.
        # Filling them corrupts the workbook. The workbook marks them hidden,
        # so read that rather than matching the _h_..._h_ naming convention —
        # a future hidden sheet under a different name is still skipped.
        if generated[sheet_name].sheet_state != "visible":
            print(f"  sheet '{sheet_name}': skipped (hidden lookup/meta sheet)")
            continue

        sample_name = sample_sheets.get(sheet_name.strip().lower())
        if not sample_name:
            continue

        target = generated[sheet_name]
        source = sample[sample_name]

        source_header_row, source_headers = _header_row(source)
        target_header_row, target_headers = _header_row(target)
        if not source_header_row or not target_header_row:
            continue

        band = _band_height(source, source_header_row)
        source_data_start = source_header_row + band
        target_data_start = target_header_row + band

        # An empty generated sheet (no rows at all) cannot be "filled" — the
        # sample's rows have to be carried over instead, or the campaign is
        # created with none of that entity (e.g. no staff at all).
        target_rows = _data_rows(target, target_data_start, target_headers)
        if not target_rows:
            source_rows = _data_rows(source, source_data_start, source_headers)
            if source_rows:
                copied = _copy_rows(
                    target, target_headers, target_data_start,
                    source, source_headers, source_rows, used_phones,
                )
                rows_filled += copied
                print(f"  sheet '{sheet_name}': generated empty, copied {copied} row(s) from sample")
            continue

        pattern = _fill_pattern(source, source_data_start, source_headers)
        if not pattern:
            continue

        writable = {
            header: column_index
            for header, column_index in target_headers.items()
            if header in pattern
        }
        if not writable:
            continue

        for row_index in target_rows:
            wrote_any = False
            for header, column_index in writable.items():
                cell = target.cell(row=row_index, column=column_index)
                matched_overwrites.update(
                    f for f in OVERWRITE_HEADER_FRAGMENTS if f in header
                )
                if cell.value in (None, "") or _is_overwritable(header):
                    # One sample value broadcast across every row would give
                    # them all the same phone number; generate per row instead.
                    new_value = (
                        _unique_phone(used_phones)
                        if _is_generated_phone(header)
                        else pattern[header]
                    )
                    if cell.value != new_value:
                        cell.value = new_value
                        wrote_any = True
            if wrote_any:
                rows_filled += 1

        print(
            f"  sheet '{sheet_name}': filled {len(writable)} column(s) "
            f"from pattern {sorted(writable)}"
        )

    unmatched = set(OVERWRITE_HEADER_FRAGMENTS) - matched_overwrites
    assert not unmatched, (
        f"Overwrite fragment(s) {sorted(unmatched)} matched no column in "
        f"{os.path.basename(generated_path)}. The console has probably renamed "
        f"the column — without it the campaign is created with no project "
        f"facilities and no staff. Update OVERWRITE_HEADER_FRAGMENTS."
    )

    generated.save(output_path)
    print(f"  filled {rows_filled} row(s) -> {output_path}")
    return output_path, rows_filled


def fill_generated_template(generated_path, campaign_type):
    """Convenience wrapper: locate the sample for a campaign type and apply it.

    Returns (output_path, rows_filled), or (None, 0) when no sample is available.
    """
    sample_path = sample_template_path(campaign_type)
    if not sample_path:
        return None, 0

    print(f"  filling template for {campaign_type} ({tenantId}) from {sample_path}")
    return fill_template(generated_path, sample_path)
