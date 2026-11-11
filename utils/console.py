"""Helpers for the HCM Admin Console (campaign) API suite.

The console UI drives a campaign through a fixed sequence of steps:

    campaign landing -> draft (name + dates) -> boundary selection
    -> delivery rules -> app configuration -> upload file -> create

Every step is a ``project-factory`` update on the same campaign record, keyed by
``additionalDetails.key``. These helpers reproduce that sequence over the API so
the console test suite mirrors the Playwright UI suite case for case.

Nothing here is environment-specific: project types come from MDMS and
boundaries come from the boundary service, so the same tests run against any
tenant without hardcoded product variants or boundary codes.
"""

import json
import os
import time
import uuid
from copy import deepcopy
from datetime import datetime, timedelta

import requests as raw_requests

from utils.auth import get_user_info
from utils.data_loader import load_payload
from utils.config import (
    appConfigSchemaCode,
    campaignNameMaxLength,
    consoleCampaignTypes,
    consoleFilestoreModule,
    consoleGenerateType,
    consoleHierarchyType,
    consoleResourceType,
    consoleValidationType,
    locale,
    mdms,
    pollAttempts,
    pollDelay,
    SERVICE_BOUNDARY,
    SERVICE_LOCALIZATION,
    SERVICE_EXCEL_INGESTION,
    SERVICE_FILESTORE,
    SERVICE_PROJECT_BASE,
    SERVICE_PROJECT_FACILITY,
    SERVICE_PROJECT_FACTORY,
    SERVICE_PROJECT_STAFF,
    tenantId,
)

PROJECT_TYPE_SCHEMA = "HCM-PROJECT-TYPES.projectTypes"

# additionalDetails.key values the console sets as the wizard advances. The
# backend uses these to decide how far the draft has progressed.
STEP_KEY_DRAFT = 2
STEP_KEY_BOUNDARY = 6
STEP_KEY_DELIVERY = 10
STEP_KEY_FILES = 10


# ---------------------------------------------------------------------------
# Dates
# ---------------------------------------------------------------------------

def tomorrow_ts():
    """Tomorrow at midnight, as a Unix timestamp in milliseconds."""
    day = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    return int(day.timestamp() * 1000)


def one_month_later_ts():
    """One month after tomorrow at 23:59:59, as a Unix timestamp in milliseconds."""
    day = datetime.now().replace(hour=23, minute=59, second=59, microsecond=0) + timedelta(days=31)
    return int(day.timestamp() * 1000)


def _iso(ts_ms):
    return datetime.fromtimestamp(ts_ms / 1000).strftime("%Y-%m-%dT%H:%M:%S.000Z")


# ---------------------------------------------------------------------------
# RequestInfo
# ---------------------------------------------------------------------------

def campaign_request_info(token, service="user"):
    """RequestInfo for project-factory calls, using the real logged-in user.

    The console sends the caller's own userInfo; deriving it from the auth
    response keeps the payload valid on any environment instead of pinning a
    specific user's uuid.
    """
    user_info = get_user_info(service) or {
        "id": 0,
        "userName": "",
        "type": "EMPLOYEE",
        "uuid": "",
        "tenantId": tenantId,
        "roles": [],
    }
    return {
        "apiId": "Rainmaker",
        "ver": "1.0",
        "ts": 0,
        "action": "create",
        "authToken": token,
        "userInfo": user_info,
        "msgId": f"{uuid.uuid4()}|{locale}",
        "plainAccessRequest": {},
    }


# ---------------------------------------------------------------------------
# Campaign types
# ---------------------------------------------------------------------------

def _campaign_types_path():
    return os.path.join(os.path.dirname(__file__), "..", "data", "console", "campaign_types.json")


def load_campaign_types():
    """Campaign types under test, filtered by CONSOLE_CAMPAIGN_TYPES if set."""
    with open(os.path.abspath(_campaign_types_path()), "r", encoding="utf-8") as f:
        all_types = json.load(f)

    selected = [t.strip() for t in consoleCampaignTypes.split(",") if t.strip()]
    if not selected:
        return all_types
    return {k: v for k, v in all_types.items() if k in selected}


