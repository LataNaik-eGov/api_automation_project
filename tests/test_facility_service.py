import pytest
import uuid
from utils.api_client import APIClient
from utils.data_loader import load_payload
from utils.auth import get_auth_token
from utils.request_info import get_request_info
from utils.search_helpers import search_entity, extract_id_from_file, poll_until_found
from utils.config import tenantId, invalidTenantId, search_limit, search_offset, boundaryCode


# --- Test functions ---

@pytest.mark.positive
def test_create_facility():
    token = get_auth_token("user")
    client = APIClient(token=token)

    res = create_facility(token, client)
    assert res.status_code in [200, 202], f"Facility creation failed: {res.text}"

    facilityId = res.json()["Facility"]["id"]
    assert facilityId, "Facility ID not found in response"
    print("Facility created with ID:", facilityId)

    with open("output/ids.txt", "a") as f:
        f.write("\n--- Facility details ---\n")
        f.write(f"Facility ID: {facilityId}\n")


@pytest.mark.positive
def test_search_facility():
    """Test to search for a facility by ID. Creates facility if ID not found in file."""
    token = get_auth_token("user")
    client = APIClient(token=token)

    facilityId = extract_id_from_file("Facility ID:")
    if not facilityId:
        # Create facility internally if ID not found
        print("Facility ID not found in file, creating new facility...")
        res = create_facility(token, client)
        assert res.status_code in [200, 202], f"Facility creation failed: {res.text}"
        facilityId = res.json()["Facility"]["id"]
        print(f"Facility created with ID: {facilityId}")

    facilitys = search_entity(
        entity_type="facility",
        token=token,
        client=client,
        entity_id=facilityId,
        payload_file="search_facility.json",
        endpoint="/facility/v1/_search",
        response_key="Facilities"
    )

    assert facilityId in [p["id"] for p in facilitys], "Facility not found"
    print("Facility found with ID:", facilityId)


@pytest.mark.negative
def test_create_facility_with_invalid_tenant_id():
    """Negative test: Creating facility with invalid tenantId should fail"""
    token = get_auth_token("user")
    client = APIClient(token=token)

    res = create_facility(token, client, tenant_id=invalidTenantId)
    assert res.status_code == 401, f"Expected  4xx, got {res.status_code}: {res.text}"
    print("Negative test passed: Creating facility with invalid tenantId returned 401")


@pytest.mark.negative
def test_search_facility_with_invalid_tenant_id():
    """Negative test: Searching facility with invalid tenantId should fail"""
    token = get_auth_token("user")
    client = APIClient(token=token)

    facility_id = extract_id_from_file("Facility ID:")
    if not facility_id:
        # Create a new facility if ID not found
        res = create_facility(token, client)
        assert res.status_code in [200, 202], f"Facility creation failed: {res.text}"
        facility_id = res.json()["Facility"]["id"]

    payload = load_payload("facility", "search_facility.json")
    payload["RequestInfo"] = get_request_info(token)
    payload["Facility"]["id"] = [facility_id]

    url = f"/facility/v1/_search?tenantId={invalidTenantId}"
    response = client.post(url, payload)

    assert response.status_code == 401, f"Expected error status code, got: {response.status_code}"
    print(f"Search correctly rejected with status: {response.status_code}")


@pytest.mark.positive
def test_update_facility():
    """Test to update a facility. Creates facility internally first, then updates the name."""
    token = get_auth_token("user")
    client = APIClient(token=token)

    # Step 1: Create facility internally
    print("Creating facility for update test...")
    facility_data, facility_status = create_facility_full(token, client)
    assert facility_status in [200, 202], f"Facility creation failed with status: {facility_status}"
    print(f"Facility created with ID: {facility_data['id']}")

    # Step 2: Use create response data directly
    original_name = facility_data.get("name", "")
    print(f"Original name: {original_name}")

    # Step 3: Update the facility (change name)
    new_name = f"Updated-{original_name}"
    response = update_facility(token, client, facility_data, new_name)
    assert response.status_code in [200, 202], f"Facility update failed: {response.text}"

    # Step 4: Verify update
    updated_facility = response.json()["Facility"]
    assert updated_facility["name"] == new_name, f"Name not updated. Expected {new_name}, got {updated_facility.get('name')}"
    print(f"Facility updated successfully. Name changed from '{original_name}' to '{new_name}'")


