import uuid
import random
import string
import pytest
from datetime import datetime, timedelta
from utils.api_client import APIClient
from utils.data_loader import load_payload
from utils.auth import get_auth_token
from utils.request_info import get_request_info
from utils.search_helpers import search_entity, extract_id_from_file, extract_boundary_levels_from_file, poll_until_found, poll_until_match
from utils.config import project, boundaryType, boundaryCode, tenantId, invalidTenantId, hierarchyType, hrms
from tests.test_individual_service import create_individual
from tests.test_household_service import create_household, create_household_member
from tests.test_product_service import create_product, create_product_variant
from tests.test_facility_service import create_facility


# --- Test functions ---

@pytest.mark.positive
def test_create_project():
    token = get_auth_token("user")
    client = APIClient(token=token)

    # Create first facility
    facility_response_1 = create_facility(token, client)
    assert facility_response_1.status_code in [200, 202], f"Facility 1 creation failed: {facility_response_1.text}"
    facility_id_1 = facility_response_1.json()["Facility"]["id"]

    # Create second facility
    facility_response_2 = create_facility(token, client)
    assert facility_response_2.status_code in [200, 202], f"Facility 2 creation failed: {facility_response_2.text}"
    facility_id_2 = facility_response_2.json()["Facility"]["id"]

    # Create first product variant
    variant_response_1 = create_product_variant(token, client)
    assert variant_response_1.status_code in [200, 202], f"Product Variant 1 creation failed: {variant_response_1.text}"
    variant_id_1 = variant_response_1.json()["ProductVariant"][0]["id"]

    # Create second product variant
    variant_response_2 = create_product_variant(token, client)
    assert variant_response_2.status_code in [200, 202], f"Product Variant 2 creation failed: {variant_response_2.text}"
    variant_id_2 = variant_response_2.json()["ProductVariant"][0]["id"]

    project_id, status_code = create_individual_project(token, client, boundaryType, boundaryCode, variant_id_1, variant_id_2)
    assert status_code in [200, 202], f"Project creation failed with status: {status_code}"

    # Create project resource mapping for first variant
    resource_id_1, resource_status_1 = create_project_resource(token, client, project_id, variant_id_1)
    assert resource_status_1 in [200, 202], f"Project Resource 1 creation failed with status: {resource_status_1}"

    # Create project resource mapping for second variant
    resource_id_2, resource_status_2 = create_project_resource(token, client, project_id, variant_id_2)
    assert resource_status_2 in [200, 202], f"Project Resource 2 creation failed with status: {resource_status_2}"

    # Create project facility mapping for first facility
    project_facility_id_1, facility_status_1 = create_project_facility(token, client, project_id, facility_id_1)
    assert facility_status_1 in [200, 202], f"Project Facility 1 creation failed with status: {facility_status_1}"

    # Create project facility mapping for second facility
    project_facility_id_2, facility_status_2 = create_project_facility(token, client, project_id, facility_id_2)
    assert facility_status_2 in [200, 202], f"Project Facility 2 creation failed with status: {facility_status_2}"

    print("Project created with ID:", project_id)
    print("Project Resource 1 created with ID:", resource_id_1)
    print("Project Resource 2 created with ID:", resource_id_2)
    print("Project Facility 1 created with ID:", project_facility_id_1)
    print("Project Facility 2 created with ID:", project_facility_id_2)

    with open("output/ids.txt", "a") as f:
        f.write("\n--- Project details ---\n")
        f.write(f"Project ID: {project_id}\n")
        f.write(f"Project Resource ID 1: {resource_id_1}\n")
        f.write(f"Project Resource ID 2: {resource_id_2}\n")
        f.write(f"Project Facility ID 1: {project_facility_id_1}\n")
        f.write(f"Project Facility ID 2: {project_facility_id_2}\n")


def _extract_one_per_level(boundaries_tree):
    """Walk the boundary tree following the first child at each depth.
    Returns an ordered list of (boundaryType, code) — one entry per level."""
    levels = []
    current = boundaries_tree
    while current:
        first = current[0]
        levels.append((first.get("boundaryType"), first.get("code")))
        current = first.get("children") or []
    return levels


def _create_campaign_employee(token, client, role_code, role_name, btype, bcode, prefix="CAMP", extra_roles=None):
    """Create an HRMS employee with a primary role (and optional extra roles) at the given boundary level.
    Returns (userServiceUuid, userName) needed for project staff creation."""
    payload = load_payload("hrms", "create_hrms.json")
    payload["RequestInfo"] = get_request_info(token)

    unique_code = f"{prefix}-" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    mobile = str(random.randint(7000000000, 9999999999))

    payload["Employees"][0]["code"] = unique_code
    payload["Employees"][0]["tenantId"] = tenantId
    payload["Employees"][0]["user"]["userName"] = unique_code
    payload["Employees"][0]["user"]["name"] = f"{role_name}-{suffix}"
    payload["Employees"][0]["user"]["mobileNumber"] = mobile
    payload["Employees"][0]["user"]["emailId"] = f"{unique_code.lower()}@campaign.test"
    payload["Employees"][0]["user"]["tenantId"] = tenantId

    primary = {"code": role_code, "name": role_name, "tenantId": tenantId,
               "labelKey": f"ACCESSCONTROL_ROLES_ROLES_{role_code}"}
    jurisdiction_roles = [primary] + [
        {"code": r["code"], "name": r["name"], "tenantId": tenantId,
         "labelKey": f"ACCESSCONTROL_ROLES_ROLES_{r['code']}"}
        for r in (extra_roles or [])
    ]
    user_roles = [{"code": r["code"], "name": r["name"], "tenantId": tenantId}
                  for r in jurisdiction_roles]

    payload["Employees"][0]["jurisdictions"] = [{
        "hierarchy": hierarchyType,
        "boundaryType": btype,
        "boundary": bcode,
        "tenantId": tenantId,
        "roles": jurisdiction_roles
    }]
    payload["Employees"][0]["user"]["roles"] = user_roles

    url = f"/{hrms}/employees/_create?tenantId={tenantId}"
    response = client.post(url, payload)

    if response.status_code not in [200, 202]:
        raise Exception(f"Employee ({role_code}) creation failed: {response.text}")

    emp = response.json()["Employees"][0]
    return emp["user"]["userServiceUuid"], emp["user"]["userName"]


def _compute_cycle_dates(num_cycles):
    """Compute cycle start/end dates in epoch milliseconds.
    Cycle 1 starts tomorrow; each cycle is 10 days; next cycle starts day after previous ends."""
    tomorrow = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    dates = []
    cycle_start = tomorrow
    for _ in range(max(num_cycles, 1)):
        cycle_end = cycle_start + timedelta(days=10)
        dates.append((int(cycle_start.timestamp() * 1000), int(cycle_end.timestamp() * 1000)))
        cycle_start = cycle_end
    return dates


def _apply_cycle_dates(payload, cycle_dates):
    """Patch the cycles array in a project payload with computed dates.
    Extends or trims the cycles list to match the number of computed cycles."""
    cycles = payload["Projects"][0]["additionalDetails"]["projectType"].get("cycles", [])
    template = cycles[0].copy() if cycles else {}
    while len(cycles) < len(cycle_dates):
        cycles.append(template.copy())
    for j, (cs, ce) in enumerate(cycle_dates):
        cycles[j]["startDate"] = cs
        cycles[j]["endDate"] = ce
    payload["Projects"][0]["additionalDetails"]["projectType"]["cycles"] = cycles[:len(cycle_dates)]
    payload["Projects"][0]["startDate"] = cycle_dates[0][0]
    payload["Projects"][0]["endDate"] = cycle_dates[-1][1]


@pytest.mark.positive
def test_configure_campaign_MR_DN():
    """Fetches boundary hierarchy, creates one MR-DN project per level (top→bottom),
    then creates one facility per top-5 level using that level's boundary code,
    and maps each facility to the corresponding level's project."""
    token = get_auth_token("user")
    client = APIClient(token=token)

    # Step 1: Fetch boundary hierarchy directly and extract one code per level
    from tests.test_boundary_service import search_boundary_data
    res = search_boundary_data(token, client, tenantId, hierarchyType)
    assert res.status_code == 200, f"Boundary search failed: {res.text}"

    tenant_boundaries = res.json().get("TenantBoundary", [])
    assert tenant_boundaries, "No TenantBoundary found in response"

    boundaries_tree = tenant_boundaries[0].get("boundary", [])
    assert boundaries_tree, "No boundary data found in response"

    levels = _extract_one_per_level(boundaries_tree)
    assert levels, "Could not extract boundary levels from hierarchy"

    print(f"\nBoundary hierarchy has {len(levels)} levels:")
    for btype, code in levels:
        print(f"  {btype}: {code}")

    # Step 2: Fetch MR-DN project type from MDMS
    project_types = _fetch_project_types()
    mrdn_types = [(tid, tcode, nc, data) for tid, tcode, nc, data in project_types if tcode.upper() == "MR-DN"]
    assert mrdn_types, "MR-DN project type not found in active MDMS project types"
    is_mrdn = True
    projectTypeId, _, num_cycles, mrdn_data = mrdn_types[0]

    cycle_dates = _compute_cycle_dates(num_cycles)
    print(f"  Project type: MR-DN | projectTypeId={projectTypeId} | cycles: {num_cycles}")

    # Create one project per level from top down, chaining immediate parent ID
    project_ids = []

    for i, (btype, code) in enumerate(levels):
        parent = project_ids[-1] if project_ids else None

        payload = load_payload("project", "create_individual_project.json")
        payload["RequestInfo"] = get_request_info(token)
        payload["Projects"][0]["tenantId"] = tenantId
        payload["Projects"][0]["projectTypeId"] = projectTypeId
        payload["Projects"][0]["projectType"] = "MR-DN"
        payload["Projects"][0]["projectSubType"] = "MR-DN"
        payload["Projects"][0]["additionalDetails"]["projectType"] = mrdn_data.copy()
        payload["Projects"][0]["address"]["tenantId"] = tenantId
        payload["Projects"][0]["address"]["boundaryType"] = btype
        payload["Projects"][0]["address"]["boundary"] = code
        payload["Projects"][0]["address"]["locality"]["code"] = code
        payload["Projects"][0]["parent"] = parent
        _apply_cycle_dates(payload, cycle_dates)

        url = f"/{project}/v1/_create"
        response = client.post(url, payload)

        assert response.status_code in [200, 202], \
            f"Project creation failed at level {i} ({btype} / {code}), parent={parent}: {response.text}"

        project_id = response.json()["Project"][0]["id"]
        project_ids.append(project_id)
        print(f"  Level {i} ({btype}): project_id={project_id}  parent={parent}")

    print(f"\nProject hierarchy created across {len(levels)} levels")

    # Step 3: Create one facility at each of the top 5 boundary levels
    top5 = levels[:5]
    facility_ids = []

    print(f"\nCreating facilities at top {len(top5)} boundary levels:")
    for i, (btype, code) in enumerate(top5):
        fac_payload = load_payload("facility", "create_facility.json")
        fac_payload["RequestInfo"] = get_request_info(token)
        fac_payload["Facility"]["clientReferenceId"] = str(uuid.uuid4())
        fac_payload["Facility"]["tenantId"] = tenantId
        fac_payload["Facility"]["address"]["tenantId"] = tenantId
        fac_payload["Facility"]["address"]["locality"]["code"] = code

        fac_res = client.post("/facility/v1/_create", fac_payload)
        assert fac_res.status_code in [200, 202], \
            f"Facility creation failed at level {i} ({btype} / {code}): {fac_res.text}"

        facility_id = fac_res.json()["Facility"]["id"]
        facility_ids.append(facility_id)
        print(f"  Level {i} ({btype}): facility_id={facility_id}")

    # Step 4: Map each facility to the project at the same boundary level
    project_facility_ids = []

    print(f"\nCreating project-facility mappings for top {len(top5)} levels:")
    for i, (facility_id, project_id) in enumerate(zip(facility_ids, project_ids[:5])):
        btype = top5[i][0]
        pf_id, _ = create_project_facility(token, client, project_id, facility_id)
        project_facility_ids.append(pf_id)
        print(f"  Level {i} ({btype}): project_facility_id={pf_id}")

    # Step 5: Create users per level and map as project staff
    print("\nCreating campaign users and project staff:")

    # Warehouse Manager at top 5 levels (skips the last level of the hierarchy)
    for i, (btype, code) in enumerate(top5):
        uuid_wm, uname_wm = _create_campaign_employee(token, client, "WAREHOUSE_MANAGER", "Warehouse Manager", btype, code, prefix="WHM")
        staff_id, _ = create_project_staff(token, client, project_ids[i], uuid_wm)
        print(f"  Level {i} ({btype}): Warehouse Manager | username={uname_wm} | staff_id={staff_id}")

    _dv_role = {"code": "DASHBOARD_VIEWER", "name": "Dashboard Viewer"}

    # Level 0: National Supervisor (+ Dashboard Viewer role)
    btype0, code0 = levels[0]
    uuid_ns, uname_ns = _create_campaign_employee(token, client, "NATIONAL_SUPERVISOR", "National Supervisor", btype0, code0, prefix="NS", extra_roles=[_dv_role])
    staff_id, _ = create_project_staff(token, client, project_ids[0], uuid_ns)
    print(f"  Level 0 ({btype0}): National Supervisor + Dashboard Viewer | username={uname_ns} | staff_id={staff_id}")

    # Level 1: Provincial Supervisor (+ Dashboard Viewer role)
    if len(levels) > 1:
        btype1, code1 = levels[1]
        uuid_ps, uname_ps = _create_campaign_employee(token, client, "PROVINCIAL_SUPERVISOR", "Provincial Supervisor", btype1, code1, prefix="PS", extra_roles=[_dv_role])
        staff_id, _ = create_project_staff(token, client, project_ids[1], uuid_ps)
        print(f"  Level 1 ({btype1}): Provincial Supervisor + Dashboard Viewer | username={uname_ps} | staff_id={staff_id}")

    # Level 2: District Supervisor (+ Dashboard Viewer role)
    if len(levels) > 2:
        btype2, code2 = levels[2]
        uuid_ds, uname_ds = _create_campaign_employee(token, client, "DISTRICT_SUPERVISOR", "District Supervisor", btype2, code2, prefix="DS", extra_roles=[_dv_role])
        staff_id, _ = create_project_staff(token, client, project_ids[2], uuid_ds)
        print(f"  Level 2 ({btype2}): District Supervisor + Dashboard Viewer | username={uname_ds} | staff_id={staff_id}")

    # Level 4 (5th level): Distributor + optionally Health Facility Worker if MR-DN
    if len(top5) >= 5:
        btype4, code4 = top5[4]
        uuid_dist, uname_dist = _create_campaign_employee(token, client, "DISTRIBUTOR", "Distributor", btype4, code4, prefix="DIST")
        staff_id, _ = create_project_staff(token, client, project_ids[4], uuid_dist)
        print(f"  Level 4 ({btype4}): Distributor | username={uname_dist} | staff_id={staff_id}")

        if is_mrdn:
            uuid_hfw, uname_hfw = _create_campaign_employee(token, client, "HEALTH_FACILITY_WORKER", "Health Facility Worker", btype4, code4, prefix="HFW")
            staff_id, _ = create_project_staff(token, client, project_ids[4], uuid_hfw)
            print(f"  Level 4 ({btype4}): Health Facility Worker | username={uname_hfw} | staff_id={staff_id}")

    with open("output/ids.txt", "a") as f:
        f.write("\n--- Project Hierarchy ---\n")
        for i, (pid, (btype, _)) in enumerate(zip(project_ids, levels)):
            f.write(f"Project Hierarchy Level {i} ({btype}): {pid}\n")
        f.write("\n--- Campaign Facilities ---\n")
        for i, (fid, (btype, _)) in enumerate(zip(facility_ids, top5)):
            f.write(f"Campaign Facility Level {i} ({btype}): {fid}\n")
        f.write("\n--- Campaign Project Facilities ---\n")
        for i, (pfid, (btype, _)) in enumerate(zip(project_facility_ids, top5)):
            f.write(f"Campaign Project Facility Level {i} ({btype}): {pfid}\n")


def _fetch_project_types():
    try:
        from tests.test_mdms_service import search_mdms_data
        token = get_auth_token("user")
        client = APIClient(token=token)
        response = search_mdms_data(token, client, "HCM-PROJECT-TYPES.projectTypes")
        if response.status_code != 200:
            return []
        mdms_data = response.json().get("mdms", [])
        return [
            (item["data"]["id"], item["data"]["code"], len(item["data"].get("cycles", [])), item["data"])
            for item in mdms_data
            if item.get("isActive") is True
        ]
    except Exception:
        return []


def _make_project_type_test(type_id, type_code, num_cycles, type_data):
    @pytest.mark.positive
    def _test():
        token = get_auth_token("user")
        client = APIClient(token=token)

        payload = load_payload("project", "create_individual_project.json")
        payload["RequestInfo"] = get_request_info(token)
        payload["Projects"][0]["tenantId"] = tenantId
        payload["Projects"][0]["projectTypeId"] = type_id
        payload["Projects"][0]["projectType"] = type_code
        payload["Projects"][0]["projectSubType"] = type_code
        payload["Projects"][0]["address"]["tenantId"] = tenantId
        payload["Projects"][0]["address"]["boundaryType"] = boundaryType
        payload["Projects"][0]["address"]["boundary"] = boundaryCode
        payload["Projects"][0]["address"]["locality"]["code"] = boundaryCode
        payload["Projects"][0]["additionalDetails"]["projectType"] = type_data.copy()
        _apply_cycle_dates(payload, _compute_cycle_dates(num_cycles))

        url = f"/{project}/v1/_create"
        response = client.post(url, payload)

        assert response.status_code in [200, 202], f"Project creation failed for type '{type_code}': {response.text}"
        project_id = response.json()["Project"][0]["id"]
        print(f"Project created for type '{type_code}' with ID: {project_id}")

    test_name = "test_create_project_" + type_code.lower().replace("-", "_").replace(" ", "_").replace(".", "_")
    _test.__name__ = test_name
    return test_name, _test


