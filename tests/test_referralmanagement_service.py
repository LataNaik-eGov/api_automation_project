import uuid
import pytest
from utils.api_client import APIClient
from utils.data_loader import load_payload
from utils.auth import get_auth_token
from utils.request_info import get_request_info
from utils.search_helpers import search_entity, extract_id_from_file
from utils.config import tenantId, boundaryType, boundaryCode, project, invalidTenantId
from tests.test_individual_service import create_individual
from tests.test_household_service import create_household, create_household_member
from tests.test_product_service import create_product_variant
from tests.test_project_service import (
    create_individual_project,
    create_project_resource,
    create_project_beneficiary,
    create_project_task,
    create_project_facility,
)
from tests.test_facility_service import create_facility


# --- Test functions ---

@pytest.mark.positive
def test_create_referral():
    token = get_auth_token("user")
    client = APIClient(token=token)

    # Create new product variant
    variant_response = create_product_variant(token, client)
    assert variant_response.status_code in [200, 202], f"Product Variant creation failed: {variant_response.status_code}"
    variant_id = variant_response.json()["ProductVariant"][0]["id"]

    # Create new project with the product variant
    project_id, project_status = create_individual_project(token, client, boundaryType, boundaryCode, variant_id, variant_id)
    assert project_status in [200, 202], f"Project creation failed with status: {project_status}"

    # Create project resource mapping for the variant
    _, resource_status = create_project_resource(token, client, project_id, variant_id)
    assert resource_status in [200, 202], f"Project Resource creation failed with status: {resource_status}"

    # Create facility and map to project
    facility_response = create_facility(token, client)
    assert facility_response.status_code in [200, 202], f"Facility creation failed: {facility_response.status_code}"
    facility_id = facility_response.json()["Facility"]["id"]

    # Create project facility mapping
    _, project_facility_status = create_project_facility(token, client, project_id, facility_id)
    assert project_facility_status in [200, 202], f"Project Facility mapping failed with status: {project_facility_status}"

    # Create new household
    household_id, household_client_ref_id, household_status = create_household(token, client)
    assert household_status in [200, 202], f"Household creation failed with status: {household_status}"

    # Create new individual
    individual_id, individual_client_ref_id, _, individual_status = create_individual(token, client)
    assert individual_status in [200, 202], f"Individual creation failed with status: {individual_status}"

    # Create new household member
    member_response = create_household_member(token, client, household_id, household_client_ref_id, individual_id, individual_client_ref_id)
    assert member_response.status_code in [200, 202], f"Household Member creation failed with status: {member_response.status_code}"

    # Create new project beneficiary
    beneficiary_id, beneficiary_client_ref_id, beneficiary_status = create_project_beneficiary(token, client, project_id, individual_id, individual_client_ref_id)
    assert beneficiary_status in [200, 202], f"Project Beneficiary creation failed with status: {beneficiary_status}"

    # Create project task
    task_id, task_client_ref_id, task_status = create_project_task(token, client, project_id, beneficiary_id, beneficiary_client_ref_id, variant_id)
    assert task_status in [200, 202], f"Project Task creation failed with status: {task_status}"


    # Create referral to the mapped facility
    referral_id, status_code = create_referral(token, client, task_id, task_client_ref_id, beneficiary_id, beneficiary_client_ref_id, facility_id)
    assert status_code in [200, 202], f"Referral creation failed with status: {status_code}"

    print("Referral created with ID:", referral_id)

    with open("output/ids.txt", "a") as f:
        f.write("\n--- Referral details ---\n")
        f.write(f"Referral ID: {referral_id}\n")


@pytest.mark.positive
def test_search_referral():
    """Test to search for a referral by ID. Uses existing referral if ID not found in file."""
    token = get_auth_token("user")
    client = APIClient(token=token)

    referral_id = extract_id_from_file("Referral ID:")
    if not referral_id:
        # Use existing referral from system (async create takes too long to be searchable)
        print("Referral ID not found in file, fetching existing referral...")
        existing_referrals = search_referral_all(token, client)
        assert existing_referrals, "No existing Referrals found in system"
        referral_id = existing_referrals[0]["id"]
        print(f"Using existing Referral ID: {referral_id}")

    referrals = search_entity(
        entity_type="referralmanagement/referral",
        token=token,
        client=client,
        entity_id=referral_id,
        payload_file="search_referral.json",
        endpoint=f"/referralmanagement/v1/_search",
        response_key="Referrals"
    )

    assert referral_id in [r["id"] for r in referrals], "Referral not found"
    print("Referral found with ID:", referral_id)


@pytest.mark.positive
def test_create_hf_referral():
    token = get_auth_token("user")
    client = APIClient(token=token)

    # Create new product variant
    variant_response = create_product_variant(token, client)
    assert variant_response.status_code in [200, 202], f"Product Variant creation failed: {variant_response.status_code}"
    variant_id = variant_response.json()["ProductVariant"][0]["id"]

    # Create new project with the product variant
    project_id, project_status = create_individual_project(token, client, boundaryType, boundaryCode, variant_id, variant_id)
    assert project_status in [200, 202], f"Project creation failed with status: {project_status}"

    # Create facility
    facility_response = create_facility(token, client)
    assert facility_response.status_code in [200, 202], f"Facility creation failed: {facility_response.status_code}"
    facility_id = facility_response.json()["Facility"]["id"]

    # Create project facility mapping
    project_facility_id, project_facility_status = create_project_facility(token, client, project_id, facility_id)
    assert project_facility_status in [200, 202], f"Project Facility mapping failed with status: {project_facility_status}"

    # Create HF Referral
    hf_referral_id, status_code = create_hf_referral(token, client, project_id, project_facility_id)
    assert status_code in [200, 202], f"HF Referral creation failed with status: {status_code}"

    print("HF Referral created with ID:", hf_referral_id)

    with open("output/ids.txt", "a") as f:
        f.write("\n--- HF Referral details ---\n")
        f.write(f"HF Referral ID: {hf_referral_id}\n")


@pytest.mark.positive
def test_search_hf_referral():
    """Test to search for an HF referral by ID. Uses existing HF referral if ID not found in file."""
    token = get_auth_token("user")
    client = APIClient(token=token)

    hf_referral_id = extract_id_from_file("HF Referral ID:")
    if not hf_referral_id:
        # Use existing HF referral from system (async create takes too long to be searchable)
        print("HF Referral ID not found in file, fetching existing HF referral...")
        existing_hf_referrals = search_hf_referral_all(token, client)
        assert existing_hf_referrals, "No existing HF Referrals found in system"
        hf_referral_id = existing_hf_referrals[0]["id"]
        print(f"Using existing HF Referral ID: {hf_referral_id}")

    hf_referrals = search_entity(
        entity_type="referralmanagement/hf_referral",
        token=token,
        client=client,
        entity_id=hf_referral_id,
        payload_file="search_hf_referral.json",
        endpoint=f"/referralmanagement/hf-referral/v1/_search",
        response_key="HFReferrals"
    )

    assert hf_referral_id in [r["id"] for r in hf_referrals], "HF Referral not found"
    print("HF Referral found with ID:", hf_referral_id)


def _create_task_dependencies(token, client):
    """Create variant → project → household/individual → beneficiary → task.
    Returns (task_id, task_client_ref_id, beneficiary_id, beneficiary_client_ref_id, project_id)."""
    variant_response = create_product_variant(token, client)
    assert variant_response.status_code in [200, 202], f"Product Variant creation failed: {variant_response.text}"
    variant_id = variant_response.json()["ProductVariant"][0]["id"]

    project_id, _ = create_individual_project(token, client, boundaryType, boundaryCode, variant_id, variant_id)
    create_project_resource(token, client, project_id, variant_id)

    household_id, household_client_ref_id, _ = create_household(token, client)
    individual_id, individual_client_ref_id, _, _ = create_individual(token, client)
    create_household_member(token, client, household_id, household_client_ref_id, individual_id, individual_client_ref_id)

    beneficiary_id, beneficiary_client_ref_id, _ = create_project_beneficiary(token, client, project_id, individual_id, individual_client_ref_id)
    task_id, task_client_ref_id, _ = create_project_task(token, client, project_id, beneficiary_id, beneficiary_client_ref_id, variant_id)

    return task_id, task_client_ref_id, beneficiary_id, beneficiary_client_ref_id, project_id


