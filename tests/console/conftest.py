"""Shared fixtures for the console (campaign) suite.

Every test that asks for ``campaign_type`` runs once per configured campaign
type, so the whole suite covers BEDNET and MR-DN the same way the Playwright
console suite does.
"""

import pytest

from utils.api_client import APIClient
from utils.auth import get_auth_token
from utils.console import (
    boundary_chain,
    campaign_type_keys,
    create_draft,
    resolve_project_type,
)


@pytest.fixture(scope="session")
def token():
    return get_auth_token("user")


@pytest.fixture
def client(token):
    return APIClient(token=token)


@pytest.fixture(params=campaign_type_keys())
def campaign_type(request):
    """One console campaign type, e.g. BEDNET or MR-DN."""
    return request.param


@pytest.fixture
def project_type(token, client, campaign_type):
    """The MDMS project type backing this campaign type."""
    data = resolve_project_type(token, client, campaign_type)
    if not data:
        pytest.skip(
            f"Project type for campaign type '{campaign_type}' is not configured in MDMS "
            f"on this environment. Update data/console/campaign_types.json if the code differs."
        )
    return data


@pytest.fixture
def boundaries(token, client):
    """A complete root-to-leaf boundary path for the configured hierarchy."""
    chain = boundary_chain(token, client)
    if len(chain) < 2:
        pytest.skip("Boundary hierarchy has fewer than two levels; cannot exercise selection.")
    return chain


@pytest.fixture
def draft(token, client, campaign_type, project_type):
    """A freshly created campaign draft, ready for the next wizard step."""
    response = create_draft(token, client, campaign_type, project_type)
    assert response.status_code in (200, 202), (
        f"Could not create draft for {campaign_type}: {response.text}"
    )
    return response.json()["CampaignDetails"]
