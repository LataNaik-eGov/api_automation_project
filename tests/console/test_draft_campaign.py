"""Draft campaign step — name and date validation.

API counterpart of DraftCampaignTest in the Playwright console suite. Each case
runs once per configured campaign type.
"""

import pytest

from utils.console import (
    assert_rejected,
    create_draft,
    invalid_campaign_names,
    search_campaign,
    unique_campaign_name,
)


# --- Positive ---------------------------------------------------------------

@pytest.mark.console
@pytest.mark.positive
def test_create_draft_campaign(token, client, campaign_type, project_type):
    """A valid name and date range creates a drafted campaign."""
    name = unique_campaign_name(prefix=campaign_type.replace("-", ""))
    response = create_draft(token, client, campaign_type, project_type, campaign_name=name)

    assert response.status_code in (200, 202), f"Draft creation failed: {response.text}"

    details = response.json()["CampaignDetails"]
    assert details.get("id"), "Draft campaign has no id"
    assert details.get("campaignNumber"), "Draft campaign has no campaignNumber"
    assert details.get("campaignName") == name, (
        f"Campaign name not persisted. Expected '{name}', got '{details.get('campaignName')}'"
    )
    assert details.get("status") == "drafted", (
        f"Expected status 'drafted', got '{details.get('status')}'"
    )
    print(f"Draft created for {campaign_type}: {details['campaignNumber']} ({details['id']})")


@pytest.mark.console
@pytest.mark.positive
def test_draft_campaign_is_searchable(token, client, campaign_type, draft):
    """A created draft can be found by its campaign number."""
    campaign_number = draft["campaignNumber"]
    response = search_campaign(token, client, campaign_number=campaign_number)

    assert response.status_code == 200, f"Campaign search failed: {response.text}"

    campaigns = response.json().get("CampaignDetails", [])
    assert any(c.get("campaignNumber") == campaign_number for c in campaigns), (
        f"Draft {campaign_number} not returned by search"
    )
    print(f"Draft {campaign_number} found for {campaign_type}")


# --- Negative: campaign name ------------------------------------------------

@pytest.mark.console
@pytest.mark.negative
@pytest.mark.parametrize(
    "case_id,invalid_name",
    invalid_campaign_names(),
    ids=[case for case, _ in invalid_campaign_names()],
)
def test_draft_campaign_rejects_invalid_name(
    token, client, campaign_type, project_type, case_id, invalid_name
):
    """Names the console UI blocks must also be blocked by project-factory.

    Covers: too long (>30 chars), leading special character, emoji, and
    consecutive underscores.
    """
    response = create_draft(
        token, client, campaign_type, project_type, campaign_name=invalid_name
    )
    assert_rejected(
        response,
        f"{campaign_type}: campaign name '{invalid_name}' ({case_id.replace('_', ' ')})",
    )


# --- Negative: dates --------------------------------------------------------