def campaign_type_keys():
    """Keys to feed into ``pytest.mark.parametrize`` (e.g. ["BEDNET", "MR-DN"])."""
    return list(load_campaign_types().keys())


def campaign_type_config(campaign_type):
    types = load_campaign_types()
    assert campaign_type in types, (
        f"Campaign type '{campaign_type}' is not defined in data/console/campaign_types.json"
    )
    return types[campaign_type]


# ---------------------------------------------------------------------------
# Campaign names — rules mirrored from the console UI
# ---------------------------------------------------------------------------

def unique_campaign_name(prefix="Auto"):
    """A valid, unique campaign name within the UI's length limit."""
    name = f"{prefix}_{uuid.uuid4().hex[:8]}"
    return name[:campaignNameMaxLength]


def invalid_campaign_names():
    """The invalid names the console UI rejects, as (case_id, name) pairs.

    Kept in one place so the API suite and the Playwright suite assert the same
    rule set. See DraftCampaignTest in the Web-Automation repo.
    """
    too_long = "N" * (campaignNameMaxLength + 1)
    return [
        ("too_long", too_long),
        ("starts_with_special_char", "_Campaign"),
        ("contains_emoji", "Camp\U0001F389ign1"),
        ("consecutive_underscores", "Camp__aign"),
    ]


# ---------------------------------------------------------------------------
# Assertion helper
# ---------------------------------------------------------------------------

def assert_rejected(response, what, allowed_status=(400, 401, 403, 500)):
    """Assert the API refused a request the console UI also refuses.

    A 2xx here is a real finding, not a test bug: it means the UI blocks the
    input client-side but the service accepts it. The message says so explicitly
    so the failure is actionable rather than confusing.
    """
    if response.status_code in allowed_status:
        print(f"  Correctly rejected ({response.status_code}): {what}")
        return

    assert response.status_code not in (200, 201, 202), (
        f"{what}\n"
        f"  The console UI rejects this input, but the API accepted it "
        f"(status {response.status_code}).\n"
        f"  This looks like a missing server-side validation.\n"
        f"  Response: {response.text[:600]}"
    )
    print(f"  Correctly rejected ({response.status_code}): {what}")


# ---------------------------------------------------------------------------
# MDMS: project types / delivery rules
# ---------------------------------------------------------------------------

_project_type_cache = {}


def fetch_project_types(token, client):
    """All active project types from MDMS, keyed by code."""
    if "all" in _project_type_cache:
        return _project_type_cache["all"]

    payload = load_payload("mdms", "search_mdmsData.json")
    payload["MdmsCriteria"]["tenantId"] = tenantId
    payload["MdmsCriteria"]["schemaCode"] = PROJECT_TYPE_SCHEMA
    payload["RequestInfo"] = campaign_request_info(token)

    response = client.post(f"/{mdms}/v2/_search", payload)
    assert response.status_code == 200, f"Project type lookup failed: {response.text}"

    by_code = {}
    for item in response.json().get("mdms", []):
        if item.get("isActive") is False:
            continue
        data = item.get("data", {})
        code = data.get("code")
        if code:
            by_code[code] = data

    _project_type_cache["all"] = by_code
    return by_code


def resolve_project_type(token, client, campaign_type):
    """Look up the MDMS project type backing a console campaign type.

    Returns ``None`` when the environment does not define it, so tests can skip
    with a clear message instead of failing on unrelated data gaps.
    """
    config = campaign_type_config(campaign_type)
    code = config["projectTypeCode"]
    by_code = fetch_project_types(token, client)

    if code in by_code:
        return by_code[code]

    # Environments name these inconsistently (Bednet / BEDNET / LLIN-mz), so
    # fall back to a case-insensitive match before giving up.
    for existing_code, data in by_code.items():
        if existing_code.lower() == code.lower():
            return data
    return None