for _type_id, _type_code, _num_cycles, _type_data in _fetch_project_types():
    _test_name, _test_fn = _make_project_type_test(_type_id, _type_code, _num_cycles, _type_data)
    globals()[_test_name] = _test_fn


@pytest.mark.positive
def test_search_project():
    """Test to search for a project by ID. Creates project if ID not found in file."""
    token = get_auth_token("user")
    client = APIClient(token=token)

    project_id = extract_id_from_file("Project ID:")
    if not project_id:
        # Create project internally if ID not found
        print("Project ID not found in file, creating new project...")
        project_id, status_code = create_individual_project(token, client, boundaryType, boundaryCode)
        assert status_code in [200, 202], f"Project creation failed with status: {status_code}"
        print(f"Project created with ID: {project_id}")

    projects = search_entity(
        entity_type="project",
        token=token,
        client=client,
        entity_id=project_id,
        payload_file="search_project.json",
        endpoint=f"/{project}/v1/_search",
        response_key="Project"
    )

    assert project_id in [p["id"] for p in projects], "Project not found"
    print("Project found with ID:", project_id)


@pytest.mark.positive
def test_create_project_resource():
    token = get_auth_token("user")
    client = APIClient(token=token)

    project_id = extract_id_from_file("Project ID:")
    variant_id = extract_id_from_file("Variant ID:")

    if not project_id or not variant_id:
        variant_response = create_product_variant(token, client)
        assert variant_response.status_code in [200, 202], f"Product Variant creation failed: {variant_response.text}"
        variant_id = variant_response.json()["ProductVariant"][0]["id"]
        project_id, proj_status = create_individual_project(token, client, boundaryType, boundaryCode, variant_id, variant_id)
        assert proj_status in [200, 202], f"Project creation failed with status: {proj_status}"

    resource_id, status_code = create_project_resource(token, client, project_id, variant_id)
    assert status_code in [200, 202], f"Project Resource creation failed with status: {status_code}"

    print("Project Resource created with ID:", resource_id)

    with open("output/ids.txt", "a") as f:
        f.write("\n--- Project Resource details ---\n")
        f.write(f"Project Resource ID 1: {resource_id}\n")


@pytest.mark.positive
def test_search_project_resource():
    """Test to search for a project resource by ID. Creates project and resource if not found in file."""
    token = get_auth_token("user")
    client = APIClient(token=token)

    project_id = extract_id_from_file("Project ID:")
    resource_id = extract_id_from_file("Project Resource ID 1:")

    if not project_id or not resource_id:
        # Create project and resource internally if not found
        print("Project/Resource ID not found in file, creating new project with resource...")
        variant_response = create_product_variant(token, client)
        assert variant_response.status_code in [200, 202], f"Product Variant creation failed"
        variant_id = variant_response.json()["ProductVariant"][0]["id"]
        project_id, status_code = create_individual_project(token, client, boundaryType, boundaryCode, variant_id, variant_id)
        assert status_code in [200, 202], f"Project creation failed with status: {status_code}"
        resource_id, resource_status = create_project_resource(token, client, project_id, variant_id)
        assert resource_status in [200, 202], f"Project Resource creation failed with status: {resource_status}"
        print(f"Project created with ID: {project_id}, Resource ID: {resource_id}")

    resources = search_project_resource(token, client, project_id)

    assert resource_id in [r["id"] for r in resources], "Project Resource not found"
    print("Project Resource found with ID:", resource_id)


@pytest.mark.positive
def test_create_project_staff():
    token = get_auth_token("user")
    client = APIClient(token=token)

    project_id = extract_id_from_file("Project ID:")
    userservice_uuid = extract_id_from_file("Employee UserService UUID:")

    if not project_id:
        project_id, _ = create_individual_project(token, client, boundaryType, boundaryCode)
    if not userservice_uuid:
        from tests.test_hrms_service import create_employee
        _, _, _, userservice_uuid, _ = create_employee(token, client)

    assert project_id, "Project ID not found"
    assert userservice_uuid, "Employee UserService UUID not found"

    staff_id, status_code = create_project_staff(token, client, project_id, userservice_uuid)
    assert status_code in [200, 202], f"Project Staff creation failed with status: {status_code}"

    print("Project Staff created with ID:", staff_id)

    with open("output/ids.txt", "a") as f:
        f.write("\n--- Project Staff details ---\n")
        f.write(f"Project Staff ID: {staff_id}\n")


@pytest.mark.positive
def test_search_project_staff():
    """Test to search for a project staff by ID. Creates project staff if ID not found in file."""
    token = get_auth_token("user")
    client = APIClient(token=token)

    staff_id = extract_id_from_file("Project Staff ID:")
    if not staff_id:
        # Create project staff internally if not found
        print("Project Staff ID not found in file, creating new project staff...")
        project_id = extract_id_from_file("Project ID:")
        userservice_uuid = extract_id_from_file("Employee UserService UUID:")
        if not project_id:
            project_id, _ = create_individual_project(token, client, boundaryType, boundaryCode)
        if not userservice_uuid:
            from tests.test_hrms_service import create_employee
            _, _, _, userservice_uuid, _ = create_employee(token, client)
        staff_id, staff_status = create_project_staff(token, client, project_id, userservice_uuid)
        assert staff_status in [200, 202], f"Project Staff creation failed with status: {staff_status}"
        print(f"Project Staff created with ID: {staff_id}")

    staff_list = search_entity(
        entity_type="project/project_staff",
        token=token,
        client=client,
        entity_id=staff_id,
        payload_file="search_project_staff.json",
        endpoint=f"/{project}/staff/v1/_search",
        response_key="ProjectStaff"
    )

    assert staff_id in [s["id"] for s in staff_list], "Project Staff not found"
    print("Project Staff found with ID:", staff_id)


@pytest.mark.positive
def test_create_project_facility():
    token = get_auth_token("user")
    client = APIClient(token=token)

    project_id = extract_id_from_file("Project ID:")
    facility_id = extract_id_from_file("Facility ID:")

    if not project_id:
        project_id, _ = create_individual_project(token, client, boundaryType, boundaryCode)
    if not facility_id:
        fac_res = create_facility(token, client)
        assert fac_res.status_code in [200, 202], f"Facility creation failed"
        facility_id = fac_res.json()["Facility"]["id"]

    project_facility_id, status_code = create_project_facility(token, client, project_id, facility_id)
    assert status_code in [200, 202], f"Project Facility creation failed with status: {status_code}"

    print("Project Facility created with ID:", project_facility_id)

    with open("output/ids.txt", "a") as f:
        f.write("\n--- Project Facility details ---\n")
        f.write(f"Project Facility ID: {project_facility_id}\n")


@pytest.mark.positive
def test_search_project_facility():
    """Test to search for a project facility by ID. Creates project facility if ID not found in file."""
    token = get_auth_token("user")
    client = APIClient(token=token)

    project_facility_id = extract_id_from_file("Project Facility ID:")
    if not project_facility_id:
        # Create project facility internally if not found
        print("Project Facility ID not found in file, creating new project facility...")
        project_id = extract_id_from_file("Project ID:")
        facility_id = extract_id_from_file("Facility ID:")
        if not project_id:
            project_id, _ = create_individual_project(token, client, boundaryType, boundaryCode)
        if not facility_id:
            facility_response = create_facility(token, client)
            assert facility_response.status_code in [200, 202], f"Facility creation failed"
            facility_id = facility_response.json()["Facility"]["id"]
        project_facility_id, status = create_project_facility(token, client, project_id, facility_id)
        assert status in [200, 202], f"Project Facility creation failed with status: {status}"
        print(f"Project Facility created with ID: {project_facility_id}")

    facilities = search_entity(
        entity_type="project/project_facility",
        token=token,
        client=client,
        entity_id=project_facility_id,
        payload_file="search_project_facility.json",
        endpoint=f"/{project}/facility/v1/_search",
        response_key="ProjectFacilities"
    )

    assert project_facility_id in [f["id"] for f in facilities], "Project Facility not found"
    print("Project Facility found with ID:", project_facility_id)


@pytest.mark.negative
def test_create_project_facility_with_invalid_tenant_id():
    token = get_auth_token("user")
    client = APIClient(token=token)

    project_id = extract_id_from_file("Project ID:")
    facility_id = extract_id_from_file("Facility ID:")

    if not project_id:
        project_id, _ = create_individual_project(token, client, boundaryType, boundaryCode)
    if not facility_id:
        fac_res = create_facility(token, client)
        assert fac_res.status_code in [200, 202], f"Facility creation failed"
        facility_id = fac_res.json()["Facility"]["id"]

    payload = load_payload("project/project_facility", "create_project_facility.json")
    payload["RequestInfo"] = get_request_info(token)
    payload["ProjectFacility"]["tenantId"] = "invalid.tenant.id"
    payload["ProjectFacility"]["projectId"] = project_id
    payload["ProjectFacility"]["facilityId"] = facility_id

    url = f"/{project}/facility/v1/_create"
    response = client.post(url, payload)

    assert response.status_code in [401], f"Expected error status code, got: {response.status_code}"
    print(f"Request correctly rejected with status: {response.status_code}")


@pytest.mark.positive
def test_create_project_beneficiary():
    token = get_auth_token("user")
    client = APIClient(token=token)

    # Create new project
    project_id, project_status = create_individual_project(token, client, boundaryType, boundaryCode)
    assert project_status in [200, 202], f"Project creation failed with status: {project_status}"

    # Create new household
    household_id, household_client_ref_id, household_status = create_household(token, client)
    assert household_status in [200, 202], f"Household creation failed with status: {household_status}"

    # Create new individual
    individual_id, individual_client_ref_id, _, individual_status = create_individual(token, client)
    assert individual_status in [200, 202], f"Individual creation failed with status: {individual_status}"

    # Create new household member
    member_response = create_household_member(token, client, household_id, household_client_ref_id, individual_id, individual_client_ref_id)
    assert member_response.status_code in [200, 202], f"Household Member creation failed with status: {member_response.status_code}"

    beneficiary_id, _, status_code = create_project_beneficiary(token, client, project_id, individual_id, individual_client_ref_id)
    assert status_code in [200, 202], f"Project Beneficiary creation failed with status: {status_code}"

    print("Project Beneficiary created with ID:", beneficiary_id)

    with open("output/ids.txt", "a") as f:
        f.write("\n--- Project Beneficiary details ---\n")
        f.write(f"Project Beneficiary ID: {beneficiary_id}\n")


@pytest.mark.positive
def test_search_project_beneficiary():
    """Test to search for a project beneficiary by ID. Creates project beneficiary if ID not found in file."""
    token = get_auth_token("user")
    client = APIClient(token=token)

    project_beneficiary_id = extract_id_from_file("Project Beneficiary ID:")
    if not project_beneficiary_id:
        # Create project beneficiary internally if not found
        print("Project Beneficiary ID not found in file, creating new project beneficiary...")
        project_id, _ = create_individual_project(token, client, boundaryType, boundaryCode)
        household_id, household_client_ref_id, _ = create_household(token, client)
        individual_id, individual_client_ref_id, _, _ = create_individual(token, client)
        create_household_member(token, client, household_id, household_client_ref_id, individual_id, individual_client_ref_id)
        project_beneficiary_id, _, status = create_project_beneficiary(token, client, project_id, individual_id, individual_client_ref_id)
        assert status in [200, 202], f"Project Beneficiary creation failed with status: {status}"
        print(f"Project Beneficiary created with ID: {project_beneficiary_id}")

    beneficiaries = search_entity(
        entity_type="project/project_beneficiary",
        token=token,
        client=client,
        entity_id=project_beneficiary_id,
        payload_file="search_project_beneficiary.json",
        endpoint=f"/{project}/beneficiary/v1/_search",
        response_key="ProjectBeneficiaries"
    )

    assert project_beneficiary_id in [b["id"] for b in beneficiaries], "Project Beneficiary not found"
    print("Project Beneficiary found with ID:", project_beneficiary_id)


@pytest.mark.positive
def test_create_project_task():
    token = get_auth_token("user")
    client = APIClient(token=token)

    # Create new product variant
    variant_response = create_product_variant(token, client)
    assert variant_response.status_code in [200, 202], f"Product Variant creation failed with status: {variant_response.status_code}"
    variant_id = variant_response.json()["ProductVariant"][0]["id"]

    # Create new project with the product variant
    project_id, project_status = create_individual_project(token, client, boundaryType, boundaryCode, variant_id, variant_id)
    assert project_status in [200, 202], f"Project creation failed with status: {project_status}"

    # Create project resource mapping for the variant
    resource_id, resource_status = create_project_resource(token, client, project_id, variant_id)
    assert resource_status in [200, 202], f"Project Resource creation failed with status: {resource_status}"

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

    # Create project task with the mapped product variant
    task_id, task_client_ref_id, status_code = create_project_task(token, client, project_id, beneficiary_id, beneficiary_client_ref_id, variant_id)
    assert status_code in [200, 202], f"Project Task creation failed with status: {status_code}"

    print("Project Task created with ID:", task_id)

    with open("output/ids.txt", "a") as f:
        f.write("\n--- Project Task details ---\n")
        f.write(f"Project Task ID: {task_id}\n")
        f.write(f"Project Task Client Reference ID: {task_client_ref_id}\n")


@pytest.mark.positive
def test_search_project_task():
    """Test to search for a project task by ID. Creates project task if ID not found in file."""
    token = get_auth_token("user")
    client = APIClient(token=token)

    project_task_id = extract_id_from_file("Project Task ID:")
    if not project_task_id:
        # Create project task with all dependencies if not found
        print("Project Task ID not found in file, creating project task with dependencies...")
        variant_response = create_product_variant(token, client)
        assert variant_response.status_code in [200, 202], f"Product Variant creation failed"
        variant_id = variant_response.json()["ProductVariant"][0]["id"]
        project_id, _ = create_individual_project(token, client, boundaryType, boundaryCode, variant_id, variant_id)
        create_project_resource(token, client, project_id, variant_id)
        household_id, household_client_ref_id, _ = create_household(token, client)
        individual_id, individual_client_ref_id, _, _ = create_individual(token, client)
        create_household_member(token, client, household_id, household_client_ref_id, individual_id, individual_client_ref_id)
        beneficiary_id, beneficiary_client_ref_id, _ = create_project_beneficiary(token, client, project_id, individual_id, individual_client_ref_id)
        project_task_id, _, status = create_project_task(token, client, project_id, beneficiary_id, beneficiary_client_ref_id, variant_id)
        assert status in [200, 202], f"Project Task creation failed with status: {status}"
        print(f"Project Task created with ID: {project_task_id}")

    tasks = search_entity(
        entity_type="project/project_task",
        token=token,
        client=client,
        entity_id=project_task_id,
        payload_file="search_project_task.json",
        endpoint=f"/{project}/task/v1/_search",
        response_key="Tasks"
    )

    assert project_task_id in [t["id"] for t in tasks], "Project Task not found"
    print("Project Task found with ID:", project_task_id)


@pytest.mark.negative
def test_create_project_task_with_invalid_tenant_id():
    token = get_auth_token("user")
    client = APIClient(token=token)

    project_id = extract_id_from_file("Project ID:")
    project_beneficiary_id = extract_id_from_file("Project Beneficiary ID:")
    variant_id = extract_id_from_file("Variant ID:")

    if not variant_id:
        var_res = create_product_variant(token, client)
        assert var_res.status_code in [200, 202], f"Product Variant creation failed"
        variant_id = var_res.json()["ProductVariant"][0]["id"]
    if not project_id:
        project_id, _ = create_individual_project(token, client, boundaryType, boundaryCode, variant_id, variant_id)
    if not project_beneficiary_id:
        ind_id, ind_ref_id, _, _ = create_individual(token, client)
        project_beneficiary_id, _, _ = create_project_beneficiary(token, client, project_id, ind_id, ind_ref_id)

    payload = load_payload("project/project_task", "create_project_task.json")
    payload["RequestInfo"] = get_request_info(token)
    payload["Task"]["tenantId"] = "invalid.tenant.id"
    payload["Task"]["projectId"] = project_id
    payload["Task"]["projectBeneficiaryId"] = project_beneficiary_id
    payload["Task"]["clientReferenceId"] = str(uuid.uuid4())
    payload["Task"]["address"]["tenantId"] = "invalid.tenant.id"
    payload["Task"]["address"]["clientReferenceId"] = str(uuid.uuid4())
    payload["Task"]["address"]["locality"]["code"] = boundaryCode
    payload["Task"]["resources"][0]["tenantId"] = "invalid.tenant.id"
    payload["Task"]["resources"][0]["clientReferenceId"] = str(uuid.uuid4())
    payload["Task"]["resources"][0]["taskClientReferenceId"] = payload["Task"]["clientReferenceId"]
    payload["Task"]["resources"][0]["productVariantId"] = variant_id

    url = f"/{project}/task/v1/_create"
    response = client.post(url, payload)

    assert response.status_code in [401], f"Expected error status code, got: {response.status_code}"
    print(f"Request correctly rejected with status: {response.status_code}")


