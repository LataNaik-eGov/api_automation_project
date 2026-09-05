"""Regression suite for the workbench-ui employee login flow.

Covers the API sequence behind https://<env>/workbench-ui/employee/user/login,
captured from a real browser sign-in. See docs/LOGIN_FLOW_TEST_CASES.md for the
test-case notes (IDs below map 1:1 to that document).
"""

import pytest

from utils.api_client import APIClient
from utils.auth import get_auth_token, get_user_info
from utils.config import (
    accessActionMaster,
    expectedLoginRoles,
    invalidTenantId,
    locale,
    loginLocalizationModules,
    loginRequiredLocalizationModules,
    tenantId,
    userType,
)
from utils.login import (
    get_authorized_actions,
    oauth_token,
    role_codes_from,
    search_localization,
    search_privacy_policy,
    search_tenants,
    search_user,
)

SERVICE = "login"


@pytest.fixture(scope="module")
def session():
    """Authenticated context shared by the post-login assertions."""
    token = get_auth_token(SERVICE)
    user_info = get_user_info(SERVICE)
    return {
        "token": token,
        "user_info": user_info,
        "roles": role_codes_from(user_info),
        "client": APIClient(token=token),
    }


@pytest.fixture(scope="module")
def login_response():
    """One sign-in shared by the happy-path assertions.

    The negative tests each need their own call with varied credentials, but
    LOGIN-10/11 assert on different halves of the same response — no reason to
    log in twice against a shared environment.
    """
    return oauth_token()


@pytest.fixture(scope="module")
def localization_response(session):
    """The i18n bundle search, shared by LOGIN-01 and LOGIN-02."""
    return search_localization(session["token"], session["client"])


@pytest.fixture(scope="module")
def profile_response(session):
    """The signed-in user's profile, shared by LOGIN-30 and LOGIN-31."""
    return search_user(
        session["token"], session["client"], uuids=[session["user_info"].get("uuid")]
    )


@pytest.fixture(scope="module")
def actions_response(session):
    """Authorised actions for the account's roles, shared by LOGIN-40 and 41."""
    return get_authorized_actions(
        session["token"], session["client"], role_codes=session["roles"]
    )


# ---------------------------------------------------------------------------
# LOGIN-01..04 — pre-login bootstrap (unauthenticated shell boot)
# ---------------------------------------------------------------------------

@pytest.mark.positive
@pytest.mark.login
def test_localization_bootstrap_bundles(localization_response):
    """LOGIN-01: the shell's i18n bundles resolve for the configured locale."""
    response = localization_response

    assert response.status_code == 200, f"Localization search failed: {response.text}"
    messages = response.json().get("messages", [])
    assert messages, f"No localization messages returned for locale {locale}"

    locales = {m.get("locale") for m in messages}
    assert locales == {locale}, f"Bundle returned foreign locales: {locales - {locale}}"
    print(f"Localization bootstrap returned {len(messages)} messages for {locale}")


@pytest.mark.positive
@pytest.mark.login
def test_localization_covers_required_modules(localization_response):
    """LOGIN-02: the bundles that carry the login page's labels have content.

    A silently-empty module is how the login page ends up rendering raw
    localization codes instead of labels. Only the modules listed in
    LOGIN_REQUIRED_LOCALIZATION_MODULES are asserted: the shell also requests
    digit-tenants and rainmaker-demo, which are empty on hcm-demo without
    breaking sign-in, so those are reported rather than failed on.
    """
    response = localization_response
    assert response.status_code == 200, f"Localization search failed: {response.text}"

    returned = {m.get("module") for m in response.json().get("messages", [])}
    required = {m.strip() for m in loginRequiredLocalizationModules.split(",") if m.strip()}
    requested = {m.strip() for m in loginLocalizationModules.split(",") if m.strip()}

    missing_required = required - returned
    assert not missing_required, (
        f"Required localization modules returned no messages: {sorted(missing_required)}"
    )

    empty_optional = requested - required - returned
    if empty_optional:
        print(f"NOTE: optional login bundles are empty on this env: {sorted(empty_optional)}")
    print(f"All {len(required)} required login localization modules resolved")


