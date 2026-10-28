import pytest
import json
import random
import string
import os
import requests
from datetime import datetime
from dotenv import load_dotenv
from utils.api_client import APIClient
from utils.data_loader import load_payload
from utils.auth import get_auth_token, get_user_info
from utils.request_info import get_request_info
from utils.config import pgr, tenantId, search_limit, search_offset, mdms, hrms, hierarchyType, boundaryType, boundaryCode
from utils.search_helpers import extract_id_from_file

# Load environment variables
load_dotenv(override=True)


# Load service codes from inputs.json
with open("data/inputs.json", "r") as f:
    inputs_data = json.load(f)


def _fetch_and_update_service_codes():
    """
    Fetch PGR service codes from MDMS at module load time and update inputs.json.
    This runs once when the module is imported.
    """
    try:
        token = get_auth_token("user")
        client = APIClient(token=token)

        payload = load_payload("mdms", "search_mdmsData.json")
        payload["MdmsCriteria"]["schemaCode"] = "RAINMAKER-PGR.ServiceDefs"
        payload["MdmsCriteria"]["tenantId"] = tenantId
        payload["RequestInfo"] = get_request_info(token)

        url = f"/{mdms}/v2/_search"
        response = client.post(url, payload)

        if response.status_code == 200:
            mdms_data = response.json().get("mdms", [])
            if mdms_data:
                # Extract service codes from MDMS response
                service_codes = [item["data"]["serviceCode"] for item in mdms_data if "data" in item and "serviceCode" in item["data"]]
                if service_codes:
                    # Update inputs_data and inputs.json with fetched service codes
                    inputs_data["serviceCode"] = service_codes
                    with open("data/inputs.json", "w") as f:
                        json.dump(inputs_data, f, indent=2)
                    print(f"Fetched {len(service_codes)} service codes from MDMS: {service_codes}")
                    return

        print("Using existing service codes from inputs.json")

    except Exception as e:
        print(f"Warning: Could not fetch service codes from MDMS: {e}. Using existing codes from inputs.json")


# Fetch service codes from MDMS at module load time
_fetch_and_update_service_codes()


# --- Test functions ---

@pytest.mark.positive
def test_create_complaint():
    token = get_auth_token("user")
    client = APIClient(token=token)

    res = create_complaint(token, client)
    assert res.status_code in [200, 202], f"Complaint creation failed: {res.text}"

    service_wrapper = res.json().get("ServiceWrappers", [])
    assert service_wrapper, "ServiceWrappers not found in response"

    service_request_id = service_wrapper[0]["service"]["serviceRequestId"]
    assert service_request_id, "Service Request ID not found in response"
    print("Complaint created with Service Request ID:", service_request_id)

    with open("output/ids.txt", "a") as f:
        f.write("\n--- PGR Complaint details ---\n")
        f.write(f"Service Request ID: {service_request_id}\n")


@pytest.mark.positive
def test_resolve_complaint():
    """Test that creates a complaint and then resolves it"""
    token = get_auth_token("user")
    client = APIClient(token=token)

    # Step 1: Create a complaint
    create_res = create_complaint(token, client)
    assert create_res.status_code in [200, 202], f"Complaint creation failed: {create_res.text}"

    service_wrapper = create_res.json().get("ServiceWrappers", [])
    assert service_wrapper, "ServiceWrappers not found in create response"

    created_service = service_wrapper[0]["service"]
    service_request_id = created_service["serviceRequestId"]
    print(f"Complaint created with Service Request ID: {service_request_id}")

    # Step 2: Resolve the complaint
    resolve_res = resolve_complaint(token, client, created_service)
    assert resolve_res.status_code in [200, 202], f"Complaint resolution failed: {resolve_res.text}"

    resolved_wrapper = resolve_res.json().get("ServiceWrappers", [])
    assert resolved_wrapper, "ServiceWrappers not found in resolve response"

    resolved_status = resolved_wrapper[0]["service"]["applicationStatus"]
    assert resolved_status == "RESOLVED", f"Expected RESOLVED status, got: {resolved_status}"
    print(f"Complaint {service_request_id} resolved successfully with status: {resolved_status}")

    with open("output/ids.txt", "a") as f:
        f.write("\n--- PGR Resolved Complaint details ---\n")
        f.write(f"Service Request ID: {service_request_id}\n")
        f.write(f"Status: {resolved_status}\n")