@pytest.mark.negative
def test_create_project_beneficiary_with_invalid_tenant_id():
    token = get_auth_token("user")
    client = APIClient(token=token)

    project_id = extract_id_from_file("Project ID:")
    individual_id = extract_id_from_file("Individual ID:")
    individual_client_ref_id = extract_id_from_file("Individual Client Reference ID:")

    if not project_id:
        project_id, _ = create_individual_project(token, client, boundaryType, boundaryCode)
    if not individual_id or not individual_client_ref_id:
        individual_id, individual_client_ref_id, _, _ = create_individual(token, client)

    payload = load_payload("project/project_beneficiary", "create_project_beneficiary.json")
    payload["RequestInfo"] = get_request_info(token)
    payload["ProjectBeneficiary"]["tenantId"] = "invalid.tenant.id"
    payload["ProjectBeneficiary"]["projectId"] = project_id
    payload["ProjectBeneficiary"]["beneficiaryId"] = individual_id
    payload["ProjectBeneficiary"]["beneficiaryClientReferenceId"] = individual_client_ref_id

    url = f"/{project}/beneficiary/v1/_create"
    response = client.post(url, payload)

    assert response.status_code in [401], f"Expected error status code, got: {response.status_code}"
    print(f"Request correctly rejected with status: {response.status_code}")


@pytest.mark.negative
def test_create_project_with_invalid_tenant_id():
    token = get_auth_token("user")
    client = APIClient(token=token)

    projectTypeId = extract_id_from_file("MR-DN:")
    payload = load_payload("project", "create_individual_project.json")
    payload["RequestInfo"] = get_request_info(token)
    payload["Projects"][0]["tenantId"] = "invalid.tenant.id"
    if projectTypeId:
        payload["Projects"][0]["projectTypeId"] = projectTypeId
        payload["Projects"][0]["additionalDetails"]["projectType"]["id"] = projectTypeId
    payload["Projects"][0]["startDate"] = 1767205799000
    payload["Projects"][0]["endDate"] = 1787670131000
    payload["Projects"][0]["additionalDetails"]["projectType"]["cycles"][0]["startDate"] = 1767205799000
    payload["Projects"][0]["additionalDetails"]["projectType"]["cycles"][0]["endDate"] = 1787670131000
    payload["Projects"][0]["additionalDetails"]["projectType"]["cycles"][1]["startDate"] = 1767205799000
    payload["Projects"][0]["additionalDetails"]["projectType"]["cycles"][1]["endDate"] = 1787670131000

    url = f"/{project}/v1/_create"
    response = client.post(url, payload)

    assert response.status_code in [401], f"Expected error status code, got: {response.status_code}"
    print(f"Request correctly rejected with status: {response.status_code}")


@pytest.mark.negative
def test_create_project_resource_with_invalid_tenant_id():
    token = get_auth_token("user")
    client = APIClient(token=token)

    project_id = extract_id_from_file("Project ID:")
    variant_id = extract_id_from_file("Variant ID:")

    if not project_id:
        project_id, _ = create_individual_project(token, client, boundaryType, boundaryCode)
    if not variant_id:
        var_res = create_product_variant(token, client)
        assert var_res.status_code in [200, 202], f"Product Variant creation failed"
        variant_id = var_res.json()["ProductVariant"][0]["id"]

    payload = load_payload("project/project_resource", "create_project_resource.json")
    payload["RequestInfo"] = get_request_info(token)
    payload["ProjectResource"]["tenantId"] = "invalid.tenant.id"
    payload["ProjectResource"]["projectId"] = project_id
    payload["ProjectResource"]["resource"]["productVariantId"] = variant_id

    url = f"/{project}/resource/v1/_create"
    response = client.post(url, payload)

    assert response.status_code in [401], f"Expected error status code, got: {response.status_code}"
    print(f"Request correctly rejected with status: {response.status_code}")


@pytest.mark.negative
def test_create_project_staff_with_invalid_tenant_id():
    token = get_auth_token("user")
    client = APIClient(token=token)

    project_id = extract_id_from_file("Project ID:")
    userservice_uuid = extract_id_from_file("Employee UserService UUID:")

    if not project_id:
        project_id, _ = create_individual_project(token, client, boundaryType, boundaryCode)
    if not userservice_uuid:
        from tests.test_hrms_service import create_employee
        _, _, _, userservice_uuid, _ = create_employee(token, client)

    payload = load_payload("project/project_staff", "create_project_staff.json")
    payload["RequestInfo"] = get_request_info(token)
    payload["ProjectStaff"]["tenantId"] = "invalid.tenant.id"
    payload["ProjectStaff"]["projectId"] = project_id
    payload["ProjectStaff"]["userId"] = userservice_uuid

    url = f"/{project}/staff/v1/_create"
    response = client.post(url, payload)

    assert response.status_code in [401], f"Expected error status code, got: {response.status_code}"
    print(f"Request correctly rejected with status: {response.status_code}")


@pytest.mark.negative
def test_search_project_with_invalid_tenant_id():
    """Negative test: Searching project with invalid tenantId should fail"""
    token = get_auth_token("user")
    client = APIClient(token=token)

    project_id = extract_id_from_file("Project ID:")
    if not project_id:
        # Create a new project if ID not found
        project_id, status_code = create_individual_project(token, client, boundaryType, boundaryCode)
        assert status_code in [200, 202], f"Project creation failed with status: {status_code}"

    payload = load_payload("project", "search_project.json")
    payload["RequestInfo"] = get_request_info(token)
    payload["Projects"][0]["id"] = project_id

    url = f"/{project}/v1/_search?tenantId={invalidTenantId}"
    response = client.post(url, payload)

    assert response.status_code in [400, 401, 403], f"Expected error status code, got: {response.status_code}"
    print(f"Search correctly rejected with status: {response.status_code}")


@pytest.mark.negative
def test_search_project_resource_with_invalid_tenant_id():
    """Negative test: Searching project resource with invalid tenantId should fail"""
    token = get_auth_token("user")
    client = APIClient(token=token)

    project_id = extract_id_from_file("Project ID:")
    if not project_id:
        # Create a new project with resource if ID not found
        variant_response = create_product_variant(token, client)
        assert variant_response.status_code in [200, 202], f"Product Variant creation failed"
        variant_id = variant_response.json()["ProductVariant"][0]["id"]
        project_id, status_code = create_individual_project(token, client, boundaryType, boundaryCode, variant_id, variant_id)
        assert status_code in [200, 202], f"Project creation failed with status: {status_code}"
        _, resource_status = create_project_resource(token, client, project_id, variant_id)
        assert resource_status in [200, 202], f"Project Resource creation failed"

    payload = load_payload("project/project_resource", "search_project_resource.json")
    payload["RequestInfo"] = get_request_info(token)
    payload["ProjectResource"]["projectId"] = [project_id]

    url = f"/{project}/resource/v1/_search?limit=100&offset=0&tenantId={invalidTenantId}"
    response = client.post(url, payload)

    assert response.status_code in [400, 401, 403], f"Expected error status code, got: {response.status_code}"
    print(f"Search correctly rejected with status: {response.status_code}")


@pytest.mark.negative
def test_search_project_staff_with_invalid_tenant_id():
    """Negative test: Searching project staff with invalid tenantId should fail"""
    token = get_auth_token("user")
    client = APIClient(token=token)

    staff_id = extract_id_from_file("Project Staff ID:")
    if not staff_id:
        # Create project and staff if not found
        project_id = extract_id_from_file("Project ID:")
        userservice_uuid = extract_id_from_file("Employee UserService UUID:")
        if not project_id:
            project_id, _ = create_individual_project(token, client, boundaryType, boundaryCode)
        if not userservice_uuid:
            from tests.test_hrms_service import create_employee
            _, _, _, userservice_uuid, _ = create_employee(token, client)
        staff_id, _ = create_project_staff(token, client, project_id, userservice_uuid)

    payload = load_payload("project/project_staff", "search_project_staff.json")
    payload["RequestInfo"] = get_request_info(token)
    payload["ProjectStaff"]["id"] = [staff_id]

    url = f"/{project}/staff/v1/_search?tenantId={invalidTenantId}"
    response = client.post(url, payload)

    assert response.status_code in [400, 401, 403], f"Expected error status code, got: {response.status_code}"
    print(f"Search correctly rejected with status: {response.status_code}")


@pytest.mark.negative
def test_search_project_facility_with_invalid_tenant_id():
    """Negative test: Searching project facility with invalid tenantId should fail"""
    token = get_auth_token("user")
    client = APIClient(token=token)

    project_facility_id = extract_id_from_file("Project Facility ID:")
    if not project_facility_id:
        # Create project and facility if not found
        project_id = extract_id_from_file("Project ID:")
        facility_id = extract_id_from_file("Facility ID:")
        if not project_id:
            project_id, _ = create_individual_project(token, client, boundaryType, boundaryCode)
        if not facility_id:
            facility_response = create_facility(token, client)
            assert facility_response.status_code in [200, 202], f"Facility creation failed"
            facility_id = facility_response.json()["Facility"]["id"]
        project_facility_id, _ = create_project_facility(token, client, project_id, facility_id)

    payload = load_payload("project/project_facility", "search_project_facility.json")
    payload["RequestInfo"] = get_request_info(token)
    payload["ProjectFacility"]["id"] = [project_facility_id]

    url = f"/{project}/facility/v1/_search?tenantId={invalidTenantId}"
    response = client.post(url, payload)

    assert response.status_code in [400, 401, 403], f"Expected error status code, got: {response.status_code}"
    print(f"Search correctly rejected with status: {response.status_code}")


@pytest.mark.negative
def test_search_project_beneficiary_with_invalid_tenant_id():
    """Negative test: Searching project beneficiary with invalid tenantId should fail"""
    token = get_auth_token("user")
    client = APIClient(token=token)

    beneficiary_id = extract_id_from_file("Project Beneficiary ID:")
    if not beneficiary_id:
        # Create project and beneficiary if not found
        project_id, _ = create_individual_project(token, client, boundaryType, boundaryCode)
        household_id, household_client_ref_id, _ = create_household(token, client)
        individual_id, individual_client_ref_id, _, _ = create_individual(token, client)
        create_household_member(token, client, household_id, household_client_ref_id, individual_id, individual_client_ref_id)
        beneficiary_id, _, _ = create_project_beneficiary(token, client, project_id, individual_id, individual_client_ref_id)

    payload = load_payload("project/project_beneficiary", "search_project_beneficiary.json")
    payload["RequestInfo"] = get_request_info(token)
    payload["ProjectBeneficiary"]["id"] = [beneficiary_id]

    url = f"/{project}/beneficiary/v1/_search?tenantId={invalidTenantId}"
    response = client.post(url, payload)

    assert response.status_code in [400, 401, 403], f"Expected error status code, got: {response.status_code}"
    print(f"Search correctly rejected with status: {response.status_code}")


@pytest.mark.negative
def test_search_project_task_with_invalid_tenant_id():
    """Negative test: Searching project task with invalid tenantId should fail"""
    token = get_auth_token("user")
    client = APIClient(token=token)

    task_id = extract_id_from_file("Project Task ID:")
    if not task_id:
        # Create project, beneficiary, and task if not found
        variant_response = create_product_variant(token, client)
        assert variant_response.status_code in [200, 202], f"Product Variant creation failed"
        variant_id = variant_response.json()["ProductVariant"][0]["id"]
        project_id, _ = create_individual_project(token, client, boundaryType, boundaryCode, variant_id, variant_id)
        create_project_resource(token, client, project_id, variant_id)
        household_id, household_client_ref_id, _ = create_household(token, client)
        individual_id, individual_client_ref_id, _, _ = create_individual(token, client)
        create_household_member(token, client, household_id, household_client_ref_id, individual_id, individual_client_ref_id)
        beneficiary_id, beneficiary_client_ref_id, _ = create_project_beneficiary(token, client, project_id, individual_id, individual_client_ref_id)
        task_id, _, _ = create_project_task(token, client, project_id, beneficiary_id, beneficiary_client_ref_id, variant_id)

    payload = load_payload("project/project_task", "search_project_task.json")
    payload["RequestInfo"] = get_request_info(token)
    payload["Task"]["id"] = [task_id]

    url = f"/{project}/task/v1/_search?tenantId={invalidTenantId}"
    response = client.post(url, payload)

    assert response.status_code in [400, 401, 403], f"Expected error status code, got: {response.status_code}"
    print(f"Search correctly rejected with status: {response.status_code}")


@pytest.mark.positive
def test_update_project_beneficiary():
    """Test to update a project beneficiary. Creates all dependencies internally first, then updates the tag."""
    token = get_auth_token("user")
    client = APIClient(token=token)

    # Step 1: Create all dependencies internally
    print("Creating project for update test...")
    project_id, project_status = create_individual_project(token, client, boundaryType, boundaryCode)
    assert project_status in [200, 202], f"Project creation failed with status: {project_status}"
    print(f"Project created with ID: {project_id}")

    print("Creating household...")
    household_id, household_client_ref_id, household_status = create_household(token, client)
    assert household_status in [200, 202], f"Household creation failed with status: {household_status}"

    print("Creating individual...")
    individual_id, individual_client_ref_id, _, individual_status = create_individual(token, client)
    assert individual_status in [200, 202], f"Individual creation failed with status: {individual_status}"

    print("Creating household member...")
    member_response = create_household_member(token, client, household_id, household_client_ref_id, individual_id, individual_client_ref_id)
    assert member_response.status_code in [200, 202], f"Household Member creation failed"

    print("Creating project beneficiary...")
    beneficiary_id, beneficiary_client_ref_id, beneficiary_status = create_project_beneficiary(token, client, project_id, individual_id, individual_client_ref_id)
    assert beneficiary_status in [200, 202], f"Project Beneficiary creation failed with status: {beneficiary_status}"
    print(f"Project Beneficiary created with ID: {beneficiary_id}")

    # Step 2: Search for the beneficiary to get full data for update
    beneficiaries = search_project_beneficiary(token, client, beneficiary_id)
    assert len(beneficiaries) > 0, "Could not find created project beneficiary"
    beneficiary_data = beneficiaries[0]
    original_tag = beneficiary_data.get("tag", "")
    print(f"Original tag: '{original_tag}'")

    # Step 3: Update the beneficiary (change tag)
    new_tag = f"UPDATED-TAG-{str(uuid.uuid4())[:8]}"
    response = update_project_beneficiary(token, client, beneficiary_data, new_tag)
    assert response.status_code in [200, 202], f"Project Beneficiary update failed: {response.text}"

    # Step 4: Verify update
    updated_beneficiary = response.json()["ProjectBeneficiary"]
    assert updated_beneficiary["tag"] == new_tag, f"Tag not updated. Expected {new_tag}, got {updated_beneficiary.get('tag')}"
    print(f"Project Beneficiary updated successfully. Tag changed from '{original_tag}' to '{new_tag}'")


@pytest.mark.positive
def test_update_project_task():
    """Test to update a project task. Creates all dependencies internally first, then updates the status."""
    token = get_auth_token("user")
    client = APIClient(token=token)

    # Step 1: Create all dependencies internally
    print("Creating product variant...")
    variant_response = create_product_variant(token, client)
    assert variant_response.status_code in [200, 202], f"Product Variant creation failed"
    variant_id = variant_response.json()["ProductVariant"][0]["id"]

    print("Creating project...")
    project_id, project_status = create_individual_project(token, client, boundaryType, boundaryCode, variant_id, variant_id)
    assert project_status in [200, 202], f"Project creation failed with status: {project_status}"
    print(f"Project created with ID: {project_id}")

    print("Creating project resource...")
    resource_id, resource_status = create_project_resource(token, client, project_id, variant_id)
    assert resource_status in [200, 202], f"Project Resource creation failed"

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
    assert task_status in [200, 202], f"Project Task creation failed with status: {task_status}"
    print(f"Project Task created with ID: {task_id}")

    # Step 2: Search for the task to get full data for update
    tasks = search_project_task(token, client, task_id)
    assert len(tasks) > 0, "Could not find created project task"
    task_data = tasks[0]
    original_status = task_data.get("status", "")
    print(f"Original status: '{original_status}'")

    # Step 3: Update the task (change status)
    new_status = "ADMINISTRATION_SUCCESS"
    response = update_project_task(token, client, task_data, new_status)
    assert response.status_code in [200, 202], f"Project Task update failed: {response.text}"

    # Step 4: Verify update
    updated_task = response.json()["Task"]
    assert updated_task["status"] == new_status, f"Status not updated. Expected {new_status}, got {updated_task.get('status')}"
    print(f"Project Task updated successfully. Status changed from '{original_status}' to '{new_status}'")


