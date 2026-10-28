import pytest
from utils.api_client import APIClient
from utils.auth import get_auth_token
from utils.data_loader import load_payload
from utils.request_info import get_request_info
from utils.search_helpers import search_entity, extract_id_from_file, poll_until_found
from test_individual_service import create_individual
from utils.config import tenantId, boundaryCode, invalidTenantId, search_limit, search_offset
import uuid
import json
import random

# Load the values from JSON file
with open("data/inputs.json", "r") as f:
    structure_data = json.load(f)


# --- Test functions ---

@pytest.mark.positive
def test_create_household():
    token = get_auth_token("user")
    client = APIClient(token=token)

    householdId, householdClientReferenceId, status_code = create_household(token, client)
    assert status_code in [200, 202], f"Household creation failed with status: {status_code}"

    with open("output/ids.txt", "a") as f:
        f.write("\n--- Household details ---\n")
        f.write(f"Household ID: {householdId}\n")
        f.write(f"Household Client Reference ID: {householdClientReferenceId}\n")

    print("Household created with ID:", householdId)


@pytest.mark.positive
def test_create_householdMember():
    token = get_auth_token("user")
    client = APIClient(token=token)

    res = create_household_member(token, client)
    assert res.status_code in [200, 202], f"Unexpected response: {res.text}"

    response_data = res.json()
    memberId = response_data["HouseholdMember"]["id"]
    clientRefId = response_data["HouseholdMember"]["clientReferenceId"]
    assert memberId, "Household Member ID missing in response"

    print("Created Household Member ID:", memberId)

    with open("output/ids.txt", "a") as f:
        f.write("\n--- Member details ---\n")
        f.write(f"Household Member ID: {memberId}\n")
        f.write(f"Household Member Client Reference ID: {clientRefId}\n")


@pytest.mark.positive
def test_search_household():
    """Test to search for a household by ID. Creates household if ID not found in file."""
    token = get_auth_token("user")
    client = APIClient(token=token)

    householdId = extract_id_from_file("Household ID:")
    if not householdId:
        # Create household internally if ID not found
        print("Household ID not found in file, creating new household...")
        householdId, _, status_code = create_household(token, client)
        assert status_code in [200, 202], f"Household creation failed with status: {status_code}"
        print(f"Household created with ID: {householdId}")

    households = search_entity(
        entity_type="household",
        token=token,
        client=client,
        entity_id=householdId,
        payload_file="search_household.json",
        endpoint="/household/v1/_search",
        response_key="Households"
    )

    assert householdId in [h["id"] for h in households], "Household not found"
    print("Household found with ID:", householdId)


@pytest.mark.positive
def test_search_householdMember_by_id():
    """Test to search for a household member by ID. Creates household member if ID not found in file."""
    token = get_auth_token("user")
    client = APIClient(token=token)

    memberId = extract_id_from_file("Household Member ID:")
    if not memberId:
        # Create household member internally if ID not found
        print("Household Member ID not found in file, creating new household member...")
        res = create_household_member(token, client)
        assert res.status_code in [200, 202], f"Household Member creation failed: {res.text}"
        memberId = res.json()["HouseholdMember"]["id"]
        print(f"Household Member created with ID: {memberId}")

    members = search_entity(
        entity_type="household",
        token=token,
        client=client,
        entity_id=memberId,
        payload_file="search_householdMember.json",
        endpoint="/household/member/v1/_search",
        response_key="HouseholdMembers"
    )

    assert memberId in [v["id"] for v in members], "Household Member not found"
    print("Household Member found with ID:", memberId)


@pytest.mark.negative
def test_create_householdMember_without_householdId():
    """Negative test: Creating household member without householdId should fail"""
    token = get_auth_token("user")
    client = APIClient(token=token)

    # Use helper with householdId=None to test negative scenario
    res = create_household_member(token, client, household_id=None, household_client_ref_id=None)

    # Should fail with 400 Bad Request
    assert res.status_code == 400, f"Expected 400, got {res.status_code}: {res.text}"
    print("Negative test passed: Creating member without householdId returned 400")


@pytest.mark.negative
def test_create_householdMember_without_individualId():
    """Negative test: Creating household member without individualId should fail"""
    token = get_auth_token("user")
    client = APIClient(token=token)

    # Use helper with individualId=None to test negative scenario
    res = create_household_member(token, client, individual_id=None, individual_client_ref_id=None)

    # Should fail with 400 Bad Request
    assert res.status_code == 400, f"Expected 400, got {res.status_code}: {res.text}"
    print("Negative test passed: Creating member without individualId returned 400")