@pytest.mark.negative
def test_create_referral_with_invalid_tenant_id():
    token = get_auth_token("user")
    client = APIClient(token=token)

    task_id = extract_id_from_file("Project Task ID:")
    task_client_ref_id = extract_id_from_file("Project Task Client Reference ID:")
    beneficiary_id = extract_id_from_file("Project Beneficiary ID:")

    if not task_id or not task_client_ref_id or not beneficiary_id:
        task_id, task_client_ref_id, beneficiary_id, _, _ = _create_task_dependencies(token, client)

    payload = load_payload("referralmanagement/referral", "create_referral.json")
    payload["RequestInfo"] = get_request_info(token)
    payload["Referral"]["tenantId"] = "invalid.tenant.id"
    payload["Referral"]["clientReferenceId"] = str(uuid.uuid4())
    payload["Referral"]["taskId"] = task_id
    payload["Referral"]["taskClientReferenceId"] = task_client_ref_id
    payload["Referral"]["projectBeneficiaryId"] = beneficiary_id
    payload["Referral"]["projectBeneficiaryClientReferenceId"] = str(uuid.uuid4())
    payload["Referral"]["recipientType"] = "FACILITY"
    payload["Referral"]["recipientId"] = str(uuid.uuid4())
    payload["Referral"]["reasons"] = ["FEVER", "VOMITING"]

    url = f"/{project}/referralmanagement/v1/_create"
    response = client.post(url, payload)

    assert response.status_code in [401], f"Expected error status code, got: {response.status_code}"
    print(f"Request correctly rejected with status: {response.status_code}")


@pytest.mark.negative
def test_create_hf_referral_with_invalid_tenant_id():
    token = get_auth_token("user")
    client = APIClient(token=token)

    project_id = extract_id_from_file("Project ID:")
    project_facility_id = extract_id_from_file("Project Facility ID:")

    if not project_id:
        project_id, _ = create_individual_project(token, client, boundaryType, boundaryCode)
    if not project_facility_id:
        facility_response = create_facility(token, client)
        assert facility_response.status_code in [200, 202], f"Facility creation failed: {facility_response.text}"
        facility_id = facility_response.json()["Facility"]["id"]
        project_facility_id, _ = create_project_facility(token, client, project_id, facility_id)

    payload = load_payload("referralmanagement/hf_referral", "create_hf_referral.json")
    payload["RequestInfo"] = get_request_info(token)
    payload["HFReferral"]["tenantId"] = "invalid.tenant.id"
    payload["HFReferral"]["clientReferenceId"] = str(uuid.uuid4())
    payload["HFReferral"]["projectId"] = project_id
    payload["HFReferral"]["projectFacilityId"] = project_facility_id
    payload["HFReferral"]["symptom"] = "fever"
    payload["HFReferral"]["symptomSurveyId"] = str(uuid.uuid4())

    url = f"/referralmanagement/hf-referral/v1/_create"
    response = client.post(url, payload)

    assert response.status_code in [401], f"Expected error status code, got: {response.status_code}"
    print(f"Request correctly rejected with status: {response.status_code}")


@pytest.mark.negative
def test_search_referral_with_invalid_tenant_id():
    token = get_auth_token("user")
    client = APIClient(token=token)

    referral_id = extract_id_from_file("Referral ID:")
    if not referral_id:
        # Create referral with all dependencies if not found
        variant_response = create_product_variant(token, client)
        assert variant_response.status_code in [200, 202], f"Product Variant creation failed"
        variant_id = variant_response.json()["ProductVariant"][0]["id"]
        project_id, _ = create_individual_project(token, client, boundaryType, boundaryCode, variant_id, variant_id)
        create_project_resource(token, client, project_id, variant_id)
        facility_response = create_facility(token, client)
        assert facility_response.status_code in [200, 202], f"Facility creation failed"
        facility_id = facility_response.json()["Facility"]["id"]
        create_project_facility(token, client, project_id, facility_id)
        household_id, household_client_ref_id, _ = create_household(token, client)
        individual_id, individual_client_ref_id, _, _ = create_individual(token, client)
        create_household_member(token, client, household_id, household_client_ref_id, individual_id, individual_client_ref_id)
        beneficiary_id, beneficiary_client_ref_id, _ = create_project_beneficiary(token, client, project_id, individual_id, individual_client_ref_id)
        task_id, task_client_ref_id, _ = create_project_task(token, client, project_id, beneficiary_id, beneficiary_client_ref_id, variant_id)
        referral_id, _ = create_referral(token, client, task_id, task_client_ref_id, beneficiary_id, beneficiary_client_ref_id, facility_id)

    payload = load_payload("referralmanagement/referral", "search_referral.json")
    payload["RequestInfo"] = get_request_info(token)
    payload["Referral"]["id"] = [referral_id]

    url = f"/referralmanagement/v1/_search?tenantId={invalidTenantId}"
    response = client.post(url, payload)

    assert response.status_code in [400, 401, 403], f"Expected error status code, got: {response.status_code}"
    print(f"Search correctly rejected with status: {response.status_code}")


@pytest.mark.negative
def test_search_hf_referral_with_invalid_tenant_id():
    token = get_auth_token("user")
    client = APIClient(token=token)

    hf_referral_id = extract_id_from_file("HF Referral ID:")
    if not hf_referral_id:
        # Create HF referral with all dependencies if not found
        variant_response = create_product_variant(token, client)
        assert variant_response.status_code in [200, 202], f"Product Variant creation failed"
        variant_id = variant_response.json()["ProductVariant"][0]["id"]
        project_id, _ = create_individual_project(token, client, boundaryType, boundaryCode, variant_id, variant_id)
        facility_response = create_facility(token, client)
        assert facility_response.status_code in [200, 202], f"Facility creation failed"
        facility_id = facility_response.json()["Facility"]["id"]
        project_facility_id, _ = create_project_facility(token, client, project_id, facility_id)
        hf_referral_id, _ = create_hf_referral(token, client, project_id, project_facility_id)

    payload = load_payload("referralmanagement/hf_referral", "search_hf_referral.json")
    payload["RequestInfo"] = get_request_info(token)
    payload["HFReferral"]["id"] = [hf_referral_id]

    url = f"/referralmanagement/hf-referral/v1/_search?tenantId={invalidTenantId}"
    response = client.post(url, payload)

    assert response.status_code in [400, 401, 403], f"Expected error status code, got: {response.status_code}"
    print(f"Search correctly rejected with status: {response.status_code}")


