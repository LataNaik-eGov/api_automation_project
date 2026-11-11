"""Upload file step — template generation, upload and validation.

API counterpart of UploadFileTest in the Playwright console suite.

The console generates a unified template for the campaign, the user fills it in
and uploads it, and excel-ingestion validates it asynchronously. The negatives
below feed that pipeline the same bad inputs the UI blocks: no file, the wrong
file type, a corrupt workbook, and a workbook with invalid data in it.
"""

import os
import uuid
import zipfile

import pytest

from utils.config import consoleResourceType, prefilled_filestore_id
from utils.console import (
    assert_rejected,
    download_to_disk,
    finalize_campaign,
    generate_template,
    get_download_url,
    search_process,
    update_boundaries,
    update_delivery_rules,
    update_resources,
    fetch_campaign,
    upload_to_filestore,
    validate_process,
    wait_for_generation,
    wait_for_process,
)
from utils.template_filler import fill_generated_template


# --- Fixture files ----------------------------------------------------------

def _scratch_dir():
    path = os.path.join(os.path.dirname(__file__), "..", "..", "output", "console")
    os.makedirs(path, exist_ok=True)
    return os.path.abspath(path)


def _write(filename, content, mode="wb"):
    path = os.path.join(_scratch_dir(), filename)
    with open(path, mode) as f:
        f.write(content)
    return path


def make_wrong_type_file():
    """A plain text file masquerading as a campaign upload."""
    return _write(
        f"not_a_template_{uuid.uuid4().hex[:6]}.txt",
        b"This is not a spreadsheet.\n",
    )


def make_corrupt_workbook():
    """A .xlsx that is not a valid zip archive, so it cannot be parsed."""
    return _write(
        f"corrupt_{uuid.uuid4().hex[:6]}.xlsx",
        b"PK\x03\x04 this is deliberately truncated and not a real workbook",
    )


def corrupt_template_data(template_path):
    """Copy a real template and write invalid values into its first data row.

    The workbook stays structurally valid, so this exercises data validation
    rather than file parsing.
    """
    openpyxl = pytest.importorskip(
        "openpyxl", reason="openpyxl is required to edit the generated template"
    )

    workbook = openpyxl.load_workbook(template_path)
    sheet = next(
        (workbook[name] for name in workbook.sheetnames if workbook[name].max_row > 1),
        workbook[workbook.sheetnames[0]],
    )

    target_row = min(sheet.max_row + 1, 3)
    for column in range(1, min(sheet.max_column, 10) + 1):
        sheet.cell(row=target_row, column=column, value="!!INVALID!!")

    corrupted = os.path.join(_scratch_dir(), f"invalid_data_{uuid.uuid4().hex[:6]}.xlsx")
    workbook.save(corrupted)
    assert zipfile.is_zipfile(corrupted), "Corrupted template is no longer a valid workbook"
    return corrupted


# --- Fixtures ---------------------------------------------------------------

@pytest.fixture
def configured_draft(token, client, project_type, draft, boundaries):
    """A draft that has cleared the boundary and delivery rule steps."""
    response = update_boundaries(token, client, draft, project_type, boundaries)
    assert response.status_code in (200, 202), f"Boundary step failed: {response.text}"
    campaign = response.json()["CampaignDetails"]

    response = update_delivery_rules(token, client, campaign, project_type, boundaries)
    assert response.status_code in (200, 202), f"Delivery rules step failed: {response.text}"
    return response.json()["CampaignDetails"]


@pytest.fixture
def generated_template(token, client, campaign_type, configured_draft):
    """The generated unified template, downloaded to disk."""
    response = generate_template(
        token, client, configured_draft["id"], configured_draft.get("projectType"),
        hierarchy_type=configured_draft.get("hierarchyType"),
    )
    assert response.status_code in (200, 202), f"Template generation failed: {response.text}"

    generation_id = response.json()["GenerateResource"]["id"]
    _, file_store_id, completed = wait_for_generation(token, client, generation_id)
    assert completed, f"Template generation did not complete for {campaign_type}"
    assert file_store_id, "Generation completed without a fileStoreId"

    url_response = get_download_url(client, file_store_id)
    assert url_response.status_code == 200, f"Download URL lookup failed: {url_response.text}"

    file_urls = url_response.json().get("fileStoreIds", [])
    assert file_urls, f"No download URL returned for {file_store_id}"
    download_url = file_urls[0].get("url")
    assert download_url, f"Empty download URL: {file_urls[0]}"

    return download_to_disk(download_url)


