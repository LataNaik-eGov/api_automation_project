# API Automation Framework

A comprehensive Python-based API automation testing framework for microservices testing using pytest. This framework provides reusable utilities, dynamic payload management, and extensive reporting capabilities.

## Table of Contents

- [Overview](#overview)
- [Project Structure](#project-structure)
- [Architecture](#architecture)
- [Prerequisites](#prerequisites)
- [Setup and Installation](#setup-and-installation)
- [Configuration](#configuration)
- [Services Covered](#services-covered)
- [Console Campaign Suite](#console-campaign-suite)
- [Writing Tests](#writing-tests)
- [Running Tests](#running-tests)
- [Reporting](#reporting)
- [Utilities Documentation](#utilities-documentation)
- [Best Practices](#best-practices)
- [Git Workflow](#git-workflow)

---

## Overview

This framework is designed to test multiple microservices with a focus on:
- **Modularity**: Reusable utilities for authentication, API calls, and data management
- **Maintainability**: Separation of test logic, payloads, and configuration
- **Extensibility**: Easy addition of new services and test cases
- **Reporting**: Multiple reporting formats (HTML, Allure)
- **Configuration Management**: Environment-based configuration using `.env` files

---

## Project Structure

```
api_automation_project/
├── tests/                          # Test modules
│   ├── test_individual_service.py
│   ├── test_household_service.py
│   ├── test_boundary_service.py
│   ├── test_facility_service.py
│   ├── test_product_service.py
│   ├── test_project_service.py
│   ├── test_mdms_service.py
│   └── console/                    # Console campaign suite (see below)
│       ├── conftest.py            # campaign_type / project_type / boundaries fixtures
│       ├── test_draft_campaign.py
│       ├── test_boundary_selection.py
│       ├── test_delivery_rules.py
│       ├── test_app_configuration.py
│       ├── test_upload_file.py
│       ├── test_campaign_e2e.py
│       └── test_campaign_search.py
├── utils/                          # Utility modules
│   ├── api_client.py              # HTTP client wrapper
│   ├── auth.py                    # Authentication token management
│   ├── config.py                  # Configuration loader
│   ├── data_loader.py             # Payload loader
│   ├── request_info.py            # Request metadata builder
│   ├── search_helpers.py          # Common search operations
│   ├── console.py                 # Campaign wizard helpers (project-factory, excel-ingestion)
│   └── template_filler.py         # Fills a generated template from a sample
├── payloads/                       # JSON payload templates
│   ├── boundary/
│   ├── facility/
│   ├── household/
│   ├── individual/
│   ├── mdms/
│   ├── product/
│   ├── project/
│   └── console/
│       ├── campaign/              # project-factory create / update / search
│       ├── excel_ingestion/       # generate, process, search
│       └── app_config/            # MDMS masters + localization labels
├── data/                          # Test input data
│   ├── inputs.json
│   └── console/
│       ├── campaign_types.json    # BEDNET / MR-DN definitions
│       └── templates/             # Filled-in sample templates (see below)
├── output/                        # Test outputs
│   ├── ids.txt                   # Generated entity IDs
│   ├── response.json             # Latest API response
│   ├── boundaries.txt            # Boundary data
│   └── console/
│       └── campaigns.json        # Campaigns created by the E2E test
├── reports/                       # Test reports
│   └── report.html
├── .env                          # Environment configuration
├── pytest.ini                    # Pytest configuration
├── requirements.txt              # Python dependencies
└── README.md                     # This file
```

---

## Architecture

### Core Components

1. **API Client Layer** (`utils/api_client.py`)
   - Abstraction over HTTP requests
   - Automatic authentication header injection
   - Support for GET, POST, PUT, DELETE methods

2. **Authentication Module** (`utils/auth.py`)
   - OAuth2 token acquisition
   - Token caching per service

3. **Configuration Management** (`utils/config.py`)
   - Centralized environment variable loading
   - Reusable search parameters
   - Service-specific configurations

4. **Payload Management** (`utils/data_loader.py`)
   - Dynamic JSON payload loading
   - Template-based payload structure

5. **Request Metadata** (`utils/request_info.py`)
   - Standardized RequestInfo object creation
   - API metadata and user context

6. **Search Helpers** (`utils/search_helpers.py`)
   - Generic search functionality
   - ID extraction from output files
   - Reusable across multiple services

### Test Flow

```
Test Execution
    ↓
Authentication (get_auth_token)
    ↓
API Client Initialization
    ↓
Load Payload Template (data_loader)
    ↓
Inject Dynamic Data (UUID, IDs, etc.)
    ↓
Add RequestInfo
    ↓
API Call (via APIClient)
    ↓
Validate Response (assertions)
    ↓
Store IDs/Data (output files)
    ↓
Generate Reports
```

---

## Prerequisites

- **Python**: 3.8 or higher
- **pip**: Python package manager
- **Virtual Environment**: Recommended for dependency isolation
- **Git**: For version control

---

## Setup and Installation

### 1. Clone the Repository

```bash
git clone <repository-url>
cd api_automation_project
```

### 2. Create Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install python-dotenv requests pytest pytest-html pytest-metadata allure-pytest
```

### 4. Configure Environment

Create or update `.env` file with your environment-specific values:

```env
BASE_URL=https://your-api-server.com
USERNAME=your_username
PASSWORD=your_password
TENANTID=your_tenant
USERTYPE=EMPLOYEE
CLIENT_AUTH_HEADER=Basic <base64_encoded_credentials>

SEARCH_LIMIT=200
SEARCH_OFFSET=0

HIERARCHYTYPE=MICROPLAN
BOUNDARY_TYPE=LOCALITY
BOUNDARY_CODE=your_boundary_code
SERVICE_INDIVIDUAL=individual
SERVICE_PROJECT=project
SERVICE_MDMS=mdms-v2
```

### 5. Verify Setup

```bash
pytest tests/ -v
```

---

## Configuration

### Environment Variables (.env)

| Variable | Description | Example |
|----------|-------------|---------|
| `BASE_URL` | API base URL | `https://hcm-demo.digit.org` |
| `USERNAME` | API username | `LNMZ` |
| `PASSWORD` | API password | `eGov@1234` |
| `TENANTID` | Tenant identifier | `mz` |
| `USERTYPE` | User type | `EMPLOYEE` |
| `CLIENT_AUTH_HEADER` | Basic auth header for OAuth | `Basic ZWdvdi11c2VyLWNsaWVudDo=` |
| `SEARCH_LIMIT` | Default search limit | `200` |
| `SEARCH_OFFSET` | Default search offset | `0` |
| `HIERARCHYTYPE` | Boundary hierarchy type | `MICROPLAN` |
| `BOUNDARY_TYPE` | Boundary type | `LOCALITY` |
| `BOUNDARY_CODE` | Boundary code | `MICROPLAN_MO_13_03_02_03_02_TUGLOR` |
| `SERVICE_INDIVIDUAL` | Individual service name | `individual` |
| `SERVICE_PROJECT` | Project service name | `project` |
| `SERVICE_MDMS` | MDMS service name | `mdms-v2` |

### Pytest Configuration (pytest.ini)

```ini
[pytest]
pythonpath = .
```

This ensures the root directory is in the Python path for imports.

---

## Services Covered

| Service | Operations | Test File |
|---------|-----------|-----------|
| **Individual** | Create, Search | `test_individual_service.py` |
| **Household** | Create Household, Create Member, Search Household, Search Member | `test_household_service.py` |
| **Boundary** | Search with hierarchy | `test_boundary_service.py` |
| **Facility** | Create, Search | `test_facility_service.py` |
| **Product** | Create Product, Create Variant, Search Product, Search Variant | `test_product_service.py` |
| **Project** | Create, Search | `test_project_service.py` |
| **MDMS** | Search master data | `test_mdms_service.py` |

**Total: 7 Services, 16 Payload Templates**

---

## Login Flow Suite

`tests/test_login_flow.py` covers the API sequence behind the workbench sign-in
page (`/workbench-ui/employee/user/login`), captured from a real browser login.

| Step | Call |
|------|------|
| Bootstrap | `POST /localization/messages/v1/_search` (shell i18n bundles) |
| Bootstrap | `POST /mdms-v2/v1/_search` (`tenant.tenants`) |
| Bootstrap | `POST /localization/messages/v1/_search` (privacy policy) |
| Sign-in | `POST /user/oauth/token` (form-encoded) |
| Post-login | `POST /user/_search` (profile) |
| Post-login | `POST /access/v1/actions/mdms/_get` (role → home cards) |

24 tests: happy path, credential rejection, user-enumeration resistance,
missing OAuth client header, unsupported grant types, forged tokens,
unbounded searches, and fail-closed role checks.

```bash
pytest -m login -v                  # whole flow
pytest -m "login and negative" -v   # negative paths only
```

Helpers in `utils/login.py`, payloads in `payloads/login/`.
Test-case register: `docs/LOGIN_FLOW_TEST_CASES.md`.

---

## Console Campaign Suite

`tests/console/` is the API counterpart of the Playwright console suite
([LataNaik-eGov/Web-Automation](https://github.com/LataNaik-eGov/Web-Automation)).
It walks the HCM Admin Console campaign wizard over the API and mirrors that
suite's test matrix case for case.

Every test runs once per campaign type — **BEDNET** and **MR-DN** by default —
via the `campaign_type` fixture. Narrow it with `CONSOLE_CAMPAIGN_TYPES` in
`.env`, or add types in `data/console/campaign_types.json`.

### Coverage

| UI step | API test file | Positive | Negative |
|---|---|---|---|
| Draft campaign | `test_draft_campaign.py` | create draft, draft is searchable | name too long / leading special char / emoji / consecutive underscores; no dates; start date only; end date only; end before start |
| Boundary selection | `test_boundary_selection.py` | full selection persists, survives reload | no selection; partial selection; missing lowest level; unknown boundary code |
| Delivery rules | `test_delivery_rules.py` | rules persist, cycleData matches cycles | first start date only; no cycle dates; non-numeric quantity; zero quantity; blank quantity; no rules |
| App configuration | `test_app_configuration.py` | config readable, entries active, label change, toggle off (and restore) | empty label; blank label code; unknown schema |
| Upload file | `test_upload_file.py` | generate template, upload + attach, filled template validates | no file attached; wrong file type; corrupt workbook; invalid data in file; unknown fileStoreId; unknown process id |
| Full flow | `test_campaign_e2e.py` | draft → boundary → delivery → generate → fill → upload → validate → attach → create → `created` | — |
| Post-create search | `test_campaign_search.py` | campaign by number / by id, projects, project facilities, project staff | unknown campaign number; unknown referenceID; unknown project id |

**36 tests per campaign type across 7 files** (72 for the default
`BEDNET,MR-DN`).

14 negative cases were removed from the suite because the API accepts input the
UI rejects — they are recorded, with expected-vs-actual, in the
*Excluded — Known Product Gaps* tab of `test_cases_sheet.html` and in
`test_cases_excluded.csv`. Restore them once project-factory validates
server-side.

### Nothing is hardcoded

- **Delivery rules** are built from the MDMS project type
  (`HCM-PROJECT-TYPES.projectTypes`) at runtime, so no product variant IDs are
  checked in. The negatives mutate whatever the environment actually defines.
- **Boundaries** are resolved from the boundary service: the hierarchy
  definition gives the level order, then a root-to-leaf path is walked. No
  boundary codes are checked in, and the negatives truncate that path.
- **RequestInfo** uses the logged-in user from the auth response rather than a
  pinned uuid.

### Sample templates

The console generates an *empty* template per campaign — boundary rows are
pre-populated, data columns are blank — so validation only passes once it is
filled in.

Drop one filled-in template per campaign type under
`data/console/templates/` (`BEDNET_sample.xlsx`, `MR-DN_sample.xlsx`, or
`sample.xlsx` as a fallback). `utils/template_filler.py` learns from it which
value belongs in which column — matching on **header text**, not position — and
applies that pattern to every data row of the freshly generated template.
Boundary and code columns are never overwritten.

The unified template uses a **two-row header band**: localization codes on row
1, localised display labels on row 2, data from row 3. The filler keys off the
**codes**, so one sample fills an `en_DEMO` and an `fr_DEMO` template alike.
Hidden `_h_*_h_` sheets (dropdown sources, per-generation meta id) are skipped.

Columns whose values come from the generated file and are never copied from the
sample: anything prefixed with the hierarchy code (`MICROPLAN_*` — boundary
levels, whose labels are localised), `*_CODE`, `__ROW_ID`, `UserService Uuids`,
and `Username`/`Password`.

`MR-DN_sample.xlsx` is the resource accepted by the real campaign
`MR-DN_september_20260501` on hcm-demo. See `docs/MR_DN_CAMPAIGN_TEST_CASES.md`.

The sample only needs **one** correctly filled data row. Tests that need it skip
with an explicit message when it is missing. See
`data/console/templates/README.md`.

### Reading a negative failure

The console enforces some rules client-side only. When a negative test fails
with:

> The console UI rejects this input, but the API accepted it (status 200).
> This looks like a missing server-side validation.

that is a **finding, not a broken test** — the UI blocks the input but the
service does not. `assert_rejected()` in `utils/console.py` writes that message
deliberately so the result is actionable.

### Preflight

Before the first real run, check the environment is wired up:

```bash
python3 scripts/console_preflight.py           # all campaign types
python3 scripts/console_preflight.py BEDNET    # one type
```

It verifies credentials and roles, lists the MDMS project types and whether the
configured campaign types resolve, walks the boundary hierarchy, checks the app
config schema, and looks for sample templates. Blockers are separated from
warnings (things that only cause skips), each with the exact fix. Exits non-zero
if anything is blocking.

### Running it

```bash
# Whole console suite
pytest tests/console -v -s

# One step
pytest tests/console/test_delivery_rules.py -v -s

# One campaign type
CONSOLE_CAMPAIGN_TYPES=BEDNET pytest tests/console -v -s

# Negatives only
pytest tests/console -m negative -v

# Full flow, then the searches that depend on it
pytest tests/console/test_campaign_e2e.py tests/console/test_campaign_search.py -v -s
```

`test_campaign_e2e.py` writes the created campaign to
`output/console/campaigns.json`; `test_campaign_search.py` reads it and skips
when it is absent.

Run with `-s` to see the campaign name/number/id banner as it is created —
pytest hides stdout for passing tests otherwise.

### Console configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `CONSOLE_CAMPAIGN_TYPES` | Campaign types to run | all in `campaign_types.json` |
| `CONSOLE_HIERARCHY_TYPE` | Boundary hierarchy | falls back to `BOUNDARY_HIERARCHY_CODE` |
| `CONSOLE_ROOT_BOUNDARY_CODE` | Root boundary | falls back to `BOUNDARY_CODE` |
| `CONSOLE_SAMPLE_TEMPLATE` | Explicit sample template path | `data/console/templates/<TYPE>_sample.xlsx` |
| `CONSOLE_PREFILLED_FILESTORE_ID` | Pre-uploaded filled template (fallback when no sample) | unset |
| `CONSOLE_PREFILLED_FILESTORE_ID_<TYPE>` | Per-type override, e.g. `..._MR_DN` / `..._BEDNET`. A single id cannot serve two types — their Boundary List target columns differ | unset |
| `CONSOLE_GENERATE_TYPE` | excel-ingestion generate type | `unified-console` |
| `CONSOLE_VALIDATION_TYPE` | excel-ingestion validation type | `unified-console-validation` |
| `CONSOLE_RESOURCE_TYPE` | project-factory resource type | `unified-console-resources` |
| `APP_CONFIG_SCHEMA_CODE` | MDMS schema holding app configuration | `HCM.APP_CONFIG` |
| `APP_CONFIG_LOCALIZATION_MODULE` | Localization module for field labels | `hcm-appconfig` |
| `CONSOLE_POLL_ATTEMPTS` / `CONSOLE_POLL_DELAY` | Async polling | `60` / `5` |
| `CAMPAIGN_NAME_MAX_LENGTH` | Name rule mirrored from the UI | `30` |

---

## Writing Tests

### Test Structure

Each test module follows this pattern:

```python
# 1. Imports
from utils.api_client import APIClient
from utils.auth import get_auth_token
from utils.data_loader import load_payload
from utils.request_info import get_request_info

# 2. Test Functions (with assertions)
def test_create_entity():
    """Test case with assertions"""
    token = get_auth_token("user")
    client = APIClient(token=token)

    response = create_entity(token, client)

    # Assertions
    assert response.status_code in [200, 202], f"Failed: {response.text}"
    entity_id = response.json()["Entity"]["id"]
    assert entity_id, "Entity ID not generated"

    # Store ID for later use
    with open("output/ids.txt", "a") as f:
        f.write(f"Entity ID: {entity_id}\n")

# 3. Helper Functions (reusable, no assertions)
def create_entity(token, client):
    """Helper function for entity creation"""
    payload = load_payload("service_name", "create_entity.json")

    # Inject dynamic data
    payload["Entity"]["clientReferenceId"] = str(uuid.uuid4())
    payload["RequestInfo"] = get_request_info(token)

    return client.post("/service/v1/_create", payload)
```

### Key Principles

1. **Separation of Concerns**: Test functions contain assertions; helper functions contain reusable logic
2. **Token Reuse**: Obtain token once per test, reuse across operations
3. **Dynamic Data Injection**: Use UUID for unique identifiers, extract IDs from output files for dependencies
4. **Status Code Flexibility**: Accept both 200 (OK) and 202 (Accepted)
5. **Detailed Error Messages**: Include response text in assertion failures

### Adding a New Service

1. **Create Payload Directory**:
   ```bash
   mkdir payloads/new_service
   ```

2. **Add Payload Templates**:
   ```bash
   # Create JSON files for create, search operations
   touch payloads/new_service/create_entity.json
   touch payloads/new_service/search_entity.json
   ```

3. **Create Test File**:
   ```bash
   touch tests/test_new_service.py
   ```

4. **Implement Tests**:
   ```python
   from utils.api_client import APIClient
   from utils.auth import get_auth_token
   from utils.data_loader import load_payload
   from utils.request_info import get_request_info
   import uuid

   def test_create_new_entity():
       token = get_auth_token("user")
       client = APIClient(token=token)

       response = create_new_entity(token, client)
       assert response.status_code in [200, 202]

   def create_new_entity(token, client):
       payload = load_payload("new_service", "create_entity.json")
       payload["Entity"]["clientReferenceId"] = str(uuid.uuid4())
       payload["RequestInfo"] = get_request_info(token)
       return client.post("/new-service/v1/_create", payload)
   ```

---

## Running Tests

### Normal Execution

```bash
# Activate virtual environment
source venv/bin/activate

# Run all tests
pytest tests/

# Run specific test file
pytest tests/test_individual_service.py

# Run specific test function
pytest tests/test_individual_service.py::test_create_individual

# Run with verbose output
pytest tests/ -v

# Run with print statements visible
pytest tests/ -s
```

### Run Tests by Tags

Tests are tagged as `positive` or `negative` for selective execution:

```bash
# Run only positive tests (create, search operations)
pytest -m positive

# Run only negative tests (invalid inputs, error scenarios)
pytest -m negative

# Run positive tests with HTML report
pytest -m positive --html=reports/report.html --self-contained-html

# Run negative tests with verbose output
pytest -m negative -v
```

### HTML Report Generation

```bash
pytest tests/ --html=reports/report.html --self-contained-html
```

The HTML report will be generated at `reports/report.html` with:
- Test results summary
- Pass/Fail status
- Execution time
- Error details

### Allure Report Generation

```bash
# Generate Allure results
pytest --alluredir=allure-results

# Generate Allure report
allure generate allure-results --clean -o allure-report

# Open Allure report in browser
allure open allure-report
```

### Fresh Test Run (Clear Previous IDs)

```bash
echo "=== New Test Run ===" > output/ids.txt && pytest tests/ --html=reports/report.html --self-contained-html
```

This clears the `output/ids.txt` file before running tests, ensuring no stale IDs are used.

---

## Reporting

### Output Files

1. **output/ids.txt**
   - Stores entity IDs created during test execution
   - Format: `Entity Type ID: <id_value>`
   - Used by subsequent tests to reference created entities

2. **output/response.json**
   - Latest API response saved for inspection
   - Useful for debugging

3. **output/boundaries.txt**
   - Boundary hierarchy information from boundary service tests

### Report Types

1. **HTML Report** (`reports/report.html`)
   - Self-contained HTML file
   - Summary dashboard with pass/fail counts
   - Detailed test results with error traces

2. **Allure Report** (`allure-report/`)
   - Rich, interactive web-based report
   - Test execution trends
   - Test categorization and filtering
   - Detailed logs and attachments

---

## Utilities Documentation

### api_client.py

**Class: APIClient**

HTTP client wrapper with automatic authentication.

```python
from utils.api_client import APIClient

# Initialize with token
client = APIClient(token="your_token_here")

# Make requests
response = client.get("/endpoint")
response = client.post("/endpoint", payload)
response = client.put("/endpoint", payload)
response = client.delete("/endpoint")
```

**Constructor Parameters:**
- `service` (optional): Service name to fetch token for
- `token` (optional): Direct token value
- Must provide either `service` or `token`

**Methods:**
- `get(endpoint, params=None)`: GET request
- `post(endpoint, data=None)`: POST request
- `put(endpoint, data=None)`: PUT request
- `delete(endpoint)`: DELETE request

### auth.py

**Function: get_auth_token(service)**

Obtains OAuth2 access token for a service.

```python
from utils.auth import get_auth_token

token = get_auth_token("user")
```

**Parameters:**
- `service` (str): Service name (e.g., "user", "individual")

**Returns:**
- `str`: Access token

**Raises:**
- `Exception`: If authentication fails

### config.py

Configuration module with environment variables.

```python
from utils.config import BASE_URL, tenantId, search_params

# Use configuration values
url = BASE_URL
tenant = tenantId
params = search_params  # Contains limit, offset, tenantId
```

**Available Variables:**
- `BASE_URL`: API base URL
- `tenantId`: Tenant identifier
- `search_limit`, `search_offset`: Pagination settings
- `search_params`: Dictionary with limit, offset, tenantId
- `hierarchyType`, `boundaryCode`, `boundaryType`: Boundary configs
- `individual`, `project`, `mdms`: Service names

### data_loader.py

**Function: load_payload(service_name, filename)**

Loads JSON payload template.

```python
from utils.data_loader import load_payload

payload = load_payload("individual", "create_individual.json")
```

**Parameters:**
- `service_name` (str): Service folder name under `payloads/`
- `filename` (str): JSON file name

**Returns:**
- `dict`: Parsed JSON payload

### request_info.py

**Function: get_request_info(token)**

Creates standardized RequestInfo object.

```python
from utils.request_info import get_request_info

request_info = get_request_info(token)
payload["RequestInfo"] = request_info
```

**Parameters:**
- `token` (str): Authentication token

**Returns:**
- `dict`: RequestInfo object with API metadata, user context, and authentication

### search_helpers.py

**Function: search_entity(...)**

Generic search operation for entities.

```python
from utils.search_helpers import search_entity

results = search_entity(
    entity_type="Individual",
    token=token,
    client=client,
    entity_id="individual_id",
    payload_file="search_individual.json",
    endpoint="/individual/v1/_search",
    response_key="Individual"
)
```

**Parameters:**
- `entity_type` (str): Type of entity being searched
- `token` (str): Authentication token
- `client` (APIClient): API client instance
- `entity_id` (str): ID to search for
- `payload_file` (str): Payload file name
- `endpoint` (str): API endpoint
- `response_key` (str): Key in response containing results

**Function: extract_id_from_file(label)**

Extracts ID from output file.

```python
from utils.search_helpers import extract_id_from_file

individual_id = extract_id_from_file("Individual ID:")
```

**Parameters:**
- `label` (str): Label to search for in output/ids.txt

**Returns:**
- `str`: Extracted ID value

---

## Best Practices

### 1. Test Independence

- Each test should be independent and not rely on execution order
- Use output files for sharing data between tests that must run sequentially
- Clean up test data when possible

### 2. Error Handling

- Always include response text in assertion messages for debugging
- Use try-except blocks for critical operations
- Log errors to output files

### 3. Payload Management

- Keep payloads as templates with minimal hardcoded values
- Inject dynamic data (UUIDs, IDs) at runtime
- Reuse payloads across similar tests

### 4. Code Reusability

- Extract common operations into helper functions
- Use utility modules for shared functionality
- Follow DRY (Don't Repeat Yourself) principle

### 5. Documentation

- Add docstrings to test functions and helpers
- Comment complex logic
- Keep README updated with new services/features

### 6. Version Control

- Commit frequently with meaningful messages
- Use feature branches for new services
- Keep `.env` file out of version control (add to `.gitignore`)

---

## Git Workflow

### Working with Branches

```bash
# Check current branch
git status

# Switch to main branch
git checkout main

# Pull latest changes
git pull origin main

# Create new feature branch
git checkout -b feature/new-service

# Make changes and commit
git add .
git commit -m "Add new service tests"

# Push feature branch
git push origin feature/new-service
```

### Merging Branches

```bash
# Switch to main branch
git checkout main

# Pull latest main
git pull origin main

# Merge feature branch
git merge feature/new-service

# Push merged changes
git push origin main
```

### Merging Product Branch to Main

```bash
# Make sure you're on main
git checkout main

# Pull latest main branch from remote
git pull origin main

# Merge product branch into main
git merge product

# Push merged changes back to remote main
git push origin main
```

---

## Troubleshooting

### Common Issues

1. **Authentication Failure**
   - Verify `.env` credentials are correct
   - Check CLIENT_AUTH_HEADER is properly base64 encoded
   - Ensure token hasn't expired

2. **Import Errors**
   - Verify virtual environment is activated
   - Check `pytest.ini` has `pythonpath = .`
   - Install all required dependencies

3. **Test Failures**
   - Check API endpoint availability
   - Verify payload structure matches API requirements
   - Review `output/response.json` for error details

4. **Missing IDs**
   - Ensure prerequisite tests ran successfully
   - Check `output/ids.txt` has required IDs
   - Run tests in correct sequence

---

## Contributing

1. Create a feature branch
2. Make changes with clear commit messages
3. Add tests for new functionality
4. Update documentation
5. Create pull request

---

## License

[Add license information here]

---

## Contact

[Add contact information here]

---

**Last Updated**: 2025-10-27