@pytest.mark.positive
def test_delete_facility():
    """Test to delete a facility. Creates facility internally first, then deletes it."""
    token = get_auth_token("user")
    client = APIClient(token=token)

    # Step 1: Create facility internally
    print("Creating facility for delete test...")
    facility_data, facility_status = create_facility_full(token, client)
    assert facility_status in [200, 202], f"Facility creation failed with status: {facility_status}"
    facility_id = facility_data['id']
    print(f"Facility created with ID: {facility_id}")

    # Step 2: Delete the facility
    print("Deleting facility...")
    response = delete_facility(token, client, facility_data)
    assert response.status_code in [200, 202], f"Facility delete failed: {response.text}"

    # Step 3: Verify deletion
    deleted_facility = response.json()["Facility"]
    assert deleted_facility["isDeleted"] == True, f"Facility not marked as deleted"
    print(f"Facility {facility_id} deleted successfully")


@pytest.mark.positive
def test_create_facility_bulk():
    """Test to bulk create a facility."""
    token = get_auth_token("user")
    client = APIClient(token=token)

    # Step 1: Bulk create — response is always 202 with status body only
    print("Bulk creating facility...")
    client_ref_id, status_code = create_facility_bulk(token, client)
    assert status_code == 202, f"Facility bulk creation failed with status: {status_code}"
    print("Bulk create accepted with 202")

    # Step 2: Poll search until bulk-created facility is persisted
    facilities = poll_until_found(lambda: search_facility_by_client_ref(token, client, client_ref_id))
    assert facilities, f"No facility found with clientReferenceId {client_ref_id} after bulk create"
    assert facilities[0]["clientReferenceId"] == client_ref_id
    print(f"Verified: facility with clientReferenceId {client_ref_id} found in search results")


@pytest.mark.positive
def test_update_facility_bulk():
    """Test to bulk update a facility. Creates facility first, then bulk updates the name."""
    token = get_auth_token("user")
    client = APIClient(token=token)

    # Step 1: Create facility via regular create to get full data
    print("Creating facility...")
    facility_data, facility_status = create_facility_full(token, client)
    assert facility_status in [200, 202], f"Facility creation failed with status: {facility_status}"
    print(f"Facility created with ID: {facility_data['id']}")

    # Step 2: Bulk update name — response is always 202
    original_name = facility_data.get("name", "")
    new_name = f"Updated-{original_name}"
    print(f"Original name: {original_name}")

    response = update_facility_bulk(token, client, facility_data, new_name)
    assert response.status_code == 202, f"Facility bulk update failed: {response.text}"
    print("Bulk update accepted with 202")

    # Step 3: Poll search until bulk-updated facility name is reflected
    facilities = poll_until_found(lambda: search_facility_by_client_ref(token, client, facility_data["clientReferenceId"]))
    assert facilities, f"Facility not found after bulk update"
    assert facilities[0]["name"] == new_name, f"Name not updated. Expected {new_name}, got {facilities[0].get('name')}"
    print(f"Facility bulk updated successfully. Name changed from '{original_name}' to '{new_name}'")


@pytest.mark.positive
def test_delete_facility_bulk():
    """Test to bulk delete a facility. Creates facility first, then bulk deletes it."""
    token = get_auth_token("user")
    client = APIClient(token=token)

    # Step 1: Create facility via regular create to get full data
    print("Creating facility...")
    facility_data, facility_status = create_facility_full(token, client)
    assert facility_status in [200, 202], f"Facility creation failed with status: {facility_status}"
    facility_id = facility_data["id"]
    print(f"Facility created with ID: {facility_id}")

    # Step 2: Bulk delete — response is always 202
    print("Bulk deleting facility...")
    response = delete_facility_bulk(token, client, facility_data)
    assert response.status_code == 202, f"Facility bulk delete failed: {response.text}"
    print(f"Facility {facility_id} bulk deleted successfully (202 accepted)")