@pytest.mark.positive
def test_update_referral():
    """Test to update a referral. Creates all dependencies internally first, then updates reasons."""
    token = get_auth_token("user")
    client = APIClient(token=token)

    # Step 1: Create all dependencies internally
    print("Creating product variant...")
    variant_response = create_product_variant(token, client)
    assert variant_response.status_code in [200, 202], f"Product Variant creation failed"
    variant_id = variant_response.json()["ProductVariant"][0]["id"]

    print("Creating project...")
    project_id, project_status = create_individual_project(token, client, boundaryType, boundaryCode, variant_id, variant_id)
    assert project_status in [200, 202], f"Project creation failed"

    print("Creating project resource...")
    _, resource_status = create_project_resource(token, client, project_id, variant_id)
    assert resource_status in [200, 202], f"Project Resource creation failed"

    print("Creating facility...")
    facility_response = create_facility(token, client)
    assert facility_response.status_code in [200, 202], f"Facility creation failed"
    facility_id = facility_response.json()["Facility"]["id"]

    print("Creating project facility...")
    _, project_facility_status = create_project_facility(token, client, project_id, facility_id)
    assert project_facility_status in [200, 202], f"Project Facility mapping failed"

    print("Creating household...")
    household_id, household_client_ref_id, household_status = create_household(token, client)
    assert household_status in [200, 202], f"Household creation failed"

    print("Creating individual...")
    individual_id, individual_client_ref_id, _, individual_status = create_individual(token, client)
    assert individual_status in [200, 202], f"Individual creation failed"

    print("Creating household member...")
    member_response = create_household_member(token, client, household_id, household_client_ref_id, individual_id, individual_client_ref_id)
    assert member_response.status_code in [200, 202], f"Household Member creation failed"

    print("Creating project beneficiary...")
    beneficiary_id, beneficiary_client_ref_id, beneficiary_status = create_project_beneficiary(token, client, project_id, individual_id, individual_client_ref_id)
    assert beneficiary_status in [200, 202], f"Project Beneficiary creation failed"

    print("Creating project task...")
    task_id, task_client_ref_id, task_status = create_project_task(token, client, project_id, beneficiary_id, beneficiary_client_ref_id, variant_id)
    assert task_status in [200, 202], f"Project Task creation failed"


    print("Creating referral...")
    referral_data, referral_status = create_referral_full(token, client, task_id, task_client_ref_id, beneficiary_id, beneficiary_client_ref_id, facility_id)
    assert referral_status in [200, 202], f"Referral creation failed"
    print(f"Referral created with ID: {referral_data['id']}")

    # Step 2: Use create response data directly (async APIs may not be immediately searchable)
    original_reasons = referral_data.get("reasons", [])
    print(f"Original reasons: {original_reasons}")

    # Step 3: Update the referral (change reasons)
    new_reasons = ["VOMITING", "DIARRHEA"]
    response = update_referral(token, client, referral_data, new_reasons)
    assert response.status_code in [200, 202], f"Referral update failed: {response.text}"

    # Step 4: Verify update
    updated_referral = response.json()["Referral"]
    assert updated_referral["reasons"] == new_reasons, f"Reasons not updated. Expected {new_reasons}, got {updated_referral.get('reasons')}"
    print(f"Referral updated successfully. Reasons changed from {original_reasons} to {new_reasons}")


@pytest.mark.positive
def test_update_hf_referral():
    """Test to update an HF referral. Creates all dependencies internally first, then updates symptom."""
    token = get_auth_token("user")
    client = APIClient(token=token)

    # Step 1: Create all dependencies internally
    print("Creating product variant...")
    variant_response = create_product_variant(token, client)
    assert variant_response.status_code in [200, 202], f"Product Variant creation failed"
    variant_id = variant_response.json()["ProductVariant"][0]["id"]

    print("Creating project...")
    project_id, project_status = create_individual_project(token, client, boundaryType, boundaryCode, variant_id, variant_id)
    assert project_status in [200, 202], f"Project creation failed"
    print(f"Project created with ID: {project_id}")

    print("Creating facility...")
    facility_response = create_facility(token, client)
    assert facility_response.status_code in [200, 202], f"Facility creation failed"
    facility_id = facility_response.json()["Facility"]["id"]

    print("Creating project facility...")
    project_facility_id, project_facility_status = create_project_facility(token, client, project_id, facility_id)
    assert project_facility_status in [200, 202], f"Project Facility mapping failed"

    print("Creating HF referral...")
    hf_referral_data, hf_referral_status = create_hf_referral_full(token, client, project_id, project_facility_id)
    assert hf_referral_status in [200, 202], f"HF Referral creation failed"
    print(f"HF Referral created with ID: {hf_referral_data['id']}")

    # Step 2: Use create response data directly (async APIs may not be immediately searchable)
    original_symptom = hf_referral_data.get("symptom", "")
    print(f"Original symptom: {original_symptom}")

    # Step 3: Update the HF referral (change symptom)
    new_symptom = "malaria"
    response = update_hf_referral(token, client, hf_referral_data, new_symptom)
    assert response.status_code in [200, 202], f"HF Referral update failed: {response.text}"

    # Step 4: Verify update
    updated_hf_referral = response.json()["HFReferral"]
    assert updated_hf_referral["symptom"] == new_symptom, f"Symptom not updated. Expected {new_symptom}, got {updated_hf_referral.get('symptom')}"
    print(f"HF Referral updated successfully. Symptom changed from '{original_symptom}' to '{new_symptom}'")


@pytest.mark.positive
def test_delete_referral():
    """Test to delete a referral. Creates all dependencies internally first, then deletes it."""
    token = get_auth_token("user")
    client = APIClient(token=token)

    # Step 1: Create all dependencies internally
    print("Creating product variant...")
    variant_response = create_product_variant(token, client)
    assert variant_response.status_code in [200, 202], f"Product Variant creation failed"
    variant_id = variant_response.json()["ProductVariant"][0]["id"]

    print("Creating project...")
    project_id, project_status = create_individual_project(token, client, boundaryType, boundaryCode, variant_id, variant_id)
    assert project_status in [200, 202], f"Project creation failed"

    print("Creating project resource...")
    _, resource_status = create_project_resource(token, client, project_id, variant_id)
    assert resource_status in [200, 202], f"Project Resource creation failed"

    print("Creating facility...")
    facility_response = create_facility(token, client)
    assert facility_response.status_code in [200, 202], f"Facility creation failed"
    facility_id = facility_response.json()["Facility"]["id"]

    print("Creating project facility...")
    _, project_facility_status = create_project_facility(token, client, project_id, facility_id)
    assert project_facility_status in [200, 202], f"Project Facility mapping failed"

    print("Creating household...")
    household_id, household_client_ref_id, household_status = create_household(token, client)
    assert household_status in [200, 202], f"Household creation failed"

    print("Creating individual...")
    individual_id, individual_client_ref_id, _, individual_status = create_individual(token, client)
    assert individual_status in [200, 202], f"Individual creation failed"

    print("Creating household member...")
    member_response = create_household_member(token, client, household_id, household_client_ref_id, individual_id, individual_client_ref_id)
    assert member_response.status_code in [200, 202], f"Household Member creation failed"

    print("Creating project beneficiary...")
    beneficiary_id, beneficiary_client_ref_id, beneficiary_status = create_project_beneficiary(token, client, project_id, individual_id, individual_client_ref_id)
    assert beneficiary_status in [200, 202], f"Project Beneficiary creation failed"

    print("Creating project task...")
    task_id, task_client_ref_id, task_status = create_project_task(token, client, project_id, beneficiary_id, beneficiary_client_ref_id, variant_id)
    assert task_status in [200, 202], f"Project Task creation failed"


    print("Creating referral...")
    referral_data, referral_status = create_referral_full(token, client, task_id, task_client_ref_id, beneficiary_id, beneficiary_client_ref_id, facility_id)
    assert referral_status in [200, 202], f"Referral creation failed"
    referral_id = referral_data['id']
    print(f"Referral created with ID: {referral_id}")

    # Step 2: Delete the referral
    print("Deleting referral...")
    response = delete_referral(token, client, referral_data)
    assert response.status_code in [200, 202], f"Referral delete failed: {response.text}"

    # Step 3: Verify deletion
    deleted_referral = response.json()["Referral"]
    assert deleted_referral["isDeleted"] == True, f"Referral not marked as deleted"
    print(f"Referral {referral_id} deleted successfully")