@pytest.mark.negative
def test_create_household_with_invalid_tenant_id():
    """Negative test: Creating household with invalid tenantId should fail"""
    token = get_auth_token("user")
    client = APIClient(token=token)

    res = create_household(token, client, tenant_id=invalidTenantId)

    # Should fail with 401 Unauthorized
    assert res.status_code == 401, f"Expected  4xx, got {res.status_code}: {res.text}"
    print("Negative test passed: Creating household with invalid tenantId returned 401")


@pytest.mark.negative
def test_create_householdMember_with_invalid_tenant_id():
    """Negative test: Creating household member with invalid tenantId should fail"""
    token = get_auth_token("user")
    client = APIClient(token=token)

    res = create_household_member(token, client, tenant_id=invalidTenantId)

    # Should fail with 401 Unauthorized
    assert res.status_code == 401, f"Expected  4xx, got {res.status_code}: {res.text}"
    print("Negative test passed: Creating household member with invalid tenantId returned 401")


@pytest.mark.negative
def test_search_household_with_invalid_tenant_id():
    """Negative test: Searching household with invalid tenantId should fail"""
    token = get_auth_token("user")
    client = APIClient(token=token)

    household_id = extract_id_from_file("Household ID:")
    if not household_id:
        # Create a new household if ID not found
        household_id, _, status_code = create_household(token, client)
        assert status_code in [200, 202], f"Household creation failed with status: {status_code}"

    payload = load_payload("household", "search_household.json")
    payload["RequestInfo"] = get_request_info(token)
    payload["Household"]["id"] = [household_id]

    url = f"/household/v1/_search?tenantId={invalidTenantId}"
    response = client.post(url, payload)

    assert response.status_code == 401, f"Expected error status code, got: {response.status_code}"
    print(f"Search correctly rejected with status: {response.status_code}")


@pytest.mark.negative
def test_search_householdMember_with_invalid_tenant_id():
    """Negative test: Searching household member with invalid tenantId should fail"""
    token = get_auth_token("user")
    client = APIClient(token=token)

    member_id = extract_id_from_file("Household Member ID:")
    if not member_id:
        # Create a new household member if ID not found
        res = create_household_member(token, client)
        assert res.status_code in [200, 202], f"Household Member creation failed: {res.text}"
        member_id = res.json()["HouseholdMember"]["id"]

    payload = load_payload("household", "search_householdMember.json")
    payload["RequestInfo"] = get_request_info(token)
    payload["HouseholdMember"]["id"] = [member_id]

    url = f"/household/member/v1/_search?tenantId={invalidTenantId}"
    response = client.post(url, payload)

    assert response.status_code == 401, f"Expected error status code, got: {response.status_code}"
    print(f"Search correctly rejected with status: {response.status_code}")


@pytest.mark.positive
def test_update_household():
    """Test to update a household. Creates household internally first, then updates memberCount."""
    token = get_auth_token("user")
    client = APIClient(token=token)

    # Step 1: Create household internally
    print("Creating household for update test...")
    householdId, householdClientReferenceId, status_code = create_household(token, client)
    assert status_code in [200, 202], f"Household creation failed with status: {status_code}"
    print(f"Household created with ID: {householdId}")

    # Step 2: Search for the household to get full data for update
    households = search_entity(
        entity_type="household",
        token=token,
        client=client,
        entity_id=householdId,
        payload_file="search_household.json",
        endpoint="/household/v1/_search",
        response_key="Households"
    )
    assert len(households) > 0, "Could not find created household"
    household_data = households[0]

    # Step 3: Update the household (change memberCount)
    original_member_count = household_data.get("memberCount", 1)
    new_member_count = original_member_count + 3
    response = update_household(token, client, household_data, new_member_count)
    assert response.status_code in [200, 202], f"Household update failed: {response.text}"

    # Step 4: Verify update
    updated_household = response.json()["Household"]
    assert updated_household["memberCount"] == new_member_count, f"memberCount not updated. Expected {new_member_count}, got {updated_household['memberCount']}"
    print(f"Household updated successfully. memberCount changed from {original_member_count} to {new_member_count}")


