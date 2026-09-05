"""App configuration step.

API counterpart of AppConfigurationTest in the Playwright console suite.

The console screen writes to two places: the module configuration itself, held
as an MDMS master, and the field labels, held in the localization service. Both
are covered here.

The schema code and localization module are configurable (APP_CONFIG_SCHEMA_CODE,
APP_CONFIG_LOCALIZATION_MODULE) because they differ between HCM releases.
"""

import uuid

import pytest

from utils.config import appConfigLocalizationModule, appConfigSchemaCode, locale
from utils.console import (
    assert_rejected,
    search_app_config,
    search_labels,
    upsert_label,
)


# --- Helpers ----------------------------------------------------------------

def _app_config_entries(token, client):
    response = search_app_config(token, client)
    assert response.status_code == 200, (
        f"App config lookup failed for schema '{appConfigSchemaCode}': {response.text}"
    )
    return response.json().get("mdms", [])


def _label_code(prefix="HCM_AUTO_LABEL"):
    return f"{prefix}_{uuid.uuid4().hex[:8].upper()}"


# --- Positive: read configuration -------------------------------------------

@pytest.mark.console
@pytest.mark.positive
def test_app_configuration_is_available(token, client, campaign_type):
    """The app configuration master exists and is readable."""
    entries = _app_config_entries(token, client)
    if not entries:
        pytest.skip(
            f"No app configuration found under schema '{appConfigSchemaCode}'. "
            f"Set APP_CONFIG_SCHEMA_CODE if this environment uses a different master."
        )

    first = entries[0]
    assert first.get("data"), "App config entry has no data block"
    assert first.get("schemaCode"), "App config entry has no schemaCode"

    print(f"{campaign_type}: {len(entries)} app config entr(ies) under {appConfigSchemaCode}")
    for key, value in list(first["data"].items())[:10]:
        print(f"  {key}: {value}")


@pytest.mark.console
@pytest.mark.positive
def test_app_configuration_entries_are_active(token, client, campaign_type):
    """Every app configuration entry the console reads back is active."""
    entries = _app_config_entries(token, client)
    if not entries:
        pytest.skip(f"No app configuration found under schema '{appConfigSchemaCode}'.")

    inactive = [e.get("uniqueIdentifier") for e in entries if e.get("isActive") is False]
    assert not inactive, f"Inactive app config entries returned to the console: {inactive}"
    print(f"{campaign_type}: all {len(entries)} app config entries are active")


# --- Positive: label change -------------------------------------------------

@pytest.mark.console
@pytest.mark.positive
def test_app_configuration_label_change(token, client, campaign_type):
    """Changing a field label writes through to the localization service."""
    code = _label_code()
    original = f"Original label {code}"

    response = upsert_label(
        token, client, code, original, appConfigLocalizationModule
    )
    assert response.status_code in (200, 201, 202), f"Label create failed: {response.text}"

    updated = f"Updated label {uuid.uuid4().hex[:6]}"
    response = upsert_label(
        token, client, code, updated, appConfigLocalizationModule
    )
    assert response.status_code in (200, 201, 202), f"Label update failed: {response.text}"

    search = search_labels(token, client, appConfigLocalizationModule)
    assert search.status_code == 200, f"Label search failed: {search.text}"

    messages = search.json().get("messages", [])
    match = next((m for m in messages if m.get("code") == code), None)
    assert match, f"Label '{code}' not found in module '{appConfigLocalizationModule}'"
    assert match.get("message") == updated, (
        f"Label not updated. Expected '{updated}', got '{match.get('message')}'"
    )
    print(f"{campaign_type}: label '{code}' changed from '{original}' to '{updated}'")


# --- Negative ---------------------------------------------------------------

@pytest.mark.console
@pytest.mark.negative
def test_app_configuration_rejects_empty_label(token, client, campaign_type):
    """A blank label must be rejected, matching the console's toast error."""
    response = upsert_label(
        token, client, _label_code("HCM_AUTO_EMPTY"), "", appConfigLocalizationModule
    )
    assert_rejected(response, f"{campaign_type}: app config field saved with an empty label")


@pytest.mark.console
@pytest.mark.negative
def test_app_configuration_rejects_blank_label_code(token, client, campaign_type):
    """A label with no code must be rejected."""
    response = upsert_label(
        token, client, "", "Some label", appConfigLocalizationModule
    )
    assert_rejected(response, f"{campaign_type}: app config label saved with no code")


@pytest.mark.console
@pytest.mark.negative
def test_app_configuration_unknown_schema_returns_no_data(token, client, campaign_type):
    """An unknown configuration schema returns nothing rather than another module's data."""
    response = search_app_config(token, client, schema_code="HCM.NON_EXISTENT_APP_CONFIG")
    assert response.status_code in (200, 400, 404), (
        f"Unexpected status for unknown schema: {response.status_code} - {response.text}"
    )

    if response.status_code == 200:
        entries = response.json().get("mdms", [])
        assert entries == [], f"Expected no data for an unknown schema, got {len(entries)} entries"
    print(f"{campaign_type}: unknown app config schema handled correctly "
          f"(status {response.status_code}, locale {locale})")