@pytest.mark.positive
@pytest.mark.login
def test_tenant_master_is_resolvable(session):
    """LOGIN-03: mdms tenant.tenants contains the tenant being logged into."""
    response = search_tenants(session["token"], session["client"])

    assert response.status_code == 200, f"Tenant search failed: {response.text}"
    tenants = response.json().get("MdmsRes", {}).get("tenant", {}).get("tenants", [])
    assert tenants, "tenant.tenants master is empty"

    codes = {t.get("code") for t in tenants}
    assert tenantId in codes, f"Tenant '{tenantId}' missing from master; got {sorted(codes)}"
    print(f"Tenant master resolved '{tenantId}' among {len(tenants)} tenants")


@pytest.mark.positive
@pytest.mark.login
def test_privacy_policy_content_available(session):
    """LOGIN-04: the consent checkbox copy is populated.

    The Continue button stays disabled until the policy is accepted, so an
    empty bundle blocks sign-in entirely.
    """
    response = search_privacy_policy(session["token"], session["client"])

    assert response.status_code == 200, f"Privacy policy search failed: {response.text}"
    messages = response.json().get("messages", [])
    assert messages, "Privacy policy localization bundle is empty — consent cannot render"
    print(f"Privacy policy bundle returned {len(messages)} messages")


# ---------------------------------------------------------------------------
# LOGIN-10..12 — the sign-in call, happy path
# ---------------------------------------------------------------------------

@pytest.mark.positive
@pytest.mark.login
def test_login_returns_access_token(login_response):
    """LOGIN-10: valid credentials mint a bearer token with a refresh token."""
    response = login_response

    assert response.status_code == 200, f"Login failed: {response.text}"
    body = response.json()

    assert body.get("access_token"), "No access_token in login response"
    assert body.get("refresh_token"), "No refresh_token in login response"
    assert body.get("token_type") == "bearer", f"Unexpected token_type: {body.get('token_type')}"
    assert int(body.get("expires_in", 0)) > 0, "Token expires_in is not positive"
    print(f"Login succeeded; token expires in {body['expires_in']}s")


@pytest.mark.positive
@pytest.mark.login
def test_login_response_carries_user_context(login_response):
    """LOGIN-11: the response embeds the UserRequest the shell caches."""
    assert login_response.status_code == 200, f"Login failed: {login_response.text}"

    user = login_response.json().get("UserRequest") or {}
    assert user.get("uuid"), "Login response has no user uuid"
    assert user.get("tenantId") == tenantId, (
        f"Logged in against tenant '{user.get('tenantId')}', expected '{tenantId}'"
    )
    assert user.get("type") == userType, (
        f"User type '{user.get('type')}' does not match configured '{userType}'"
    )
    assert user.get("roles"), "Login response carries no roles — shell would render no home cards"
    print(f"Login context: {user.get('userName')} / {user.get('type')} / {user.get('tenantId')}")


@pytest.mark.positive
@pytest.mark.login
def test_login_grants_expected_roles(session):
    """LOGIN-12: the account holds the roles the workbench modules require."""
    if not expectedLoginRoles.strip():
        pytest.skip("EXPECTED_LOGIN_ROLES not configured")

    expected = {r.strip() for r in expectedLoginRoles.split(",") if r.strip()}
    actual = set(session["roles"])
    missing = expected - actual

    assert not missing, f"Account is missing required roles: {sorted(missing)}"
    print(f"All {len(expected)} expected roles present")


# ---------------------------------------------------------------------------
# LOGIN-20..26 — the sign-in call, negative paths
# ---------------------------------------------------------------------------