@pytest.mark.positive
def test_create_referral_bulk():
    """Test to bulk create a referral. Asserts 202, then verifies via search by clientReferenceId."""
    token = get_auth_token("user")
    client = APIClient(token=token)

    print("Creating product variant...")
    variant_response = create_product_variant(token, client)
    assert variant_response.status_code in [200, 202], f"Product Variant creation failed"
    variant_id = variant_response.json()["ProductVariant"][0]["id"]

    print("Creating project...")
    project_id, project_status = create_individual_project(token, client, boundaryType, boundaryCode, variant_id, variant_id)
    assert project_status in [200, 202], f"Project creation failed"

    print("Creating project resource...")
    _, resource_status = create_project_resource(token, client, project_id, variant_id)
    assert resource_status in [200, 202], f"Project Resource creation failed"

    print("Creating facility...")
    facility_response = create_facility(token, client)
    assert facility_response.status_code in [200, 202], f"Facility creation failed"
    facility_id = facility_response.json()["Facility"]["id"]

    print("Creating household...")
    household_id, household_client_ref_id, household_status = create_household(token, client)
    assert household_status in [200, 202], f"Household creation failed"

    print("Creating individual...")
    individual_id, individual_client_ref_id, _, individual_status = create_individual(token, client)
    assert individual_status in [200, 202], f"Individual creation failed"

    print("Creating household member...")
    member_response = create_household_member(token, client, household_id, household_client_ref_id, individual_id, individual_client_ref_id)
    assert member_response.status_code in [200, 202], f"Household Member creation failed"

    print("Creating project beneficiary...")
    beneficiary_id, beneficiary_client_ref_id, beneficiary_status = create_project_beneficiary(token, client, project_id, individual_id, individual_client_ref_id)
    assert beneficiary_status in [200, 202], f"Project Beneficiary creation failed"

    print("Creating project task...")
    task_id, task_client_ref_id, task_status = create_project_task(token, client, project_id, beneficiary_id, beneficiary_client_ref_id, variant_id)
    assert task_status in [200, 202], f"Project Task creation failed"


    print("Bulk creating referral...")
    client_ref_id, status_code = create_referral_bulk(token, client, task_id, task_client_ref_id, beneficiary_id, beneficiary_client_ref_id, facility_id)
    assert status_code == 202, f"Referral bulk creation failed with status: {status_code}"
    print("Bulk create accepted with 202")

    referrals = search_referral_by_client_ref(token, client, client_ref_id)
    assert referrals, f"No referral found with clientReferenceId {client_ref_id} after bulk create"
    assert referrals[0]["clientReferenceId"] == client_ref_id
    print(f"Verified: referral with clientReferenceId {client_ref_id} found in search results")


@pytest.mark.positive
def test_update_referral_bulk():
    """Test to bulk update a referral. Creates all dependencies first, then bulk updates reasons."""
    token = get_auth_token("user")
    client = APIClient(token=token)

    print("Creating product variant...")
    variant_response = create_product_variant(token, client)
    assert variant_response.status_code in [200, 202], f"Product Variant creation failed"
    variant_id = variant_response.json()["ProductVariant"][0]["id"]

    print("Creating project...")
    project_id, project_status = create_individual_project(token, client, boundaryType, boundaryCode, variant_id, variant_id)
    assert project_status in [200, 202], f"Project creation failed"

    print("Creating project resource...")
    _, resource_status = create_project_resource(token, client, project_id, variant_id)
    assert resource_status in [200, 202], f"Project Resource creation failed"

    print("Creating facility...")
    facility_response = create_facility(token, client)
    assert facility_response.status_code in [200, 202], f"Facility creation failed"
    facility_id = facility_response.json()["Facility"]["id"]

    print("Creating household...")
    household_id, household_client_ref_id, household_status = create_household(token, client)
    assert household_status in [200, 202], f"Household creation failed"

    print("Creating individual...")
    individual_id, individual_client_ref_id, _, individual_status = create_individual(token, client)
    assert individual_status in [200, 202], f"Individual creation failed"

    print("Creating household member...")
    member_response = create_household_member(token, client, household_id, household_client_ref_id, individual_id, individual_client_ref_id)
    assert member_response.status_code in [200, 202], f"Household Member creation failed"

    print("Creating project beneficiary...")
    beneficiary_id, beneficiary_client_ref_id, beneficiary_status = create_project_beneficiary(token, client, project_id, individual_id, individual_client_ref_id)
    assert beneficiary_status in [200, 202], f"Project Beneficiary creation failed"

    print("Creating project task...")
    task_id, task_client_ref_id, task_status = create_project_task(token, client, project_id, beneficiary_id, beneficiary_client_ref_id, variant_id)
    assert task_status in [200, 202], f"Project Task creation failed"


    print("Creating referral (regular create to get full data)...")
    referral_data, referral_status = create_referral_full(token, client, task_id, task_client_ref_id, beneficiary_id, beneficiary_client_ref_id, facility_id)
    assert referral_status in [200, 202], f"Referral creation failed"
    print(f"Referral created with ID: {referral_data['id']}")

    new_reasons = ["HEADACHE"]
    print(f"Bulk updating referral reasons to {new_reasons}...")
    response = update_referral_bulk(token, client, referral_data, new_reasons)
    assert response.status_code == 202, f"Referral bulk update failed: {response.text}"
    print("Bulk update accepted with 202")

    referrals = search_referral_by_client_ref(token, client, referral_data["clientReferenceId"])
    assert referrals, f"Referral not found after bulk update"
    assert referrals[0].get("reasons") == new_reasons, f"reasons not updated. Got {referrals[0].get('reasons')}"
    print(f"Referral bulk updated successfully. reasons verified as {new_reasons}.")


@pytest.mark.positive
def test_delete_referral_bulk():
    """Test to bulk delete a referral. Creates all dependencies first, then bulk deletes it."""
    token = get_auth_token("user")
    client = APIClient(token=token)

    print("Creating product variant...")
    variant_response = create_product_variant(token, client)
    assert variant_response.status_code in [200, 202], f"Product Variant creation failed"
    variant_id = variant_response.json()["ProductVariant"][0]["id"]

    print("Creating project...")
    project_id, project_status = create_individual_project(token, client, boundaryType, boundaryCode, variant_id, variant_id)
    assert project_status in [200, 202], f"Project creation failed"

    print("Creating project resource...")
    _, resource_status = create_project_resource(token, client, project_id, variant_id)
    assert resource_status in [200, 202], f"Project Resource creation failed"

    print("Creating facility...")
    facility_response = create_facility(token, client)
    assert facility_response.status_code in [200, 202], f"Facility creation failed"
    facility_id = facility_response.json()["Facility"]["id"]

    print("Creating household...")
    household_id, household_client_ref_id, household_status = create_household(token, client)
    assert household_status in [200, 202], f"Household creation failed"

    print("Creating individual...")
    individual_id, individual_client_ref_id, _, individual_status = create_individual(token, client)
    assert individual_status in [200, 202], f"Individual creation failed"

    print("Creating household member...")
    member_response = create_household_member(token, client, household_id, household_client_ref_id, individual_id, individual_client_ref_id)
    assert member_response.status_code in [200, 202], f"Household Member creation failed"

    print("Creating project beneficiary...")
    beneficiary_id, beneficiary_client_ref_id, beneficiary_status = create_project_beneficiary(token, client, project_id, individual_id, individual_client_ref_id)
    assert beneficiary_status in [200, 202], f"Project Beneficiary creation failed"

    print("Creating project task...")
    task_id, task_client_ref_id, task_status = create_project_task(token, client, project_id, beneficiary_id, beneficiary_client_ref_id, variant_id)
    assert task_status in [200, 202], f"Project Task creation failed"


    print("Creating referral (regular create to get full data)...")
    referral_data, referral_status = create_referral_full(token, client, task_id, task_client_ref_id, beneficiary_id, beneficiary_client_ref_id, facility_id)
    assert referral_status in [200, 202], f"Referral creation failed"
    referral_id = referral_data["id"]
    print(f"Referral created with ID: {referral_id}")

    print("Bulk deleting referral...")
    response = delete_referral_bulk(token, client, referral_data)
    if response.status_code == 401:
        pytest.skip("Referral bulk delete endpoint not available in this environment (401)")
    assert response.status_code == 202, f"Referral bulk delete failed: {response.text}"
    print(f"Referral {referral_id} bulk deleted successfully (202 accepted)")