@pytest.mark.positive
def test_update_household_member():
    """Test updating a non-head household member to become the head (isHeadOfHousehold: False → True).
    Creates a household with a head member first, then adds a second non-head member and promotes it."""
    token = get_auth_token("user")
    client = APIClient(token=token)

    # Step 1: Create household with a head member
    print("Creating household...")
    household_data, household_status = create_household_full(token, client)
    assert household_status in [200, 202], f"Household creation failed: {household_status}"
    household_id = household_data["id"]
    household_client_ref_id = household_data["clientReferenceId"]
    print(f"Household created with ID: {household_id}")

    print("Creating first individual (head member)...")
    head_individual_id, head_individual_client_ref_id, _, ind_status = create_individual(token, client)
    assert ind_status in [200, 202], f"Individual creation failed: {ind_status}"
    create_household_member_full(token, client, household_id, household_client_ref_id, head_individual_id, head_individual_client_ref_id, is_head=True)
    print("Head member created.")

    # Step 2: Create a second individual and add as non-head member
    print("Creating second individual (non-head member)...")
    individual_id, individual_client_ref_id, _, ind_status2 = create_individual(token, client)
    assert ind_status2 in [200, 202], f"Second individual creation failed: {ind_status2}"

    member_data, member_status = create_household_member_full(
        token, client, household_id, household_client_ref_id,
        individual_id, individual_client_ref_id, is_head=False
    )
    assert member_status in [200, 202], f"Non-head member creation failed: {member_status}"
    print(f"Non-head member created with ID: {member_data['id']}, isHeadOfHousehold: {member_data['isHeadOfHousehold']}")

    # Step 3: Promote non-head member to head (False → True)
    print("Updating member: setting isHeadOfHousehold to True...")
    response = update_household_member(token, client, member_data, True)
    assert response.status_code in [200, 202], f"Update failed: {response.text}"
    updated_member = response.json()["HouseholdMember"]
    assert updated_member["isHeadOfHousehold"] == True, f"Update failed. Expected True, got {updated_member['isHeadOfHousehold']}"
    print(f"Household Member updated successfully. isHeadOfHousehold is now True")


@pytest.mark.positive
def test_delete_household():
    """Test to delete a household. Creates household internally first, then deletes it."""
    token = get_auth_token("user")
    client = APIClient(token=token)

    # Step 1: Create household internally
    print("Creating household for delete test...")
    household_data, household_status = create_household_full(token, client)
    assert household_status in [200, 202], f"Household creation failed with status: {household_status}"
    household_id = household_data['id']
    print(f"Household created with ID: {household_id}")

    # Step 2: Delete the household
    print("Deleting household...")
    response = delete_household(token, client, household_data)
    assert response.status_code in [200, 202], f"Household delete failed: {response.text}"

    # Step 3: Verify deletion
    deleted_household = response.json()["Household"]
    assert deleted_household["isDeleted"] == True, f"Household not marked as deleted"
    print(f"Household {household_id} deleted successfully")


@pytest.mark.positive
def test_create_household_bulk():
    """Test to bulk create a household. Asserts 202, then verifies via search by clientReferenceId."""
    token = get_auth_token("user")
    client = APIClient(token=token)

    print("Bulk creating household...")
    client_ref_id, status_code = create_household_bulk(token, client)
    assert status_code == 202, f"Household bulk creation failed with status: {status_code}"
    print("Bulk create accepted with 202")

    households = poll_until_found(lambda: search_household_by_client_ref(token, client, client_ref_id))
    assert households, f"No household found with clientReferenceId {client_ref_id} after bulk create"
    assert households[0]["clientReferenceId"] == client_ref_id
    print(f"Verified: household with clientReferenceId {client_ref_id} found in search results")


@pytest.mark.positive
def test_update_household_bulk():
    """Test to bulk update a household. Creates household first, then bulk updates memberCount."""
    token = get_auth_token("user")
    client = APIClient(token=token)

    print("Creating household for bulk update test...")
    household_data, household_status = create_household_full(token, client)
    assert household_status in [200, 202], f"Household creation failed with status: {household_status}"
    print(f"Household created with ID: {household_data['id']}")

    print("Bulk updating household memberCount to 5...")
    response = update_household_bulk(token, client, household_data, new_member_count=5)
    assert response.status_code == 202, f"Household bulk update failed: {response.text}"
    print("Bulk update accepted with 202")

    households = poll_until_found(lambda: search_household_by_client_ref(token, client, household_data["clientReferenceId"]))
    assert households, f"Household not found after bulk update"
    assert households[0]["memberCount"] == 5, f"memberCount not updated. Got {households[0].get('memberCount')}"
    print("Household bulk updated successfully. memberCount verified as 5.")


@pytest.mark.positive
def test_delete_household_bulk():
    """Test to bulk delete a household. Creates household first, then bulk deletes it."""
    token = get_auth_token("user")
    client = APIClient(token=token)

    print("Creating household for bulk delete test...")
    household_data, household_status = create_household_full(token, client)
    assert household_status in [200, 202], f"Household creation failed with status: {household_status}"
    household_id = household_data["id"]
    print(f"Household created with ID: {household_id}")

    print("Bulk deleting household...")
    response = delete_household_bulk(token, client, household_data)
    assert response.status_code == 202, f"Household bulk delete failed: {response.text}"
    print(f"Household {household_id} bulk deleted successfully (202 accepted)")


