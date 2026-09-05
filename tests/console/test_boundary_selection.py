"""Boundary selection step.

API counterpart of BoundarySelectionTest in the Playwright console suite.

The boundary chain is resolved from the boundary service at runtime, so these
tests carry no hardcoded boundary codes and run against any hierarchy.
"""

import pytest

from utils.console import (
    boundary_chain,
    fetch_campaign,
    update_boundaries,
)


# --- Positive ---------------------------------------------------------------

@pytest.mark.console
@pytest.mark.positive
def test_boundary_selection(token, client, campaign_type, project_type, draft, boundaries):
    """A complete root-to-leaf selection is accepted and persisted."""
    response = update_boundaries(token, client, draft, project_type, boundaries)
    assert response.status_code in (200, 202), f"Boundary update failed: {response.text}"

    details = response.json()["CampaignDetails"]
    saved = details.get("boundaries", [])
    assert len(saved) == len(boundaries), (
        f"Expected {len(boundaries)} boundaries persisted, got {len(saved)}"
    )

    saved_codes = {b.get("code") for b in saved}
    expected_codes = {b["code"] for b in boundaries}
    assert saved_codes == expected_codes, (
        f"Persisted boundary codes differ.\n  expected: {sorted(expected_codes)}"
        f"\n  actual:   {sorted(saved_codes)}"
    )

    root = next((b for b in saved if b.get("isRoot")), None)
    assert root, "No root boundary marked in the persisted selection"
    print(
        f"{campaign_type}: {len(saved)} boundaries selected, "
        f"root={root.get('code')} ({root.get('type')})"
    )


@pytest.mark.console
@pytest.mark.positive
def test_boundary_selection_survives_reload(
    token, client, campaign_type, project_type, draft, boundaries
):
    """Boundaries are still on the campaign when it is read back."""
    response = update_boundaries(token, client, draft, project_type, boundaries)
    assert response.status_code in (200, 202), f"Boundary update failed: {response.text}"

    match = fetch_campaign(token, client, draft["campaignNumber"])
    assert match.get("boundaries"), "Boundaries missing from the reloaded campaign"
    print(f"{campaign_type}: {len(match['boundaries'])} boundaries present after reload")


# --- Negative ---------------------------------------------------------------