def build_delivery_rules(project_type_data, start_ts, end_ts):
    """Turn an MDMS project type into the console's deliveryRules array."""
    rule = deepcopy(project_type_data)
    code = rule.get("code")

    rule["id"] = code
    rule["code"] = code
    rule["name"] = rule.get("name", code)

    # UI-only display flags the console sends alongside the MDMS definition.
    rule.setdefault("IsCycleDisable", True)
    rule.setdefault("attrAddDisable", False)
    rule.setdefault("productCountHide", True)
    rule.setdefault("deliveryAddDisable", True)

    for cycle in rule.get("cycles", []) or []:
        cycle["startDate"] = start_ts
        cycle["endDate"] = end_ts

    return [rule]


def build_cycle_data(project_type_data, start_ts, end_ts):
    """The additionalDetails.cycleData block matching the delivery rules."""
    cycles = project_type_data.get("cycles", []) or []
    cycle_count = len(cycles) or 1
    delivery_count = len(cycles[0].get("deliveries", [])) if cycles else 1

    return {
        "cycleConfgureDate": {
            "cycle": cycle_count,
            "isDisable": True,
            "deliveries": delivery_count or 1,
        },
        "cycleData": [
            {"key": i + 1, "fromDate": _iso(start_ts), "toDate": _iso(end_ts)}
            for i in range(cycle_count)
        ],
    }


# ---------------------------------------------------------------------------
# Boundaries
# ---------------------------------------------------------------------------

_boundary_cache = {}


def fetch_boundary_hierarchy(token, client, hierarchy_type=None):
    """Ordered boundary types for a hierarchy, root first."""
    hierarchy_type = hierarchy_type or consoleHierarchyType
    cache_key = f"hierarchy:{hierarchy_type}"
    if cache_key in _boundary_cache:
        return _boundary_cache[cache_key]

    payload = load_payload("console/campaign", "search_boundary_hierarchy.json")
    payload["BoundaryTypeHierarchySearchCriteria"]["tenantId"] = tenantId
    payload["BoundaryTypeHierarchySearchCriteria"]["hierarchyType"] = hierarchy_type
    payload["RequestInfo"] = campaign_request_info(token)

    url = f"{SERVICE_BOUNDARY}/boundary-hierarchy-definition/_search"
    response = client.post(url, payload)
    assert response.status_code == 200, f"Boundary hierarchy lookup failed: {response.text}"

    definitions = response.json().get("BoundaryHierarchy", [])
    assert definitions, f"No boundary hierarchy defined for '{hierarchy_type}'"

    levels = definitions[0].get("boundaryHierarchy", [])
    # Order by walking parent links from the root down.
    by_parent = {}
    root = None
    for level in levels:
        parent = level.get("parentBoundaryType")
        if not parent:
            root = level.get("boundaryType")
        else:
            by_parent[parent] = level.get("boundaryType")

    ordered = []
    current = root
    while current:
        ordered.append(current)
        current = by_parent.get(current)

    _boundary_cache[cache_key] = ordered
    return ordered


def fetch_boundary_tree(token, client, hierarchy_type=None):
    """The full boundary relationship tree, rooted at the top boundary type."""
    hierarchy_type = hierarchy_type or consoleHierarchyType
    cache_key = f"tree:{hierarchy_type}"
    if cache_key in _boundary_cache:
        return _boundary_cache[cache_key]

    root_type = fetch_boundary_hierarchy(token, client, hierarchy_type)[0]

    payload = load_payload("console/campaign", "search_boundary_relationship.json")
    payload["RequestInfo"] = campaign_request_info(token)

    url = (
        f"{SERVICE_BOUNDARY}/boundary-relationships/_search"
        f"?tenantId={tenantId}&includeChildren=true"
        f"&boundaryType={root_type}&hierarchyType={hierarchy_type}"
    )
    response = client.post(url, payload)
    assert response.status_code == 200, f"Boundary relationship search failed: {response.text}"

    tenant_boundaries = response.json().get("TenantBoundary", [])
    assert tenant_boundaries, f"No TenantBoundary returned for hierarchy '{hierarchy_type}'"

    boundaries = tenant_boundaries[0].get("boundary", [])
    assert boundaries, f"No boundaries returned for hierarchy '{hierarchy_type}'"

    _boundary_cache[cache_key] = boundaries[0]
    return boundaries[0]