# --- Reusable Functions ---

def create_facility(token, client, tenant_id=None):
    """
    Create a facility.

    Args:
        tenant_id: Pass None to use default, or provide custom tenantId for negative testing
    """
    payload = load_payload("facility", "create_facility.json")
    payload["RequestInfo"] = get_request_info(token)
    # Inject dynamic values
    payload["Facility"]["clientReferenceId"] = str(uuid.uuid4())
    effective_tenant = tenant_id if tenant_id is not None else tenantId
    payload["Facility"]["tenantId"] = effective_tenant
    payload["Facility"]["address"]["tenantId"] = effective_tenant
    payload["Facility"]["address"]["locality"]["code"] = boundaryCode

    return client.post("/facility/v1/_create", payload)


def create_facility_full(token, client):
    """
    Create a facility and return full data for update operations.

    Returns:
        Tuple of (facility_data, status_code)
    """
    payload = load_payload("facility", "create_facility.json")
    payload["RequestInfo"] = get_request_info(token)
    payload["Facility"]["clientReferenceId"] = str(uuid.uuid4())
    payload["Facility"]["tenantId"] = tenantId
    payload["Facility"]["address"]["tenantId"] = tenantId
    payload["Facility"]["address"]["locality"]["code"] = boundaryCode

    response = client.post("/facility/v1/_create", payload)

    if response.status_code not in [200, 202]:
        raise Exception(f"Facility creation failed with status {response.status_code}: {response.text}")

    return response.json()["Facility"], response.status_code


def update_facility(token, client, facility_data, new_name):
    """
    Update a facility's name.

    Args:
        facility_data: Full facility object from create response
        new_name: New name value to set
    """
    payload = load_payload("facility", "update_facility.json")

    # Copy required fields from the created facility
    payload["Facility"]["id"] = facility_data["id"]
    payload["Facility"]["tenantId"] = facility_data["tenantId"]
    payload["Facility"]["clientReferenceId"] = facility_data["clientReferenceId"]
    payload["Facility"]["rowVersion"] = facility_data["rowVersion"]
    payload["Facility"]["auditDetails"] = facility_data["auditDetails"]
    payload["Facility"]["clientAuditDetails"] = facility_data.get("clientAuditDetails")
    payload["Facility"]["isPermanent"] = facility_data.get("isPermanent", True)
    payload["Facility"]["name"] = new_name
    payload["Facility"]["usage"] = facility_data.get("usage")
    payload["Facility"]["storageCapacity"] = facility_data.get("storageCapacity")
    payload["Facility"]["address"] = facility_data.get("address")
    payload["RequestInfo"] = get_request_info(token)

    response = client.post("/facility/v1/_update", payload)
    return response


def delete_facility(token, client, facility_data):
    """
    Delete a facility (soft delete by setting isDeleted=true).

    Args:
        facility_data: Full facility object from create response
    """
    payload = load_payload("facility", "delete_facility.json")

    # Copy required fields from the created facility
    payload["Facility"]["id"] = facility_data["id"]
    payload["Facility"]["tenantId"] = facility_data["tenantId"]
    payload["Facility"]["clientReferenceId"] = facility_data["clientReferenceId"]
    payload["Facility"]["rowVersion"] = facility_data["rowVersion"]
    payload["Facility"]["auditDetails"] = facility_data["auditDetails"]
    payload["Facility"]["clientAuditDetails"] = facility_data.get("clientAuditDetails")
    payload["Facility"]["isPermanent"] = facility_data.get("isPermanent", True)
    payload["Facility"]["name"] = facility_data.get("name")
    payload["Facility"]["usage"] = facility_data.get("usage")
    payload["Facility"]["storageCapacity"] = facility_data.get("storageCapacity")
    payload["Facility"]["address"] = facility_data.get("address")
    payload["Facility"]["isDeleted"] = True
    payload["RequestInfo"] = get_request_info(token)

    response = client.post("/facility/v1/_delete", payload)
    return response