@pytest.mark.positive
def test_delete_household_member():
    """Test to delete a household member. Creates all dependencies internally first, then deletes it."""
    token = get_auth_token("user")
    client = APIClient(token=token)

    # Step 1: Create household
    print("Creating household...")
    household_data, household_status = create_household_full(token, client)
    assert household_status in [200, 202], f"Household creation failed with status: {household_status}"
    household_id = household_data['id']
    household_client_ref_id = household_data['clientReferenceId']
    print(f"Household created with ID: {household_id}")

    # Step 2: Create individual
    print("Creating individual...")
    individual_id, individual_client_ref_id, _, individual_status = create_individual(token, client)
    assert individual_status in [200, 202], f"Individual creation failed with status: {individual_status}"
    print(f"Individual created with ID: {individual_id}")

    # Step 3: Create household member
    print("Creating household member...")
    member_data, member_status = create_household_member_full(token, client, household_id, household_client_ref_id, individual_id, individual_client_ref_id)
    assert member_status in [200, 202], f"Household Member creation failed with status: {member_status}"
    member_id = member_data['id']
    print(f"Household Member created with ID: {member_id}")

    # Step 4: Delete the household member
    print("Deleting household member...")
    response = delete_household_member(token, client, member_data)
    assert response.status_code in [200, 202], f"Household Member delete failed: {response.text}"

    # Step 5: Verify deletion
    deleted_member = response.json()["HouseholdMember"]
    assert deleted_member["isDeleted"] == True, f"Household Member not marked as deleted"
    print(f"Household Member {member_id} deleted successfully")


@pytest.mark.positive
def test_create_household_member_bulk():
    """Test to bulk create a household member. Asserts 202, then verifies via search by clientReferenceId."""
    token = get_auth_token("user")
    client = APIClient(token=token)

    print("Creating household...")
    household_data, household_status = create_household_full(token, client)
    assert household_status in [200, 202], f"Household creation failed with status: {household_status}"
    household_id = household_data["id"]
    household_client_ref_id = household_data["clientReferenceId"]
    print(f"Household created with ID: {household_id}")

    print("Creating individual...")
    individual_id, individual_client_ref_id, _, individual_status = create_individual(token, client)
    assert individual_status in [200, 202], f"Individual creation failed with status: {individual_status}"
    print(f"Individual created with ID: {individual_id}")

    print("Bulk creating household member...")
    client_ref_id, status_code = create_household_member_bulk(
        token, client, household_id, household_client_ref_id, individual_id, individual_client_ref_id
    )
    assert status_code == 202, f"Household Member bulk creation failed with status: {status_code}"
    print("Bulk create accepted with 202")

    members = poll_until_found(lambda: search_household_member_by_client_ref(token, client, client_ref_id))
    assert members, f"No household member found with clientReferenceId {client_ref_id} after bulk create"
    assert members[0]["clientReferenceId"] == client_ref_id
    print(f"Verified: household member with clientReferenceId {client_ref_id} found in search results")


@pytest.mark.positive
def test_update_household_member_bulk():
    """Test bulk updating a non-head household member to become the head (isHeadOfHousehold: False → True).
    Creates a household with a head member first, then adds a second non-head member and bulk promotes it."""
    token = get_auth_token("user")
    client = APIClient(token=token)

    print("Creating household...")
    household_data, household_status = create_household_full(token, client)
    assert household_status in [200, 202], f"Household creation failed with status: {household_status}"
    household_id = household_data["id"]
    household_client_ref_id = household_data["clientReferenceId"]
    print(f"Household created with ID: {household_id}")

    print("Creating first individual (head member)...")
    head_individual_id, head_individual_client_ref_id, _, head_status = create_individual(token, client)
    assert head_status in [200, 202], f"Head individual creation failed: {head_status}"
    create_household_member_full(token, client, household_id, household_client_ref_id, head_individual_id, head_individual_client_ref_id, is_head=True)
    print("Head member created.")

    print("Creating second individual (non-head member)...")
    individual_id, individual_client_ref_id, _, individual_status = create_individual(token, client)
    assert individual_status in [200, 202], f"Individual creation failed with status: {individual_status}"
    print(f"Individual created with ID: {individual_id}")

    print("Creating non-head household member...")
    member_data, member_status = create_household_member_full(
        token, client, household_id, household_client_ref_id, individual_id, individual_client_ref_id, is_head=False
    )
    assert member_status in [200, 202], f"Household Member creation failed with status: {member_status}"
    print(f"Non-head member created with ID: {member_data['id']}, isHeadOfHousehold: {member_data['isHeadOfHousehold']}")

    print("Bulk updating household member isHeadOfHousehold to True...")
    response = update_household_member_bulk(token, client, member_data, new_is_head=True)
    assert response.status_code == 202, f"Household Member bulk update failed: {response.text}"
    print("Bulk update accepted with 202")

    members = poll_until_found(lambda: search_household_member_by_client_ref(token, client, member_data["clientReferenceId"]))
    assert members, f"Household Member not found after bulk update"
    assert members[0]["isHeadOfHousehold"] == True, f"isHeadOfHousehold not updated. Got {members[0].get('isHeadOfHousehold')}"
    print("Household Member bulk updated successfully. isHeadOfHousehold verified as True.")