@pytest.mark.negative
@pytest.mark.login
@pytest.mark.parametrize(
    "case,kwargs",
    [
        ("wrong password", {"password": "definitely-not-the-password"}),
        ("unknown username", {"username": "no-such-user-automation"}),
        ("blank password", {"password": ""}),
        ("wrong tenant", {"tenant": invalidTenantId}),
        ("wrong user type", {"user_type": "CITIZEN"}),
    ],
)
def test_login_rejects_invalid_credentials(case, kwargs):
    """LOGIN-20..24: bad credentials are rejected without leaking a token.

    The user service answers all of these with a uniform 400
    "Invalid login credentials" — it does not distinguish an unknown username
    from a wrong password, which is the desired non-enumerable behaviour.
    """
    response = oauth_token(**kwargs)

    assert response.status_code in (400, 401), (
        f"[{case}] expected rejection, got {response.status_code}: {response.text}"
    )
    assert "access_token" not in response.text, f"[{case}] a token was issued despite bad input"
    print(f"[{case}] correctly rejected with {response.status_code}")


@pytest.mark.negative
@pytest.mark.login
def test_login_does_not_enumerate_users():
    """LOGIN-25: unknown user and wrong password are indistinguishable.

    Divergent status codes or messages would let an attacker enumerate valid
    usernames from the login form.
    """
    unknown = oauth_token(username="no-such-user-automation")
    wrong_pwd = oauth_token(password="definitely-not-the-password")

    assert unknown.status_code == wrong_pwd.status_code, (
        f"Status differs: unknown user {unknown.status_code} vs "
        f"wrong password {wrong_pwd.status_code} — user enumeration is possible"
    )

    def description(resp):
        try:
            return resp.json().get("error_description")
        except ValueError:
            return resp.text

    assert description(unknown) == description(wrong_pwd), (
        f"Error text differs: '{description(unknown)}' vs '{description(wrong_pwd)}'"
    )
    print(f"Both rejected identically: {unknown.status_code} / {description(unknown)}")


@pytest.mark.negative
@pytest.mark.login
def test_login_requires_oauth_client_header():
    """LOGIN-26: the OAuth client Basic header is mandatory."""
    response = oauth_token(auth_header="")

    assert response.status_code == 401, (
        f"Expected 401 without client header, got {response.status_code}: {response.text}"
    )
    print("Login correctly requires the OAuth client header")


@pytest.mark.negative
@pytest.mark.login
def test_login_rejects_unsupported_grant_type():
    """LOGIN-27: only the password grant is permitted for this client."""
    response = oauth_token(grant_type="client_credentials")

    assert response.status_code in (400, 401), (
        f"Expected rejection, got {response.status_code}: {response.text}"
    )
    assert "access_token" not in response.text, "A token was issued for an unsupported grant"
    print(f"Unsupported grant type rejected with {response.status_code}")


# ---------------------------------------------------------------------------
# LOGIN-30..33 — post-login profile fetch
# ---------------------------------------------------------------------------

@pytest.mark.positive
@pytest.mark.login
def test_user_search_returns_logged_in_profile(session, profile_response):
    """LOGIN-30: /user/_search resolves the signed-in user by uuid."""
    uuid = session["user_info"].get("uuid")
    assert uuid, "No uuid on the authenticated session"

    response = profile_response

    assert response.status_code == 200, f"User search failed: {response.text}"
    users = response.json().get("user", [])
    assert len(users) == 1, f"Expected exactly 1 user for uuid {uuid}, got {len(users)}"
    assert users[0].get("uuid") == uuid, "User search returned a different user"
    assert users[0].get("tenantId") == tenantId
    print(f"Profile resolved: {users[0].get('userName')} ({users[0].get('name')})")


@pytest.mark.positive
@pytest.mark.login
def test_user_search_roles_match_login_response(session, profile_response):
    """LOGIN-31: profile roles agree with the roles minted at login.

    A mismatch means the shell's cached permissions drift from the server's.
    """
    assert profile_response.status_code == 200, f"User search failed: {profile_response.text}"

    from_search = role_codes_from(profile_response.json()["user"][0])
    from_login = session["roles"]

    assert from_search == from_login, (
        f"Role drift — login: {from_login}, /user/_search: {from_search}"
    )
    print(f"Roles consistent across login and profile: {len(from_login)} roles")


