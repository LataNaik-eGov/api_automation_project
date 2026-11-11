"""Configure delivery rules step.

API counterpart of ConfigureDeliveryRulesTest in the Playwright console suite.

Delivery rules are built from the MDMS project type definition rather than a
checked-in payload, so no product variant IDs are hardcoded and the negatives
mutate whatever the environment actually defines.
"""

from copy import deepcopy

import pytest

from utils.console import (
    build_cycle_data,
    build_delivery_rules,
    one_month_later_ts,
    fetch_campaign,
    tomorrow_ts,
    update_boundaries,
    update_delivery_rules,
)


# --- Helpers ----------------------------------------------------------------

def _rules_for(project_type, draft):
    start_ts = draft.get("startDate") or tomorrow_ts()
    end_ts = draft.get("endDate") or one_month_later_ts()
    return (
        build_delivery_rules(project_type, start_ts, end_ts),
        build_cycle_data(project_type, start_ts, end_ts),
    )


def _product_variants(rules):
    """Every ProductVariants entry across all cycles, deliveries and criteria."""
    variants = []
    for rule in rules:
        for cycle in rule.get("cycles") or []:
            for delivery in cycle.get("deliveries") or []:
                for criteria in delivery.get("doseCriteria") or []:
                    variants.extend(criteria.get("ProductVariants") or [])
    return variants


def _set_quantity(rules, value):
    """Set every product variant quantity, returning how many were changed."""
    variants = _product_variants(rules)
    for variant in variants:
        variant["quantity"] = value
    return len(variants)


def _cycles(rules):
    return [cycle for rule in rules for cycle in (rule.get("cycles") or [])]


@pytest.fixture
def boundaried_draft(token, client, project_type, draft, boundaries):
    """A draft that has already cleared the boundary step."""
    response = update_boundaries(token, client, draft, project_type, boundaries)
    assert response.status_code in (200, 202), f"Boundary step failed: {response.text}"
    return response.json()["CampaignDetails"]


# --- Positive ---------------------------------------------------------------

@pytest.mark.console
@pytest.mark.positive
def test_configure_delivery_rules(
    token, client, campaign_type, project_type, boundaried_draft, boundaries
):
    """The project type's delivery rules are accepted and persisted."""
    rules, cycle_data = _rules_for(project_type, boundaried_draft)
    assert rules, f"No delivery rules could be built for {campaign_type}"

    response = update_delivery_rules(
        token, client, boundaried_draft, project_type, boundaries,
        delivery_rules=rules, cycle_data=cycle_data,
    )
    assert response.status_code in (200, 202), f"Delivery rules update failed: {response.text}"

    # The update response omits deliveryRules/cycleData/resources even when the
    # write succeeded, so assert against the read model instead.
    details = fetch_campaign(token, client, boundaried_draft["campaignNumber"])
    saved = details.get("deliveryRules", [])
    assert saved, (
        "No delivery rules persisted on the campaign "
        f"(update returned {len(response.json()['CampaignDetails'].get('deliveryRules') or [])})"
    )

    saved_cycles = _cycles(saved)
    assert saved_cycles, "Persisted delivery rules contain no cycles"
    for cycle in saved_cycles:
        assert cycle.get("startDate"), "Persisted cycle has no start date"
        assert cycle.get("endDate"), "Persisted cycle has no end date"
        assert cycle["endDate"] > cycle["startDate"], (
            f"Cycle end date {cycle['endDate']} is not after start date {cycle['startDate']}"
        )

    print(
        f"{campaign_type}: {len(saved)} delivery rule(s), {len(saved_cycles)} cycle(s), "
        f"{len(_product_variants(saved))} product variant(s)"
    )


@pytest.mark.console
@pytest.mark.positive
def test_delivery_rules_cycle_data_matches_cycles(
    token, client, campaign_type, project_type, boundaried_draft, boundaries
):
    """additionalDetails.cycleData stays in step with the delivery rule cycles."""
    rules, cycle_data = _rules_for(project_type, boundaried_draft)

    response = update_delivery_rules(
        token, client, boundaried_draft, project_type, boundaries,
        delivery_rules=rules, cycle_data=cycle_data,
    )
    assert response.status_code in (200, 202), f"Delivery rules update failed: {response.text}"

    details = fetch_campaign(token, client, boundaried_draft["campaignNumber"])
    saved_cycle_data = details.get("additionalDetails", {}).get("cycleData", {})
    entries = saved_cycle_data.get("cycleData", [])
    configured = saved_cycle_data.get("cycleConfgureDate", {})

    assert entries, "cycleData is empty on the persisted campaign"
    assert configured.get("cycle") == len(entries), (
        f"cycleConfgureDate.cycle ({configured.get('cycle')}) does not match "
        f"the {len(entries)} cycleData entries"
    )
    print(f"{campaign_type}: {len(entries)} cycle(s) configured")


# --- Negative: cycle dates --------------------------------------------------