@pytest.mark.positive
def test_delete_household_member_bulk():
    """Test to bulk delete a household member. Creates all dependencies first, then bulk deletes it."""
    token = get_auth_token("user")
    client = APIClient(token=token)

    print("Creating household...")
    household_data, household_status = create_household_full(token, client)
    assert household_status in [200, 202], f"Household creation failed with status: {household_status}"
    household_id = household_data["id"]
    household_client_ref_id = household_data["clientReferenceId"]
    print(f"Household created with ID: {household_id}")

    print("Creating individual...")
    individual_id, individual_client_ref_id, _, individual_status = create_individual(token, client)
    assert individual_status in [200, 202], f"Individual creation failed with status: {individual_status}"
    print(f"Individual created with ID: {individual_id}")

    print("Creating household member (regular create to get full data)...")
    member_data, member_status = create_household_member_full(
        token, client, household_id, household_client_ref_id, individual_id, individual_client_ref_id
    )
    assert member_status in [200, 202], f"Household Member creation failed with status: {member_status}"
    member_id = member_data["id"]
    print(f"Household Member created with ID: {member_id}")

    print("Bulk deleting household member...")
    response = delete_household_member_bulk(token, client, member_data)
    assert response.status_code == 202, f"Household Member bulk delete failed: {response.text}"
    print(f"Household Member {member_id} bulk deleted successfully (202 accepted)")


# --- Helper function ---

def create_household(token, client, tenant_id=None):
    """
    Create a household.

    Args:
        tenant_id: Pass None to use default, or provide custom tenantId for negative testing
    """
    payload = load_payload("household", "create_household.json")

    # Inject dynamic values
    payload["Household"]["clientReferenceId"] = str(uuid.uuid4())
    payload["Household"]["address"]["clientReferenceId"] = str(uuid.uuid4())
    payload["Household"]["address"]["locality"]["code"] = boundaryCode
    selected_type = random.choice(structure_data["houseStructureTypes"])
    payload["Household"]["additionalFields"]["fields"][0]["value"] = selected_type
    payload["RequestInfo"] = get_request_info(token)

    effective_tenant = tenant_id if tenant_id is not None else tenantId
    payload["Household"]["tenantId"] = effective_tenant
    payload["Household"]["address"]["tenantId"] = effective_tenant

    # Make the API call
    response = client.post("/household/v1/_create", payload)

    # For negative tests, return response directly
    if tenant_id is not None:
        return response

    # Handle error if status is not success
    if response.status_code not in [200, 202]:
        raise Exception(f"Household creation failed with status {response.status_code}: {response.text}")

    household_data = response.json()["Household"]
    household_id = household_data["id"]
    household_client_reference_id = household_data["clientReferenceId"]

    # Return all desired values including status_code
    return household_id, household_client_reference_id, response.status_code


def create_household_member(token, client, household_id="create", household_client_ref_id="create",
                            individual_id="create", individual_client_ref_id="create", tenant_id=None):
    """
    Create a household member.

    Args:
        household_id: Pass None to skip, "create" to create new, or provide existing ID
        household_client_ref_id: Pass None to skip, "create" to create new, or provide existing ID
        individual_id: Pass None to skip, "create" to create new, or provide existing ID
        individual_client_ref_id: Pass None to skip, "create" to create new, or provide existing ID
        tenant_id: Pass None to use default, or provide custom tenantId for negative testing
    """
    # Create or use provided household
    if household_id == "create":
        householdId, householdClientReferenceId, _ = create_household(token, client)
    else:
        householdId = household_id
        householdClientReferenceId = household_client_ref_id

    # Create or use provided individual
    if individual_id == "create":
        individualId, individualClientReferenceId, _, _ = create_individual(token, client)
    else:
        individualId = individual_id
        individualClientReferenceId = individual_client_ref_id

    payload = load_payload("household", "create_householdMember.json")

    payload["HouseholdMember"]["clientReferenceId"] = str(uuid.uuid4())
    payload["HouseholdMember"]["householdId"] = householdId
    payload["HouseholdMember"]["householdClientReferenceId"] = householdClientReferenceId
    payload["HouseholdMember"]["individualId"] = individualId
    payload["HouseholdMember"]["individualClientReferenceId"] = individualClientReferenceId
    payload["RequestInfo"] = get_request_info(token)

    payload["HouseholdMember"]["tenantId"] = tenant_id if tenant_id is not None else tenantId

    res = client.post("/household/member/v1/_create", payload)
    return res