def boundary_chain(token, client, depth=None, hierarchy_type=None):
    """One complete root-to-leaf boundary path in project-factory format.

    ``depth`` limits how many levels are selected — used by the negative tests
    to reproduce a partial selection. ``includeAllChildren`` is set on the last
    selected node, matching what the console sends when a level is ticked.
    """
    root = fetch_boundary_tree(token, client, hierarchy_type)

    path = []
    node = root
    while node is not None:
        path.append(node)
        if depth is not None and len(path) >= depth:
            break
        children = node.get("children") or []
        node = children[0] if children else None

    chain = []
    for index, node in enumerate(path):
        code = node.get("code")
        entry = {
            "code": code,
            "name": code,
            "type": node.get("boundaryType"),
            "isRoot": index == 0,
            "includeAllChildren": index == len(path) - 1,
        }
        if index > 0:
            entry["parent"] = path[index - 1].get("code")
        chain.append(entry)

    return chain


def boundary_chain_depth(token, client, hierarchy_type=None):
    """How many levels deep the boundary data actually goes."""
    return len(boundary_chain(token, client, hierarchy_type=hierarchy_type))


# ---------------------------------------------------------------------------
# Campaign lifecycle (project-factory)
# ---------------------------------------------------------------------------

def create_draft(token, client, campaign_type, project_type_data,
                 campaign_name=None, start_ts=None, end_ts=None,
                 hierarchy_type=None):
    """Step 1 — create the campaign draft (name, type, dates)."""
    payload = load_payload("console/campaign", "create_setup.json")
    details = payload["CampaignDetails"]

    details["tenantId"] = tenantId
    details["hierarchyType"] = hierarchy_type or consoleHierarchyType
    details["projectType"] = project_type_data.get("code")
    details["campaignName"] = campaign_name if campaign_name is not None else unique_campaign_name()
    details["startDate"] = tomorrow_ts() if start_ts is None else start_ts
    details["endDate"] = one_month_later_ts() if end_ts is None else end_ts
    details["locale"] = locale
    details["additionalDetails"]["key"] = STEP_KEY_DRAFT

    # Date negatives send the field absent rather than zero, matching a form
    # submitted with the picker left empty.
    if start_ts is False:
        details.pop("startDate", None)
    if end_ts is False:
        details.pop("endDate", None)

    payload["RequestInfo"] = campaign_request_info(token)
    return client.post(f"{SERVICE_PROJECT_FACTORY}/create", payload)


def _update_payload(token, campaign, project_type_data, step_key,
                    boundaries=None, delivery_rules=None, resources=None,
                    cycle_data=None, action="draft", template="update_campaign.json"):
    payload = load_payload("console/campaign", template)
    details = payload["CampaignDetails"]

    start_ts = campaign.get("startDate") or tomorrow_ts()
    end_ts = campaign.get("endDate") or one_month_later_ts()

    details["id"] = campaign.get("id", "")
    details["campaignNumber"] = campaign.get("campaignNumber", "")
    details["campaignName"] = campaign.get("campaignName", "")
    details["tenantId"] = tenantId
    details["locale"] = locale
    details["hierarchyType"] = campaign.get("hierarchyType") or consoleHierarchyType
    details["projectType"] = campaign.get("projectType") or project_type_data.get("code")
    details["startDate"] = start_ts
    details["endDate"] = end_ts
    details["action"] = action

    details["boundaries"] = boundaries if boundaries is not None else []
    details["deliveryRules"] = delivery_rules if delivery_rules is not None else []
    details["resources"] = resources if resources is not None else []

    if boundaries:
        root = next((b for b in boundaries if b.get("isRoot")), boundaries[0])
        details["boundaryCode"] = root.get("code", "")

    details["additionalDetails"]["key"] = step_key
    details["additionalDetails"]["beneficiaryType"] = project_type_data.get("beneficiaryType", "")
    if cycle_data is not None:
        details["additionalDetails"]["cycleData"] = cycle_data

    payload["RequestInfo"] = campaign_request_info(token)
    return payload


