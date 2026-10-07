import os
from dotenv import load_dotenv

load_dotenv(override=True)  # This forces reloading of updated values

BASE_URL = os.getenv("BASE_URL")
tenantId = os.getenv("TENANTID", "mz")

search_limit = os.getenv("SEARCH_LIMIT", "100")
search_offset = os.getenv("SEARCH_OFFSET", "0")
hierarchyType = os.getenv("BOUNDARY_HIERARCHY_CODE") or os.getenv("HIERARCHYTYPE")
boundaryCode = os.getenv("BOUNDARY_CODE")
boundaryType=os.getenv("BOUNDARY_TYPE")

if not BASE_URL:
    raise ValueError("BASE_URL not found in .env")


# Define reusable params dict
search_params = {
    "limit": search_limit,
    "offset": search_offset,
    "tenantId": tenantId
}

individual=os.getenv("SERVICE_INDIVIDUAL")
project=os.getenv("SERVICE_PROJECT")
mdms=os.getenv("SERVICE_MDMS")
hrms=os.getenv("SERVICE_HRMS")
pgr=os.getenv("SERVICE_PGR")

# Invalid values for negative testing
invalidTenantId=os.getenv("INVALID_TENANT_ID", "invalid_tenant")


# ---------------------------------------------------------------------------
# Console (HCM Admin Console / campaign) configuration
#
# Mirrors the campaign creation flow driven by the Playwright console suite:
#   campaign landing -> draft -> boundary -> delivery rules -> app config
#   -> upload file -> create
# ---------------------------------------------------------------------------

locale = os.getenv("LOCALE", "en_MZ")

# Service base paths. Every one is overridable so the suite can be pointed at a
# different environment without touching test code.
SERVICE_PROJECT_FACTORY = os.getenv("SERVICE_PROJECT_FACTORY", "/project-factory/v1/project-type")
SERVICE_EXCEL_INGESTION = os.getenv("SERVICE_EXCEL_INGESTION", "/excel-ingestion/v1/data")
SERVICE_FILESTORE = os.getenv("SERVICE_FILESTORE", "/filestore/v1/files")
SERVICE_PROJECT_BASE = os.getenv("SERVICE_PROJECT_BASE", "/project/v1")
SERVICE_PROJECT_FACILITY = os.getenv("SERVICE_PROJECT_FACILITY", "/project/facility/v1")
SERVICE_PROJECT_STAFF = os.getenv("SERVICE_PROJECT_STAFF", "/project/staff/v1")
SERVICE_BOUNDARY = os.getenv("SERVICE_BOUNDARY", "/boundary-service")
SERVICE_LOCALIZATION = os.getenv("SERVICE_LOCALIZATION", "/localization")

# Campaign context. Falls back to the boundary config already used by the
# service-level suites so a single .env drives both.
consoleHierarchyType = os.getenv("CONSOLE_HIERARCHY_TYPE") or hierarchyType
consoleRootBoundaryCode = os.getenv("CONSOLE_ROOT_BOUNDARY_CODE") or boundaryCode

# Campaign types under test, e.g. "BEDNET,MR-DN". Empty means "all types
# defined in data/console/campaign_types.json".
consoleCampaignTypes = os.getenv("CONSOLE_CAMPAIGN_TYPES", "")

# Excel ingestion resource types (project-factory <-> excel-ingestion contract).
consoleGenerateType = os.getenv("CONSOLE_GENERATE_TYPE", "unified-console")
consoleValidationType = os.getenv("CONSOLE_VALIDATION_TYPE", "unified-console-validation")
consoleResourceType = os.getenv("CONSOLE_RESOURCE_TYPE", "unified-console-resources")
consoleFilestoreModule = os.getenv("CONSOLE_FILESTORE_MODULE", "HCM-ADMIN-CONSOLE")

# A filestoreId for a template that has already been filled in with valid
# campaign data. The generated template is empty, so end-to-end validation
# needs a populated one. Optional — tests that need it skip when it is unset.
consolePrefilledFileStoreId = os.getenv("CONSOLE_PREFILLED_FILESTORE_ID", "")