def update_household(token, client, household_data, new_member_count):
    """
    Update a household's memberCount.

    Args:
        household_data: Full household object from search
        new_member_count: New memberCount value to set
    """
    payload = load_payload("household", "update_household.json")

    # Copy required fields from the searched household
    payload["Household"]["id"] = household_data["id"]
    payload["Household"]["tenantId"] = household_data["tenantId"]
    payload["Household"]["clientReferenceId"] = household_data["clientReferenceId"]
    payload["Household"]["rowVersion"] = household_data["rowVersion"]
    payload["Household"]["auditDetails"] = household_data["auditDetails"]
    payload["Household"]["clientAuditDetails"] = household_data.get("clientAuditDetails")
    payload["Household"]["address"] = household_data["address"]
    payload["Household"]["memberCount"] = new_member_count
    payload["RequestInfo"] = get_request_info(token)

    response = client.post("/household/v1/_update", payload)
    return response


def update_household_member(token, client, member_data, new_is_head):
    """
    Update a household member's isHeadOfHousehold status.

    Args:
        member_data: Full household member object from search
        new_is_head: New isHeadOfHousehold value to set
    """
    payload = load_payload("household", "update_householdMember.json")

    # Copy required fields from the searched member
    payload["HouseholdMember"]["id"] = member_data["id"]
    payload["HouseholdMember"]["tenantId"] = member_data["tenantId"]
    payload["HouseholdMember"]["clientReferenceId"] = member_data["clientReferenceId"]
    payload["HouseholdMember"]["rowVersion"] = member_data["rowVersion"]
    payload["HouseholdMember"]["auditDetails"] = member_data["auditDetails"]
    payload["HouseholdMember"]["clientAuditDetails"] = member_data.get("clientAuditDetails")
    payload["HouseholdMember"]["householdId"] = member_data["householdId"]
    payload["HouseholdMember"]["householdClientReferenceId"] = member_data["householdClientReferenceId"]
    payload["HouseholdMember"]["individualId"] = member_data["individualId"]
    payload["HouseholdMember"]["individualClientReferenceId"] = member_data["individualClientReferenceId"]
    payload["HouseholdMember"]["isHeadOfHousehold"] = new_is_head
    payload["RequestInfo"] = get_request_info(token)

    response = client.post("/household/member/v1/_update", payload)
    return response


def create_household_full(token, client):
    """
    Create a household and return full data for delete operations.

    Returns:
        Tuple of (household_data, status_code)
    """
    payload = load_payload("household", "create_household.json")

    # Inject dynamic values
    payload["Household"]["clientReferenceId"] = str(uuid.uuid4())
    payload["Household"]["address"]["clientReferenceId"] = str(uuid.uuid4())
    payload["Household"]["address"]["locality"]["code"] = boundaryCode
    selected_type = random.choice(structure_data["houseStructureTypes"])
    payload["Household"]["additionalFields"]["fields"][0]["value"] = selected_type
    payload["RequestInfo"] = get_request_info(token)

    payload["Household"]["tenantId"] = tenantId
    payload["Household"]["address"]["tenantId"] = tenantId

    response = client.post("/household/v1/_create", payload)

    if response.status_code not in [200, 202]:
        raise Exception(f"Household creation failed with status {response.status_code}: {response.text}")

    return response.json()["Household"], response.status_code


def delete_household(token, client, household_data):
    """
    Delete a household (soft delete by setting isDeleted=true).

    Args:
        household_data: Full household object from create response
    """
    payload = load_payload("household", "delete_household.json")

    # Copy required fields from the created household
    payload["Household"]["id"] = household_data["id"]
    payload["Household"]["tenantId"] = household_data["tenantId"]
    payload["Household"]["clientReferenceId"] = household_data["clientReferenceId"]
    payload["Household"]["rowVersion"] = household_data["rowVersion"]
    payload["Household"]["auditDetails"] = household_data["auditDetails"]
    payload["Household"]["clientAuditDetails"] = household_data.get("clientAuditDetails")
    payload["Household"]["address"] = household_data["address"]
    payload["Household"]["memberCount"] = household_data.get("memberCount", 1)
    payload["Household"]["isDeleted"] = True
    payload["RequestInfo"] = get_request_info(token)

    response = client.post("/household/v1/_delete", payload)
    return response


