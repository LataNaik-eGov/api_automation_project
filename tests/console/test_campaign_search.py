"""Search the artefacts a created campaign produces.

Runs after test_campaign_e2e.py, against the campaign it recorded in
output/console/campaigns.json.
"""

import pytest

from utils.console import (
    load_campaign_result,
    search_campaign,
    search_project_facilities,
    search_project_staff,
    search_projects,
)


@pytest.fixture
def created_campaign(campaign_type):
    """The campaign created by the end-to-end test for this campaign type."""
    data = load_campaign_result(campaign_type)
    if not data:
        pytest.skip(
            f"No created campaign recorded for {campaign_type}. "
            f"Run tests/console/test_campaign_e2e.py first."
        )
    return data


@pytest.fixture
def project_ids(token, client, created_campaign):
    response = search_projects(token, client, created_campaign["campaignNumber"])
    assert response.status_code == 200, f"Project search failed: {response.text}"
    ids = [p.get("id") for p in response.json().get("Project", []) if p.get("id")]
    if not ids:
        pytest.skip(
            f"Campaign {created_campaign['campaignNumber']} produced no projects to search."
        )
    return ids


# --- Campaign ---------------------------------------------------------------

@pytest.mark.console
@pytest.mark.positive
def test_search_campaign_by_number(token, client, campaign_type, created_campaign):
    number = created_campaign["campaignNumber"]
    response = search_campaign(token, client, campaign_number=number)

    assert response.status_code == 200, f"Campaign search failed: {response.text}"
    campaigns = response.json().get("CampaignDetails", [])
    match = next((c for c in campaigns if c.get("campaignNumber") == number), None)

    assert match, f"Campaign {number} not found"
    assert match.get("status") == "created", (
        f"Expected status 'created', got '{match.get('status')}'"
    )
    for field in ("id", "campaignNumber", "campaignName", "tenantId", "status"):
        assert field in match, f"Campaign response missing '{field}'"
    print(f"{campaign_type}: campaign {number} found with status {match['status']}")


@pytest.mark.console
@pytest.mark.positive
def test_search_campaign_by_id(token, client, campaign_type, created_campaign):
    campaign_id = created_campaign["campaignId"]
    response = search_campaign(token, client, campaign_id=campaign_id)

    assert response.status_code == 200, f"Campaign search failed: {response.text}"
    campaigns = response.json().get("CampaignDetails", [])
    assert any(c.get("id") == campaign_id for c in campaigns), (
        f"Campaign {campaign_id} not found by id"
    )
    print(f"{campaign_type}: campaign found by id {campaign_id}")


@pytest.mark.console
@pytest.mark.negative
def test_search_campaign_with_unknown_number(token, client, campaign_type):
    response = search_campaign(token, client, campaign_number="NO-SUCH-CAMPAIGN-00000")

    assert response.status_code == 200, f"Campaign search failed: {response.text}"
    campaigns = response.json().get("CampaignDetails", [])
    assert campaigns == [], f"Expected no campaigns, got {len(campaigns)}"
    print(f"{campaign_type}: unknown campaign number returned no results")


# --- Projects ---------------------------------------------------------------

@pytest.mark.console
@pytest.mark.positive
def test_search_projects_for_campaign(token, client, campaign_type, created_campaign):
    number = created_campaign["campaignNumber"]
    response = search_projects(token, client, number)

    assert response.status_code == 200, f"Project search failed: {response.text}"
    data = response.json()
    assert "TotalCount" in data, "Project response missing TotalCount"

    projects = data.get("Project", [])
    assert projects, f"Campaign {number} created no projects"

    for project in projects:
        assert project.get("referenceID") == number, (
            f"Project {project.get('id')} has referenceID "
            f"{project.get('referenceID')}, expected {number}"
        )
        assert project.get("address", {}).get("boundaryType"), (
            f"Project {project.get('id')} has no boundaryType"
        )

    by_boundary = {}
    for project in projects:
        boundary_type = project["address"]["boundaryType"]
        by_boundary.setdefault(boundary_type, []).append(project["id"])

    print(f"{campaign_type}: {data['TotalCount']} project(s) across {len(by_boundary)} level(s)")
    for boundary_type, ids in by_boundary.items():
        print(f"  {boundary_type}: {len(ids)}")


@pytest.mark.console
@pytest.mark.negative
def test_search_projects_with_unknown_reference(token, client, campaign_type):
    response = search_projects(token, client, "NO-SUCH-CAMPAIGN-00000")

    assert response.status_code == 200, f"Project search failed: {response.text}"
    assert response.json().get("TotalCount", 0) == 0, "Expected no projects"
    print(f"{campaign_type}: unknown referenceID returned no projects")


# --- Project facilities -----------------------------------------------------

@pytest.mark.console
@pytest.mark.positive
def test_search_project_facilities(token, client, campaign_type, project_ids):
    response = search_project_facilities(token, client, project_ids)

    assert response.status_code == 200, f"Facility search failed: {response.text}"
    facilities = response.json().get("ProjectFacilities", [])
    assert facilities, "Campaign projects have no facilities mapped"

    for facility in facilities:
        for field in ("id", "projectId", "facilityId"):
            assert field in facility, f"Facility mapping missing '{field}'"
        assert facility["projectId"] in project_ids, (
            f"Facility {facility['id']} belongs to an unrelated project"
        )
    print(f"{campaign_type}: {len(facilities)} facility mapping(s)")


@pytest.mark.console
@pytest.mark.negative
def test_search_project_facilities_with_unknown_project(token, client, campaign_type):
    response = search_project_facilities(token, client, ["no-such-project-id"])

    assert response.status_code == 200, f"Facility search failed: {response.text}"
    assert response.json().get("ProjectFacilities", []) == [], "Expected no facilities"
    print(f"{campaign_type}: unknown project id returned no facilities")


# --- Project staff ----------------------------------------------------------

@pytest.mark.console
@pytest.mark.positive
def test_search_project_staff(token, client, campaign_type, project_ids):
    response = search_project_staff(token, client, project_ids)

    assert response.status_code == 200, f"Staff search failed: {response.text}"
    staff = response.json().get("ProjectStaff", [])
    assert staff, "Campaign projects have no staff mapped"

    for member in staff:
        for field in ("id", "projectId", "userId"):
            assert field in member, f"Staff mapping missing '{field}'"
        assert member["projectId"] in project_ids, (
            f"Staff {member['id']} belongs to an unrelated project"
        )
    print(f"{campaign_type}: {len(staff)} staff assignment(s)")


@pytest.mark.console
@pytest.mark.negative
def test_search_project_staff_with_unknown_project(token, client, campaign_type):
    response = search_project_staff(token, client, ["no-such-project-id"])

    assert response.status_code == 200, f"Staff search failed: {response.text}"
    assert response.json().get("ProjectStaff", []) == [], "Expected no staff"
    print(f"{campaign_type}: unknown project id returned no staff")