def create_facility_bulk(token, client):
    payload = load_payload("facility", "create_bulk_facility.json")
    payload["RequestInfo"] = get_request_info(token)
    client_ref_id = str(uuid.uuid4())
    payload["Facilities"][0]["clientReferenceId"] = client_ref_id
    payload["Facilities"][0]["tenantId"] = tenantId
    payload["Facilities"][0]["address"]["tenantId"] = tenantId
    payload["Facilities"][0]["address"]["locality"]["code"] = boundaryCode

    response = client.post("/facility/v1/bulk/_create", payload)

    if response.status_code not in [200, 202]:
        raise Exception(f"Facility bulk creation failed with status {response.status_code}: {response.text}")

    return client_ref_id, response.status_code


def update_facility_bulk(token, client, facility_data, new_name):
    payload = load_payload("facility", "update_bulk_facility.json")

    payload["Facilities"][0]["id"] = facility_data["id"]
    payload["Facilities"][0]["tenantId"] = facility_data["tenantId"]
    payload["Facilities"][0]["clientReferenceId"] = facility_data["clientReferenceId"]
    payload["Facilities"][0]["rowVersion"] = facility_data["rowVersion"]
    payload["Facilities"][0]["auditDetails"] = facility_data["auditDetails"]
    payload["Facilities"][0]["clientAuditDetails"] = facility_data.get("clientAuditDetails")
    payload["Facilities"][0]["isPermanent"] = facility_data.get("isPermanent", True)
    payload["Facilities"][0]["name"] = new_name
    payload["Facilities"][0]["usage"] = facility_data.get("usage")
    payload["Facilities"][0]["storageCapacity"] = facility_data.get("storageCapacity")
    payload["Facilities"][0]["address"] = facility_data.get("address")
    payload["RequestInfo"] = get_request_info(token)

    response = client.post("/facility/v1/bulk/_update", payload)
    return response


def delete_facility_bulk(token, client, facility_data):
    payload = load_payload("facility", "delete_bulk_facility.json")

    payload["Facilities"][0]["id"] = facility_data["id"]
    payload["Facilities"][0]["tenantId"] = facility_data["tenantId"]
    payload["Facilities"][0]["clientReferenceId"] = facility_data["clientReferenceId"]
    payload["Facilities"][0]["rowVersion"] = facility_data["rowVersion"]
    payload["Facilities"][0]["auditDetails"] = facility_data["auditDetails"]
    payload["Facilities"][0]["clientAuditDetails"] = facility_data.get("clientAuditDetails")
    payload["Facilities"][0]["isPermanent"] = facility_data.get("isPermanent", True)
    payload["Facilities"][0]["name"] = facility_data.get("name")
    payload["Facilities"][0]["usage"] = facility_data.get("usage")
    payload["Facilities"][0]["storageCapacity"] = facility_data.get("storageCapacity")
    payload["Facilities"][0]["address"] = facility_data.get("address")
    payload["Facilities"][0]["isDeleted"] = True
    payload["RequestInfo"] = get_request_info(token)

    response = client.post("/facility/v1/bulk/_delete", payload)
    return response


def search_facility_by_client_ref(token, client, client_ref_id):
    payload = load_payload("facility", "search_facility.json")
    payload["RequestInfo"] = get_request_info(token)
    payload["Facility"] = {"clientReferenceId": [client_ref_id]}

    url = f"/facility/v1/_search?tenantId={tenantId}&limit={search_limit}&offset={search_offset}"
    response = client.post(url, payload)

    if response.status_code not in [200, 202]:
        raise Exception(f"Facility search failed with status {response.status_code}: {response.text}")

    return response.json().get("Facilities", [])