# --- Helpers ----------------------------------------------------------------

def assert_validation_fails(token, client, response, what):
    """Fail the upload either at submission or at the end of async validation."""
    if response.status_code not in (200, 202):
        print(f"  Correctly rejected at submission ({response.status_code}): {what}")
        return

    process_id = response.json().get("ProcessResource", {}).get("id")
    assert process_id, f"Validation accepted but returned no process id: {response.text}"

    _, completed, details = wait_for_process(token, client, process_id)
    assert not completed, (
        f"{what}\n"
        f"  The console UI rejects this file, but excel-ingestion validated it "
        f"successfully (process {process_id}).\n"
        f"  This looks like a missing server-side validation."
    )
    reason = (details or {}).get("additionalDetails") or (details or {}).get("status")
    print(f"  Correctly failed validation: {what} (process {process_id}, {reason})")


# --- Positive ---------------------------------------------------------------

@pytest.mark.console
@pytest.mark.positive
def test_generate_campaign_template(token, client, campaign_type, configured_draft):
    """The console can generate a unified template for a configured campaign."""
    response = generate_template(
        token, client, configured_draft["id"], configured_draft.get("projectType"),
        hierarchy_type=configured_draft.get("hierarchyType"),
    )
    assert response.status_code in (200, 202), f"Template generation failed: {response.text}"

    resource = response.json()["GenerateResource"]
    assert resource.get("id"), "Generation returned no id"

    _, file_store_id, completed = wait_for_generation(token, client, resource["id"])
    assert completed, f"Template generation did not complete for {campaign_type}"
    assert file_store_id, "Generation completed without a fileStoreId"
    print(f"{campaign_type}: template generated, fileStoreId={file_store_id}")


@pytest.mark.console
@pytest.mark.positive
def test_upload_template_and_attach_to_campaign(
    token, client, campaign_type, project_type, configured_draft, boundaries, generated_template
):
    """A downloaded template uploads to filestore and attaches to the campaign."""
    upload = upload_to_filestore(client, generated_template)
    assert upload.status_code in (200, 201), f"Template upload failed: {upload.text}"

    files = upload.json().get("files", [])
    assert files, f"Upload returned no files: {upload.text}"
    file_store_id = files[0].get("fileStoreId")
    assert file_store_id, f"Upload returned no fileStoreId: {files[0]}"

    response = update_resources(
        token, client, configured_draft, project_type, boundaries, file_store_id,
        filename=os.path.basename(generated_template),
    )
    assert response.status_code in (200, 202), f"Attaching the template failed: {response.text}"

    # The update response's `resources` array is unreliable: once a template has
    # been generated for the campaign, project-factory answers 200 with an empty
    # array even though the resource is persisted. Verify against the read model.
    found = fetch_campaign(token, client, configured_draft["campaignNumber"])
    resources = found.get("resources", [])
    assert resources, (
        f"No resource attached to campaign {configured_draft['campaignNumber']} "
        f"(update returned {response.json()['CampaignDetails'].get('resources')})"
    )
    assert resources[0].get("filestoreId") == file_store_id, (
        f"Attached filestoreId mismatch. Expected {file_store_id}, "
        f"got {resources[0].get('filestoreId')}"
    )
    assert resources[0].get("type") == consoleResourceType
    print(f"{campaign_type}: template attached, fileStoreId={file_store_id}")


@pytest.mark.console
@pytest.mark.positive
def test_filled_template_passes_validation(
    token, client, campaign_type, configured_draft, generated_template
):
    """The generated template, filled in from the sample, passes validation.

    The sample under data/console/templates/ is the pattern: the filler reads
    which value belongs in which column and applies it to the rows the
    environment just generated.
    """
    filled_path, rows_filled = fill_generated_template(generated_template, campaign_type)

    if filled_path:
        assert rows_filled > 0, (
            f"The sample template for {campaign_type} produced no fill pattern. "
            f"Check that its column headers match the generated template."
        )
        upload = upload_to_filestore(client, filled_path)
        assert upload.status_code in (200, 201), f"Filled template upload failed: {upload.text}"
        file_store_id = upload.json()["files"][0]["fileStoreId"]
    elif prefilled_filestore_id(campaign_type):
        file_store_id = prefilled_filestore_id(campaign_type)
    else:
        pytest.skip(
            f"No sample template for {campaign_type}. Drop a filled-in unified template at "
            f"data/console/templates/{campaign_type}_sample.xlsx (or set "
            f"CONSOLE_SAMPLE_TEMPLATE) to run this test."
        )

    response = validate_process(
        token, client, file_store_id, configured_draft["id"],
        hierarchy_type=configured_draft.get("hierarchyType"),
    )
    assert response.status_code in (200, 202), f"Process validation failed: {response.text}"

    resource = response.json()["ProcessResource"]
    assert resource.get("id"), "Validation returned no process id"
    assert resource.get("fileStoreId") == file_store_id
    assert resource.get("referenceId") == configured_draft["id"]

    _, completed, details = wait_for_process(token, client, resource["id"])
    assert completed, (
        f"Validation of the filled template did not complete for {campaign_type}: {details}"
    )
    print(f"{campaign_type}: filled template validated ({rows_filled} row(s), "
          f"process {resource['id']})")


