import requests
from dotenv import load_dotenv

from utils.config import (
    BASE_URL,
    SERVICE_OAUTH_TOKEN,
    clientAuthHeader,
    loginPassword,
    loginUsername,
    tenantId,
    userType,
)

# Load environment variables from .env file
load_dotenv(override=True)  # This forces reloading of updated values

_token_cache: dict[str, str] = {}
_user_info_cache: dict[str, dict] = {}


def oauth_token(
    username=None,
    password=None,
    tenant=None,
    user_type=None,
    grant_type="password",
    auth_header=None,
):
    """POST /user/oauth/token exactly as the workbench login form does.

    The single definition of how this product signs in. Deliberately not routed
    through APIClient: the call is ``application/x-www-form-urlencoded`` and
    carries the OAuth client Basic header rather than a Bearer token.

    Every field is overridable so the login suite's negative tests can vary one
    at a time; ``auth_header=""`` omits the client header entirely. Returns the
    raw response so those tests can assert on status as well as body.
    """
    data = {
        "username": loginUsername if username is None else username,
        "password": loginPassword if password is None else password,
        "grant_type": grant_type,
        "scope": "read",
        "tenantId": tenantId if tenant is None else tenant,
        "userType": userType if user_type is None else user_type,
    }

    headers = {
        "accept": "application/json, text/plain, */*",
        "content-type": "application/x-www-form-urlencoded",
    }
    header_value = clientAuthHeader if auth_header is None else auth_header
    if header_value:
        headers["authorization"] = header_value

    return requests.post(BASE_URL + SERVICE_OAUTH_TOKEN, data=data, headers=headers)


def get_auth_token(service: str):
    """A cached bearer token for ``service``, logging in on first use."""
    if service in _token_cache:
        return _token_cache[service]

    response = oauth_token()
    assert response.status_code == 200, f"Auth failed: {response.text}"

    data = response.json()
    token = data.get("access_token")
    _token_cache[service] = token
    _user_info_cache[service] = data.get("UserRequest", {})
    return token


def get_user_info(service: str) -> dict:
    if service not in _user_info_cache:
        get_auth_token(service)
    return _user_info_cache.get(service, {})


def clear_token_cache():
    _token_cache.clear()
    _user_info_cache.clear()
