#!/usr/bin/env python3
"""Check everything the console suite needs before running it for real.

Each check runs independently and reports what it found, so one missing piece
does not hide the rest. Exits non-zero if anything is blocking.

    python3 scripts/console_preflight.py
    python3 scripts/console_preflight.py BEDNET     # check one campaign type
"""

import os
import sys
import traceback

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

BLOCKERS = []
WARNINGS = []


def blocker(message, fix):
    BLOCKERS.append((message, fix))
    print(f"  [BLOCKED] {message}")
    print(f"            fix: {fix}")


def warn(message, fix):
    WARNINGS.append((message, fix))
    print(f"  [WARN]    {message}")
    print(f"            fix: {fix}")


def ok(message):
    print(f"  [OK]      {message}")


def section(title):
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")


def main(requested_types=None):
    # --- 1. Configuration -------------------------------------------------
    section("1. Configuration (.env)")
    try:
        from utils.config import (
            BASE_URL, tenantId, locale, consoleHierarchyType,
            appConfigSchemaCode, consoleCampaignTypes,
        )
    except Exception as exc:
        blocker(f"Could not load configuration: {exc}",
                "Copy .env.example to .env and fill in BASE_URL / USERNAME / PASSWORD.")
        return report()

    ok(f"BASE_URL           = {BASE_URL}")
    ok(f"tenantId           = {tenantId}")
    ok(f"locale             = {locale}")
    ok(f"hierarchyType      = {consoleHierarchyType}")
    ok(f"appConfigSchema    = {appConfigSchemaCode}")
    ok(f"campaignTypes      = {consoleCampaignTypes or '(all)'}")

    if not consoleHierarchyType:
        blocker("No boundary hierarchy configured.",
                "Set CONSOLE_HIERARCHY_TYPE (or BOUNDARY_HIERARCHY_CODE) in .env.")

    for name in ("USERNAME", "PASSWORD"):
        value = os.getenv(name)
        if not value or value == "CHANGE_ME":
            blocker(f"{name} is not set in .env.",
                    f"Set {name} to a console user with the Campaign Manager role.")

    if BLOCKERS:
        return report()

    # --- 2. Authentication ------------------------------------------------
    section("2. Authentication")
    try:
        from utils.auth import get_auth_token, get_user_info
        from utils.api_client import APIClient

        token = get_auth_token("user")
        client = APIClient(token=token)
        user = get_user_info("user")

        ok(f"authenticated as {user.get('userName')} (uuid {user.get('uuid')})")
        roles = [r.get("code") for r in user.get("roles", [])]
        ok(f"roles: {', '.join(roles) if roles else '(none)'}")

        if "CAMPAIGN_MANAGER" not in roles:
            warn("User does not have the CAMPAIGN_MANAGER role.",
                 "Campaign create/update calls will likely return 403. "
                 "Use a console user, or add the role in HRMS.")
    except Exception as exc:
        blocker(f"Authentication failed: {exc}",
                "Check BASE_URL, USERNAME, PASSWORD and CLIENT_AUTH_HEADER in .env.")
        return report()

    # --- 3. Campaign types / project types --------------------------------
    section("3. Campaign types (MDMS project types)")
    resolved_types = []
    try:
        from utils.console import (
            campaign_type_keys, campaign_type_config,
            fetch_project_types, resolve_project_type,
        )

        available = fetch_project_types(token, client)
        ok(f"{len(available)} active project type(s) in MDMS")
        print(f"            codes: {', '.join(sorted(available)) or '(none)'}")

        types_to_check = requested_types or campaign_type_keys()
        for campaign_type in types_to_check:
            config = campaign_type_config(campaign_type)
            expected = config["projectTypeCode"]
            data = resolve_project_type(token, client, campaign_type)

            if not data:
                blocker(
                    f"{campaign_type}: project type '{expected}' not found in MDMS.",
                    f"Set the right code for {campaign_type} in "
                    f"data/console/campaign_types.json. Available: {', '.join(sorted(available))}",
                )
                continue

            cycles = data.get("cycles") or []
            variants = [
                v
                for c in cycles
                for d in (c.get("deliveries") or [])
                for dc in (d.get("doseCriteria") or [])
                for v in (dc.get("ProductVariants") or [])
            ]
            ok(f"{campaign_type} -> '{data.get('code')}': "
               f"{len(cycles)} cycle(s), {len(variants)} product variant(s)")

            if not cycles:
                warn(f"{campaign_type}: project type defines no cycles.",
                     "The delivery-rule date negatives will skip.")
            if not variants:
                warn(f"{campaign_type}: project type defines no product variants.",
                     "The delivery-rule quantity negatives will skip.")
            resolved_types.append(campaign_type)
    except Exception as exc:
        blocker(f"Project type lookup failed: {exc}",
                "Check that SERVICE_MDMS is set and the user can read MDMS.")
        traceback.print_exc()

    # --- 4. Boundaries ----------------------------------------------------
    section("4. Boundaries")
    try:
        from utils.console import boundary_chain, fetch_boundary_hierarchy

        levels = fetch_boundary_hierarchy(token, client)
        ok(f"hierarchy '{consoleHierarchyType}': {' > '.join(levels)}")

        chain = boundary_chain(token, client)
        ok(f"resolved a {len(chain)}-level path:")
        for entry in chain:
            marker = " (root)" if entry["isRoot"] else ""
            children = " +all children" if entry["includeAllChildren"] else ""
            print(f"            {entry['type']}: {entry['code']}{marker}{children}")

        if len(chain) < 2:
            blocker("Boundary path has fewer than two levels.",
                    "Load boundary data for this hierarchy, or point "
                    "CONSOLE_HIERARCHY_TYPE at one that has data.")
        elif len(chain) < 3:
            warn("Boundary path has only two levels.",
                 "The partial-selection negative will skip.")
    except Exception as exc:
        blocker(f"Boundary lookup failed: {exc}",
                "Check CONSOLE_HIERARCHY_TYPE and that boundary data is loaded for this tenant.")
        traceback.print_exc()

    # --- 5. App configuration ---------------------------------------------
    section("5. App configuration")
    try:
        from utils.console import search_app_config

        response = search_app_config(token, client)
        if response.status_code != 200:
            warn(f"App config search returned {response.status_code}.",
                 "Set APP_CONFIG_SCHEMA_CODE to the schema this environment uses.")
        else:
            entries = response.json().get("mdms", [])
            if not entries:
                warn(f"No entries under schema '{appConfigSchemaCode}'.",
                     "Set APP_CONFIG_SCHEMA_CODE to the console's app config schema. "
                     "The app configuration tests will skip until then.")
            else:
                ok(f"{len(entries)} entr(ies) under '{appConfigSchemaCode}'")
                booleans = [
                    k for k, v in (entries[0].get("data") or {}).items()
                    if isinstance(v, bool)
                ]
                if booleans:
                    ok(f"toggles available: {', '.join(booleans[:5])}")
                else:
                    warn("No boolean toggle found in the config data.",
                         "The toggle-off test will skip.")
    except Exception as exc:
        warn(f"App config check failed: {exc}",
             "Set APP_CONFIG_SCHEMA_CODE, or ignore if app config tests are out of scope.")

    # --- 6. Sample templates ----------------------------------------------
    section("6. Sample templates")
    try:
        from utils.config import prefilled_filestore_id
        from utils.template_filler import sample_template_path

        for campaign_type in (resolved_types or requested_types or []):
            path = sample_template_path(campaign_type)
            if path:
                ok(f"{campaign_type}: {path}")
            elif prefilled_filestore_id(campaign_type):
                warn(f"{campaign_type}: no sample template; "
                     f"falling back to CONSOLE_PREFILLED_FILESTORE_ID"
                     f"[_{campaign_type.replace('-', '_').upper()}].",
                     "Add a sample so the fill is reproducible across environments.")
            else:
                blocker(
                    f"{campaign_type}: no filled-in sample template.",
                    f"Add data/console/templates/{campaign_type}_sample.xlsx — one "
                    f"correctly filled data row is enough. Without it the end-to-end "
                    f"and validation tests skip.",
                )
    except Exception as exc:
        warn(f"Template check failed: {exc}", "Check that openpyxl is installed.")

    return report()


def report():
    section("Summary")
    if not BLOCKERS and not WARNINGS:
        print("  Ready. Run: python3 -m pytest tests/console -v -s")
        return 0

    if BLOCKERS:
        print(f"  {len(BLOCKERS)} blocker(s) — the suite cannot complete a flow:\n")
        for message, fix in BLOCKERS:
            print(f"    - {message}\n      {fix}\n")

    if WARNINGS:
        print(f"  {len(WARNINGS)} warning(s) — some tests will skip:\n")
        for message, fix in WARNINGS:
            print(f"    - {message}\n      {fix}\n")

    return 1 if BLOCKERS else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:] or None))