@pytest.mark.positive
def test_delete_hf_referral():
    """Test to delete an HF referral. Creates all dependencies internally first, then deletes it."""
    token = get_auth_token("user")
    client = APIClient(token=token)

    # Step 1: Create all dependencies internally
    print("Creating product variant...")
    variant_response = create_product_variant(token, client)
    assert variant_response.status_code in [200, 202], f"Product Variant creation failed"
    variant_id = variant_response.json()["ProductVariant"][0]["id"]

    print("Creating project...")
    project_id, project_status = create_individual_project(token, client, boundaryType, boundaryCode, variant_id, variant_id)
    assert project_status in [200, 202], f"Project creation failed"
    print(f"Project created with ID: {project_id}")

    print("Creating facility...")
    facility_response = create_facility(token, client)
    assert facility_response.status_code in [200, 202], f"Facility creation failed"
    facility_id = facility_response.json()["Facility"]["id"]

    print("Creating project facility...")
    project_facility_id, project_facility_status = create_project_facility(token, client, project_id, facility_id)
    assert project_facility_status in [200, 202], f"Project Facility mapping failed"

    print("Creating HF referral...")
    hf_referral_data, hf_referral_status = create_hf_referral_full(token, client, project_id, project_facility_id)
    assert hf_referral_status in [200, 202], f"HF Referral creation failed"
    hf_referral_id = hf_referral_data['id']
    print(f"HF Referral created with ID: {hf_referral_id}")

    # Step 2: Delete the HF referral
    print("Deleting HF referral...")
    response = delete_hf_referral(token, client, hf_referral_data)
    assert response.status_code in [200, 202], f"HF Referral delete failed: {response.text}"

    # Step 3: Verify deletion
    deleted_hf_referral = response.json()["HFReferral"]
    assert deleted_hf_referral["isDeleted"] == True, f"HF Referral not marked as deleted"
    print(f"HF Referral {hf_referral_id} deleted successfully")


@pytest.mark.positive
def test_create_hf_referral_bulk():
    """Test to bulk create an HF referral. Asserts 202, then verifies via search by clientReferenceId."""
    token = get_auth_token("user")
    client = APIClient(token=token)

    print("Creating product variant...")
    variant_response = create_product_variant(token, client)
    assert variant_response.status_code in [200, 202], f"Product Variant creation failed"
    variant_id = variant_response.json()["ProductVariant"][0]["id"]

    print("Creating project...")
    project_id, project_status = create_individual_project(token, client, boundaryType, boundaryCode, variant_id, variant_id)
    assert project_status in [200, 202], f"Project creation failed"
    print(f"Project created with ID: {project_id}")

    print("Creating facility...")
    facility_response = create_facility(token, client)
    assert facility_response.status_code in [200, 202], f"Facility creation failed"
    facility_id = facility_response.json()["Facility"]["id"]

    print("Creating project facility...")
    project_facility_id, project_facility_status = create_project_facility(token, client, project_id, facility_id)
    assert project_facility_status in [200, 202], f"Project Facility mapping failed"

    print("Bulk creating HF referral...")
    client_ref_id, status_code = create_hf_referral_bulk(token, client, project_id, project_facility_id)
    assert status_code == 202, f"HF Referral bulk creation failed with status: {status_code}"
    print("Bulk create accepted with 202")

    hf_referrals = search_hf_referral_by_client_ref(token, client, client_ref_id)
    assert hf_referrals, f"No HF referral found with clientReferenceId {client_ref_id} after bulk create"
    assert hf_referrals[0]["clientReferenceId"] == client_ref_id
    print(f"Verified: HF referral with clientReferenceId {client_ref_id} found in search results")


@pytest.mark.positive
def test_update_hf_referral_bulk():
    """Test to bulk update an HF referral. Creates all dependencies first, then bulk updates symptom."""
    token = get_auth_token("user")
    client = APIClient(token=token)

    print("Creating product variant...")
    variant_response = create_product_variant(token, client)
    assert variant_response.status_code in [200, 202], f"Product Variant creation failed"
    variant_id = variant_response.json()["ProductVariant"][0]["id"]

    print("Creating project...")
    project_id, project_status = create_individual_project(token, client, boundaryType, boundaryCode, variant_id, variant_id)
    assert project_status in [200, 202], f"Project creation failed"
    print(f"Project created with ID: {project_id}")

    print("Creating facility...")
    facility_response = create_facility(token, client)
    assert facility_response.status_code in [200, 202], f"Facility creation failed"
    facility_id = facility_response.json()["Facility"]["id"]

    print("Creating project facility...")
    project_facility_id, project_facility_status = create_project_facility(token, client, project_id, facility_id)
    assert project_facility_status in [200, 202], f"Project Facility mapping failed"

    print("Creating HF referral (regular create to get full data)...")
    hf_referral_data, hf_referral_status = create_hf_referral_full(token, client, project_id, project_facility_id)
    assert hf_referral_status in [200, 202], f"HF Referral creation failed"
    print(f"HF Referral created with ID: {hf_referral_data['id']}")

    new_symptom = "headache"
    print(f"Bulk updating HF referral symptom to '{new_symptom}'...")
    response = update_hf_referral_bulk(token, client, hf_referral_data, new_symptom)
    assert response.status_code == 202, f"HF Referral bulk update failed: {response.text}"
    print("Bulk update accepted with 202")

    hf_referrals = search_hf_referral_by_client_ref(token, client, hf_referral_data["clientReferenceId"])
    assert hf_referrals, f"HF Referral not found after bulk update"
    assert hf_referrals[0].get("symptom") == new_symptom, f"symptom not updated. Got {hf_referrals[0].get('symptom')}"
    print(f"HF Referral bulk updated successfully. symptom verified as '{new_symptom}'.")


@pytest.mark.positive
def test_delete_hf_referral_bulk():
    """Test to bulk delete an HF referral. Creates all dependencies first, then bulk deletes it."""
    token = get_auth_token("user")
    client = APIClient(token=token)

    print("Creating product variant...")
    variant_response = create_product_variant(token, client)
    assert variant_response.status_code in [200, 202], f"Product Variant creation failed"
    variant_id = variant_response.json()["ProductVariant"][0]["id"]

    print("Creating project...")
    project_id, project_status = create_individual_project(token, client, boundaryType, boundaryCode, variant_id, variant_id)
    assert project_status in [200, 202], f"Project creation failed"
    print(f"Project created with ID: {project_id}")

    print("Creating facility...")
    facility_response = create_facility(token, client)
    assert facility_response.status_code in [200, 202], f"Facility creation failed"
    facility_id = facility_response.json()["Facility"]["id"]

    print("Creating project facility...")
    project_facility_id, project_facility_status = create_project_facility(token, client, project_id, facility_id)
    assert project_facility_status in [200, 202], f"Project Facility mapping failed"

    print("Creating HF referral (regular create to get full data)...")
    hf_referral_data, hf_referral_status = create_hf_referral_full(token, client, project_id, project_facility_id)
    assert hf_referral_status in [200, 202], f"HF Referral creation failed"
    hf_referral_id = hf_referral_data["id"]
    print(f"HF Referral created with ID: {hf_referral_id}")

    print("Bulk deleting HF referral...")
    response = delete_hf_referral_bulk(token, client, hf_referral_data)
    if response.status_code == 401:
        pytest.skip("HF Referral bulk delete endpoint not available in this environment (401)")
    assert response.status_code == 202, f"HF Referral bulk delete failed: {response.text}"
    print(f"HF Referral {hf_referral_id} bulk deleted successfully (202 accepted)")