def update_boundaries(token, client, campaign, project_type_data, boundaries):
    """Step 2 — boundary selection."""
    payload = _update_payload(
        token, campaign, project_type_data, STEP_KEY_BOUNDARY,
        boundaries=boundaries,
    )
    return client.post(f"{SERVICE_PROJECT_FACTORY}/update", payload)


def update_delivery_rules(token, client, campaign, project_type_data, boundaries,
                          delivery_rules=None, cycle_data=None):
    """Step 3 — delivery rules."""
    start_ts = campaign.get("startDate") or tomorrow_ts()
    end_ts = campaign.get("endDate") or one_month_later_ts()

    if delivery_rules is None:
        delivery_rules = build_delivery_rules(project_type_data, start_ts, end_ts)
    if cycle_data is None:
        cycle_data = build_cycle_data(project_type_data, start_ts, end_ts)

    payload = _update_payload(
        token, campaign, project_type_data, STEP_KEY_DELIVERY,
        boundaries=boundaries, delivery_rules=delivery_rules, cycle_data=cycle_data,
    )
    return client.post(f"{SERVICE_PROJECT_FACTORY}/update", payload)


def update_resources(token, client, campaign, project_type_data, boundaries,
                     file_store_id, filename="Unified_Template.xlsx",
                     resource_type=None, delivery_rules=None, cycle_data=None):
    """Step 4 — attach the uploaded template."""
    start_ts = campaign.get("startDate") or tomorrow_ts()
    end_ts = campaign.get("endDate") or one_month_later_ts()

    if delivery_rules is None:
        delivery_rules = build_delivery_rules(project_type_data, start_ts, end_ts)
    if cycle_data is None:
        cycle_data = build_cycle_data(project_type_data, start_ts, end_ts)

    resources = [{
        "type": resource_type or consoleResourceType,
        "filename": filename,
        "filestoreId": file_store_id,
    }]

    payload = _update_payload(
        token, campaign, project_type_data, STEP_KEY_FILES,
        boundaries=boundaries, delivery_rules=delivery_rules,
        resources=resources, cycle_data=cycle_data,
    )
    return client.post(f"{SERVICE_PROJECT_FACTORY}/update", payload)


def finalize_campaign(token, client, campaign, project_type_data, boundaries,
                      resources, delivery_rules=None, cycle_data=None):
    """Final step — flip action to ``create`` and submit the campaign."""
    start_ts = campaign.get("startDate") or tomorrow_ts()
    end_ts = campaign.get("endDate") or one_month_later_ts()

    if delivery_rules is None:
        delivery_rules = build_delivery_rules(project_type_data, start_ts, end_ts)
    if cycle_data is None:
        cycle_data = build_cycle_data(project_type_data, start_ts, end_ts)

    payload = _update_payload(
        token, campaign, project_type_data, STEP_KEY_FILES,
        boundaries=boundaries, delivery_rules=delivery_rules,
        resources=resources, cycle_data=cycle_data,
        action="create", template="create_campaign.json",
    )
    return client.post(f"{SERVICE_PROJECT_FACTORY}/update", payload)


def search_campaign(token, client, campaign_number=None, campaign_id=None):
    payload = load_payload("console/campaign", "search_campaign.json")
    payload["CampaignDetails"]["tenantId"] = tenantId
    if campaign_number:
        payload["CampaignDetails"]["campaignNumber"] = campaign_number
    if campaign_id:
        payload["CampaignDetails"]["ids"] = [campaign_id]
    payload["RequestInfo"] = campaign_request_info(token)
    return client.post(f"{SERVICE_PROJECT_FACTORY}/search", payload)