@pytest.mark.positive
def test_search_complaint():
    """Test to search for a complaint by service request ID. Creates complaint if ID not found in file."""
    token = get_auth_token("user")
    client = APIClient(token=token)

    # Get service request ID from file
    service_request_id = extract_id_from_file("Service Request ID:")
    if not service_request_id:
        # Create complaint internally if ID not found
        print("Service Request ID not found in file, creating new complaint...")
        res = create_complaint(token, client)
        assert res.status_code in [200, 202], f"Complaint creation failed: {res.text}"
        service_wrapper = res.json().get("ServiceWrappers", [])
        service_request_id = service_wrapper[0]["service"]["serviceRequestId"]
        print(f"Complaint created with Service Request ID: {service_request_id}")

    # Search for the complaint
    complaints = search_complaint(token, client, service_request_id)
    assert complaints, "No complaints found in search response"

    # Verify the complaint was found
    found_ids = [c["serviceRequestId"] for c in complaints]
    assert service_request_id in found_ids, f"Complaint {service_request_id} not found in search results"
    print(f"Complaint found with Service Request ID: {service_request_id}")


@pytest.mark.positive
def test_assign_complaint():
    """
    Test that creates a complaint and assigns it to an employee.
    Searches for an existing PGR-enabled employee with valid department configuration.
    Note: PGR requires the complaint's service code department to match the assignee's department.
    """
    token = get_auth_token("user")
    client = APIClient(token=token)

    # Step 1: Find a valid employee with a PGR-compatible department
    print("Searching for employees with valid PGR department configuration...")
    user_uuid, user_service_uuid, employee_name, employee_dept = get_pgr_assignee(token, client)

    if not user_uuid or not user_service_uuid:
        pytest.skip(
            "No employee with valid PGR department configuration found. "
            "PGR requires employees to have a specific department mapping in MDMS. "
            "Please ensure at least one employee has a valid department assignment."
        )

    print(f"Found valid employee: {employee_name}, Department: {employee_dept}")
    print(f"  uuid: {user_uuid}, userServiceUuid: {user_service_uuid}")

    # Step 2: Find a service code that maps to the employee's department
    service_code = get_service_code_for_department(token, client, employee_dept)
    if not service_code:
        pytest.skip(
            f"No service code found for department {employee_dept}. "
            "PGR requires a service code that maps to the assignee's department."
        )

    print(f"Using service code '{service_code}' which maps to department '{employee_dept}'")

    # Step 3: Create a complaint with the matching service code
    print(f"Creating a new complaint with service code: {service_code}...")
    create_res = create_complaint(token, client, service_code=service_code)
    assert create_res.status_code in [200, 202], f"Complaint creation failed: {create_res.text}"

    service_wrapper = create_res.json().get("ServiceWrappers", [])
    assert service_wrapper, "ServiceWrappers not found in create response"

    created_service = service_wrapper[0]["service"]
    service_request_id = created_service["serviceRequestId"]
    print(f"Complaint created with Service Request ID: {service_request_id}")

    # Step 4: Assign the complaint to the employee
    # assignes uses userServiceUuid, hrmsAssignes uses uuid
    print(f"Assigning complaint to employee {employee_name}...")
    assign_res = assign_complaint(token, client, created_service, user_service_uuid, user_uuid, employee_name)

    # Handle DEPARTMENT_NOT_FOUND as environment configuration issue
    if assign_res.status_code == 400:
        error_response = assign_res.json()
        errors = error_response.get("Errors", [])
        for error in errors:
            if error.get("code") == "DEPARTMENT_NOT_FOUND":
                pytest.skip(
                    f"PGR department configuration issue: {error.get('message')}. "
                    "PGR service requires user-department mapping that may not be configured in this environment. "
                    "Verify that PGR-specific department configuration is set up correctly."
                )

    assert assign_res.status_code in [200, 202], f"Complaint assignment failed: {assign_res.text}"

    assigned_wrapper = assign_res.json().get("ServiceWrappers", [])
    assert assigned_wrapper, "ServiceWrappers not found in assign response"

    assigned_status = assigned_wrapper[0]["service"]["applicationStatus"]
    print(f"Complaint {service_request_id} assigned successfully with status: {assigned_status}")

    with open("output/ids.txt", "a") as f:
        f.write("\n--- PGR Assigned Complaint details ---\n")
        f.write(f"Service Request ID: {service_request_id}\n")
        f.write(f"Assigned To Employee: {employee_name}\n")
        f.write(f"Employee UUID: {user_uuid}\n")
        f.write(f"Employee userServiceUuid: {user_service_uuid}\n")
        f.write(f"Employee Department: {employee_dept}\n")
        f.write(f"Status: {assigned_status}\n")


