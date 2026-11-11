"""Helpers for the workbench-ui login flow.

The workbench sign-in page (``/workbench-ui/employee/user/login``) drives a
fixed sequence of backend calls. Captured from the browser against
hcm-demo.digit.org:

  Before the form renders
    1. POST /localization/messages/v1/_search
           ?module=rainmaker-common,digit-ui,digit-tenants,rainmaker-demo
           &locale=<locale>&tenantId=<tenant>
    2. POST /mdms-v2/v1/_search?tenantId=<tenant>        (tenant.tenants)
    3. POST /localization/messages/v1/_search
           ?module=digit-privacy-policy&...              (consent checkbox copy)

  On "Continue"
    4. POST /user/oauth/token                            (form-encoded)
    5. POST /user/_search                                (full profile by uuid)
    6. POST /access/v1/actions/mdms/_get                 (role -> nav/actions)

Steps 4-6 are what actually gate the employee landing page, so they are the
core of the regression suite. Everything here returns the raw ``requests``
response so tests can assert on status codes as well as bodies.

Step 4 lives in :mod:`utils.auth` — it is how every suite authenticates, not
just this one — and is re-exported here so the flow reads in order.
"""

from utils.api_client import APIClient
from utils.auth import oauth_token  # noqa: F401  (re-exported: step 4 of the flow)
from utils.config import (
    SERVICE_ACCESS_ACTIONS,
    SERVICE_LOCALIZATION,
    SERVICE_MDMS_V2_SEARCH,
    SERVICE_USER_SEARCH,
    accessActionMaster,
    locale,
    loginLocalizationModules,
    privacyPolicyModule,
    tenantId,
)
from utils.data_loader import load_payload
from utils.request_info import get_request_info

LOCALIZATION_SEARCH = f"{SERVICE_LOCALIZATION}/messages/v1/_search"


# ---------------------------------------------------------------------------
# Step 5 — profile lookup
# ---------------------------------------------------------------------------

def search_user(token, client=None, uuids=None, omit_criteria=False):
    """POST /user/_search — the profile fetch that populates the header menu."""
    client = client or APIClient(token=token)
    payload = {"RequestInfo": get_request_info(token), "tenantId": tenantId}
    if not omit_criteria:
        payload["uuid"] = uuids or []
    return client.post(SERVICE_USER_SEARCH, payload)


# ---------------------------------------------------------------------------
# Step 6 — role-based actions
# ---------------------------------------------------------------------------

def get_authorized_actions(token, client=None, role_codes=None, action_master=None):
    """POST /access/v1/actions/mdms/_get — drives the home cards and side nav.

    Note the server requires ``RequestInfo.ts`` to be a number; a null or empty
    string returns 400 with a NullPointerException. get_request_info() sends 0,
    which satisfies it.
    """
    client = client or APIClient(token=token)
    payload = {
        "RequestInfo": get_request_info(token),
        "actionMaster": action_master or accessActionMaster,
        "enabled": True,
        "roleCodes": role_codes or [],
        "tenantId": tenantId,
    }
    return client.post(SERVICE_ACCESS_ACTIONS, payload)


# ---------------------------------------------------------------------------
# Steps 1-3 — the pre-login bootstrap
# ---------------------------------------------------------------------------

def search_localization(token, client=None, modules=None):
    """POST /localization/messages/v1/_search for the shell's i18n bundles."""
    client = client or APIClient(token=token)
    url = (
        f"{LOCALIZATION_SEARCH}"
        f"?module={modules or loginLocalizationModules}"
        f"&locale={locale}"
        f"&tenantId={tenantId}"
    )
    return client.post(url, {"RequestInfo": get_request_info(token)})


def search_privacy_policy(token, client=None):
    """The separate bundle behind the login page's Privacy Policy consent."""
    return search_localization(token, client, modules=privacyPolicyModule)


def search_tenants(token, client=None):
    """POST /mdms-v2/v1/_search for tenant.tenants — the city/tenant picker."""
    client = client or APIClient(token=token)
    payload = load_payload("login", "mdms_tenants.json")
    payload["RequestInfo"] = get_request_info(token)
    payload["MdmsCriteria"]["tenantId"] = tenantId
    return client.post(f"{SERVICE_MDMS_V2_SEARCH}?tenantId={tenantId}", payload)


# ---------------------------------------------------------------------------
# Convenience
# ---------------------------------------------------------------------------

def role_codes_from(user_info):
    """Distinct, sorted role codes from a UserRequest/user object."""
    return sorted({r.get("code") for r in (user_info or {}).get("roles", []) if r.get("code")})