def create_household_member_full(token, client, household_id, household_client_ref_id, individual_id, individual_client_ref_id, is_head=True):
    """
    Create a household member and return full data for delete operations.

    Returns:
        Tuple of (household_member_data, status_code)
    """
    payload = load_payload("household", "create_householdMember.json")
    payload["HouseholdMember"]["clientReferenceId"] = str(uuid.uuid4())
    payload["HouseholdMember"]["householdId"] = household_id
    payload["HouseholdMember"]["householdClientReferenceId"] = household_client_ref_id
    payload["HouseholdMember"]["individualId"] = individual_id
    payload["HouseholdMember"]["individualClientReferenceId"] = individual_client_ref_id
    payload["HouseholdMember"]["isHeadOfHousehold"] = is_head
    payload["RequestInfo"] = get_request_info(token)

    response = client.post("/household/member/v1/_create", payload)

    if response.status_code not in [200, 202]:
        raise Exception(f"Household Member creation failed with status {response.status_code}: {response.text}")

    return response.json()["HouseholdMember"], response.status_code


def delete_household_member(token, client, member_data):
    """
    Delete a household member (soft delete by setting isDeleted=true).

    Args:
        member_data: Full household member object from create response
    """
    payload = load_payload("household", "delete_householdMember.json")

    # Copy required fields from the created member
    payload["HouseholdMember"]["id"] = member_data["id"]
    payload["HouseholdMember"]["tenantId"] = member_data["tenantId"]
    payload["HouseholdMember"]["clientReferenceId"] = member_data["clientReferenceId"]
    payload["HouseholdMember"]["rowVersion"] = member_data["rowVersion"]
    payload["HouseholdMember"]["auditDetails"] = member_data["auditDetails"]
    payload["HouseholdMember"]["clientAuditDetails"] = member_data.get("clientAuditDetails")
    payload["HouseholdMember"]["householdId"] = member_data["householdId"]
    payload["HouseholdMember"]["householdClientReferenceId"] = member_data["householdClientReferenceId"]
    payload["HouseholdMember"]["individualId"] = member_data["individualId"]
    payload["HouseholdMember"]["individualClientReferenceId"] = member_data["individualClientReferenceId"]
    payload["HouseholdMember"]["isHeadOfHousehold"] = member_data.get("isHeadOfHousehold", False)
    payload["HouseholdMember"]["isDeleted"] = True
    payload["RequestInfo"] = get_request_info(token)

    response = client.post("/household/member/v1/_delete", payload)
    return response


def create_household_bulk(token, client):
    payload = load_payload("household", "create_bulk_household.json")
    payload["RequestInfo"] = get_request_info(token)
    client_ref_id = str(uuid.uuid4())
    payload["Households"][0]["clientReferenceId"] = client_ref_id
    payload["Households"][0]["address"]["clientReferenceId"] = str(uuid.uuid4())
    payload["Households"][0]["tenantId"] = tenantId
    payload["Households"][0]["address"]["tenantId"] = tenantId

    response = client.post("/household/v1/bulk/_create", payload)

    if response.status_code not in [200, 202]:
        raise Exception(f"Household bulk create failed with status {response.status_code}: {response.text}")

    return client_ref_id, response.status_code


def update_household_bulk(token, client, household_data, new_member_count):
    payload = load_payload("household", "update_bulk_household.json")
    payload["RequestInfo"] = get_request_info(token)
    payload["Households"][0]["id"] = household_data["id"]
    payload["Households"][0]["tenantId"] = household_data["tenantId"]
    payload["Households"][0]["clientReferenceId"] = household_data["clientReferenceId"]
    payload["Households"][0]["rowVersion"] = household_data["rowVersion"]
    payload["Households"][0]["auditDetails"] = household_data["auditDetails"]
    payload["Households"][0]["clientAuditDetails"] = household_data.get("clientAuditDetails")
    payload["Households"][0]["address"] = household_data["address"]
    payload["Households"][0]["memberCount"] = new_member_count
    payload["Households"][0]["isDeleted"] = False

    response = client.post("/household/v1/bulk/_update", payload)
    return response


def delete_household_bulk(token, client, household_data):
    payload = load_payload("household", "delete_bulk_household.json")
    payload["RequestInfo"] = get_request_info(token)
    payload["Households"][0]["id"] = household_data["id"]
    payload["Households"][0]["tenantId"] = household_data["tenantId"]
    payload["Households"][0]["clientReferenceId"] = household_data["clientReferenceId"]
    payload["Households"][0]["rowVersion"] = household_data["rowVersion"]
    payload["Households"][0]["auditDetails"] = household_data["auditDetails"]
    payload["Households"][0]["clientAuditDetails"] = household_data.get("clientAuditDetails")
    payload["Households"][0]["address"] = household_data["address"]
    payload["Households"][0]["memberCount"] = household_data.get("memberCount", 1)
    payload["Households"][0]["isDeleted"] = True

    response = client.post("/household/v1/bulk/_delete", payload)
    return response