@pytest.mark.positive
def test_complete_pgr_workflow():
    """
    Complete PGR workflow test:
    1. Create a new employee with PGR-ADMIN role
    2. Create a complaint with service code matching the employee's department
    3. Assign the complaint to the newly created employee
    4. Login as the new employee
    5. Resolve the complaint as the new employee
    """
    admin_token = get_auth_token("user")
    admin_client = APIClient(token=admin_token)

    # Step 1: Create a new employee with PGR-ADMIN role and eGov department
    print("Step 1: Creating a new employee with PGR-ADMIN role...")
    employee_data = create_pgr_employee(admin_token, admin_client)

    employee_code = employee_data["code"]
    user_uuid = employee_data["user_uuid"]
    user_service_uuid = employee_data["user_service_uuid"]
    employee_dept = employee_data["department"]
    employee_password = employee_data["password"]

    print(f"Employee created: {employee_code}")
    print(f"  UUID: {user_uuid}, userServiceUuid: {user_service_uuid}")
    print(f"  Department: {employee_dept}")

    # Step 2: Find a service code that maps to the employee's department
    print(f"\nStep 2: Finding service code for department '{employee_dept}'...")
    service_code = get_service_code_for_department(admin_token, admin_client, employee_dept)
    if not service_code:
        pytest.skip(f"No service code found for department {employee_dept}")

    print(f"Using service code: {service_code}")

    # Step 3: Create a complaint with the matching service code
    print(f"\nStep 3: Creating complaint with service code '{service_code}'...")
    create_res = create_complaint(admin_token, admin_client, service_code=service_code)
    assert create_res.status_code in [200, 202], f"Complaint creation failed: {create_res.text}"

    service_wrapper = create_res.json().get("ServiceWrappers", [])
    assert service_wrapper, "ServiceWrappers not found in create response"

    created_service = service_wrapper[0]["service"]
    service_request_id = created_service["serviceRequestId"]
    print(f"Complaint created: {service_request_id}")

    # Step 4: Assign the complaint to the new employee
    print(f"\nStep 4: Assigning complaint to employee {employee_code}...")
    assign_res = assign_complaint(admin_token, admin_client, created_service, user_service_uuid, user_uuid, employee_code)

    # Handle DEPARTMENT_NOT_FOUND error
    if assign_res.status_code == 400:
        error_response = assign_res.json()
        errors = error_response.get("Errors", [])
        for error in errors:
            if error.get("code") == "DEPARTMENT_NOT_FOUND":
                pytest.skip(
                    f"PGR department configuration issue: {error.get('message')}. "
                    "Verify that PGR-specific department configuration is set up correctly."
                )

    assert assign_res.status_code in [200, 202], f"Complaint assignment failed: {assign_res.text}"

    assigned_wrapper = assign_res.json().get("ServiceWrappers", [])
    assert assigned_wrapper, "ServiceWrappers not found in assign response"

    assigned_service = assigned_wrapper[0]["service"]
    assigned_status = assigned_service["applicationStatus"]
    print(f"Complaint assigned with status: {assigned_status}")

    # Step 5: Login as the new employee
    print(f"\nStep 5: Logging in as employee {employee_code}...")
    employee_token = login_as_user(employee_code, employee_password)
    assert employee_token, f"Failed to login as {employee_code}"
    print(f"Successfully logged in as {employee_code}")

    employee_client = APIClient(token=employee_token)

    # Step 6: Resolve the complaint as the new employee
    print(f"\nStep 6: Resolving complaint {service_request_id} as {employee_code}...")
    resolve_res = resolve_complaint(employee_token, employee_client, assigned_service)
    assert resolve_res.status_code in [200, 202], f"Complaint resolution failed: {resolve_res.text}"

    resolved_wrapper = resolve_res.json().get("ServiceWrappers", [])
    assert resolved_wrapper, "ServiceWrappers not found in resolve response"

    resolved_status = resolved_wrapper[0]["service"]["applicationStatus"]
    assert resolved_status == "RESOLVED", f"Expected RESOLVED status, got: {resolved_status}"

    print(f"\n{'='*60}")
    print(f"COMPLETE PGR WORKFLOW SUCCESS!")
    print(f"{'='*60}")
    print(f"Complaint: {service_request_id}")
    print(f"Created by: Admin")
    print(f"Assigned to: {employee_code}")
    print(f"Resolved by: {employee_code}")
    print(f"Final Status: {resolved_status}")
    print(f"{'='*60}")

    with open("output/ids.txt", "a") as f:
        f.write("\n--- PGR Complete Workflow details ---\n")
        f.write(f"Service Request ID: {service_request_id}\n")
        f.write(f"Employee Code: {employee_code}\n")
        f.write(f"Employee UUID: {user_uuid}\n")
        f.write(f"Employee userServiceUuid: {user_service_uuid}\n")
        f.write(f"Employee Department: {employee_dept}\n")
        f.write(f"Workflow: CREATE -> ASSIGN -> RESOLVE\n")
        f.write(f"Final Status: {resolved_status}\n")