@pytest.mark.negative
@pytest.mark.login
def test_user_search_rejects_invalid_token(session):
    """LOGIN-32: a forged auth token cannot read profiles."""
    forged = "00000000-0000-0000-0000-000000000000"
    response = search_user(forged, uuids=[session["user_info"].get("uuid")])

    assert response.status_code in (400, 401, 403), (
        f"Expected auth rejection, got {response.status_code}: {response.text}"
    )
    print(f"Forged token correctly rejected with {response.status_code}")


@pytest.mark.negative
@pytest.mark.login
def test_user_search_requires_criteria(session):
    """LOGIN-33: an unbounded /user/_search is refused.

    Without criteria the service would otherwise dump the whole user table.
    """
    response = search_user(session["token"], session["client"], omit_criteria=True)

    assert response.status_code == 400, (
        f"Expected 400 for criteria-less search, got {response.status_code}: {response.text}"
    )
    print("Unbounded user search correctly refused")


# ---------------------------------------------------------------------------
# LOGIN-40..43 — role-based actions (the landing page)
# ---------------------------------------------------------------------------

@pytest.mark.positive
@pytest.mark.login
def test_authorized_actions_returned_for_roles(session, actions_response):
    """LOGIN-40: the access service returns the actions behind the home cards."""
    response = actions_response

    assert response.status_code == 200, f"Action lookup failed: {response.text}"
    actions = response.json().get("actions", [])
    assert actions, f"No actions for roles {session['roles']} — landing page would be empty"
    print(f"{len(actions)} actions authorised for {len(session['roles'])} roles")


@pytest.mark.positive
@pytest.mark.login
def test_authorized_actions_are_well_formed(actions_response):
    """LOGIN-41: every action carries the fields the shell renders/routes on."""
    response = actions_response
    assert response.status_code == 200, f"Action lookup failed: {response.text}"

    # The master mixes two shapes: API actions (url/name) and nav entries
    # (displayName/navigationURL/path). An entry is usable if it is identified
    # and carries at least one of those handles — several nav entries on
    # hcm-demo legitimately have a blank `name`.
    handles = ("name", "url", "displayName", "navigationURL", "path")
    malformed = [
        a for a in response.json().get("actions", [])
        if a.get("id") is None
        or not a.get("tenantId")
        or not any(a.get(h) for h in handles)
    ]
    assert not malformed, (
        f"{len(malformed)} actions are unusable (need id, tenantId and one of "
        f"{handles}), e.g. {malformed[0]}"
    )
    print("All authorised actions are well-formed")


@pytest.mark.negative
@pytest.mark.login
def test_authorized_actions_requires_at_least_one_role(session):
    """LOGIN-42: an empty roleCodes list is rejected rather than defaulted."""
    response = get_authorized_actions(session["token"], session["client"], role_codes=[])

    assert response.status_code == 400, (
        f"Expected 400 for empty roleCodes, got {response.status_code}: {response.text}"
    )
    print("Empty roleCodes correctly rejected")


@pytest.mark.negative
@pytest.mark.login
def test_unknown_role_grants_no_actions(session):
    """LOGIN-43: an unrecognised role grants nothing (fails closed).

    The service answers 200 with an empty list rather than erroring, so this
    guards against it ever falling back to a permissive default.
    """
    response = get_authorized_actions(session["token"], session["client"],
                                      role_codes=["NO_SUCH_ROLE_AUTOMATION"])

    assert response.status_code == 200, f"Unexpected status: {response.status_code}"
    actions = response.json().get("actions") or []
    assert actions == [], f"Unknown role was granted {len(actions)} actions"
    print("Unknown role correctly granted zero actions")


@pytest.mark.negative
@pytest.mark.login
def test_unknown_action_master_grants_no_actions(session):
    """LOGIN-44: an unknown actionMaster does not widen access."""
    response = get_authorized_actions(
        session["token"], session["client"],
        role_codes=session["roles"], action_master="no-such-master-automation",
    )

    assert response.status_code in (200, 400), f"Unexpected status: {response.status_code}"
    if response.status_code == 200:
        actions = response.json().get("actions") or []
        assert actions == [], f"Unknown action master returned {len(actions)} actions"
    print(f"Unknown action master handled safely ({response.status_code}), master={accessActionMaster} is the valid one")