@pytest.mark.positive
def test_update_project():
    """Test to update a project. Creates project internally first, then updates the description."""
    token = get_auth_token("user")
    client = APIClient(token=token)

    # Step 1: Create project internally
    print("Creating product variants...")
    variant_response_1 = create_product_variant(token, client)
    assert variant_response_1.status_code in [200, 202], f"Product Variant 1 creation failed"
    variant_id_1 = variant_response_1.json()["ProductVariant"][0]["id"]

    variant_response_2 = create_product_variant(token, client)
    assert variant_response_2.status_code in [200, 202], f"Product Variant 2 creation failed"
    variant_id_2 = variant_response_2.json()["ProductVariant"][0]["id"]

    print("Creating project...")
    project_data, project_status = create_individual_project_full(token, client, boundaryType, boundaryCode, variant_id_1, variant_id_2)
    assert project_status in [200, 202], f"Project creation failed with status: {project_status}"
    print(f"Project created with ID: {project_data['id']}")

    # Step 2: Use create response data directly
    original_description = project_data.get("description", "")
    print(f"Original description: {original_description}")

    # Step 3: Update the project (change description)
    new_description = f"Updated description via automated test - {str(uuid.uuid4())[:8]}"
    response = update_project(token, client, project_data, new_description)
    assert response.status_code in [200, 202], f"Project update failed: {response.text}"

    # Step 4: Verify update
    updated_project = response.json()["Project"][0]
    assert updated_project["description"] == new_description, f"Description not updated. Expected {new_description}, got {updated_project.get('description')}"
    print(f"Project updated successfully. Description changed from '{original_description}' to '{new_description}'")


@pytest.mark.positive
def test_update_project_staff():
    """Test to update a project staff. Creates all dependencies internally first, then updates the endDate."""
    token = get_auth_token("user")
    client = APIClient(token=token)

    # Step 1: Create all dependencies internally
    print("Creating project...")
    project_id, project_status = create_individual_project(token, client, boundaryType, boundaryCode)
    assert project_status in [200, 202], f"Project creation failed with status: {project_status}"
    print(f"Project created with ID: {project_id}")

    print("Creating employee...")
    from tests.test_hrms_service import create_employee
    _, _, _, userservice_uuid, employee_status = create_employee(token, client)
    assert employee_status in [200, 202], f"Employee creation failed"
    print(f"Employee created with userServiceUuid: {userservice_uuid}")

    print("Creating project staff...")
    staff_data, staff_status = create_project_staff_full(token, client, project_id, userservice_uuid)
    assert staff_status in [200, 202], f"Project Staff creation failed with status: {staff_status}"
    print(f"Project Staff created with ID: {staff_data['id']}")

    # Step 2: Use create response data directly
    original_end_date = staff_data.get("endDate", 0)
    print(f"Original endDate: {original_end_date}")

    # Step 3: Update the project staff (change endDate)
    new_end_date = 9999999999999
    response = update_project_staff(token, client, staff_data, new_end_date)
    assert response.status_code in [200, 202], f"Project Staff update failed: {response.text}"

    # Step 4: Verify update
    updated_staff = response.json()["ProjectStaff"]
    assert updated_staff["endDate"] == new_end_date, f"EndDate not updated. Expected {new_end_date}, got {updated_staff.get('endDate')}"
    print(f"Project Staff updated successfully. EndDate changed from {original_end_date} to {new_end_date}")


@pytest.mark.positive
def test_update_project_resource():
    """Test to update a project resource. Creates all dependencies internally first, then updates the resource type."""
    token = get_auth_token("user")
    client = APIClient(token=token)

    # Step 1: Create all dependencies internally
    print("Creating product variant...")
    variant_response = create_product_variant(token, client)
    assert variant_response.status_code in [200, 202], f"Product Variant creation failed"
    variant_id = variant_response.json()["ProductVariant"][0]["id"]

    print("Creating project...")
    project_id, project_status = create_individual_project(token, client, boundaryType, boundaryCode, variant_id, variant_id)
    assert project_status in [200, 202], f"Project creation failed with status: {project_status}"
    print(f"Project created with ID: {project_id}")

    print("Creating project resource...")
    resource_data, resource_status = create_project_resource_full(token, client, project_id, variant_id)
    assert resource_status in [200, 202], f"Project Resource creation failed with status: {resource_status}"
    print(f"Project Resource created with ID: {resource_data['id']}")

    # Step 2: Use create response data directly
    original_type = resource_data.get("resource", {}).get("type", "")
    print(f"Original resource type: {original_type}")

    # Step 3: Update the project resource (change resource type)
    new_type = "BEDNET"
    response = update_project_resource(token, client, resource_data, new_type)
    assert response.status_code in [200, 202], f"Project Resource update failed: {response.text}"

    # Step 4: Verify update
    updated_resource = response.json()["ProjectResource"]
    assert updated_resource["resource"]["type"] == new_type, f"Resource type not updated. Expected {new_type}, got {updated_resource.get('resource', {}).get('type')}"
    print(f"Project Resource updated successfully. Resource type changed from '{original_type}' to '{new_type}'")


@pytest.mark.positive
def test_update_project_facility():
    """Test to update a project facility. Creates all dependencies internally first, then updates additionalFields."""
    token = get_auth_token("user")
    client = APIClient(token=token)

    # Step 1: Create all dependencies internally
    print("Creating project...")
    project_id, project_status = create_individual_project(token, client, boundaryType, boundaryCode)
    assert project_status in [200, 202], f"Project creation failed with status: {project_status}"
    print(f"Project created with ID: {project_id}")

    print("Creating facility...")
    facility_response = create_facility(token, client)
    assert facility_response.status_code in [200, 202], f"Facility creation failed"
    facility_id = facility_response.json()["Facility"]["id"]
    print(f"Facility created with ID: {facility_id}")

    print("Creating project facility...")
    project_facility_data, project_facility_status = create_project_facility_full(token, client, project_id, facility_id)
    assert project_facility_status in [200, 202], f"Project Facility creation failed with status: {project_facility_status}"
    print(f"Project Facility created with ID: {project_facility_data['id']}")

    # Step 2: Use create response data directly
    original_additional = project_facility_data.get("additionalFields", {})
    print(f"Original additionalFields: {original_additional}")

    # Step 3: Update the project facility (add additionalFields)
    new_additional_fields = {
        "schema": "updated_schema",
        "version": 2,
        "fields": [
            {"key": "updated_key", "value": "updated_value"}
        ]
    }
    response = update_project_facility(token, client, project_facility_data, new_additional_fields)
    assert response.status_code in [200, 202], f"Project Facility update failed: {response.text}"

    # Step 4: Verify update
    updated_facility = response.json()["ProjectFacility"]
    assert updated_facility.get("additionalFields", {}).get("schema") == "updated_schema", f"AdditionalFields not updated correctly"
    print(f"Project Facility updated successfully. AdditionalFields updated.")


@pytest.mark.positive
def test_delete_project_facility():
    """Test to delete a project facility. Creates all dependencies internally first, then deletes it."""
    token = get_auth_token("user")
    client = APIClient(token=token)

    # Step 1: Create all dependencies internally
    print("Creating project...")
    project_id, project_status = create_individual_project(token, client, boundaryType, boundaryCode)
    assert project_status in [200, 202], f"Project creation failed with status: {project_status}"
    print(f"Project created with ID: {project_id}")

    print("Creating facility...")
    facility_response = create_facility(token, client)
    assert facility_response.status_code in [200, 202], f"Facility creation failed"
    facility_id = facility_response.json()["Facility"]["id"]
    print(f"Facility created with ID: {facility_id}")

    print("Creating project facility...")
    project_facility_data, project_facility_status = create_project_facility_full(token, client, project_id, facility_id)
    assert project_facility_status in [200, 202], f"Project Facility creation failed with status: {project_facility_status}"
    project_facility_id = project_facility_data['id']
    print(f"Project Facility created with ID: {project_facility_id}")

    # Step 2: Delete the project facility
    print("Deleting project facility...")
    response = delete_project_facility(token, client, project_facility_data)
    assert response.status_code in [200, 202], f"Project Facility delete failed: {response.text}"

    # Step 3: Verify deletion
    deleted_facility = response.json()["ProjectFacility"]
    assert deleted_facility["isDeleted"] == True, f"Project Facility not marked as deleted"
    print(f"Project Facility {project_facility_id} deleted successfully")


@pytest.mark.positive
def test_delete_project_resource():
    """Test to delete a project resource. Creates all dependencies internally first, then deletes it."""
    token = get_auth_token("user")
    client = APIClient(token=token)

    # Step 1: Create all dependencies internally
    print("Creating product variant...")
    variant_response = create_product_variant(token, client)
    assert variant_response.status_code in [200, 202], f"Product Variant creation failed"
    variant_id = variant_response.json()["ProductVariant"][0]["id"]

    print("Creating project...")
    project_id, project_status = create_individual_project(token, client, boundaryType, boundaryCode, variant_id, variant_id)
    assert project_status in [200, 202], f"Project creation failed with status: {project_status}"
    print(f"Project created with ID: {project_id}")

    print("Creating project resource...")
    resource_data, resource_status = create_project_resource_full(token, client, project_id, variant_id)
    assert resource_status in [200, 202], f"Project Resource creation failed with status: {resource_status}"
    resource_id = resource_data['id']
    print(f"Project Resource created with ID: {resource_id}")

    # Step 2: Delete the project resource
    print("Deleting project resource...")
    response = delete_project_resource(token, client, resource_data)
    assert response.status_code in [200, 202], f"Project Resource delete failed: {response.text}"

    # Step 3: Verify deletion
    deleted_resource = response.json()["ProjectResource"]
    assert deleted_resource["isDeleted"] == True, f"Project Resource not marked as deleted"
    print(f"Project Resource {resource_id} deleted successfully")


@pytest.mark.positive
def test_create_project_resource_bulk():
    """Test to bulk create a project resource. Creates all dependencies internally first."""
    token = get_auth_token("user")
    client = APIClient(token=token)

    # Step 1: Create dependencies
    print("Creating product variant...")
    variant_response = create_product_variant(token, client)
    assert variant_response.status_code in [200, 202], f"Product Variant creation failed"
    variant_id = variant_response.json()["ProductVariant"][0]["id"]

    print("Creating project...")
    project_id, project_status = create_individual_project(token, client, boundaryType, boundaryCode, variant_id, variant_id)
    assert project_status in [200, 202], f"Project creation failed with status: {project_status}"
    print(f"Project created with ID: {project_id}")

    # Step 2: Bulk create project resource — response is always 202 with status body only
    print("Bulk creating project resource...")
    status_code = create_project_resource_bulk(token, client, project_id, variant_id)
    assert status_code == 202, f"Project Resource bulk creation failed with status: {status_code}"
    print("Bulk create accepted with 202")

    # Step 3: Search by projectId and verify resource with variant_id exists
    resources = search_project_resource(token, client, project_id)
    matching = [r for r in resources if r.get("resource", {}).get("productVariantId") == variant_id]
    assert matching, f"No resource found with productVariantId {variant_id} after bulk create"
    print(f"Verified: resource with productVariantId {variant_id} found in search results")


@pytest.mark.positive
def test_update_project_resource_bulk():
    """Test to bulk update a project resource. Creates resource first, then bulk updates the resource type."""
    token = get_auth_token("user")
    client = APIClient(token=token)

    # Step 1: Create dependencies
    print("Creating product variant...")
    variant_response = create_product_variant(token, client)
    assert variant_response.status_code in [200, 202], f"Product Variant creation failed"
    variant_id = variant_response.json()["ProductVariant"][0]["id"]

    print("Creating project...")
    project_id, project_status = create_individual_project(token, client, boundaryType, boundaryCode, variant_id, variant_id)
    assert project_status in [200, 202], f"Project creation failed with status: {project_status}"
    print(f"Project created with ID: {project_id}")

    print("Creating project resource (regular create to get resource data)...")
    resource_data, resource_status = create_project_resource_full(token, client, project_id, variant_id)
    assert resource_status in [200, 202], f"Project Resource creation failed with status: {resource_status}"
    print(f"Project Resource created with ID: {resource_data['id']}")

    # Step 2: Bulk update the project resource (change resource type) — response is always 202
    original_type = resource_data.get("resource", {}).get("type", "")
    print(f"Original resource type: {original_type}")

    new_type = "BEDNET"
    response = update_project_resource_bulk(token, client, resource_data, new_type)
    assert response.status_code == 202, f"Project Resource bulk update failed: {response.text}"
    print("Bulk update accepted with 202")

    # Step 3: Search and verify resource type was updated
    resources = search_project_resource(token, client, project_id)
    updated = next((r for r in resources if r.get("id") == resource_data["id"]), None)
    assert updated is not None, f"Resource {resource_data['id']} not found after bulk update"
    assert updated["resource"]["type"] == new_type, f"Resource type not updated. Expected {new_type}, got {updated.get('resource', {}).get('type')}"
    print(f"Project Resource bulk updated successfully. Resource type changed from '{original_type}' to '{new_type}'")


@pytest.mark.positive
def test_delete_project_resource_bulk():
    """Test to bulk delete a project resource. Creates resource first, then bulk deletes it."""
    token = get_auth_token("user")
    client = APIClient(token=token)

    # Step 1: Create dependencies
    print("Creating product variant...")
    variant_response = create_product_variant(token, client)
    assert variant_response.status_code in [200, 202], f"Product Variant creation failed"
    variant_id = variant_response.json()["ProductVariant"][0]["id"]

    print("Creating project...")
    project_id, project_status = create_individual_project(token, client, boundaryType, boundaryCode, variant_id, variant_id)
    assert project_status in [200, 202], f"Project creation failed with status: {project_status}"
    print(f"Project created with ID: {project_id}")

    print("Creating project resource (regular create to get resource data)...")
    resource_data, resource_status = create_project_resource_full(token, client, project_id, variant_id)
    assert resource_status in [200, 202], f"Project Resource creation failed with status: {resource_status}"
    resource_id = resource_data["id"]
    print(f"Project Resource created with ID: {resource_id}")

    # Step 2: Bulk delete the project resource — response is always 202
    print("Bulk deleting project resource...")
    response = delete_project_resource_bulk(token, client, resource_data)
    assert response.status_code == 202, f"Project Resource bulk delete failed: {response.text}"
    print(f"Project Resource {resource_id} bulk deleted successfully (202 accepted)")


@pytest.mark.positive
def test_delete_project_staff():
    """Test to delete a project staff. Creates all dependencies internally first, then deletes it."""
    token = get_auth_token("user")
    client = APIClient(token=token)

    # Step 1: Create all dependencies internally
    print("Creating project...")
    project_id, project_status = create_individual_project(token, client, boundaryType, boundaryCode)
    assert project_status in [200, 202], f"Project creation failed with status: {project_status}"
    print(f"Project created with ID: {project_id}")

    print("Creating employee...")
    from tests.test_hrms_service import create_employee
    _, _, _, userservice_uuid, employee_status = create_employee(token, client)
    assert employee_status in [200, 202], f"Employee creation failed"
    print(f"Employee created with userServiceUuid: {userservice_uuid}")

    print("Creating project staff...")
    staff_data, staff_status = create_project_staff_full(token, client, project_id, userservice_uuid)
    assert staff_status in [200, 202], f"Project Staff creation failed with status: {staff_status}"
    staff_id = staff_data['id']
    print(f"Project Staff created with ID: {staff_id}")

    # Step 2: Delete the project staff
    print("Deleting project staff...")
    response = delete_project_staff(token, client, staff_data)
    assert response.status_code in [200, 202], f"Project Staff delete failed: {response.text}"

    # Step 3: Verify deletion
    deleted_staff = response.json()["ProjectStaff"]
    assert deleted_staff["isDeleted"] == True, f"Project Staff not marked as deleted"
    print(f"Project Staff {staff_id} deleted successfully")


@pytest.mark.positive
def test_create_project_facility_bulk():
    """Test to bulk create a project facility. Creates all dependencies internally first."""
    token = get_auth_token("user")
    client = APIClient(token=token)

    # Step 1: Create dependencies
    print("Creating project...")
    project_id, project_status = create_individual_project(token, client, boundaryType, boundaryCode)
    assert project_status in [200, 202], f"Project creation failed with status: {project_status}"
    print(f"Project created with ID: {project_id}")

    print("Creating facility...")
    facility_response = create_facility(token, client)
    assert facility_response.status_code in [200, 202], f"Facility creation failed"
    facility_id = facility_response.json()["Facility"]["id"]
    print(f"Facility created with ID: {facility_id}")

    # Step 2: Bulk create project facility — response is always 202 with status body only
    print("Bulk creating project facility...")
    status_code = create_project_facility_bulk(token, client, project_id, facility_id)
    assert status_code == 202, f"Project Facility bulk creation failed with status: {status_code}"
    print("Bulk create accepted with 202")

    # Step 3: Search by projectId and verify facility was linked
    facilities = search_project_facility_by_project(token, client, project_id)
    matching = [f for f in facilities if f.get("facilityId") == facility_id]
    assert matching, f"No project facility found with facilityId {facility_id} after bulk create"
    print(f"Verified: project facility with facilityId {facility_id} found in search results")