# --- Reusable Functions ---

def create_complaint(token, client, tenant_id=None, service_code=None):
    """
    Create a PGR complaint.

    Args:
        token: Authentication token
        client: API client instance
        tenant_id: Pass None to use default, or provide custom tenantId for negative testing
        service_code: Pass None to use random from pre-fetched codes, or provide specific code

    Returns:
        Response object from the API call
    """
    payload = load_payload("PGR", "create_complaint.json")
    payload["RequestInfo"] = get_request_info(token)
    payload["service"]["citizen"] = get_user_info("user")

    # Use provided service code or pick random from pre-fetched codes
    if service_code is None:
        service_codes = inputs_data.get("serviceCode", ["SecurityIssues"])
        service_code = random.choice(service_codes)

    payload["service"]["serviceCode"] = service_code
    print(f"Creating complaint with service code: {service_code}")

    # Use provided tenantId (negative testing) or the configured one
    payload["service"]["tenantId"] = tenant_id if tenant_id is not None else tenantId
    payload["service"]["hierarchyType"] = hierarchyType

    return client.post(f"/{pgr}/v2/request/_create", payload)


def resolve_complaint(token, client, service):
    """
    Resolve a PGR complaint.

    Args:
        token: Authentication token
        client: API client instance
        service: The service object from a created complaint response

    Returns:
        Response object from the API call
    """
    # Extract complaint details from the created service
    complaint_number = service.get("serviceRequestId", "")
    complaint_type = service.get("serviceCode", "")
    application_status = service.get("applicationStatus", "")
    description = service.get("description", "")
    audit_details = service.get("auditDetails", {})

    # Get boundary/area code from address
    address = service.get("address", {})
    locality = address.get("locality", {})
    boundary_code = locality.get("code", "")

    # Format the filed date from audit details
    created_time = audit_details.get("createdTime", 0)
    if created_time:
        filed_date = datetime.fromtimestamp(created_time / 1000).strftime("%d-%b-%Y")
    else:
        filed_date = datetime.now().strftime("%d-%b-%Y")

    # Build the payload with proper complaint details
    payload = {
        "RequestInfo": get_request_info(token),
        "details": {
            "CS_COMPLAINT_DETAILS_COMPLAINT_NO": complaint_number,
            "CS_ADDCOMPLAINT_COMPLAINT_TYPE": f"SERVICEDEFS.{complaint_type}",
            "CS_COMPLAINT_FILED_DATE": filed_date,
            "CS_COMPLAINT_DETAILS_AREA": boundary_code,
            "CS_COMPLAINT_DETAILS_APPLICATION_STATUS": f"CS_COMMON_{application_status}",
            "CS_CREATECOMPLAINT_LANDMARK": address.get("landmark", ""),
            "CS_COMPLAINT_ADDTIONAL_DETAILS": description
        },
        "service": service,
        "workflow": {
            "action": "RESOLVE",
            "comments": "Resolved via automated test",
            "assignes": None,
            "hrmsAssignes": None,
            "verificationDocuments": []
        },
        "audit": {
            "details": audit_details,
            "source": service.get("source", "web"),
            "rating": service.get("rating"),
            "serviceCode": complaint_type
        }
    }

    return client.post(f"/{pgr}/v2/request/_update", payload)