def fetch_campaign(token, client, campaign_number):
    """The campaign as the server actually holds it, by campaign number.

    Read-after-write matters here: ``/project-type/update`` answers 200 with a
    CampaignDetails that omits ``deliveryRules``, ``additionalDetails.cycleData``
    and ``resources`` even though all three were persisted. Anything asserting
    on written state has to come back through this function rather than trust
    the update response.
    """
    response = search_campaign(token, client, campaign_number=campaign_number)
    assert response.status_code == 200, (
        f"Campaign search failed for {campaign_number}: {response.text}"
    )
    found = response.json().get("CampaignDetails") or []
    match = next(
        (c for c in found if c.get("campaignNumber") == campaign_number), None
    )
    assert match, f"Campaign {campaign_number} not found on search ({len(found)} result(s))"
    return match


def wait_for_campaign_status(token, client, campaign_number, target_status="created",
                             max_attempts=None, delay=None):
    """Poll a campaign until it reaches ``target_status`` or fails."""
    max_attempts = max_attempts or pollAttempts
    delay = delay if delay is not None else pollDelay

    response = None
    for attempt in range(1, max_attempts + 1):
        response = search_campaign(token, client, campaign_number=campaign_number)
        if response.status_code == 200:
            campaigns = response.json().get("CampaignDetails", [])
            match = next(
                (c for c in campaigns if c.get("campaignNumber") == campaign_number), None
            )
            if match:
                status = match.get("status")
                print(f"  Attempt {attempt}: campaign status = {status}")
                if status == target_status:
                    return response, True, match
                if status == "failed":
                    print("  Campaign reached 'failed'. Stopping poll.")
                    return response, False, match
        if attempt < max_attempts:
            time.sleep(delay)

    print(f"  Campaign did not reach '{target_status}' after {max_attempts} attempts")
    return response, False, None


# ---------------------------------------------------------------------------
# Excel ingestion
# ---------------------------------------------------------------------------

def generate_template(token, client, campaign_id, project_type, hierarchy_type=None):
    payload = load_payload("console/excel_ingestion", "generate_init.json")
    resource = payload["GenerateResource"]
    resource["tenantId"] = tenantId
    resource["type"] = consoleGenerateType
    resource["hierarchyType"] = hierarchy_type or consoleHierarchyType
    resource["referenceId"] = campaign_id
    resource["referenceType"] = project_type
    payload["RequestInfo"] = campaign_request_info(token)
    return client.post(f"{SERVICE_EXCEL_INGESTION}/generate/_init", payload)


def search_generation(token, client, generation_id):
    payload = load_payload("console/excel_ingestion", "generation_search.json")
    payload["GenerationSearchCriteria"]["tenantId"] = tenantId
    payload["GenerationSearchCriteria"]["ids"] = [generation_id]
    payload["RequestInfo"] = campaign_request_info(token)
    return client.post(f"{SERVICE_EXCEL_INGESTION}/generate/_search", payload)


def wait_for_generation(token, client, generation_id, max_attempts=None, delay=None):
    """Poll template generation. Returns (response, fileStoreId, completed)."""
    max_attempts = max_attempts or pollAttempts
    delay = delay if delay is not None else pollDelay

    response = None
    for attempt in range(1, max_attempts + 1):
        response = search_generation(token, client, generation_id)
        if response.status_code == 200:
            details = response.json().get("GenerationDetails", [])
            if details:
                status = details[0].get("status")
                print(f"  Attempt {attempt}: generation status = {status}")
                if status == "completed":
                    return response, details[0].get("fileStoreId"), True
                if status == "failed":
                    return response, None, False
        if attempt < max_attempts:
            time.sleep(delay)

    print(f"  Generation did not complete after {max_attempts} attempts")
    return response, None, False


def get_download_url(client, file_store_id):
    url = f"{SERVICE_FILESTORE}/url?tenantId={tenantId}&fileStoreIds={file_store_id}"
    return client.get(url)