@pytest.mark.positive
def test_update_project_facility_bulk():
    """Test to bulk update a project facility. Creates facility first, then bulk updates additionalFields."""
    token = get_auth_token("user")
    client = APIClient(token=token)

    # Step 1: Create dependencies
    print("Creating project...")
    project_id, project_status = create_individual_project(token, client, boundaryType, boundaryCode)
    assert project_status in [200, 202], f"Project creation failed with status: {project_status}"
    print(f"Project created with ID: {project_id}")

    print("Creating facility...")
    facility_response = create_facility(token, client)
    assert facility_response.status_code in [200, 202], f"Facility creation failed"
    facility_id = facility_response.json()["Facility"]["id"]
    print(f"Facility created with ID: {facility_id}")

    print("Creating project facility (regular create to get full data)...")
    project_facility_data, pf_status = create_project_facility_full(token, client, project_id, facility_id)
    assert pf_status in [200, 202], f"Project Facility creation failed with status: {pf_status}"
    print(f"Project Facility created with ID: {project_facility_data['id']}")

    # Step 2: Bulk update additionalFields — response is always 202
    new_additional_fields = {"schema": "updated_schema", "version": 2, "fields": [{"key": "updated_key", "value": "updated_value"}]}
    response = update_project_facility_bulk(token, client, project_facility_data, new_additional_fields)
    assert response.status_code == 202, f"Project Facility bulk update failed: {response.text}"
    print("Bulk update accepted with 202")

    # Step 3: Search by projectId and verify additionalFields updated
    facilities = search_project_facility_by_project(token, client, project_id)
    updated = next((f for f in facilities if f.get("id") == project_facility_data["id"]), None)
    assert updated is not None, f"Project Facility {project_facility_data['id']} not found after bulk update"
    assert updated.get("additionalFields", {}).get("schema") == "updated_schema", "additionalFields not updated"
    print("Project Facility bulk updated successfully. additionalFields updated.")


@pytest.mark.positive
def test_delete_project_facility_bulk():
    """Test to bulk delete a project facility. Creates facility first, then bulk deletes it."""
    token = get_auth_token("user")
    client = APIClient(token=token)

    # Step 1: Create dependencies
    print("Creating project...")
    project_id, project_status = create_individual_project(token, client, boundaryType, boundaryCode)
    assert project_status in [200, 202], f"Project creation failed with status: {project_status}"
    print(f"Project created with ID: {project_id}")

    print("Creating facility...")
    facility_response = create_facility(token, client)
    assert facility_response.status_code in [200, 202], f"Facility creation failed"
    facility_id = facility_response.json()["Facility"]["id"]
    print(f"Facility created with ID: {facility_id}")

    print("Creating project facility (regular create to get full data)...")
    project_facility_data, pf_status = create_project_facility_full(token, client, project_id, facility_id)
    assert pf_status in [200, 202], f"Project Facility creation failed with status: {pf_status}"
    pf_id = project_facility_data["id"]
    print(f"Project Facility created with ID: {pf_id}")

    # Step 2: Bulk delete — response is always 202
    print("Bulk deleting project facility...")
    response = delete_project_facility_bulk(token, client, project_facility_data)
    assert response.status_code == 202, f"Project Facility bulk delete failed: {response.text}"
    print(f"Project Facility {pf_id} bulk deleted successfully (202 accepted)")


@pytest.mark.positive
def test_create_project_staff_bulk():
    """Test to bulk create a project staff. Creates all dependencies internally first."""
    token = get_auth_token("user")
    client = APIClient(token=token)

    # Step 1: Create dependencies
    print("Creating project...")
    project_id, project_status = create_individual_project(token, client, boundaryType, boundaryCode)
    assert project_status in [200, 202], f"Project creation failed with status: {project_status}"
    print(f"Project created with ID: {project_id}")

    print("Creating employee...")
    from tests.test_hrms_service import create_employee
    _, _, _, userservice_uuid, employee_status = create_employee(token, client)
    assert employee_status in [200, 202], f"Employee creation failed"
    print(f"Employee created with userServiceUuid: {userservice_uuid}")

    # Step 2: Bulk create project staff — response is always 202 with status body only
    print("Bulk creating project staff...")
    status_code = create_project_staff_bulk(token, client, project_id, userservice_uuid)
    assert status_code == 202, f"Project Staff bulk creation failed with status: {status_code}"
    print("Bulk create accepted with 202")

    # Step 3: Search by projectId and verify staff with matching userId exists
    staff_list = search_project_staff_by_project(token, client, project_id)
    matching = [s for s in staff_list if s.get("userId") == userservice_uuid]
    assert matching, f"No staff found with userId {userservice_uuid} after bulk create"
    print(f"Verified: staff with userId {userservice_uuid} found in search results")


@pytest.mark.positive
def test_update_project_staff_bulk():
    """Test to bulk update a project staff. Creates staff first, then bulk updates the endDate."""
    token = get_auth_token("user")
    client = APIClient(token=token)

    # Step 1: Create dependencies
    print("Creating project...")
    project_id, project_status = create_individual_project(token, client, boundaryType, boundaryCode)
    assert project_status in [200, 202], f"Project creation failed with status: {project_status}"
    print(f"Project created with ID: {project_id}")

    print("Creating employee...")
    from tests.test_hrms_service import create_employee
    _, _, _, userservice_uuid, employee_status = create_employee(token, client)
    assert employee_status in [200, 202], f"Employee creation failed"
    print(f"Employee created with userServiceUuid: {userservice_uuid}")

    print("Creating project staff (regular create to get staff data)...")
    staff_data, staff_status = create_project_staff_full(token, client, project_id, userservice_uuid)
    assert staff_status in [200, 202], f"Project Staff creation failed with status: {staff_status}"
    print(f"Project Staff created with ID: {staff_data['id']}")

    # Step 2: Bulk update the project staff (change endDate) — response is always 202
    original_end_date = staff_data.get("endDate")
    new_end_date = 1987670400000
    print(f"Original endDate: {original_end_date}")

    response = update_project_staff_bulk(token, client, staff_data, new_end_date)
    assert response.status_code == 202, f"Project Staff bulk update failed: {response.text}"
    print("Bulk update accepted with 202")

    # Step 3: Search and verify endDate was updated
    staff_list = search_project_staff_by_project(token, client, project_id)
    updated = next((s for s in staff_list if s.get("id") == staff_data["id"]), None)
    assert updated is not None, f"Staff {staff_data['id']} not found after bulk update"
    assert updated.get("endDate") == new_end_date, f"endDate not updated. Expected {new_end_date}, got {updated.get('endDate')}"
    print(f"Project Staff bulk updated successfully. endDate changed from '{original_end_date}' to '{new_end_date}'")


@pytest.mark.positive
def test_delete_project_staff_bulk():
    """Test to bulk delete a project staff. Creates staff first, then bulk deletes it."""
    token = get_auth_token("user")
    client = APIClient(token=token)

    # Step 1: Create dependencies
    print("Creating project...")
    project_id, project_status = create_individual_project(token, client, boundaryType, boundaryCode)
    assert project_status in [200, 202], f"Project creation failed with status: {project_status}"
    print(f"Project created with ID: {project_id}")

    print("Creating employee...")
    from tests.test_hrms_service import create_employee
    _, _, _, userservice_uuid, employee_status = create_employee(token, client)
    assert employee_status in [200, 202], f"Employee creation failed"
    print(f"Employee created with userServiceUuid: {userservice_uuid}")

    print("Creating project staff (regular create to get staff data)...")
    staff_data, staff_status = create_project_staff_full(token, client, project_id, userservice_uuid)
    assert staff_status in [200, 202], f"Project Staff creation failed with status: {staff_status}"
    staff_id = staff_data["id"]
    print(f"Project Staff created with ID: {staff_id}")

    # Step 2: Bulk delete the project staff — response is always 202
    print("Bulk deleting project staff...")
    response = delete_project_staff_bulk(token, client, staff_data)
    assert response.status_code == 202, f"Project Staff bulk delete failed: {response.text}"
    print(f"Project Staff {staff_id} bulk deleted successfully (202 accepted)")


@pytest.mark.positive
def test_delete_project_beneficiary():
    """Test to delete a project beneficiary. Creates all dependencies internally first, then deletes it."""
    token = get_auth_token("user")
    client = APIClient(token=token)

    # Step 1: Create all dependencies internally
    print("Creating project...")
    project_id, project_status = create_individual_project(token, client, boundaryType, boundaryCode)
    assert project_status in [200, 202], f"Project creation failed with status: {project_status}"
    print(f"Project created with ID: {project_id}")

    print("Creating household...")
    household_id, household_client_ref_id, household_status = create_household(token, client)
    assert household_status in [200, 202], f"Household creation failed with status: {household_status}"

    print("Creating individual...")
    individual_id, individual_client_ref_id, _, individual_status = create_individual(token, client)
    assert individual_status in [200, 202], f"Individual creation failed with status: {individual_status}"

    print("Creating household member...")
    member_response = create_household_member(token, client, household_id, household_client_ref_id, individual_id, individual_client_ref_id)
    assert member_response.status_code in [200, 202], f"Household Member creation failed"

    print("Creating project beneficiary...")
    beneficiary_data, beneficiary_status = create_project_beneficiary_full(token, client, project_id, individual_id, individual_client_ref_id)
    assert beneficiary_status in [200, 202], f"Project Beneficiary creation failed with status: {beneficiary_status}"
    beneficiary_id = beneficiary_data['id']
    print(f"Project Beneficiary created with ID: {beneficiary_id}")

    # Step 2: Delete the project beneficiary
    print("Deleting project beneficiary...")
    response = delete_project_beneficiary(token, client, beneficiary_data)
    assert response.status_code in [200, 202], f"Project Beneficiary delete failed: {response.text}"

    # Step 3: Verify deletion
    deleted_beneficiary = response.json()["ProjectBeneficiary"]
    assert deleted_beneficiary["isDeleted"] == True, f"Project Beneficiary not marked as deleted"
    print(f"Project Beneficiary {beneficiary_id} deleted successfully")


@pytest.mark.positive
def test_create_project_beneficiary_bulk():
    """Test to bulk create a project beneficiary. Asserts 202, then verifies via search by clientReferenceId."""
    token = get_auth_token("user")
    client = APIClient(token=token)

    print("Creating project...")
    project_id, project_status = create_individual_project(token, client, boundaryType, boundaryCode)
    assert project_status in [200, 202], f"Project creation failed with status: {project_status}"
    print(f"Project created with ID: {project_id}")

    print("Creating individual...")
    individual_id, individual_client_ref_id, _, individual_status = create_individual(token, client)
    assert individual_status in [200, 202], f"Individual creation failed with status: {individual_status}"
    print(f"Individual created with ID: {individual_id}")

    print("Bulk creating project beneficiary...")
    client_ref_id, status_code = create_project_beneficiary_bulk(token, client, project_id, individual_id, individual_client_ref_id)
    assert status_code == 202, f"Project Beneficiary bulk creation failed with status: {status_code}"
    print("Bulk create accepted with 202")

    beneficiaries = search_project_beneficiary_by_client_ref(token, client, client_ref_id)
    assert beneficiaries, f"No project beneficiary found with clientReferenceId {client_ref_id} after bulk create"
    assert beneficiaries[0]["clientReferenceId"] == client_ref_id
    print(f"Verified: project beneficiary with clientReferenceId {client_ref_id} found in search results")


@pytest.mark.positive
def test_update_project_beneficiary_bulk():
    """Test to bulk update a project beneficiary. Creates all dependencies first, then bulk updates tag."""
    token = get_auth_token("user")
    client = APIClient(token=token)

    print("Creating project...")
    project_id, project_status = create_individual_project(token, client, boundaryType, boundaryCode)
    assert project_status in [200, 202], f"Project creation failed with status: {project_status}"
    print(f"Project created with ID: {project_id}")

    print("Creating individual...")
    individual_id, individual_client_ref_id, _, individual_status = create_individual(token, client)
    assert individual_status in [200, 202], f"Individual creation failed with status: {individual_status}"
    print(f"Individual created with ID: {individual_id}")

    print("Creating project beneficiary (regular create to get full data)...")
    beneficiary_data, beneficiary_status = create_project_beneficiary_full(token, client, project_id, individual_id, individual_client_ref_id)
    assert beneficiary_status in [200, 202], f"Project Beneficiary creation failed with status: {beneficiary_status}"
    print(f"Project Beneficiary created with ID: {beneficiary_data['id']}")

    new_tag = "UPDATED_TAG"
    print(f"Bulk updating project beneficiary tag to '{new_tag}'...")
    response = update_project_beneficiary_bulk(token, client, beneficiary_data, new_tag)
    assert response.status_code == 202, f"Project Beneficiary bulk update failed: {response.text}"
    print("Bulk update accepted with 202")

    beneficiaries = search_project_beneficiary_by_client_ref(token, client, beneficiary_data["clientReferenceId"])
    assert beneficiaries, f"Project Beneficiary not found after bulk update"
    assert beneficiaries[0].get("tag") == new_tag, f"tag not updated. Got {beneficiaries[0].get('tag')}"
    print(f"Project Beneficiary bulk updated successfully. tag verified as '{new_tag}'.")


@pytest.mark.positive
def test_delete_project_beneficiary_bulk():
    """Test to bulk delete a project beneficiary. Creates all dependencies first, then bulk deletes it."""
    token = get_auth_token("user")
    client = APIClient(token=token)

    print("Creating project...")
    project_id, project_status = create_individual_project(token, client, boundaryType, boundaryCode)
    assert project_status in [200, 202], f"Project creation failed with status: {project_status}"
    print(f"Project created with ID: {project_id}")

    print("Creating individual...")
    individual_id, individual_client_ref_id, _, individual_status = create_individual(token, client)
    assert individual_status in [200, 202], f"Individual creation failed with status: {individual_status}"
    print(f"Individual created with ID: {individual_id}")

    print("Creating project beneficiary (regular create to get full data)...")
    beneficiary_data, beneficiary_status = create_project_beneficiary_full(token, client, project_id, individual_id, individual_client_ref_id)
    assert beneficiary_status in [200, 202], f"Project Beneficiary creation failed with status: {beneficiary_status}"
    beneficiary_id = beneficiary_data["id"]
    print(f"Project Beneficiary created with ID: {beneficiary_id}")

    print("Bulk deleting project beneficiary...")
    response = delete_project_beneficiary_bulk(token, client, beneficiary_data)
    assert response.status_code == 202, f"Project Beneficiary bulk delete failed: {response.text}"
    print(f"Project Beneficiary {beneficiary_id} bulk deleted successfully (202 accepted)")


@pytest.mark.positive
def test_delete_project_task():
    """Test to delete a project task. Creates all dependencies internally first, then deletes it."""
    token = get_auth_token("user")
    client = APIClient(token=token)

    # Step 1: Create all dependencies internally
    print("Creating product variant...")
    variant_response = create_product_variant(token, client)
    assert variant_response.status_code in [200, 202], f"Product Variant creation failed"
    variant_id = variant_response.json()["ProductVariant"][0]["id"]

    print("Creating project...")
    project_id, project_status = create_individual_project(token, client, boundaryType, boundaryCode, variant_id, variant_id)
    assert project_status in [200, 202], f"Project creation failed with status: {project_status}"
    print(f"Project created with ID: {project_id}")

    print("Creating project resource...")
    resource_id, resource_status = create_project_resource(token, client, project_id, variant_id)
    assert resource_status in [200, 202], f"Project Resource creation failed"

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
    task_data, task_status = create_project_task_full(token, client, project_id, beneficiary_id, beneficiary_client_ref_id, variant_id)
    assert task_status in [200, 202], f"Project Task creation failed with status: {task_status}"
    task_id = task_data['id']
    print(f"Project Task created with ID: {task_id}")

    # Step 2: Delete the project task
    print("Deleting project task...")
    response = delete_project_task(token, client, task_data)
    assert response.status_code in [200, 202], f"Project Task delete failed: {response.text}"

    # Step 3: Verify deletion
    deleted_task = response.json()["Task"]
    assert deleted_task["isDeleted"] == True, f"Project Task not marked as deleted"
    print(f"Project Task {task_id} deleted successfully")


@pytest.mark.positive
def test_create_project_task_bulk():
    """Test to bulk create a project task. Asserts 202, then verifies via search by clientReferenceId."""
    token = get_auth_token("user")
    client = APIClient(token=token)

    print("Creating product variant...")
    variant_response = create_product_variant(token, client)
    assert variant_response.status_code in [200, 202], f"Product Variant creation failed"
    variant_id = variant_response.json()["ProductVariant"][0]["id"]

    print("Creating project...")
    project_id, project_status = create_individual_project(token, client, boundaryType, boundaryCode, variant_id, variant_id)
    assert project_status in [200, 202], f"Project creation failed with status: {project_status}"
    print(f"Project created with ID: {project_id}")

    print("Creating project resource...")
    resource_id, resource_status = create_project_resource(token, client, project_id, variant_id)
    assert resource_status in [200, 202], f"Project Resource creation failed"

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

    print("Bulk creating project task...")
    client_ref_id, status_code = create_project_task_bulk(token, client, project_id, beneficiary_id, beneficiary_client_ref_id, variant_id)
    assert status_code == 202, f"Project Task bulk creation failed with status: {status_code}"
    print("Bulk create accepted with 202")

    tasks = poll_until_found(lambda: search_project_task_by_client_ref(token, client, client_ref_id))
    assert tasks, f"No project task found with clientReferenceId {client_ref_id} after bulk create"
    assert tasks[0]["clientReferenceId"] == client_ref_id
    print(f"Verified: project task with clientReferenceId {client_ref_id} found in search results")