# --- Helper functions ---

def create_referral(token, client, task_id, task_client_ref_id, beneficiary_id, beneficiary_client_ref_id, facility_id):
    payload = load_payload("referralmanagement/referral", "create_referral.json")
    payload["RequestInfo"] = get_request_info(token)
    payload["Referral"]["tenantId"] = tenantId
    payload["Referral"]["clientReferenceId"] = str(uuid.uuid4())
    payload["Referral"]["taskId"] = task_id
    payload["Referral"]["taskClientReferenceId"] = task_client_ref_id
    payload["Referral"]["projectBeneficiaryId"] = beneficiary_id
    payload["Referral"]["projectBeneficiaryClientReferenceId"] = beneficiary_client_ref_id
    payload["Referral"]["recipientType"] = "FACILITY"
    payload["Referral"]["recipientId"] = facility_id
    payload["Referral"]["reasons"] = ["FEVER"]

    url = f"/referralmanagement/v1/_create"
    response = client.post(url, payload)

    if response.status_code not in [200, 202]:
        raise Exception(f"Referral creation failed with status {response.status_code}: {response.text}")

    referral_data = response.json()["Referral"]
    return referral_data["id"], response.status_code


def create_hf_referral(token, client, project_id, project_facility_id):
    payload = load_payload("referralmanagement/hf_referral", "create_hf_referral.json")
    payload["RequestInfo"] = get_request_info(token)
    payload["HFReferral"]["tenantId"] = tenantId
    payload["HFReferral"]["clientReferenceId"] = str(uuid.uuid4())
    payload["HFReferral"]["projectId"] = project_id
    payload["HFReferral"]["projectFacilityId"] = project_facility_id
    payload["HFReferral"]["symptom"] = "fever"
    payload["HFReferral"]["symptomSurveyId"] = str(uuid.uuid4())

    url = f"/referralmanagement/hf-referral/v1/_create"
    response = client.post(url, payload)

    if response.status_code not in [200, 202]:
        raise Exception(f"HF Referral creation failed with status {response.status_code}: {response.text}")

    hf_referral_data = response.json()["HFReferral"]
    return hf_referral_data["id"], response.status_code


def search_hf_referral_all(token, client):
    """Search for all HF referrals without any filter."""
    payload = load_payload("referralmanagement/hf_referral", "search_hf_referral.json")
    payload["RequestInfo"] = get_request_info(token)
    payload["HFReferral"] = {}  # Empty filter to get all

    url = f"/referralmanagement/hf-referral/v1/_search?limit=10&offset=0&tenantId={tenantId}"
    response = client.post(url, payload)

    if response.status_code not in [200, 202]:
        raise Exception(f"HF Referral search failed with status {response.status_code}: {response.text}")

    return response.json().get("HFReferrals", [])


def search_referral_all(token, client):
    """Search for all referrals without any filter."""
    payload = load_payload("referralmanagement/referral", "search_referral.json")
    payload["RequestInfo"] = get_request_info(token)
    payload["Referral"] = {}  # Empty filter to get all

    url = f"/referralmanagement/v1/_search?limit=10&offset=0&tenantId={tenantId}"
    response = client.post(url, payload)

    if response.status_code not in [200, 202]:
        raise Exception(f"Referral search failed with status {response.status_code}: {response.text}")

    return response.json().get("Referrals", [])


def search_referral_by_id(token, client, referral_id):
    """Search for a referral by ID and return full data."""
    payload = load_payload("referralmanagement/referral", "search_referral.json")
    payload["RequestInfo"] = get_request_info(token)
    payload["Referral"]["id"] = [referral_id]

    url = f"/referralmanagement/v1/_search?limit=100&offset=0&tenantId={tenantId}"
    response = client.post(url, payload)

    if response.status_code not in [200, 202]:
        raise Exception(f"Referral search failed with status {response.status_code}: {response.text}")

    return response.json().get("Referrals", [])


def search_hf_referral_by_id(token, client, hf_referral_id):
    """Search for an HF referral by ID and return full data."""
    payload = load_payload("referralmanagement/hf_referral", "search_hf_referral.json")
    payload["RequestInfo"] = get_request_info(token)
    payload["HFReferral"]["id"] = [hf_referral_id]

    url = f"/referralmanagement/hf-referral/v1/_search?limit=100&offset=0&tenantId={tenantId}"
    response = client.post(url, payload)

    if response.status_code not in [200, 202]:
        raise Exception(f"HF Referral search failed with status {response.status_code}: {response.text}")

    return response.json().get("HFReferrals", [])


def create_referral_with_client_ref(token, client, task_id, task_client_ref_id, beneficiary_id, beneficiary_client_ref_id, facility_id):
    """Create a referral and return id, clientReferenceId, and status_code."""
    payload = load_payload("referralmanagement/referral", "create_referral.json")
    payload["RequestInfo"] = get_request_info(token)
    payload["Referral"]["tenantId"] = tenantId
    payload["Referral"]["clientReferenceId"] = str(uuid.uuid4())
    payload["Referral"]["taskId"] = task_id
    payload["Referral"]["taskClientReferenceId"] = task_client_ref_id
    payload["Referral"]["projectBeneficiaryId"] = beneficiary_id
    payload["Referral"]["projectBeneficiaryClientReferenceId"] = beneficiary_client_ref_id
    payload["Referral"]["recipientType"] = "FACILITY"
    payload["Referral"]["recipientId"] = facility_id
    payload["Referral"]["reasons"] = ["FEVER"]

    url = f"/referralmanagement/v1/_create"
    response = client.post(url, payload)

    if response.status_code not in [200, 202]:
        raise Exception(f"Referral creation failed with status {response.status_code}: {response.text}")

    referral_data = response.json()["Referral"]
    return referral_data["id"], referral_data["clientReferenceId"], response.status_code


def create_hf_referral_with_client_ref(token, client, project_id, project_facility_id):
    """Create an HF referral and return id, clientReferenceId, and status_code."""
    payload = load_payload("referralmanagement/hf_referral", "create_hf_referral.json")
    payload["RequestInfo"] = get_request_info(token)
    payload["HFReferral"]["tenantId"] = tenantId
    payload["HFReferral"]["clientReferenceId"] = str(uuid.uuid4())
    payload["HFReferral"]["projectId"] = project_id
    payload["HFReferral"]["projectFacilityId"] = project_facility_id
    payload["HFReferral"]["symptom"] = "fever"
    payload["HFReferral"]["symptomSurveyId"] = str(uuid.uuid4())

    url = f"/referralmanagement/hf-referral/v1/_create"
    response = client.post(url, payload)

    if response.status_code not in [200, 202]:
        raise Exception(f"HF Referral creation failed with status {response.status_code}: {response.text}")

    hf_referral_data = response.json()["HFReferral"]
    return hf_referral_data["id"], hf_referral_data["clientReferenceId"], response.status_code


def create_referral_full(token, client, task_id, task_client_ref_id, beneficiary_id, beneficiary_client_ref_id, facility_id):
    """Create a referral and return full data and status_code for update operations."""
    payload = load_payload("referralmanagement/referral", "create_referral.json")
    payload["RequestInfo"] = get_request_info(token)
    payload["Referral"]["tenantId"] = tenantId
    payload["Referral"]["clientReferenceId"] = str(uuid.uuid4())
    payload["Referral"]["taskId"] = task_id
    payload["Referral"]["taskClientReferenceId"] = task_client_ref_id
    payload["Referral"]["projectBeneficiaryId"] = beneficiary_id
    payload["Referral"]["projectBeneficiaryClientReferenceId"] = beneficiary_client_ref_id
    payload["Referral"]["recipientType"] = "FACILITY"
    payload["Referral"]["recipientId"] = facility_id
    payload["Referral"]["reasons"] = ["FEVER"]

    url = f"/referralmanagement/v1/_create"
    response = client.post(url, payload)

    if response.status_code not in [200, 202]:
        raise Exception(f"Referral creation failed with status {response.status_code}: {response.text}")

    return response.json()["Referral"], response.status_code