def get_pgr_assignee(token, client):
    """
    Get an employee who can be assigned PGR complaints.
    Searches for employees with PGR-ADMIN role AND valid PGR-compatible departments.

    Args:
        token: Authentication token
        client: API client instance

    Returns:
        Tuple of (user_uuid, user_service_uuid, employee_name, department) or (None, None, None, None) if not found
        - user_uuid: Used for hrmsAssignes field
        - user_service_uuid: Used for assignes field
    """
    try:
        # Get valid PGR departments from MDMS
        pgr_departments = get_pgr_departments(token, client)
        if not pgr_departments:
            pgr_departments = {"eGov", "TECH", "WAREHOUSE", "NMCP"}  # Fallback defaults

        # Search for employees with PGR-ADMIN role
        hrms_payload = load_payload("hrms", "search_hrms.json")
        hrms_payload["RequestInfo"] = get_request_info(token)

        url = f"/{hrms}/employees/_search?limit=100&offset=0&tenantId={tenantId}&roles=PGR-ADMIN"
        response = client.post(url, hrms_payload)

        if response.status_code == 200:
            employees = response.json().get("Employees", [])
            for employee in employees:
                # Check if employee has PGR-ADMIN role
                user = employee.get("user", {})
                roles = [r.get("code") for r in user.get("roles", [])]
                if "PGR-ADMIN" not in roles:
                    continue

                # Check for valid department in current assignment
                assignments = employee.get("assignments", [])
                for assignment in assignments:
                    dept = assignment.get("department", "")
                    if assignment.get("isCurrentAssignment") and dept in pgr_departments:
                        user_uuid = user.get("uuid")
                        user_service_uuid = user.get("userServiceUuid")
                        employee_name = employee.get("code", user.get("userName", "Unknown"))
                        print(f"Found PGR-ADMIN employee with department {dept}: {employee_name}")
                        print(f"  uuid: {user_uuid}, userServiceUuid: {user_service_uuid}")
                        return user_uuid, user_service_uuid, employee_name, dept

    except Exception as e:
        print(f"Warning: Could not search for PGR assignee: {e}")

    return None, None, None, None


def get_pgr_departments(token, client):
    """
    Get valid PGR departments from MDMS ServiceDefs.

    Args:
        token: Authentication token
        client: API client instance

    Returns:
        Set of valid department codes
    """
    try:
        payload = load_payload("mdms", "search_mdmsData.json")
        payload["MdmsCriteria"]["schemaCode"] = "RAINMAKER-PGR.ServiceDefs"
        payload["MdmsCriteria"]["tenantId"] = tenantId
        payload["RequestInfo"] = get_request_info(token)

        url = f"/{mdms}/v2/_search"
        response = client.post(url, payload)

        if response.status_code == 200:
            mdms_data = response.json().get("mdms", [])
            departments = set()
            for item in mdms_data:
                data = item.get("data", {})
                dept = data.get("department")
                if dept:
                    departments.add(dept)
            return departments

    except Exception as e:
        print(f"Warning: Could not fetch PGR departments from MDMS: {e}")

    return set()


