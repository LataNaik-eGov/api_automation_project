import pytest
from utils.api_client import APIClient
from utils.data_loader import load_payload
from utils.auth import get_auth_token
from utils.request_info import get_request_info
from utils.config import tenantId, hierarchyType, invalidTenantId


@pytest.mark.positive
def test_search_boundary():
    token = get_auth_token("user")
    client = APIClient(token=token)

    res = search_boundary_data(token, client, tenantId, hierarchyType)
    assert res.status_code == 200, f"Boundary search failed: {res.text}"

    data = res.json()
    tenant_boundaries = data.get("TenantBoundary", [])
    assert tenant_boundaries, "No TenantBoundary found in response"

    boundaries = tenant_boundaries[0].get("boundary", [])
    assert boundaries, "No boundary data found in TenantBoundary"

    boundary_info = collect_boundary_info(boundaries)
    assert boundary_info, "No boundary info collected from response"

    print("\n--- Boundary Hierarchy ---")
    for b_type, code in boundary_info:
        print(f"{b_type}: {code}")

    # Save to file
    with open("output/boundaries.txt", "w") as f:
        f.write("--- Boundary Hierarchy ---\n")
        for b_type, code in boundary_info:
            f.write(f"{b_type}: {code}\n")


@pytest.mark.positive
def test_fetch_boundary_codes_per_level():
    """Fetch the first boundary code at each level of the hierarchy and save to ids.txt."""
    token = get_auth_token("user")
    client = APIClient(token=token)

    res = search_boundary_data(token, client, tenantId, hierarchyType)
    assert res.status_code == 200, f"Boundary search failed: {res.text}"

    tenant_boundaries = res.json().get("TenantBoundary", [])
    assert tenant_boundaries, "No TenantBoundary found in response"

    boundaries_tree = tenant_boundaries[0].get("boundary", [])
    assert boundaries_tree, "No boundary data found"

    # Follow the first child at each depth to get one code per level
    levels = []
    current = boundaries_tree
    while current:
        first = current[0]
        levels.append((first.get("boundaryType"), first.get("code")))
        current = first.get("children") or []

    assert levels, "Could not extract any boundary levels"

    print(f"\nBoundary codes per level ({len(levels)} levels):")
    for btype, code in levels:
        print(f"  {btype}: {code}")

    with open("output/ids.txt", "a") as f:
        f.write("\n--- Boundary Codes Per Level ---\n")
        for btype, code in levels:
            f.write(f"Boundary {btype}: {code}\n")


@pytest.mark.negative
def test_search_boundary_with_invalid_tenant_id():
    """Negative test: Searching boundary with invalid tenantId should fail"""
    token = get_auth_token("user")
    client = APIClient(token=token)

    payload = load_payload("boundary", "search_boundary.json")
    payload["RequestInfo"] = get_request_info(token)

    url = (
        f"/boundary-service/boundary-relationships/_search"
        f"?tenantId={invalidTenantId}&includeChildren=true"
        f"&hierarchyType={hierarchyType}"
    )

    response = client.post(url, payload)

    assert response.status_code in [400, 401, 403], f"Expected error status code, got: {response.status_code}"
    print(f"Search correctly rejected with status: {response.status_code}")


def collect_boundary_info(boundaries, results=None):
    if results is None:
        results = []
    for b in boundaries:
        results.append((b.get("boundaryType"), b.get("code")))
        if "children" in b and b["children"]:
            collect_boundary_info(b["children"], results)
    return results


def search_boundary_data(token, client, tenant_id, hierarchy_type):
    """Search the full boundary tree for a hierarchy, starting at its actual root.

    boundaryType is intentionally omitted: root-level names differ across
    hierarchies (e.g. COUNTRY, PAYS), and the API returns the full tree from
    the true root when it's left unset.
    """
    payload = load_payload("boundary", "search_boundary.json")
    payload["RequestInfo"] = get_request_info(token)

    url = (
        f"/boundary-service/boundary-relationships/_search"
        f"?tenantId={tenant_id}&includeChildren=true"
        f"&hierarchyType={hierarchy_type}"
    )

    response = client.post(url, payload)
    return response