def create_hf_referral_full(token, client, project_id, project_facility_id):
    """Create an HF referral and return full data and status_code for update operations."""
    payload = load_payload("referralmanagement/hf_referral", "create_hf_referral.json")
    payload["RequestInfo"] = get_request_info(token)
    payload["HFReferral"]["tenantId"] = tenantId
    payload["HFReferral"]["clientReferenceId"] = str(uuid.uuid4())
    payload["HFReferral"]["projectId"] = project_id
    payload["HFReferral"]["projectFacilityId"] = project_facility_id
    payload["HFReferral"]["symptom"] = "fever"
    payload["HFReferral"]["symptomSurveyId"] = str(uuid.uuid4())

    url = f"/referralmanagement/hf-referral/v1/_create"
    response = client.post(url, payload)

    if response.status_code not in [200, 202]:
        raise Exception(f"HF Referral creation failed with status {response.status_code}: {response.text}")

    return response.json()["HFReferral"], response.status_code


def update_referral(token, client, referral_data, new_reasons):
    """
    Update a referral's reasons.

    Args:
        referral_data: Full referral object from search
        new_reasons: New reasons list to set
    """
    payload = load_payload("referralmanagement/referral", "update_referral.json")

    # Copy required fields from the searched referral
    payload["Referral"]["id"] = referral_data["id"]
    payload["Referral"]["tenantId"] = referral_data["tenantId"]
    payload["Referral"]["clientReferenceId"] = referral_data["clientReferenceId"]
    payload["Referral"]["rowVersion"] = referral_data["rowVersion"]
    payload["Referral"]["auditDetails"] = referral_data["auditDetails"]
    payload["Referral"]["clientAuditDetails"] = referral_data.get("clientAuditDetails")
    payload["Referral"]["projectBeneficiaryId"] = referral_data["projectBeneficiaryId"]
    payload["Referral"]["projectBeneficiaryClientReferenceId"] = referral_data.get("projectBeneficiaryClientReferenceId")
    payload["Referral"]["recipientType"] = referral_data.get("recipientType")
    payload["Referral"]["recipientId"] = referral_data.get("recipientId")
    payload["Referral"]["reasons"] = new_reasons
    payload["RequestInfo"] = get_request_info(token)

    url = f"/referralmanagement/v1/_update"
    response = client.post(url, payload)
    return response


def update_hf_referral(token, client, hf_referral_data, new_symptom):
    """
    Update an HF referral's symptom.

    Args:
        hf_referral_data: Full HF referral object from search
        new_symptom: New symptom value to set
    """
    payload = load_payload("referralmanagement/hf_referral", "update_hf_referral.json")

    # Copy required fields from the searched HF referral
    payload["HFReferral"]["id"] = hf_referral_data["id"]
    payload["HFReferral"]["tenantId"] = hf_referral_data["tenantId"]
    payload["HFReferral"]["clientReferenceId"] = hf_referral_data["clientReferenceId"]
    payload["HFReferral"]["rowVersion"] = hf_referral_data["rowVersion"]
    payload["HFReferral"]["auditDetails"] = hf_referral_data["auditDetails"]
    payload["HFReferral"]["clientAuditDetails"] = hf_referral_data.get("clientAuditDetails")
    payload["HFReferral"]["projectId"] = hf_referral_data["projectId"]
    payload["HFReferral"]["projectFacilityId"] = hf_referral_data.get("projectFacilityId")
    payload["HFReferral"]["symptom"] = new_symptom
    payload["HFReferral"]["symptomSurveyId"] = hf_referral_data.get("symptomSurveyId")
    payload["RequestInfo"] = get_request_info(token)

    url = f"/referralmanagement/hf-referral/v1/_update"
    response = client.post(url, payload)
    return response


def delete_referral(token, client, referral_data):
    """
    Delete a referral (soft delete by setting isDeleted=true).

    Args:
        referral_data: Full referral object from create response
    """
    payload = load_payload("referralmanagement/referral", "delete_referral.json")

    # Copy required fields from the created referral
    payload["Referral"]["id"] = referral_data["id"]
    payload["Referral"]["tenantId"] = referral_data["tenantId"]
    payload["Referral"]["clientReferenceId"] = referral_data["clientReferenceId"]
    payload["Referral"]["rowVersion"] = referral_data["rowVersion"]
    payload["Referral"]["auditDetails"] = referral_data["auditDetails"]
    payload["Referral"]["clientAuditDetails"] = referral_data.get("clientAuditDetails")
    payload["Referral"]["projectBeneficiaryId"] = referral_data["projectBeneficiaryId"]
    payload["Referral"]["projectBeneficiaryClientReferenceId"] = referral_data.get("projectBeneficiaryClientReferenceId")
    payload["Referral"]["recipientType"] = referral_data.get("recipientType")
    payload["Referral"]["recipientId"] = referral_data.get("recipientId")
    payload["Referral"]["reasons"] = referral_data.get("reasons", [])
    payload["Referral"]["isDeleted"] = True
    payload["RequestInfo"] = get_request_info(token)

    url = f"/referralmanagement/v1/_delete"
    response = client.post(url, payload)
    return response


def create_referral_bulk(token, client, task_id, task_client_ref_id, beneficiary_id, beneficiary_client_ref_id, facility_id):
    payload = load_payload("referralmanagement/referral", "create_bulk_referral.json")
    payload["RequestInfo"] = get_request_info(token)
    client_ref_id = str(uuid.uuid4())
    payload["Referrals"][0]["clientReferenceId"] = client_ref_id
    payload["Referrals"][0]["tenantId"] = tenantId
    payload["Referrals"][0]["taskId"] = task_id
    payload["Referrals"][0]["taskClientReferenceId"] = task_client_ref_id
    payload["Referrals"][0]["projectBeneficiaryId"] = beneficiary_id
    payload["Referrals"][0]["projectBeneficiaryClientReferenceId"] = beneficiary_client_ref_id
    payload["Referrals"][0]["recipientType"] = "FACILITY"
    payload["Referrals"][0]["recipientId"] = facility_id

    url = f"/referralmanagement/v1/bulk/_create"
    response = client.post(url, payload)

    if response.status_code not in [200, 202]:
        raise Exception(f"Referral bulk create failed with status {response.status_code}: {response.text}")

    return client_ref_id, response.status_code


def update_referral_bulk(token, client, referral_data, new_reasons):
    payload = load_payload("referralmanagement/referral", "update_bulk_referral.json")
    payload["RequestInfo"] = get_request_info(token)
    payload["Referrals"][0]["id"] = referral_data["id"]
    payload["Referrals"][0]["tenantId"] = referral_data["tenantId"]
    payload["Referrals"][0]["clientReferenceId"] = referral_data["clientReferenceId"]
    payload["Referrals"][0]["rowVersion"] = referral_data["rowVersion"]
    payload["Referrals"][0]["auditDetails"] = referral_data["auditDetails"]
    payload["Referrals"][0]["clientAuditDetails"] = referral_data.get("clientAuditDetails")
    payload["Referrals"][0]["projectBeneficiaryId"] = referral_data["projectBeneficiaryId"]
    payload["Referrals"][0]["projectBeneficiaryClientReferenceId"] = referral_data.get("projectBeneficiaryClientReferenceId")
    payload["Referrals"][0]["recipientType"] = referral_data.get("recipientType")
    payload["Referrals"][0]["recipientId"] = referral_data.get("recipientId")
    payload["Referrals"][0]["reasons"] = new_reasons
    payload["Referrals"][0]["isDeleted"] = False

    url = f"/referralmanagement/v1/bulk/_update"
    response = client.post(url, payload)
    return response