def search_household_by_client_ref(token, client, client_ref_id):
    payload = load_payload("household", "search_household.json")
    payload["RequestInfo"] = get_request_info(token)
    payload["Household"] = {"clientReferenceId": [client_ref_id]}

    url = f"/household/v1/_search?tenantId={tenantId}&limit={search_limit}&offset={search_offset}"
    response = client.post(url, payload)

    if response.status_code not in [200, 202]:
        raise Exception(f"Household search failed with status {response.status_code}: {response.text}")

    return response.json().get("Households", [])


def create_household_member_bulk(token, client, household_id, household_client_ref_id, individual_id, individual_client_ref_id):
    payload = load_payload("household", "create_bulk_householdMember.json")
    payload["RequestInfo"] = get_request_info(token)
    client_ref_id = str(uuid.uuid4())
    payload["HouseholdMembers"][0]["clientReferenceId"] = client_ref_id
    payload["HouseholdMembers"][0]["tenantId"] = tenantId
    payload["HouseholdMembers"][0]["householdId"] = household_id
    payload["HouseholdMembers"][0]["householdClientReferenceId"] = household_client_ref_id
    payload["HouseholdMembers"][0]["individualId"] = individual_id
    payload["HouseholdMembers"][0]["individualClientReferenceId"] = individual_client_ref_id

    response = client.post("/household/member/v1/bulk/_create", payload)

    if response.status_code not in [200, 202]:
        raise Exception(f"Household Member bulk create failed with status {response.status_code}: {response.text}")

    return client_ref_id, response.status_code


def update_household_member_bulk(token, client, member_data, new_is_head):
    payload = load_payload("household", "update_bulk_householdMember.json")
    payload["RequestInfo"] = get_request_info(token)
    payload["HouseholdMembers"][0]["id"] = member_data["id"]
    payload["HouseholdMembers"][0]["tenantId"] = member_data["tenantId"]
    payload["HouseholdMembers"][0]["clientReferenceId"] = member_data["clientReferenceId"]
    payload["HouseholdMembers"][0]["rowVersion"] = member_data["rowVersion"]
    payload["HouseholdMembers"][0]["auditDetails"] = member_data["auditDetails"]
    payload["HouseholdMembers"][0]["clientAuditDetails"] = member_data.get("clientAuditDetails")
    payload["HouseholdMembers"][0]["householdId"] = member_data["householdId"]
    payload["HouseholdMembers"][0]["householdClientReferenceId"] = member_data["householdClientReferenceId"]
    payload["HouseholdMembers"][0]["individualId"] = member_data["individualId"]
    payload["HouseholdMembers"][0]["individualClientReferenceId"] = member_data["individualClientReferenceId"]
    payload["HouseholdMembers"][0]["isHeadOfHousehold"] = new_is_head
    payload["HouseholdMembers"][0]["isDeleted"] = False

    response = client.post("/household/member/v1/bulk/_update", payload)
    return response


def delete_household_member_bulk(token, client, member_data):
    payload = load_payload("household", "delete_bulk_householdMember.json")
    payload["RequestInfo"] = get_request_info(token)
    payload["HouseholdMembers"][0]["id"] = member_data["id"]
    payload["HouseholdMembers"][0]["tenantId"] = member_data["tenantId"]
    payload["HouseholdMembers"][0]["clientReferenceId"] = member_data["clientReferenceId"]
    payload["HouseholdMembers"][0]["rowVersion"] = member_data["rowVersion"]
    payload["HouseholdMembers"][0]["auditDetails"] = member_data["auditDetails"]
    payload["HouseholdMembers"][0]["clientAuditDetails"] = member_data.get("clientAuditDetails")
    payload["HouseholdMembers"][0]["householdId"] = member_data["householdId"]
    payload["HouseholdMembers"][0]["householdClientReferenceId"] = member_data["householdClientReferenceId"]
    payload["HouseholdMembers"][0]["individualId"] = member_data["individualId"]
    payload["HouseholdMembers"][0]["individualClientReferenceId"] = member_data["individualClientReferenceId"]
    payload["HouseholdMembers"][0]["isHeadOfHousehold"] = member_data.get("isHeadOfHousehold", False)
    payload["HouseholdMembers"][0]["isDeleted"] = True

    response = client.post("/household/member/v1/bulk/_delete", payload)
    return response


def search_household_member_by_client_ref(token, client, client_ref_id):
    payload = load_payload("household", "search_householdMember.json")
    payload["RequestInfo"] = get_request_info(token)
    payload["HouseholdMember"] = {"clientReferenceId": [client_ref_id]}

    url = f"/household/member/v1/_search?tenantId={tenantId}&limit={search_limit}&offset={search_offset}"
    response = client.post(url, payload)

    if response.status_code not in [200, 202]:
        raise Exception(f"Household Member search failed with status {response.status_code}: {response.text}")

    return response.json().get("HouseholdMembers", [])