@pytest.mark.positive
def test_update_project_task_bulk():
    """Test to bulk update a project task. Creates all dependencies first, then bulk updates status."""
    token = get_auth_token("user")
    client = APIClient(token=token)

    print("Creating product variant...")
    variant_response = create_product_variant(token, client)
    assert variant_response.status_code in [200, 202], f"Product Variant creation failed"
    variant_id = variant_response.json()["ProductVariant"][0]["id"]

    print("Creating project...")
    project_id, project_status = create_individual_project(token, client, boundaryType, boundaryCode, variant_id, variant_id)
    assert project_status in [200, 202], f"Project creation failed with status: {project_status}"
    print(f"Project created with ID: {project_id}")

    print("Creating project resource...")
    resource_id, resource_status = create_project_resource(token, client, project_id, variant_id)
    assert resource_status in [200, 202], f"Project Resource creation failed"

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

    print("Creating project task (regular create to get full data)...")
    task_data, task_status = create_project_task_full(token, client, project_id, beneficiary_id, beneficiary_client_ref_id, variant_id)
    assert task_status in [200, 202], f"Project Task creation failed with status: {task_status}"
    print(f"Project Task created with ID: {task_data['id']}")

    new_status = "BENEFICIARY_REFUSED"
    print(f"Bulk updating project task status to '{new_status}'...")
    response = update_project_task_bulk(token, client, task_data, new_status)
    assert response.status_code == 202, f"Project Task bulk update failed: {response.text}"
    print("Bulk update accepted with 202")

    tasks = poll_until_match(
        lambda: search_project_task_by_client_ref(token, client, task_data["clientReferenceId"]),
        lambda results: results[0].get("status") == new_status,
        retries=10,
        delay=5
    )
    assert tasks, f"Project Task not found after bulk update"
    assert tasks[0].get("status") == new_status, f"status not updated. Got {tasks[0].get('status')}"
    print(f"Project Task bulk updated successfully. status verified as '{new_status}'.")


@pytest.mark.positive
def test_delete_project_task_bulk():
    """Test to bulk delete a project task. Creates all dependencies first, then bulk deletes it."""
    token = get_auth_token("user")
    client = APIClient(token=token)

    print("Creating product variant...")
    variant_response = create_product_variant(token, client)
    assert variant_response.status_code in [200, 202], f"Product Variant creation failed"
    variant_id = variant_response.json()["ProductVariant"][0]["id"]

    print("Creating project...")
    project_id, project_status = create_individual_project(token, client, boundaryType, boundaryCode, variant_id, variant_id)
    assert project_status in [200, 202], f"Project creation failed with status: {project_status}"
    print(f"Project created with ID: {project_id}")

    print("Creating project resource...")
    resource_id, resource_status = create_project_resource(token, client, project_id, variant_id)
    assert resource_status in [200, 202], f"Project Resource creation failed"

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

    print("Creating project task (regular create to get full data)...")
    task_data, task_status = create_project_task_full(token, client, project_id, beneficiary_id, beneficiary_client_ref_id, variant_id)
    assert task_status in [200, 202], f"Project Task creation failed with status: {task_status}"
    task_id = task_data["id"]
    print(f"Project Task created with ID: {task_id}")

    print("Bulk deleting project task...")
    response = delete_project_task_bulk(token, client, task_data)
    assert response.status_code == 202, f"Project Task bulk delete failed: {response.text}"
    print(f"Project Task {task_id} bulk deleted successfully (202 accepted)")


# --- Helper functions ---

def search_project_by_id(token, client, project_id):
    payload = load_payload("project", "search_project.json")
    payload["RequestInfo"] = get_request_info(token)
    payload["Projects"][0]["id"] = project_id

    url = f"/{project}/v1/_search?limit=10&offset=0&tenantId={tenantId}"
    response = client.post(url, payload)

    if response.status_code != 200:
        return []
    return response.json().get("Project", [])


def create_individual_project(token, client, boundaryType, boundaryCode, variant_id_1=None, variant_id_2=None):
    projectTypeId = extract_id_from_file("MR-DN:")
    payload = load_payload("project", "create_individual_project.json")
    payload["RequestInfo"] = get_request_info(token)
    if projectTypeId:
        payload["Projects"][0]["projectTypeId"] = projectTypeId
        payload["Projects"][0]["additionalDetails"]["projectType"]["id"] = projectTypeId
    payload["Projects"][0]["tenantId"] = tenantId
    payload["Projects"][0]["address"]["tenantId"] = tenantId
    payload["Projects"][0]["address"]["boundaryType"] = boundaryType
    payload["Projects"][0]["address"]["boundary"] = boundaryCode
    payload["Projects"][0]["address"]["locality"]["code"] = boundaryCode
    payload["Projects"][0]["startDate"] = 1767205799000
    payload["Projects"][0]["endDate"] = 1787670131000
    payload["Projects"][0]["additionalDetails"]["projectType"]["cycles"][0]["startDate"] = 1767205799000
    payload["Projects"][0]["additionalDetails"]["projectType"]["cycles"][0]["endDate"] = 1787670131000
    payload["Projects"][0]["additionalDetails"]["projectType"]["cycles"][1]["startDate"] = 1767205799000
    payload["Projects"][0]["additionalDetails"]["projectType"]["cycles"][1]["endDate"] = 1787670131000

    # Set product variant IDs if provided
    if variant_id_1 is not None and variant_id_2 is not None:
        # Update resources
        payload["Projects"][0]["additionalDetails"]["projectType"]["resources"][0]["productVariantId"] = variant_id_1
        payload["Projects"][0]["additionalDetails"]["projectType"]["resources"][1]["productVariantId"] = variant_id_2

        # Update product variants in cycles' deliveries' doseCriteria
        for cycle in payload["Projects"][0]["additionalDetails"]["projectType"]["cycles"]:
            for delivery in cycle.get("deliveries", []):
                for dose in delivery.get("doseCriteria", []):
                    for i, pv in enumerate(dose.get("ProductVariants", [])):
                        if i == 0:
                            pv["productVariantId"] = variant_id_1
                        elif i == 1:
                            pv["productVariantId"] = variant_id_2

    url = f"/{project}/v1/_create"
    response = client.post(url, payload)

    if response.status_code not in [200, 202]:
        raise Exception(f"Project creation failed with status {response.status_code}: {response.text}")

    project_data = response.json()["Project"][0]
    project_id = project_data["id"]

    if response.status_code == 202:
        poll_until_found(lambda: search_project_by_id(token, client, project_id))

    return project_id, response.status_code


def create_project_resource(token, client, project_id, variant_id):
    payload = load_payload("project/project_resource", "create_project_resource.json")
    payload["RequestInfo"] = get_request_info(token)
    payload["ProjectResource"]["tenantId"] = tenantId
    payload["ProjectResource"]["projectId"] = project_id
    payload["ProjectResource"]["resource"]["productVariantId"] = variant_id

    url = f"/{project}/resource/v1/_create"
    response = client.post(url, payload)

    if response.status_code not in [200, 202]:
        raise Exception(f"Project Resource creation failed with status {response.status_code}: {response.text}")

    resource_data = response.json()["ProjectResource"]
    resource_id = resource_data["id"]

    return resource_id, response.status_code


def search_project_resource(token, client, project_id):
    payload = load_payload("project/project_resource", "search_project_resource.json")
    payload["RequestInfo"] = get_request_info(token)
    payload["ProjectResource"]["projectId"] = [project_id]

    url = f"/{project}/resource/v1/_search?limit=100&offset=0&tenantId={tenantId}"
    response = client.post(url, payload)

    if response.status_code != 200:
        raise Exception(f"Project Resource search failed with status {response.status_code}: {response.text}")

    return response.json().get("ProjectResources", [])


def create_project_staff(token, client, project_id, userservice_uuid):
    payload = load_payload("project/project_staff", "create_project_staff.json")
    payload["RequestInfo"] = get_request_info(token)
    payload["ProjectStaff"]["tenantId"] = tenantId
    payload["ProjectStaff"]["projectId"] = project_id
    payload["ProjectStaff"]["userId"] = userservice_uuid

    url = f"/{project}/staff/v1/_create"
    response = client.post(url, payload)

    if response.status_code not in [200, 202]:
        raise Exception(f"Project Staff creation failed with status {response.status_code}: {response.text}")

    staff_data = response.json()["ProjectStaff"]
    return staff_data["id"], response.status_code


def create_project_facility(token, client, project_id, facility_id):
    payload = load_payload("project/project_facility", "create_project_facility.json")
    payload["RequestInfo"] = get_request_info(token)
    payload["ProjectFacility"]["tenantId"] = tenantId
    payload["ProjectFacility"]["projectId"] = project_id
    payload["ProjectFacility"]["facilityId"] = facility_id

    url = f"/{project}/facility/v1/_create"
    response = client.post(url, payload)

    if response.status_code not in [200, 202]:
        raise Exception(f"Project Facility creation failed with status {response.status_code}: {response.text}")

    facility_data = response.json()["ProjectFacility"]
    return facility_data["id"], response.status_code


def create_project_beneficiary(token, client, project_id, individual_id, individual_client_ref_id):
    payload = load_payload("project/project_beneficiary", "create_project_beneficiary.json")
    payload["RequestInfo"] = get_request_info(token)
    payload["ProjectBeneficiary"]["tenantId"] = tenantId
    payload["ProjectBeneficiary"]["projectId"] = project_id
    payload["ProjectBeneficiary"]["beneficiaryId"] = individual_id
    payload["ProjectBeneficiary"]["beneficiaryClientReferenceId"] = individual_client_ref_id
    payload["ProjectBeneficiary"]["clientReferenceId"] = str(uuid.uuid4())

    url = f"/{project}/beneficiary/v1/_create"
    response = client.post(url, payload)

    if response.status_code not in [200, 202]:
        raise Exception(f"Project Beneficiary creation failed with status {response.status_code}: {response.text}")

    beneficiary_data = response.json()["ProjectBeneficiary"]
    return beneficiary_data["id"], beneficiary_data["clientReferenceId"], response.status_code


def create_project_task(token, client, project_id, beneficiary_id, beneficiary_client_ref_id, variant_id):
    payload = load_payload("project/project_task", "create_project_task.json")
    payload["RequestInfo"] = get_request_info(token)
    payload["Task"]["tenantId"] = tenantId
    payload["Task"]["projectId"] = project_id
    payload["Task"]["projectBeneficiaryId"] = beneficiary_id
    payload["Task"]["projectBeneficiaryClientReferenceId"] = beneficiary_client_ref_id
    payload["Task"]["clientReferenceId"] = str(uuid.uuid4())
    payload["Task"]["address"]["tenantId"] = tenantId
    payload["Task"]["address"]["clientReferenceId"] = str(uuid.uuid4())
    payload["Task"]["address"]["locality"]["code"] = boundaryCode
    payload["Task"]["resources"][0]["tenantId"] = tenantId
    payload["Task"]["resources"][0]["clientReferenceId"] = str(uuid.uuid4())
    payload["Task"]["resources"][0]["taskClientReferenceId"] = payload["Task"]["clientReferenceId"]
    payload["Task"]["resources"][0]["productVariantId"] = variant_id

    url = f"/{project}/task/v1/_create"
    response = client.post(url, payload)

    if response.status_code not in [200, 202]:
        raise Exception(f"Project Task creation failed with status {response.status_code}: {response.text}")

    task_data = response.json()["Task"]
    return task_data["id"], task_data["clientReferenceId"], response.status_code


def search_project_beneficiary(token, client, beneficiary_id):
    """Search for a project beneficiary by ID and return full data."""
    payload = load_payload("project/project_beneficiary", "search_project_beneficiary.json")
    payload["RequestInfo"] = get_request_info(token)
    payload["ProjectBeneficiary"]["id"] = [beneficiary_id]

    url = f"/{project}/beneficiary/v1/_search?limit=100&offset=0&tenantId={tenantId}"
    response = client.post(url, payload)

    if response.status_code not in [200, 202]:
        raise Exception(f"Project Beneficiary search failed with status {response.status_code}: {response.text}")

    return response.json().get("ProjectBeneficiaries", [])


def search_project_task(token, client, task_id):
    """Search for a project task by ID and return full data."""
    payload = load_payload("project/project_task", "search_project_task.json")
    payload["RequestInfo"] = get_request_info(token)
    payload["Task"]["id"] = [task_id]

    url = f"/{project}/task/v1/_search?limit=100&offset=0&tenantId={tenantId}"
    response = client.post(url, payload)

    if response.status_code not in [200, 202]:
        raise Exception(f"Project Task search failed with status {response.status_code}: {response.text}")

    return response.json().get("Tasks", [])


def update_project_beneficiary(token, client, beneficiary_data, new_tag):
    """
    Update a project beneficiary's tag.

    Args:
        beneficiary_data: Full project beneficiary object from search
        new_tag: New tag value to set
    """
    payload = load_payload("project/project_beneficiary", "update_project_beneficiary.json")

    # Copy required fields from the searched beneficiary
    payload["ProjectBeneficiary"]["id"] = beneficiary_data["id"]
    payload["ProjectBeneficiary"]["tenantId"] = beneficiary_data["tenantId"]
    payload["ProjectBeneficiary"]["clientReferenceId"] = beneficiary_data["clientReferenceId"]
    payload["ProjectBeneficiary"]["rowVersion"] = beneficiary_data["rowVersion"]
    payload["ProjectBeneficiary"]["auditDetails"] = beneficiary_data["auditDetails"]
    payload["ProjectBeneficiary"]["clientAuditDetails"] = beneficiary_data.get("clientAuditDetails")
    payload["ProjectBeneficiary"]["projectId"] = beneficiary_data["projectId"]
    payload["ProjectBeneficiary"]["beneficiaryId"] = beneficiary_data["beneficiaryId"]
    payload["ProjectBeneficiary"]["beneficiaryClientReferenceId"] = beneficiary_data["beneficiaryClientReferenceId"]
    payload["ProjectBeneficiary"]["dateOfRegistration"] = beneficiary_data.get("dateOfRegistration")
    payload["ProjectBeneficiary"]["tag"] = new_tag
    payload["RequestInfo"] = get_request_info(token)

    url = f"/{project}/beneficiary/v1/_update"
    response = client.post(url, payload)
    return response


def update_project_task(token, client, task_data, new_status):
    """
    Update a project task's status.

    Args:
        task_data: Full project task object from search
        new_status: New status value to set
    """
    payload = load_payload("project/project_task", "update_project_task.json")

    # Copy required fields from the searched task
    payload["Task"]["id"] = task_data["id"]
    payload["Task"]["tenantId"] = task_data["tenantId"]
    payload["Task"]["clientReferenceId"] = task_data["clientReferenceId"]
    payload["Task"]["rowVersion"] = task_data["rowVersion"]
    payload["Task"]["auditDetails"] = task_data["auditDetails"]
    payload["Task"]["clientAuditDetails"] = task_data.get("clientAuditDetails")
    payload["Task"]["projectId"] = task_data["projectId"]
    payload["Task"]["projectBeneficiaryId"] = task_data["projectBeneficiaryId"]
    payload["Task"]["projectBeneficiaryClientReferenceId"] = task_data.get("projectBeneficiaryClientReferenceId")
    payload["Task"]["resources"] = task_data.get("resources", [])
    payload["Task"]["address"] = task_data.get("address")
    payload["Task"]["status"] = new_status
    payload["RequestInfo"] = get_request_info(token)

    url = f"/{project}/task/v1/_update"
    response = client.post(url, payload)
    return response


def create_project_staff_full(token, client, project_id, userservice_uuid):
    """
    Create a project staff and return full data for update operations.

    Returns:
        Tuple of (staff_data, status_code)
    """
    payload = load_payload("project/project_staff", "create_project_staff.json")
    payload["RequestInfo"] = get_request_info(token)
    payload["ProjectStaff"]["tenantId"] = tenantId
    payload["ProjectStaff"]["projectId"] = project_id
    payload["ProjectStaff"]["userId"] = userservice_uuid

    url = f"/{project}/staff/v1/_create"
    response = client.post(url, payload)

    if response.status_code not in [200, 202]:
        raise Exception(f"Project Staff creation failed with status {response.status_code}: {response.text}")

    return response.json()["ProjectStaff"], response.status_code


def create_project_resource_full(token, client, project_id, variant_id):
    """
    Create a project resource and return full data for update operations.

    Returns:
        Tuple of (resource_data, status_code)
    """
    payload = load_payload("project/project_resource", "create_project_resource.json")
    payload["RequestInfo"] = get_request_info(token)
    payload["ProjectResource"]["tenantId"] = tenantId
    payload["ProjectResource"]["projectId"] = project_id
    payload["ProjectResource"]["resource"]["productVariantId"] = variant_id

    url = f"/{project}/resource/v1/_create"
    response = client.post(url, payload)

    if response.status_code not in [200, 202]:
        raise Exception(f"Project Resource creation failed with status {response.status_code}: {response.text}")

    return response.json()["ProjectResource"], response.status_code


def create_project_facility_full(token, client, project_id, facility_id):
    """
    Create a project facility and return full data for update operations.

    Returns:
        Tuple of (facility_data, status_code)
    """
    payload = load_payload("project/project_facility", "create_project_facility.json")
    payload["RequestInfo"] = get_request_info(token)
    payload["ProjectFacility"]["tenantId"] = tenantId
    payload["ProjectFacility"]["projectId"] = project_id
    payload["ProjectFacility"]["facilityId"] = facility_id

    url = f"/{project}/facility/v1/_create"
    response = client.post(url, payload)

    if response.status_code not in [200, 202]:
        raise Exception(f"Project Facility creation failed with status {response.status_code}: {response.text}")

    return response.json()["ProjectFacility"], response.status_code


