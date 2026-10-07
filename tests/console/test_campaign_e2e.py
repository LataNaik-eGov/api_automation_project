"""End-to-end console campaign creation.

Walks the whole console wizard over the API, once per campaign type:

    draft -> boundary -> delivery rules -> generate template -> fill from sample
    -> upload -> validate -> attach resource -> create -> poll until 'created'

The created campaign is written to output/console/campaigns.json so the search
tests can assert against real data.
"""

import os

import pytest

from utils.config import prefilled_filestore_id
from utils.console import (
    create_draft,
    download_to_disk,
    finalize_campaign,
    generate_template,
    get_download_url,
    save_campaign_result,
    fetch_campaign,
    unique_campaign_name,
    update_boundaries,
    update_delivery_rules,
    update_resources,
    upload_to_filestore,
    validate_process,
    wait_for_campaign_status,
    wait_for_generation,
    wait_for_process,
)
from utils.template_filler import fill_generated_template, sample_template_path


@pytest.mark.console
@pytest.mark.positive
def test_create_campaign_end_to_end(token, client, campaign_type, project_type, boundaries):
    """Create a campaign the way the console does, from scratch to 'created'."""
    if not sample_template_path(campaign_type) and not prefilled_filestore_id(campaign_type):
        pytest.skip(
            f"No sample template for {campaign_type}. Drop a filled-in unified template at "
            f"data/console/templates/{campaign_type}_sample.xlsx (or set CONSOLE_SAMPLE_TEMPLATE) "
            f"so the generated template can be filled the same way."
        )

    # --- Step 1: draft ---
    print(f"\n=== {campaign_type} | Step 1: draft ===")
    name = unique_campaign_name(prefix=campaign_type.replace("-", ""))
    response = create_draft(token, client, campaign_type, project_type, campaign_name=name)
    assert response.status_code in (200, 202), f"Draft creation failed: {response.text}"

    campaign = response.json()["CampaignDetails"]
    campaign_id = campaign["id"]
    campaign_number = campaign["campaignNumber"]
    print(f"  {name} -> {campaign_number} ({campaign_id})")

    # --- Step 2: boundary selection ---
    print(f"=== {campaign_type} | Step 2: boundary selection ===")
    response = update_boundaries(token, client, campaign, project_type, boundaries)
    assert response.status_code in (200, 202), f"Boundary step failed: {response.text}"
    campaign = response.json()["CampaignDetails"]
    print(f"  {len(boundaries)} boundaries selected")

    # --- Step 3: delivery rules ---
    print(f"=== {campaign_type} | Step 3: delivery rules ===")
    response = update_delivery_rules(token, client, campaign, project_type, boundaries)
    assert response.status_code in (200, 202), f"Delivery rules step failed: {response.text}"
    campaign = response.json()["CampaignDetails"]
    print(f"  {len(campaign.get('deliveryRules', []))} delivery rule(s) configured")

    # --- Step 4: generate the template ---
    print(f"=== {campaign_type} | Step 4: generate template ===")
    response = generate_template(
        token, client, campaign_id, campaign.get("projectType"),
        hierarchy_type=campaign.get("hierarchyType"),
    )
    assert response.status_code in (200, 202), f"Template generation failed: {response.text}"
    generation_id = response.json()["GenerateResource"]["id"]

    _, generated_file_store_id, completed = wait_for_generation(token, client, generation_id)
    assert completed, "Template generation did not complete"
    assert generated_file_store_id, "Generation completed without a fileStoreId"
    print(f"  generated fileStoreId={generated_file_store_id}")

    # --- Step 5: download the template ---
    print(f"=== {campaign_type} | Step 5: download template ===")
    url_response = get_download_url(client, generated_file_store_id)
    assert url_response.status_code == 200, f"Download URL lookup failed: {url_response.text}"
    file_urls = url_response.json().get("fileStoreIds", [])
    assert file_urls, f"No download URL returned for {generated_file_store_id}"

    local_path = download_to_disk(file_urls[0]["url"])
    assert os.path.getsize(local_path) > 0, "Downloaded template is empty"

    # --- Step 6: fill it in from the sample, then upload ---
    print(f"=== {campaign_type} | Step 6: fill template from sample ===")
    filled_path, rows_filled = fill_generated_template(local_path, campaign_type)

    if filled_path:
        assert rows_filled > 0, (
            f"The sample template for {campaign_type} produced no fill pattern. "
            f"Check that its column headers match the generated template."
        )
        upload = upload_to_filestore(client, filled_path)
        assert upload.status_code in (200, 201), f"Filled template upload failed: {upload.text}"
        upload_file_store_id = upload.json()["files"][0]["fileStoreId"]
        upload_filename = os.path.basename(filled_path)
        print(f"  filled {rows_filled} row(s), uploaded as {upload_file_store_id}")
    else:
        # Fall back to a pre-uploaded template when no sample is checked in.
        upload_file_store_id = prefilled_filestore_id(campaign_type)
        upload_filename = os.path.basename(local_path)
        print(f"  using CONSOLE_PREFILLED_FILESTORE_ID={upload_file_store_id}")

    # --- Step 7: validate the filled template ---
    print(f"=== {campaign_type} | Step 7: validate filled template ===")
    response = validate_process(
        token, client, upload_file_store_id, campaign_id,
        hierarchy_type=campaign.get("hierarchyType"),
    )
    assert response.status_code in (200, 202), f"Process validation failed: {response.text}"
    process_id = response.json()["ProcessResource"]["id"]

    _, validated, process_details = wait_for_process(token, client, process_id)
    assert validated, f"Template validation failed: {process_details}"
    print(f"  validated (process {process_id})")

    # --- Step 8: attach the resource ---
    print(f"=== {campaign_type} | Step 8: attach resource ===")
    response = update_resources(
        token, client, campaign, project_type, boundaries, upload_file_store_id,
        filename=upload_filename,
    )
    assert response.status_code in (200, 202), f"Attaching the template failed: {response.text}"

    # project-factory answers 200 with an empty `resources` array once a
    # template has been generated for the campaign, even though the resource is
    # persisted. Read the campaign back rather than trusting the write response.
    campaign = fetch_campaign(token, client, campaign_number)
    resources = campaign.get("resources", [])
    assert resources, (
        f"No resource attached to campaign {campaign_number} "
        f"(update returned {response.json()['CampaignDetails'].get('resources')})"
    )
    assert resources[0].get("filestoreId") == upload_file_store_id, (
        f"Attached filestoreId mismatch. Expected {upload_file_store_id}, "
        f"got {resources[0].get('filestoreId')}"
    )

    # --- Step 9: create the campaign ---
    print(f"=== {campaign_type} | Step 9: create campaign ===")
    response = finalize_campaign(token, client, campaign, project_type, boundaries, resources)
    assert response.status_code in (200, 202), f"Campaign creation failed: {response.text}"

    # --- Step 10: wait for 'created' ---
    print(f"=== {campaign_type} | Step 10: wait for 'created' ===")
    search, reached, created = wait_for_campaign_status(token, client, campaign_number)
    assert reached, (
        f"Campaign {campaign_number} did not reach 'created'. "
        f"Last response: {search.text if search else 'none'}"
    )

    # --- Step 11: record it for the search tests ---
    path = save_campaign_result(campaign_type, {
        "campaignType": campaign_type,
        "campaignId": campaign_id,
        "campaignNumber": campaign_number,
        "campaignName": name,
        "projectType": campaign.get("projectType"),
        "hierarchyType": campaign.get("hierarchyType"),
        "boundaryCount": len(boundaries),
        "excelIngestion": {
            "generationId": generation_id,
            "generatedFileStoreId": generated_file_store_id,
            "uploadedFileStoreId": upload_file_store_id,
            "processId": process_id,
            "rowsFilled": rows_filled,
        },
    })
    print(f"\n{'=' * 68}")
    print(f"  CAMPAIGN CREATED — verify in the UI under My campaigns")
    print(f"{'-' * 68}")
    print(f"  Campaign name   : {name}")
    print(f"  Campaign number : {campaign_number}")
    print(f"  Campaign id     : {campaign_id}")
    print(f"  Type / status   : {campaign_type} / created")
    print(f"  Saved to        : {path}")
    print(f"{'=' * 68}\n")
    assert created.get("status") == "created"