def prefilled_filestore_id(campaign_type):
    """Pre-uploaded template filestoreId for a campaign type.

    A single global id cannot serve two campaign types — the MR-DN and BEDNET
    templates have different Boundary List target columns, so applying one to
    the other fails validation. Per-type overrides win; the global value is
    only a fallback for single-type setups.

        CONSOLE_PREFILLED_FILESTORE_ID_MR_DN=...
        CONSOLE_PREFILLED_FILESTORE_ID_BEDNET=...
    """
    key = f"CONSOLE_PREFILLED_FILESTORE_ID_{campaign_type.replace('-', '_').upper()}"
    return os.getenv(key) or consolePrefilledFileStoreId

# Sample template a human filled in once. The suite learns the fill pattern
# from it and applies it to whatever template the environment generates.
# Defaults to data/console/templates/<CAMPAIGN_TYPE>_sample.xlsx.
consoleSampleTemplate = os.getenv("CONSOLE_SAMPLE_TEMPLATE", "")

# App configuration masters. The console stores per-module app configuration in
# MDMS and the field labels in the localization service.
appConfigSchemaCode = os.getenv("APP_CONFIG_SCHEMA_CODE", "HCM.APP_CONFIG")
appConfigLocalizationModule = os.getenv("APP_CONFIG_LOCALIZATION_MODULE", "hcm-appconfig")

# Polling. Campaign creation and excel ingestion are async.
pollAttempts = int(os.getenv("CONSOLE_POLL_ATTEMPTS", "60"))
pollDelay = float(os.getenv("CONSOLE_POLL_DELAY", "5"))

# Campaign name rules enforced by the console UI. Kept here so the API-side
# negative tests and the UI suite stay in step.
campaignNameMaxLength = int(os.getenv("CAMPAIGN_NAME_MAX_LENGTH", "30"))

# ---------------------------------------------------------------------------
# Login flow (workbench-ui /employee/user/login)
#
# Mirrors the API sequence the workbench shell issues around sign-in:
#   localization bootstrap -> mdms tenants -> privacy policy ->
#   POST /user/oauth/token -> POST /user/_search -> POST /access/.../_get
# ---------------------------------------------------------------------------

loginUsername = os.getenv("USERNAME")
loginPassword = os.getenv("PASSWORD")
userType = os.getenv("USERTYPE", "EMPLOYEE")
# Standard DIGIT OAuth client header (base64 of "egov-user-client:")
clientAuthHeader = os.getenv("CLIENT_AUTH_HEADER", "Basic ZWdvdi11c2VyLWNsaWVudDo=")

# Service paths exercised by the login flow.
SERVICE_OAUTH_TOKEN = os.getenv("SERVICE_OAUTH_TOKEN", "/user/oauth/token")
SERVICE_USER_SEARCH = os.getenv("SERVICE_USER_SEARCH", "/user/_search")
SERVICE_ACCESS_ACTIONS = os.getenv("SERVICE_ACCESS_ACTIONS", "/access/v1/actions/mdms/_get")
SERVICE_MDMS_V2_SEARCH = os.getenv("SERVICE_MDMS_V2_SEARCH", "/mdms-v2/v1/_search")

# Localization bundles the shell loads before the login form renders, and the
# separate bundle behind the "I accept the Privacy Policy" link.
loginLocalizationModules = os.getenv(
    "LOGIN_LOCALIZATION_MODULES",
    "rainmaker-common,digit-ui,digit-tenants,rainmaker-demo",
)
privacyPolicyModule = os.getenv("PRIVACY_POLICY_MODULE", "digit-privacy-policy")

# Access-control master the shell asks for to build the role-based home cards.
accessActionMaster = os.getenv("ACCESS_ACTION_MASTER", "actions-test")

# Roles the logged-in employee is expected to hold. Comma-separated; empty
# means "assert nothing about roles". Used by the login regression test.
expectedLoginRoles = os.getenv("EXPECTED_LOGIN_ROLES", "")

# Localization modules that MUST return content for the login page to render
# its labels. The shell also requests digit-tenants and rainmaker-demo, which
# are legitimately empty on some environments (see LOGIN-02 in
# docs/LOGIN_FLOW_TEST_CASES.md), so they are reported but not asserted.
loginRequiredLocalizationModules = os.getenv(
    "LOGIN_REQUIRED_LOCALIZATION_MODULES", "rainmaker-common,digit-ui"
)