def update_project_staff(token, client, staff_data, new_end_date):
    """
    Update a project staff's endDate.

    Args:
        staff_data: Full project staff object from create response
        new_end_date: New endDate value to set
    """
    payload = load_payload("project/project_staff", "update_project_staff.json")

    # Copy required fields from the created staff
    payload["ProjectStaff"]["id"] = staff_data["id"]
    payload["ProjectStaff"]["tenantId"] = staff_data["tenantId"]
    payload["ProjectStaff"]["rowVersion"] = staff_data["rowVersion"]
    payload["ProjectStaff"]["auditDetails"] = staff_data["auditDetails"]
    payload["ProjectStaff"]["userId"] = staff_data["userId"]
    payload["ProjectStaff"]["projectId"] = staff_data["projectId"]
    payload["ProjectStaff"]["startDate"] = staff_data.get("startDate")
    payload["ProjectStaff"]["endDate"] = new_end_date
    payload["RequestInfo"] = get_request_info(token)

    url = f"/{project}/staff/v1/_update"
    response = client.post(url, payload)
    return response


def update_project_resource(token, client, resource_data, new_type):
    """
    Update a project resource's type.

    Args:
        resource_data: Full project resource object from create response
        new_type: New resource type value to set
    """
    payload = load_payload("project/project_resource", "update_project_resource.json")

    # Copy required fields from the created resource
    payload["ProjectResource"]["id"] = resource_data["id"]
    payload["ProjectResource"]["tenantId"] = resource_data["tenantId"]
    payload["ProjectResource"]["rowVersion"] = resource_data["rowVersion"]
    payload["ProjectResource"]["auditDetails"] = resource_data["auditDetails"]
    payload["ProjectResource"]["projectId"] = resource_data["projectId"]
    payload["ProjectResource"]["resource"] = resource_data["resource"].copy()
    payload["ProjectResource"]["resource"]["type"] = new_type
    payload["ProjectResource"]["startDate"] = resource_data.get("startDate")
    payload["ProjectResource"]["endDate"] = resource_data.get("endDate")
    payload["RequestInfo"] = get_request_info(token)

    url = f"/{project}/resource/v1/_update"
    response = client.post(url, payload)
    return response


def update_project_facility(token, client, facility_data, new_additional_fields):
    """
    Update a project facility's additionalFields.

    Args:
        facility_data: Full project facility object from create response
        new_additional_fields: New additionalFields value to set
    """
    payload = load_payload("project/project_facility", "update_project_facility.json")

    # Copy required fields from the created facility
    payload["ProjectFacility"]["id"] = facility_data["id"]
    payload["ProjectFacility"]["tenantId"] = facility_data["tenantId"]
    payload["ProjectFacility"]["rowVersion"] = facility_data["rowVersion"]
    payload["ProjectFacility"]["auditDetails"] = facility_data["auditDetails"]
    payload["ProjectFacility"]["facilityId"] = facility_data["facilityId"]
    payload["ProjectFacility"]["projectId"] = facility_data["projectId"]
    payload["ProjectFacility"]["additionalFields"] = new_additional_fields
    payload["RequestInfo"] = get_request_info(token)

    url = f"/{project}/facility/v1/_update"
    response = client.post(url, payload)
    return response


def create_individual_project_full(token, client, boundaryType, boundaryCode, variant_id_1=None, variant_id_2=None):
    """
    Create a project and return full data for update operations.

    Returns:
        Tuple of (project_data, status_code)
    """
    projectTypeId = extract_id_from_file("MR-DN:")
    payload = load_payload("project", "create_individual_project.json")
    payload["RequestInfo"] = get_request_info(token)
    if projectTypeId:
        payload["Projects"][0]["projectTypeId"] = projectTypeId
        payload["Projects"][0]["additionalDetails"]["projectType"]["id"] = projectTypeId
    payload["Projects"][0]["tenantId"] = tenantId
    payload["Projects"][0]["address"]["tenantId"] = tenantId
    payload["Projects"][0]["address"]["boundaryType"] = boundaryType
    payload["Projects"][0]["address"]["boundary"] = boundaryCode
    payload["Projects"][0]["address"]["locality"]["code"] = boundaryCode
    payload["Projects"][0]["startDate"] = 1767205799000
    payload["Projects"][0]["endDate"] = 1787670131000
    payload["Projects"][0]["additionalDetails"]["projectType"]["cycles"][0]["startDate"] = 1767205799000
    payload["Projects"][0]["additionalDetails"]["projectType"]["cycles"][0]["endDate"] = 1787670131000
    payload["Projects"][0]["additionalDetails"]["projectType"]["cycles"][1]["startDate"] = 1767205799000
    payload["Projects"][0]["additionalDetails"]["projectType"]["cycles"][1]["endDate"] = 1787670131000

    # Set product variant IDs if provided
    if variant_id_1 is not None and variant_id_2 is not None:
        # Update resources
        payload["Projects"][0]["additionalDetails"]["projectType"]["resources"][0]["productVariantId"] = variant_id_1
        payload["Projects"][0]["additionalDetails"]["projectType"]["resources"][1]["productVariantId"] = variant_id_2

        # Update product variants in cycles' deliveries' doseCriteria
        for cycle in payload["Projects"][0]["additionalDetails"]["projectType"]["cycles"]:
            for delivery in cycle.get("deliveries", []):
                for dose in delivery.get("doseCriteria", []):
                    for i, pv in enumerate(dose.get("ProductVariants", [])):
                        if i == 0:
                            pv["productVariantId"] = variant_id_1
                        elif i == 1:
                            pv["productVariantId"] = variant_id_2

    url = f"/{project}/v1/_create"
    response = client.post(url, payload)

    if response.status_code not in [200, 202]:
        raise Exception(f"Project creation failed with status {response.status_code}: {response.text}")

    return response.json()["Project"][0], response.status_code


def update_project(token, client, project_data, new_description):
    """
    Update a project's description.

    Args:
        project_data: Full project object from create response
        new_description: New description value to set
    """
    payload = load_payload("project", "update_project.json")

    # Copy required fields from the created project
    payload["Projects"][0]["id"] = project_data["id"]
    payload["Projects"][0]["tenantId"] = project_data["tenantId"]
    payload["Projects"][0]["projectNumber"] = project_data.get("projectNumber")
    payload["Projects"][0]["name"] = project_data.get("name")
    payload["Projects"][0]["projectType"] = project_data.get("projectType")
    payload["Projects"][0]["projectSubType"] = project_data.get("projectSubType")
    payload["Projects"][0]["department"] = project_data.get("department")
    payload["Projects"][0]["description"] = new_description
    payload["Projects"][0]["referenceID"] = project_data.get("referenceID")
    payload["Projects"][0]["projectTypeId"] = project_data.get("projectTypeId")
    payload["Projects"][0]["address"] = project_data.get("address")
    payload["Projects"][0]["startDate"] = project_data.get("startDate")
    payload["Projects"][0]["endDate"] = project_data.get("endDate")
    payload["Projects"][0]["isTaskEnabled"] = project_data.get("isTaskEnabled", False)
    payload["Projects"][0]["targets"] = project_data.get("targets", [])
    payload["Projects"][0]["additionalDetails"] = project_data.get("additionalDetails")
    payload["Projects"][0]["rowVersion"] = project_data.get("rowVersion", 0)
    payload["Projects"][0]["auditDetails"] = project_data.get("auditDetails")
    payload["RequestInfo"] = get_request_info(token)

    url = f"/{project}/v1/_update"
    response = client.post(url, payload)
    return response


def delete_project_facility(token, client, facility_data):
    """
    Delete a project facility (soft delete by setting isDeleted=true).

    Args:
        facility_data: Full project facility object from create response
    """
    payload = load_payload("project/project_facility", "delete_project_facility.json")

    # Copy required fields from the created facility
    payload["ProjectFacility"]["id"] = facility_data["id"]
    payload["ProjectFacility"]["tenantId"] = facility_data["tenantId"]
    payload["ProjectFacility"]["rowVersion"] = facility_data["rowVersion"]
    payload["ProjectFacility"]["auditDetails"] = facility_data["auditDetails"]
    payload["ProjectFacility"]["facilityId"] = facility_data["facilityId"]
    payload["ProjectFacility"]["projectId"] = facility_data["projectId"]
    payload["ProjectFacility"]["additionalFields"] = facility_data.get("additionalFields")
    payload["ProjectFacility"]["isDeleted"] = True
    payload["RequestInfo"] = get_request_info(token)

    url = f"/{project}/facility/v1/_delete"
    response = client.post(url, payload)
    return response


def create_project_facility_bulk(token, client, project_id, facility_id):
    payload = load_payload("project/project_facility", "create_bulk_project_facility.json")
    payload["RequestInfo"] = get_request_info(token)
    payload["ProjectFacilities"][0]["tenantId"] = tenantId
    payload["ProjectFacilities"][0]["projectId"] = project_id
    payload["ProjectFacilities"][0]["facilityId"] = facility_id

    url = f"/{project}/facility/v1/bulk/_create"
    response = client.post(url, payload)

    if response.status_code not in [200, 202]:
        raise Exception(f"Project Facility bulk create failed with status {response.status_code}: {response.text}")

    return response.status_code


def update_project_facility_bulk(token, client, facility_data, new_additional_fields):
    payload = load_payload("project/project_facility", "update_bulk_project_facility.json")
    payload["RequestInfo"] = get_request_info(token)
    payload["ProjectFacilities"][0]["id"] = facility_data["id"]
    payload["ProjectFacilities"][0]["tenantId"] = facility_data["tenantId"]
    payload["ProjectFacilities"][0]["rowVersion"] = facility_data["rowVersion"]
    payload["ProjectFacilities"][0]["auditDetails"] = facility_data["auditDetails"]
    payload["ProjectFacilities"][0]["facilityId"] = facility_data["facilityId"]
    payload["ProjectFacilities"][0]["projectId"] = facility_data["projectId"]
    payload["ProjectFacilities"][0]["additionalFields"] = new_additional_fields
    payload["ProjectFacilities"][0]["isDeleted"] = False

    url = f"/{project}/facility/v1/bulk/_update"
    response = client.post(url, payload)
    return response


def delete_project_facility_bulk(token, client, facility_data):
    payload = load_payload("project/project_facility", "delete_bulk_project_facility.json")
    payload["RequestInfo"] = get_request_info(token)
    payload["ProjectFacilities"][0]["id"] = facility_data["id"]
    payload["ProjectFacilities"][0]["tenantId"] = facility_data["tenantId"]
    payload["ProjectFacilities"][0]["rowVersion"] = facility_data["rowVersion"]
    payload["ProjectFacilities"][0]["auditDetails"] = facility_data["auditDetails"]
    payload["ProjectFacilities"][0]["facilityId"] = facility_data["facilityId"]
    payload["ProjectFacilities"][0]["projectId"] = facility_data["projectId"]
    payload["ProjectFacilities"][0]["additionalFields"] = facility_data.get("additionalFields")
    payload["ProjectFacilities"][0]["isDeleted"] = True

    url = f"/{project}/facility/v1/bulk/_delete"
    response = client.post(url, payload)
    return response


def search_project_facility_by_project(token, client, project_id):
    payload = load_payload("project/project_facility", "search_project_facility.json")
    payload["RequestInfo"] = get_request_info(token)
    payload["ProjectFacility"] = {"projectId": [project_id]}

    url = f"/{project}/facility/v1/_search?limit=100&offset=0&tenantId={tenantId}"
    response = client.post(url, payload)

    if response.status_code not in [200, 202]:
        raise Exception(f"Project Facility search failed with status {response.status_code}: {response.text}")

    return response.json().get("ProjectFacilities", [])


def delete_project_resource(token, client, resource_data):
    """
    Delete a project resource (soft delete by setting isDeleted=true).

    Args:
        resource_data: Full project resource object from create response
    """
    payload = load_payload("project/project_resource", "delete_project_resource.json")

    # Copy required fields from the created resource
    payload["ProjectResource"]["id"] = resource_data["id"]
    payload["ProjectResource"]["tenantId"] = resource_data["tenantId"]
    payload["ProjectResource"]["rowVersion"] = resource_data["rowVersion"]
    payload["ProjectResource"]["auditDetails"] = resource_data["auditDetails"]
    payload["ProjectResource"]["projectId"] = resource_data["projectId"]
    payload["ProjectResource"]["resource"] = resource_data["resource"]
    payload["ProjectResource"]["startDate"] = resource_data.get("startDate")
    payload["ProjectResource"]["endDate"] = resource_data.get("endDate")
    payload["ProjectResource"]["isDeleted"] = True
    payload["RequestInfo"] = get_request_info(token)

    url = f"/{project}/resource/v1/_delete"
    response = client.post(url, payload)
    return response


def create_project_resource_bulk(token, client, project_id, variant_id):
    payload = load_payload("project/project_resource", "create_bulk_project_resource.json")
    payload["RequestInfo"] = get_request_info(token)
    payload["ProjectResources"][0]["tenantId"] = tenantId
    payload["ProjectResources"][0]["projectId"] = project_id
    payload["ProjectResources"][0]["resource"]["productVariantId"] = variant_id

    url = f"/{project}/resource/v1/bulk/_create"
    response = client.post(url, payload)

    if response.status_code not in [200, 202]:
        raise Exception(f"Project Resource bulk creation failed with status {response.status_code}: {response.text}")

    return response.status_code


def update_project_resource_bulk(token, client, resource_data, new_type):
    payload = load_payload("project/project_resource", "update_bulk_project_resource.json")

    payload["ProjectResources"][0]["id"] = resource_data["id"]
    payload["ProjectResources"][0]["tenantId"] = resource_data["tenantId"]
    payload["ProjectResources"][0]["rowVersion"] = resource_data["rowVersion"]
    payload["ProjectResources"][0]["auditDetails"] = resource_data["auditDetails"]
    payload["ProjectResources"][0]["projectId"] = resource_data["projectId"]
    payload["ProjectResources"][0]["resource"] = resource_data["resource"].copy()
    payload["ProjectResources"][0]["resource"]["type"] = new_type
    payload["ProjectResources"][0]["startDate"] = resource_data.get("startDate")
    payload["ProjectResources"][0]["endDate"] = resource_data.get("endDate")
    payload["RequestInfo"] = get_request_info(token)

    url = f"/{project}/resource/v1/bulk/_update"
    response = client.post(url, payload)
    return response


def delete_project_resource_bulk(token, client, resource_data):
    payload = load_payload("project/project_resource", "delete_bulk_project_resource.json")

    payload["ProjectResources"][0]["id"] = resource_data["id"]
    payload["ProjectResources"][0]["tenantId"] = resource_data["tenantId"]
    payload["ProjectResources"][0]["rowVersion"] = resource_data["rowVersion"]
    payload["ProjectResources"][0]["auditDetails"] = resource_data["auditDetails"]
    payload["ProjectResources"][0]["projectId"] = resource_data["projectId"]
    payload["ProjectResources"][0]["resource"] = resource_data["resource"]
    payload["ProjectResources"][0]["startDate"] = resource_data.get("startDate")
    payload["ProjectResources"][0]["endDate"] = resource_data.get("endDate")
    payload["ProjectResources"][0]["isDeleted"] = True
    payload["RequestInfo"] = get_request_info(token)

    url = f"/{project}/resource/v1/bulk/_delete"
    response = client.post(url, payload)
    return response


def delete_project_staff(token, client, staff_data):
    """
    Delete a project staff (soft delete by setting isDeleted=true).

    Args:
        staff_data: Full project staff object from create response
    """
    payload = load_payload("project/project_staff", "delete_project_staff.json")

    # Copy required fields from the created staff
    payload["ProjectStaff"]["id"] = staff_data["id"]
    payload["ProjectStaff"]["tenantId"] = staff_data["tenantId"]
    payload["ProjectStaff"]["rowVersion"] = staff_data["rowVersion"]
    payload["ProjectStaff"]["auditDetails"] = staff_data["auditDetails"]
    payload["ProjectStaff"]["userId"] = staff_data["userId"]
    payload["ProjectStaff"]["projectId"] = staff_data["projectId"]
    payload["ProjectStaff"]["startDate"] = staff_data.get("startDate")
    payload["ProjectStaff"]["endDate"] = staff_data.get("endDate")
    payload["ProjectStaff"]["additionalFields"] = staff_data.get("additionalFields")
    payload["ProjectStaff"]["isDeleted"] = True
    payload["RequestInfo"] = get_request_info(token)

    url = f"/{project}/staff/v1/_delete"
    response = client.post(url, payload)
    return response


def create_project_staff_bulk(token, client, project_id, userservice_uuid):
    payload = load_payload("project/project_staff", "create_bulk_project_staff.json")
    payload["RequestInfo"] = get_request_info(token)
    payload["ProjectStaff"][0]["tenantId"] = tenantId
    payload["ProjectStaff"][0]["projectId"] = project_id
    payload["ProjectStaff"][0]["userId"] = userservice_uuid

    url = f"/{project}/staff/v1/bulk/_create"
    response = client.post(url, payload)

    if response.status_code not in [200, 202]:
        raise Exception(f"Project Staff bulk creation failed with status {response.status_code}: {response.text}")

    return response.status_code