def download_to_disk(download_url, filename=None):
    """Download a pre-signed filestore URL to output/console/."""
    output_dir = os.path.join(os.path.dirname(__file__), "..", "output", "console")
    os.makedirs(output_dir, exist_ok=True)

    if not filename:
        filename = download_url.split("/")[-1].split("?")[0]
        if not filename.endswith(".xlsx"):
            filename = f"template_{uuid.uuid4().hex[:8]}.xlsx"

    file_path = os.path.abspath(os.path.join(output_dir, filename))
    response = raw_requests.get(download_url)
    assert response.status_code == 200, f"Template download failed: {response.status_code}"

    with open(file_path, "wb") as f:
        f.write(response.content)

    print(f"  Downloaded {len(response.content)} bytes to {file_path}")
    return file_path


def upload_to_filestore(client, file_path):
    form_fields = {"tenantId": tenantId, "module": consoleFilestoreModule}
    return client.upload_file(SERVICE_FILESTORE, file_path, form_fields)


def validate_process(token, client, file_store_id, campaign_id, hierarchy_type=None,
                     resource_type=None):
    payload = load_payload("console/excel_ingestion", "process_validation.json")
    details = payload["ResourceDetails"]
    details["type"] = resource_type or consoleValidationType
    details["tenantId"] = tenantId
    details["hierarchyType"] = hierarchy_type or consoleHierarchyType
    details["fileStoreId"] = file_store_id
    details["referenceId"] = campaign_id
    details["locale"] = locale
    payload["RequestInfo"] = campaign_request_info(token)
    return client.post(f"{SERVICE_EXCEL_INGESTION}/process/_validation", payload)


def search_process(token, client, process_id):
    payload = load_payload("console/excel_ingestion", "process_search.json")
    payload["ProcessingSearchCriteria"]["tenantId"] = tenantId
    payload["ProcessingSearchCriteria"]["ids"] = [process_id]
    payload["RequestInfo"] = campaign_request_info(token)
    return client.post(f"{SERVICE_EXCEL_INGESTION}/process/_search", payload)


def wait_for_process(token, client, process_id, max_attempts=None, delay=None):
    """Poll file processing. Returns (response, completed, details)."""
    max_attempts = max_attempts or pollAttempts
    delay = delay if delay is not None else pollDelay

    response = None
    for attempt in range(1, max_attempts + 1):
        response = search_process(token, client, process_id)
        if response.status_code == 200:
            details = response.json().get("ProcessingDetails", [])
            if details:
                status = details[0].get("status")
                print(f"  Attempt {attempt}: process status = {status}")
                if status == "completed":
                    return response, True, details[0]
                if status == "failed":
                    return response, False, details[0]
        if attempt < max_attempts:
            time.sleep(delay)

    print(f"  Processing did not settle after {max_attempts} attempts")
    return response, False, None


# ---------------------------------------------------------------------------
# Downstream search (projects created by the campaign)
# ---------------------------------------------------------------------------

def search_projects(token, client, campaign_number):
    payload = load_payload("console/campaign", "search_project.json")
    payload["Projects"][0]["referenceID"] = campaign_number
    payload["Projects"][0]["tenantId"] = tenantId
    payload["tenantId"] = tenantId
    payload["RequestInfo"] = campaign_request_info(token)
    url = f"{SERVICE_PROJECT_BASE}/_search?limit=100&offset=0&tenantId={tenantId}"
    return client.post(url, payload)


def search_project_facilities(token, client, project_ids):
    payload = load_payload("console/campaign", "search_project_facility.json")
    payload["ProjectFacility"]["projectId"] = project_ids
    payload["RequestInfo"] = campaign_request_info(token)
    url = f"{SERVICE_PROJECT_FACILITY}/_search?tenantId={tenantId}&offset=0&limit=100"
    return client.post(url, payload)


def search_project_staff(token, client, project_ids):
    payload = load_payload("console/campaign", "search_project_staff.json")
    payload["ProjectStaff"]["projectId"] = project_ids
    payload["RequestInfo"] = campaign_request_info(token)
    url = f"{SERVICE_PROJECT_STAFF}/_search?tenantId={tenantId}&offset=0&limit=100"
    return client.post(url, payload)