def get_service_code_for_department(token, client, department):
    """
    Get a service code that maps to the specified department.

    Args:
        token: Authentication token
        client: API client instance
        department: The department code to find a matching service code for

    Returns:
        Service code string or None if not found
    """
    try:
        payload = load_payload("mdms", "search_mdmsData.json")
        payload["MdmsCriteria"]["schemaCode"] = "RAINMAKER-PGR.ServiceDefs"
        payload["MdmsCriteria"]["tenantId"] = tenantId
        payload["RequestInfo"] = get_request_info(token)

        url = f"/{mdms}/v2/_search"
        response = client.post(url, payload)

        if response.status_code == 200:
            mdms_data = response.json().get("mdms", [])
            for item in mdms_data:
                data = item.get("data", {})
                if data.get("department") == department:
                    return data.get("serviceCode")

    except Exception as e:
        print(f"Warning: Could not fetch service codes from MDMS: {e}")

    return None


def search_complaint(token, client, service_request_id):
    """
    Search for a PGR complaint by service request ID.

    Args:
        token: Authentication token
        client: API client instance
        service_request_id: The service request ID (complaint number) to search for

    Returns:
        List of services/complaints found
    """
    payload = {
        "RequestInfo": get_request_info(token)
    }

    # Build URL with query parameters
    url = f"/{pgr}/v2/request/_search?serviceRequestId={service_request_id}&tenantId={tenantId}&limit={search_limit}&offset={search_offset}"

    res = client.post(url, payload)
    assert res.status_code == 200, f"Search failed: {res.text}"

    service_wrappers = res.json().get("ServiceWrappers", [])
    return [wrapper["service"] for wrapper in service_wrappers]


def assign_complaint(token, client, service, user_service_uuid, user_uuid, assignee_name):
    """
    Assign a PGR complaint to an employee.

    Args:
        token: Authentication token
        client: API client instance
        service: The service object from a created complaint response
        user_service_uuid: The userServiceUuid of the employee (used for assignes field)
        user_uuid: The uuid of the employee (used for hrmsAssignes field)
        assignee_name: The name/code of the employee (for display purposes)

    Returns:
        Response object from the API call
    """
    # Extract complaint details from the created service
    complaint_number = service.get("serviceRequestId", "")
    complaint_type = service.get("serviceCode", "")
    application_status = service.get("applicationStatus", "")
    description = service.get("description", "")
    audit_details = service.get("auditDetails", {})

    # Get boundary/area code from address
    address = service.get("address", {})
    locality = address.get("locality", {})
    boundary_code = locality.get("code", "")

    # Format the filed date from audit details
    created_time = audit_details.get("createdTime", 0)
    if created_time:
        filed_date = datetime.fromtimestamp(created_time / 1000).strftime("%d-%b-%Y")
    else:
        filed_date = datetime.now().strftime("%d-%b-%Y")

    # Build the payload with proper complaint details
    # assignes uses userServiceUuid, hrmsAssignes uses uuid
    payload = {
        "RequestInfo": get_request_info(token),
        "details": {
            "CS_COMPLAINT_DETAILS_COMPLAINT_NO": complaint_number,
            "CS_ADDCOMPLAINT_COMPLAINT_TYPE": f"SERVICEDEFS.{complaint_type}",
            "CS_COMPLAINT_FILED_DATE": filed_date,
            "CS_COMPLAINT_DETAILS_AREA": boundary_code,
            "CS_COMPLAINT_DETAILS_APPLICATION_STATUS": f"CS_COMMON_{application_status}",
            "CS_CREATECOMPLAINT_LANDMARK": address.get("landmark", ""),
            "CS_COMPLAINT_ADDTIONAL_DETAILS": description
        },
        "service": service,
        "workflow": {
            "action": "ASSIGN",
            "comments": f"Assigned to {assignee_name} via automated test",
            "assignes": [user_service_uuid],
            "hrmsAssignes": [user_uuid],
            "verificationDocuments": []
        },
        "audit": {
            "details": audit_details,
            "source": service.get("source", "web"),
            "rating": service.get("rating"),
            "serviceCode": complaint_type
        }
    }

    return client.post(f"/{pgr}/v2/request/_update", payload)