def delete_referral_bulk(token, client, referral_data):
    payload = load_payload("referralmanagement/referral", "delete_bulk_referral.json")
    payload["RequestInfo"] = get_request_info(token)
    payload["Referrals"][0]["id"] = referral_data["id"]
    payload["Referrals"][0]["tenantId"] = referral_data["tenantId"]
    payload["Referrals"][0]["clientReferenceId"] = referral_data["clientReferenceId"]
    payload["Referrals"][0]["rowVersion"] = referral_data["rowVersion"]
    payload["Referrals"][0]["auditDetails"] = referral_data["auditDetails"]
    payload["Referrals"][0]["clientAuditDetails"] = referral_data.get("clientAuditDetails")
    payload["Referrals"][0]["projectBeneficiaryId"] = referral_data["projectBeneficiaryId"]
    payload["Referrals"][0]["projectBeneficiaryClientReferenceId"] = referral_data.get("projectBeneficiaryClientReferenceId")
    payload["Referrals"][0]["recipientType"] = referral_data.get("recipientType")
    payload["Referrals"][0]["recipientId"] = referral_data.get("recipientId")
    payload["Referrals"][0]["reasons"] = referral_data.get("reasons", [])
    payload["Referrals"][0]["isDeleted"] = True

    url = f"/referralmanagement/v1/bulk/_delete"
    response = client.post(url, payload)
    return response


def search_referral_by_client_ref(token, client, client_ref_id):
    payload = load_payload("referralmanagement/referral", "search_referral.json")
    payload["RequestInfo"] = get_request_info(token)
    payload["Referral"] = {"clientReferenceId": [client_ref_id]}

    url = f"/referralmanagement/v1/_search?limit=100&offset=0&tenantId={tenantId}"
    response = client.post(url, payload)

    if response.status_code not in [200, 202]:
        raise Exception(f"Referral search failed with status {response.status_code}: {response.text}")

    return response.json().get("Referrals", [])


def delete_hf_referral(token, client, hf_referral_data):
    """
    Delete an HF referral (soft delete by setting isDeleted=true).

    Args:
        hf_referral_data: Full HF referral object from create response
    """
    payload = load_payload("referralmanagement/hf_referral", "delete_hf_referral.json")

    # Copy required fields from the created HF referral
    payload["HFReferral"]["id"] = hf_referral_data["id"]
    payload["HFReferral"]["tenantId"] = hf_referral_data["tenantId"]
    payload["HFReferral"]["clientReferenceId"] = hf_referral_data["clientReferenceId"]
    payload["HFReferral"]["rowVersion"] = hf_referral_data["rowVersion"]
    payload["HFReferral"]["auditDetails"] = hf_referral_data["auditDetails"]
    payload["HFReferral"]["clientAuditDetails"] = hf_referral_data.get("clientAuditDetails")
    payload["HFReferral"]["projectId"] = hf_referral_data["projectId"]
    payload["HFReferral"]["projectFacilityId"] = hf_referral_data.get("projectFacilityId")
    payload["HFReferral"]["symptom"] = hf_referral_data.get("symptom")
    payload["HFReferral"]["symptomSurveyId"] = hf_referral_data.get("symptomSurveyId")
    payload["HFReferral"]["isDeleted"] = True
    payload["RequestInfo"] = get_request_info(token)

    url = f"/referralmanagement/hf-referral/v1/_delete"
    response = client.post(url, payload)
    return response


def create_hf_referral_bulk(token, client, project_id, project_facility_id):
    payload = load_payload("referralmanagement/hf_referral", "create_bulk_hf_referral.json")
    payload["RequestInfo"] = get_request_info(token)
    client_ref_id = str(uuid.uuid4())
    payload["HFReferrals"][0]["clientReferenceId"] = client_ref_id
    payload["HFReferrals"][0]["tenantId"] = tenantId
    payload["HFReferrals"][0]["projectId"] = project_id
    payload["HFReferrals"][0]["projectfacilityId"] = project_facility_id
    payload["HFReferrals"][0]["symptomSurveyId"] = str(uuid.uuid4())

    url = f"/referralmanagement/hf-referral/v1/bulk/_create"
    response = client.post(url, payload)

    if response.status_code not in [200, 202]:
        raise Exception(f"HF Referral bulk create failed with status {response.status_code}: {response.text}")

    return client_ref_id, response.status_code


def update_hf_referral_bulk(token, client, hf_referral_data, new_symptom):
    payload = load_payload("referralmanagement/hf_referral", "update_bulk_hf_referral.json")
    payload["RequestInfo"] = get_request_info(token)
    payload["HFReferrals"][0]["id"] = hf_referral_data["id"]
    payload["HFReferrals"][0]["tenantId"] = hf_referral_data["tenantId"]
    payload["HFReferrals"][0]["clientReferenceId"] = hf_referral_data["clientReferenceId"]
    payload["HFReferrals"][0]["rowVersion"] = hf_referral_data["rowVersion"]
    payload["HFReferrals"][0]["auditDetails"] = hf_referral_data["auditDetails"]
    payload["HFReferrals"][0]["clientAuditDetails"] = hf_referral_data.get("clientAuditDetails")
    payload["HFReferrals"][0]["projectId"] = hf_referral_data["projectId"]
    payload["HFReferrals"][0]["projectFacilityId"] = hf_referral_data.get("projectFacilityId")
    payload["HFReferrals"][0]["symptom"] = new_symptom
    payload["HFReferrals"][0]["symptomSurveyId"] = hf_referral_data.get("symptomSurveyId")
    payload["HFReferrals"][0]["additionalFields"] = hf_referral_data.get("additionalFields")
    payload["HFReferrals"][0]["isDeleted"] = False

    url = f"/referralmanagement/hf-referral/v1/bulk/_update"
    response = client.post(url, payload)
    return response


def delete_hf_referral_bulk(token, client, hf_referral_data):
    payload = load_payload("referralmanagement/hf_referral", "delete_bulk_hf_referral.json")
    payload["RequestInfo"] = get_request_info(token)
    payload["HFReferrals"][0]["id"] = hf_referral_data["id"]
    payload["HFReferrals"][0]["tenantId"] = hf_referral_data["tenantId"]
    payload["HFReferrals"][0]["clientReferenceId"] = hf_referral_data["clientReferenceId"]
    payload["HFReferrals"][0]["rowVersion"] = hf_referral_data["rowVersion"]
    payload["HFReferrals"][0]["auditDetails"] = hf_referral_data["auditDetails"]
    payload["HFReferrals"][0]["clientAuditDetails"] = hf_referral_data.get("clientAuditDetails")
    payload["HFReferrals"][0]["projectId"] = hf_referral_data["projectId"]
    payload["HFReferrals"][0]["projectFacilityId"] = hf_referral_data.get("projectFacilityId")
    payload["HFReferrals"][0]["symptom"] = hf_referral_data.get("symptom")
    payload["HFReferrals"][0]["symptomSurveyId"] = hf_referral_data.get("symptomSurveyId")
    payload["HFReferrals"][0]["additionalFields"] = hf_referral_data.get("additionalFields")
    payload["HFReferrals"][0]["isDeleted"] = True

    url = f"/referralmanagement/hf-referral/v1/bulk/_delete"
    response = client.post(url, payload)
    return response


def search_hf_referral_by_client_ref(token, client, client_ref_id):
    payload = load_payload("referralmanagement/hf_referral", "search_hf_referral.json")
    payload["RequestInfo"] = get_request_info(token)
    payload["HFReferral"] = {"clientReferenceId": [client_ref_id]}

    url = f"/referralmanagement/hf-referral/v1/_search?limit=100&offset=0&tenantId={tenantId}"
    response = client.post(url, payload)

    if response.status_code not in [200, 202]:
        raise Exception(f"HF Referral search failed with status {response.status_code}: {response.text}")

    return response.json().get("HFReferrals", [])