# ---------------------------------------------------------------------------
# App configuration (MDMS masters + localization labels)
# ---------------------------------------------------------------------------

def search_app_config(token, client, schema_code=None):
    payload = load_payload("console/app_config", "search_app_config.json")
    payload["MdmsCriteria"]["tenantId"] = tenantId
    payload["MdmsCriteria"]["schemaCode"] = schema_code or appConfigSchemaCode
    payload["RequestInfo"] = campaign_request_info(token)
    return client.post(f"/{mdms}/v2/_search", payload)


def upsert_app_config(token, client, data, schema_code=None, unique_identifier=None):
    schema_code = schema_code or appConfigSchemaCode
    payload = load_payload("console/app_config", "upsert_app_config.json")
    payload["Mdms"]["tenantId"] = tenantId
    payload["Mdms"]["schemaCode"] = schema_code
    payload["Mdms"]["uniqueIdentifier"] = unique_identifier
    payload["Mdms"]["data"] = data
    payload["RequestInfo"] = campaign_request_info(token)
    return client.post(f"/{mdms}/v2/_create/{schema_code}", payload)


def update_app_config(token, client, entry, schema_code=None):
    """Write an existing app-config master back with modified data.

    ``entry`` is an item straight from the MDMS search response, so its ``id``
    and ``uniqueIdentifier`` are preserved.
    """
    schema_code = schema_code or appConfigSchemaCode
    payload = load_payload("console/app_config", "upsert_app_config.json")
    payload["Mdms"]["id"] = entry.get("id")
    payload["Mdms"]["tenantId"] = tenantId
    payload["Mdms"]["schemaCode"] = schema_code
    payload["Mdms"]["uniqueIdentifier"] = entry.get("uniqueIdentifier")
    payload["Mdms"]["data"] = entry.get("data", {})
    payload["Mdms"]["isActive"] = entry.get("isActive", True)
    payload["RequestInfo"] = campaign_request_info(token)
    return client.post(f"/{mdms}/v2/_update/{schema_code}", payload)


def upsert_label(token, client, code, message, module, label_locale=None):
    label_locale = label_locale or locale
    payload = load_payload("console/app_config", "upsert_label.json")
    payload["tenantId"] = tenantId
    payload["module"] = module
    payload["locale"] = label_locale
    payload["messages"][0] = {
        "code": code,
        "message": message,
        "module": module,
        "locale": label_locale,
    }
    payload["RequestInfo"] = campaign_request_info(token)
    return client.post(f"{SERVICE_LOCALIZATION}/messages/v1/_upsert", payload)


def search_labels(token, client, module, label_locale=None):
    label_locale = label_locale or locale
    payload = load_payload("console/app_config", "search_label.json")
    payload["RequestInfo"] = campaign_request_info(token)
    url = (
        f"{SERVICE_LOCALIZATION}/messages/v1/_search"
        f"?tenantId={tenantId}&locale={label_locale}&module={module}"
    )
    return client.post(url, payload)


# ---------------------------------------------------------------------------
# Result store — shared across console test modules
# ---------------------------------------------------------------------------

def _store_path():
    output_dir = os.path.join(os.path.dirname(__file__), "..", "output", "console")
    os.makedirs(output_dir, exist_ok=True)
    return os.path.abspath(os.path.join(output_dir, "campaigns.json"))


def save_campaign_result(campaign_type, data):
    """Record a created campaign so the search tests can reuse it."""
    path = _store_path()
    store = {}
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                store = json.load(f)
        except (ValueError, OSError):
            store = {}

    store[campaign_type] = data
    with open(path, "w", encoding="utf-8") as f:
        json.dump(store, f, indent=2)
    return path


def load_campaign_result(campaign_type):
    path = _store_path()
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f).get(campaign_type)
    except (ValueError, OSError):
        return None