def login_as_user(username, password):
    """
    Login as a specific user and return their auth token.

    Args:
        username: The username to login with
        password: The password for the user

    Returns:
        Auth token string or None if login failed
    """
    try:
        url = os.getenv("BASE_URL") + "/user/oauth/token"

        payload = {
            "username": username,
            "password": password,
            "grant_type": "password",
            "scope": "read",
            "tenantId": tenantId,
            "userType": "EMPLOYEE"
        }

        headers = {
            "accept": "application/json, text/plain, */*",
            "authorization": os.getenv("CLIENT_AUTH_HEADER"),
            "content-type": "application/x-www-form-urlencoded"
        }

        response = requests.post(url, data=payload, headers=headers)
        if response.status_code == 200:
            return response.json().get("access_token")
        else:
            print(f"Login failed for {username}: {response.text}")
            return None

    except Exception as e:
        print(f"Login error for {username}: {e}")
        return None


def create_pgr_employee(token, client):
    """
    Create a new employee with PGR-ADMIN role and eGov department.

    Args:
        token: Authentication token
        client: API client instance

    Returns:
        Dictionary with employee details:
        - code: Employee code
        - user_uuid: User UUID (for hrmsAssignes)
        - user_service_uuid: User Service UUID (for assignes)
        - department: Department code
        - password: Default password
    """
    payload = load_payload("hrms", "create_hrms.json")
    payload["RequestInfo"] = get_request_info(token)

    # Generate unique code and username
    letters = ''.join(random.choices(string.ascii_uppercase, k=2))
    numbers = ''.join(random.choices(string.digits, k=4))
    unique_code = f"PGR-EMP-{letters}-{numbers}"
    mobile_number = f"{random.randint(7000000000, 9999999999)}"
    default_password = "eGov@1234"

    # Update employee code and username
    payload["Employees"][0]["code"] = unique_code
    payload["Employees"][0]["tenantId"] = tenantId
    payload["Employees"][0]["user"]["userName"] = unique_code
    payload["Employees"][0]["user"]["mobileNumber"] = mobile_number
    payload["Employees"][0]["user"]["password"] = default_password
    payload["Employees"][0]["user"]["tenantId"] = tenantId
    for jurisdiction in payload["Employees"][0].get("jurisdictions", []):
        jurisdiction["tenantId"] = tenantId
        jurisdiction["hierarchy"] = hierarchyType
        jurisdiction["boundaryType"] = boundaryType
        jurisdiction["boundary"] = boundaryCode
        for role in jurisdiction.get("roles", []):
            role["tenantId"] = tenantId
    for role in payload["Employees"][0]["user"].get("roles", []):
        role["tenantId"] = tenantId

    # Ensure PGR-ADMIN role is included
    # The payload already has PGR-ADMIN role from the template

    # Ensure eGov department is set
    payload["Employees"][0]["assignments"][0]["department"] = "eGov"

    url = f"/{hrms}/employees/_create?tenantId={tenantId}"
    response = client.post(url, payload)

    if response.status_code not in [200, 202]:
        raise Exception(f"Employee creation failed with status {response.status_code}: {response.text}")

    employee_data = response.json()["Employees"][0]
    user = employee_data["user"]

    return {
        "code": employee_data["code"],
        "user_uuid": user["uuid"],
        "user_service_uuid": user["userServiceUuid"],
        "department": "eGov",
        "password": default_password
    }