def update_project_staff_bulk(token, client, staff_data, new_end_date):
    payload = load_payload("project/project_staff", "update_bulk_project_staff.json")

    payload["ProjectStaff"][0]["id"] = staff_data["id"]
    payload["ProjectStaff"][0]["tenantId"] = staff_data["tenantId"]
    payload["ProjectStaff"][0]["rowVersion"] = staff_data["rowVersion"]
    payload["ProjectStaff"][0]["auditDetails"] = staff_data["auditDetails"]
    payload["ProjectStaff"][0]["userId"] = staff_data["userId"]
    payload["ProjectStaff"][0]["projectId"] = staff_data["projectId"]
    payload["ProjectStaff"][0]["startDate"] = staff_data.get("startDate")
    payload["ProjectStaff"][0]["endDate"] = new_end_date
    payload["ProjectStaff"][0]["additionalFields"] = staff_data.get("additionalFields")
    payload["RequestInfo"] = get_request_info(token)

    url = f"/{project}/staff/v1/bulk/_update"
    response = client.post(url, payload)
    return response


def delete_project_staff_bulk(token, client, staff_data):
    payload = load_payload("project/project_staff", "delete_bulk_project_staff.json")

    payload["ProjectStaff"][0]["id"] = staff_data["id"]
    payload["ProjectStaff"][0]["tenantId"] = staff_data["tenantId"]
    payload["ProjectStaff"][0]["rowVersion"] = staff_data["rowVersion"]
    payload["ProjectStaff"][0]["auditDetails"] = staff_data["auditDetails"]
    payload["ProjectStaff"][0]["userId"] = staff_data["userId"]
    payload["ProjectStaff"][0]["projectId"] = staff_data["projectId"]
    payload["ProjectStaff"][0]["startDate"] = staff_data.get("startDate")
    payload["ProjectStaff"][0]["endDate"] = staff_data.get("endDate")
    payload["ProjectStaff"][0]["additionalFields"] = staff_data.get("additionalFields")
    payload["ProjectStaff"][0]["isDeleted"] = True
    payload["RequestInfo"] = get_request_info(token)

    url = f"/{project}/staff/v1/bulk/_delete"
    response = client.post(url, payload)
    return response


def search_project_staff_by_project(token, client, project_id):
    payload = load_payload("project/project_staff", "search_project_staff.json")
    payload["RequestInfo"] = get_request_info(token)
    payload["ProjectStaff"] = {"projectId": [project_id]}

    url = f"/{project}/staff/v1/_search?limit=100&offset=0&tenantId={tenantId}"
    response = client.post(url, payload)

    if response.status_code != 200:
        raise Exception(f"Project Staff search failed with status {response.status_code}: {response.text}")

    return response.json().get("ProjectStaff", [])


def create_project_beneficiary_full(token, client, project_id, individual_id, individual_client_ref_id):
    """
    Create a project beneficiary and return full data for delete operations.

    Returns:
        Tuple of (beneficiary_data, status_code)
    """
    payload = load_payload("project/project_beneficiary", "create_project_beneficiary.json")
    payload["RequestInfo"] = get_request_info(token)
    payload["ProjectBeneficiary"]["tenantId"] = tenantId
    payload["ProjectBeneficiary"]["projectId"] = project_id
    payload["ProjectBeneficiary"]["beneficiaryId"] = individual_id
    payload["ProjectBeneficiary"]["beneficiaryClientReferenceId"] = individual_client_ref_id
    payload["ProjectBeneficiary"]["clientReferenceId"] = str(uuid.uuid4())

    url = f"/{project}/beneficiary/v1/_create"
    response = client.post(url, payload)

    if response.status_code not in [200, 202]:
        raise Exception(f"Project Beneficiary creation failed with status {response.status_code}: {response.text}")

    return response.json()["ProjectBeneficiary"], response.status_code


def create_project_task_full(token, client, project_id, beneficiary_id, beneficiary_client_ref_id, variant_id):
    """
    Create a project task and return full data for delete operations.

    Returns:
        Tuple of (task_data, status_code)
    """
    payload = load_payload("project/project_task", "create_project_task.json")
    payload["RequestInfo"] = get_request_info(token)
    payload["Task"]["tenantId"] = tenantId
    payload["Task"]["projectId"] = project_id
    payload["Task"]["projectBeneficiaryId"] = beneficiary_id
    payload["Task"]["projectBeneficiaryClientReferenceId"] = beneficiary_client_ref_id
    payload["Task"]["clientReferenceId"] = str(uuid.uuid4())
    payload["Task"]["address"]["tenantId"] = tenantId
    payload["Task"]["address"]["clientReferenceId"] = str(uuid.uuid4())
    payload["Task"]["address"]["locality"]["code"] = boundaryCode
    payload["Task"]["resources"][0]["tenantId"] = tenantId
    payload["Task"]["resources"][0]["clientReferenceId"] = str(uuid.uuid4())
    payload["Task"]["resources"][0]["taskClientReferenceId"] = payload["Task"]["clientReferenceId"]
    payload["Task"]["resources"][0]["productVariantId"] = variant_id

    url = f"/{project}/task/v1/_create"
    response = client.post(url, payload)

    if response.status_code not in [200, 202]:
        raise Exception(f"Project Task creation failed with status {response.status_code}: {response.text}")

    return response.json()["Task"], response.status_code


def delete_project_beneficiary(token, client, beneficiary_data):
    """
    Delete a project beneficiary (soft delete by setting isDeleted=true).

    Args:
        beneficiary_data: Full project beneficiary object from create response
    """
    payload = load_payload("project/project_beneficiary", "delete_project_beneficiary.json")

    # Copy required fields from the created beneficiary
    payload["ProjectBeneficiary"]["id"] = beneficiary_data["id"]
    payload["ProjectBeneficiary"]["tenantId"] = beneficiary_data["tenantId"]
    payload["ProjectBeneficiary"]["clientReferenceId"] = beneficiary_data["clientReferenceId"]
    payload["ProjectBeneficiary"]["rowVersion"] = beneficiary_data["rowVersion"]
    payload["ProjectBeneficiary"]["auditDetails"] = beneficiary_data["auditDetails"]
    payload["ProjectBeneficiary"]["clientAuditDetails"] = beneficiary_data.get("clientAuditDetails")
    payload["ProjectBeneficiary"]["projectId"] = beneficiary_data["projectId"]
    payload["ProjectBeneficiary"]["beneficiaryId"] = beneficiary_data["beneficiaryId"]
    payload["ProjectBeneficiary"]["beneficiaryClientReferenceId"] = beneficiary_data["beneficiaryClientReferenceId"]
    payload["ProjectBeneficiary"]["dateOfRegistration"] = beneficiary_data.get("dateOfRegistration")
    payload["ProjectBeneficiary"]["isDeleted"] = True
    payload["RequestInfo"] = get_request_info(token)

    url = f"/{project}/beneficiary/v1/_delete"
    response = client.post(url, payload)
    return response


def create_project_beneficiary_bulk(token, client, project_id, individual_id, individual_client_ref_id):
    payload = load_payload("project/project_beneficiary", "create_bulk_project_beneficiary.json")
    payload["RequestInfo"] = get_request_info(token)
    client_ref_id = str(uuid.uuid4())
    payload["ProjectBeneficiaries"][0]["clientReferenceId"] = client_ref_id
    payload["ProjectBeneficiaries"][0]["tenantId"] = tenantId
    payload["ProjectBeneficiaries"][0]["projectId"] = project_id
    payload["ProjectBeneficiaries"][0]["beneficiaryId"] = individual_id
    payload["ProjectBeneficiaries"][0]["beneficiaryClientReferenceId"] = individual_client_ref_id

    url = f"/{project}/beneficiary/v1/bulk/_create"
    response = client.post(url, payload)

    if response.status_code not in [200, 202]:
        raise Exception(f"Project Beneficiary bulk create failed with status {response.status_code}: {response.text}")

    return client_ref_id, response.status_code


def update_project_beneficiary_bulk(token, client, beneficiary_data, new_tag):
    payload = load_payload("project/project_beneficiary", "update_bulk_project_beneficiary.json")
    payload["RequestInfo"] = get_request_info(token)
    payload["ProjectBeneficiaries"][0]["id"] = beneficiary_data["id"]
    payload["ProjectBeneficiaries"][0]["tenantId"] = beneficiary_data["tenantId"]
    payload["ProjectBeneficiaries"][0]["clientReferenceId"] = beneficiary_data["clientReferenceId"]
    payload["ProjectBeneficiaries"][0]["rowVersion"] = beneficiary_data["rowVersion"]
    payload["ProjectBeneficiaries"][0]["auditDetails"] = beneficiary_data["auditDetails"]
    payload["ProjectBeneficiaries"][0]["clientAuditDetails"] = beneficiary_data.get("clientAuditDetails")
    payload["ProjectBeneficiaries"][0]["projectId"] = beneficiary_data["projectId"]
    payload["ProjectBeneficiaries"][0]["beneficiaryId"] = beneficiary_data["beneficiaryId"]
    payload["ProjectBeneficiaries"][0]["beneficiaryClientReferenceId"] = beneficiary_data["beneficiaryClientReferenceId"]
    payload["ProjectBeneficiaries"][0]["dateOfRegistration"] = beneficiary_data.get("dateOfRegistration")
    payload["ProjectBeneficiaries"][0]["tag"] = new_tag
    payload["ProjectBeneficiaries"][0]["isDeleted"] = False

    url = f"/{project}/beneficiary/v1/bulk/_update"
    response = client.post(url, payload)
    return response


def delete_project_beneficiary_bulk(token, client, beneficiary_data):
    payload = load_payload("project/project_beneficiary", "delete_bulk_project_beneficiary.json")
    payload["RequestInfo"] = get_request_info(token)
    payload["ProjectBeneficiaries"][0]["id"] = beneficiary_data["id"]
    payload["ProjectBeneficiaries"][0]["tenantId"] = beneficiary_data["tenantId"]
    payload["ProjectBeneficiaries"][0]["clientReferenceId"] = beneficiary_data["clientReferenceId"]
    payload["ProjectBeneficiaries"][0]["rowVersion"] = beneficiary_data["rowVersion"]
    payload["ProjectBeneficiaries"][0]["auditDetails"] = beneficiary_data["auditDetails"]
    payload["ProjectBeneficiaries"][0]["clientAuditDetails"] = beneficiary_data.get("clientAuditDetails")
    payload["ProjectBeneficiaries"][0]["projectId"] = beneficiary_data["projectId"]
    payload["ProjectBeneficiaries"][0]["beneficiaryId"] = beneficiary_data["beneficiaryId"]
    payload["ProjectBeneficiaries"][0]["beneficiaryClientReferenceId"] = beneficiary_data["beneficiaryClientReferenceId"]
    payload["ProjectBeneficiaries"][0]["dateOfRegistration"] = beneficiary_data.get("dateOfRegistration")
    payload["ProjectBeneficiaries"][0]["isDeleted"] = True

    url = f"/{project}/beneficiary/v1/bulk/_delete"
    response = client.post(url, payload)
    return response


def search_project_beneficiary_by_client_ref(token, client, client_ref_id):
    payload = load_payload("project/project_beneficiary", "search_project_beneficiary.json")
    payload["RequestInfo"] = get_request_info(token)
    payload["ProjectBeneficiary"] = {"clientReferenceId": [client_ref_id]}

    url = f"/{project}/beneficiary/v1/_search?limit=100&offset=0&tenantId={tenantId}"
    response = client.post(url, payload)

    if response.status_code not in [200, 202]:
        raise Exception(f"Project Beneficiary search failed with status {response.status_code}: {response.text}")

    return response.json().get("ProjectBeneficiaries", [])


def delete_project_task(token, client, task_data):
    """
    Delete a project task (soft delete by setting isDeleted=true).

    Args:
        task_data: Full project task object from create response
    """
    payload = load_payload("project/project_task", "delete_project_task.json")

    # Copy required fields from the created task
    payload["Task"]["id"] = task_data["id"]
    payload["Task"]["tenantId"] = task_data["tenantId"]
    payload["Task"]["clientReferenceId"] = task_data["clientReferenceId"]
    payload["Task"]["rowVersion"] = task_data["rowVersion"]
    payload["Task"]["auditDetails"] = task_data["auditDetails"]
    payload["Task"]["clientAuditDetails"] = task_data.get("clientAuditDetails")
    payload["Task"]["projectId"] = task_data["projectId"]
    payload["Task"]["projectBeneficiaryId"] = task_data["projectBeneficiaryId"]
    payload["Task"]["projectBeneficiaryClientReferenceId"] = task_data.get("projectBeneficiaryClientReferenceId")
    payload["Task"]["resources"] = task_data.get("resources", [])
    payload["Task"]["address"] = task_data.get("address")
    payload["Task"]["status"] = task_data.get("status")
    payload["Task"]["isDeleted"] = True
    payload["RequestInfo"] = get_request_info(token)

    url = f"/{project}/task/v1/_delete"
    response = client.post(url, payload)
    return response


def create_project_task_bulk(token, client, project_id, beneficiary_id, beneficiary_client_ref_id, variant_id):
    payload = load_payload("project/project_task", "create_bulk_project_task.json")
    payload["RequestInfo"] = get_request_info(token)
    client_ref_id = str(uuid.uuid4())
    payload["Tasks"][0]["clientReferenceId"] = client_ref_id
    payload["Tasks"][0]["tenantId"] = tenantId
    payload["Tasks"][0]["projectId"] = project_id
    payload["Tasks"][0]["projectBeneficiaryId"] = beneficiary_id
    payload["Tasks"][0]["projectBeneficiaryClientReferenceId"] = beneficiary_client_ref_id
    payload["Tasks"][0]["resources"][0]["clientReferenceId"] = str(uuid.uuid4())
    payload["Tasks"][0]["resources"][0]["taskClientReferenceId"] = client_ref_id
    payload["Tasks"][0]["resources"][0]["productVariantId"] = variant_id
    payload["Tasks"][0]["resources"][0]["tenantId"] = tenantId
    payload["Tasks"][0]["address"]["clientReferenceId"] = str(uuid.uuid4())
    payload["Tasks"][0]["address"]["tenantId"] = tenantId
    payload["Tasks"][0]["address"]["locality"]["code"] = boundaryCode

    url = f"/{project}/task/v1/bulk/_create"
    response = client.post(url, payload)

    if response.status_code not in [200, 202]:
        raise Exception(f"Project Task bulk create failed with status {response.status_code}: {response.text}")

    return client_ref_id, response.status_code


def update_project_task_bulk(token, client, task_data, new_status):
    payload = load_payload("project/project_task", "update_bulk_project_task.json")
    payload["RequestInfo"] = get_request_info(token)
    payload["Tasks"][0]["id"] = task_data["id"]
    payload["Tasks"][0]["tenantId"] = task_data["tenantId"]
    payload["Tasks"][0]["clientReferenceId"] = task_data["clientReferenceId"]
    payload["Tasks"][0]["rowVersion"] = task_data["rowVersion"]
    payload["Tasks"][0]["auditDetails"] = task_data["auditDetails"]
    payload["Tasks"][0]["clientAuditDetails"] = task_data.get("clientAuditDetails")
    payload["Tasks"][0]["projectId"] = task_data["projectId"]
    payload["Tasks"][0]["projectBeneficiaryId"] = task_data["projectBeneficiaryId"]
    payload["Tasks"][0]["projectBeneficiaryClientReferenceId"] = task_data.get("projectBeneficiaryClientReferenceId")
    payload["Tasks"][0]["resources"] = task_data.get("resources", [])
    payload["Tasks"][0]["address"] = task_data.get("address")
    payload["Tasks"][0]["status"] = new_status
    payload["Tasks"][0]["isDeleted"] = False

    url = f"/{project}/task/v1/bulk/_update"
    response = client.post(url, payload)
    return response


def delete_project_task_bulk(token, client, task_data):
    payload = load_payload("project/project_task", "delete_bulk_project_task.json")
    payload["RequestInfo"] = get_request_info(token)
    payload["Tasks"][0]["id"] = task_data["id"]
    payload["Tasks"][0]["tenantId"] = task_data["tenantId"]
    payload["Tasks"][0]["clientReferenceId"] = task_data["clientReferenceId"]
    payload["Tasks"][0]["rowVersion"] = task_data["rowVersion"]
    payload["Tasks"][0]["auditDetails"] = task_data["auditDetails"]
    payload["Tasks"][0]["clientAuditDetails"] = task_data.get("clientAuditDetails")
    payload["Tasks"][0]["projectId"] = task_data["projectId"]
    payload["Tasks"][0]["projectBeneficiaryId"] = task_data["projectBeneficiaryId"]
    payload["Tasks"][0]["projectBeneficiaryClientReferenceId"] = task_data.get("projectBeneficiaryClientReferenceId")
    payload["Tasks"][0]["resources"] = task_data.get("resources", [])
    payload["Tasks"][0]["address"] = task_data.get("address")
    payload["Tasks"][0]["status"] = task_data.get("status")
    payload["Tasks"][0]["isDeleted"] = True

    url = f"/{project}/task/v1/bulk/_delete"
    response = client.post(url, payload)
    return response


def search_project_task_by_client_ref(token, client, client_ref_id):
    payload = load_payload("project/project_task", "search_project_task.json")
    payload["RequestInfo"] = get_request_info(token)
    payload["Task"] = {"clientReferenceId": [client_ref_id]}

    url = f"/{project}/task/v1/_search?limit=100&offset=0&tenantId={tenantId}"
    response = client.post(url, payload)

    if response.status_code not in [200, 202]:
        raise Exception(f"Project Task search failed with status {response.status_code}: {response.text}")

    return response.json().get("Tasks", [])