# --- Negative ---------------------------------------------------------------

@pytest.mark.console
@pytest.mark.negative
def test_submit_without_file(token, client, campaign_type, project_type,
                             configured_draft, boundaries):
    """Creating the campaign with no uploaded template must be rejected."""
    response = finalize_campaign(
        token, client, configured_draft, project_type, boundaries, resources=[]
    )
    assert_rejected(response, f"{campaign_type}: campaign submitted with no template attached")


@pytest.mark.console
@pytest.mark.negative
def test_upload_invalid_file_type(token, client, campaign_type, configured_draft):
    """A non-spreadsheet upload must not pass validation."""
    path = make_wrong_type_file()
    upload = upload_to_filestore(client, path)

    if upload.status_code not in (200, 201):
        print(f"  Correctly rejected at upload ({upload.status_code}): non-spreadsheet file")
        return

    file_store_id = upload.json()["files"][0]["fileStoreId"]
    response = validate_process(
        token, client, file_store_id, configured_draft["id"],
        hierarchy_type=configured_draft.get("hierarchyType"),
    )
    assert_validation_fails(
        token, client, response, f"{campaign_type}: uploaded a .txt file instead of a template"
    )


@pytest.mark.console
@pytest.mark.negative
def test_upload_corrupt_workbook(token, client, campaign_type, configured_draft):
    """A .xlsx that cannot be parsed must not pass validation."""
    path = make_corrupt_workbook()
    upload = upload_to_filestore(client, path)

    if upload.status_code not in (200, 201):
        print(f"  Correctly rejected at upload ({upload.status_code}): corrupt workbook")
        return

    file_store_id = upload.json()["files"][0]["fileStoreId"]
    response = validate_process(
        token, client, file_store_id, configured_draft["id"],
        hierarchy_type=configured_draft.get("hierarchyType"),
    )
    assert_validation_fails(
        token, client, response, f"{campaign_type}: uploaded an unreadable .xlsx"
    )


@pytest.mark.console
@pytest.mark.negative
def test_upload_template_with_invalid_data(
    token, client, campaign_type, configured_draft, generated_template
):
    """A structurally valid template holding invalid data must fail validation."""
    corrupted = corrupt_template_data(generated_template)
    upload = upload_to_filestore(client, corrupted)
    assert upload.status_code in (200, 201), f"Upload of the edited template failed: {upload.text}"

    file_store_id = upload.json()["files"][0]["fileStoreId"]
    response = validate_process(
        token, client, file_store_id, configured_draft["id"],
        hierarchy_type=configured_draft.get("hierarchyType"),
    )
    assert_validation_fails(
        token, client, response,
        f"{campaign_type}: template rows filled with invalid values",
    )


@pytest.mark.console
@pytest.mark.negative
def test_process_validation_with_unknown_filestore_id(
    token, client, campaign_type, configured_draft
):
    """Validation against a filestoreId that does not exist must be rejected."""
    response = validate_process(
        token, client, "00000000-0000-0000-0000-000000000000", configured_draft["id"],
        hierarchy_type=configured_draft.get("hierarchyType"),
    )
    assert_validation_fails(
        token, client, response, f"{campaign_type}: validation against an unknown fileStoreId"
    )


@pytest.mark.console
@pytest.mark.negative
def test_process_search_with_unknown_id(token, client, campaign_type):
    """Searching an unknown process id returns nothing rather than an error."""
    response = search_process(token, client, "00000000-0000-0000-0000-000000000000")
    assert response.status_code == 200, f"Process search failed: {response.text}"

    details = response.json().get("ProcessingDetails", [])
    assert details == [], f"Expected no results for an unknown process id, got {len(details)}"
    print(f"{campaign_type}: unknown process id returned no results")
