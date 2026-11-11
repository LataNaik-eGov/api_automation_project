# Workbench-UI Login Flow — API Notes & Test Cases

Target: `https://hcm-demo.digit.org/workbench-ui/employee/user/login`
Captured: 2026-09-05, from a real browser sign-in with network tracing.
Automation: `tests/test_login_flow.py` (helpers in `utils/login.py`,
payloads in `payloads/login/`).

Run with:

```bash
pytest tests/test_login_flow.py -v          # whole flow
pytest -m login -v                          # same, by marker
pytest -m "login and negative" -v           # negative paths only
```

---

## 1. Environment

| Setting | Value | Source |
|---|---|---|
| Base URL | `https://hcm-demo.digit.org` | `.env` `BASE_URL` |
| Tenant | `demo` | `globalConfigsWorkbenchDemo.js` → `stateTenantId` |
| Locale | `en_DEMO` | `localeDefault` + `localeRegion` (`en` + `DEMO`) |
| Hierarchy | `MICROPLAN` | `globalConfigsWorkbenchDemo.js` |
| User type | `EMPLOYEE` | login form |
| Context path | `workbench-ui` | `globalConfigsWorkbenchDemo.js` |

> The repo previously had `LOCALE=en_MZ`, which does not match this
> environment. Corrected to `en_DEMO` in `.env` and `.env.example`.

## 2. Files the page loads

Runtime config, fetched before the app boots — the source of truth for
tenant/locale/service paths:

- `https://hcm-demo-assets.s3.ap-south-1.amazonaws.com/demo/globalConfigsWorkbenchDemo.js`
- `https://hcm-demo-assets.s3.ap-south-1.amazonaws.com/analytics/consoleAnalyticsDemo.js`

Third-party CSS/JS (pinned versions — worth noting for UI regressions):

- `@egovernments/digit-ui-css@2.0.0-dev-08`
- `@egovernments/digit-ui-components-css@2.0.0-dev-13`
- `@egovernments/digit-ui-health-css@1.0.44`
- `xlsx@0.18.5` (and an unpinned `xlsx` — both are requested)

App bundles: `runtime`, `react`, `digit-ui`, `main`, plus vendor chunks and
the lazy `campaign-manager.*.chunk.js` / `workbench.*.chunk.js`.

Analytics: Google Tag Manager `GTM-KHMZGGJ2`, GA4 `G-SWNFWJXDJM`.
GA `collect` calls returned **503** during capture — noise, not a blocker.

## 3. API sequence

### Before the form renders (unauthenticated)

| # | Call | Purpose |
|---|---|---|
| 1 | `POST /localization/messages/v1/_search?module=rainmaker-common,digit-ui,digit-tenants,rainmaker-demo&locale=en_DEMO&tenantId=demo` | i18n for the shell + login form |
| 2 | `POST /mdms-v2/v1/_search?tenantId=demo` | `tenant.tenants` master |
| 3 | `POST /localization/messages/v1/_search?module=digit-privacy-policy&locale=en_DEMO&tenantId=demo` | consent checkbox copy |

### On "Continue"

| # | Call | Purpose |
|---|---|---|
| 4 | `POST /user/oauth/token` | sign-in (form-encoded) |
| 5 | `POST /user/_search` | full profile by uuid |
| 6 | `POST /access/v1/actions/mdms/_get` | role → home cards / side nav |

`/user/_search` is called **twice** by the shell — a redundant duplicate, not
a functional issue.

### Contract details worth knowing

**`POST /user/oauth/token`** — `application/x-www-form-urlencoded`, *not* JSON.
Requires header `authorization: Basic ZWdvdi11c2VyLWNsaWVudDo=`
(base64 of `egov-user-client:`). Body: `username`, `password`, `grant_type=password`,
`scope=read`, `tenantId`, `userType`.
Returns `access_token`, `refresh_token`, `token_type=bearer`, `expires_in`,
and a `UserRequest` object the shell caches as the user context.

**`POST /access/v1/actions/mdms/_get`** — `RequestInfo.ts` **must be a number**.
Sending `null` or `""` returns HTTP 400 with a server-side
`NullPointerException` on `RequestInfo.getTs()`. `utils/request_info.py` sends
`0`, which satisfies it. Body also needs `actionMaster: "actions-test"`,
`enabled: true`, `roleCodes: [...]`, `tenantId`.

**Landing page** after login shows two cards: *Payment* (Setup Payment
Attributes) and *HCM Console* (Create Campaign, My Campaigns).

---

## 4. Test cases

Legend: **P** positive, **N** negative. All are automated unless noted.

### Pre-login bootstrap

| ID | Type | Case | Expected | Test |
|---|---|---|---|---|
| LOGIN-01 | P | i18n bundles resolve for the configured locale | 200; non-empty; every message's `locale` == `en_DEMO` | `test_localization_bootstrap_bundles` |
| LOGIN-02 | P | Required bundles carry content | `rainmaker-common` + `digit-ui` non-empty | `test_localization_covers_required_modules` |
| LOGIN-03 | P | Tenant master resolvable | 200; `tenant.tenants` contains `demo` | `test_tenant_master_is_resolvable` |
| LOGIN-04 | P | Privacy-policy copy available | 200; non-empty (else Continue stays disabled) | `test_privacy_policy_content_available` |

### Sign-in — happy path

| ID | Type | Case | Expected | Test |
|---|---|---|---|---|
| LOGIN-10 | P | Valid credentials | 200; `access_token` + `refresh_token`; `token_type=bearer`; `expires_in > 0` | `test_login_returns_access_token` |
| LOGIN-11 | P | Response carries user context | `UserRequest.uuid` set; `tenantId=demo`; `type=EMPLOYEE`; roles non-empty | `test_login_response_carries_user_context` |
| LOGIN-12 | P | Account holds required roles | all of `EXPECTED_LOGIN_ROLES` present (skips if unset) | `test_login_grants_expected_roles` |

### Sign-in — negative paths

| ID | Type | Case | Observed | Test |
|---|---|---|---|---|
| LOGIN-20 | N | Wrong password | 400 `invalid_request` / "Invalid login credentials" | `test_login_rejects_invalid_credentials` |
| LOGIN-21 | N | Unknown username | 400, same message | ″ |
| LOGIN-22 | N | Blank password | 400, same message | ″ |
| LOGIN-23 | N | Wrong tenantId | 400, same message | ″ |
| LOGIN-24 | N | `userType=CITIZEN` for an employee | 400, same message | ″ |
| LOGIN-25 | N | User enumeration | unknown user and wrong password must be **identical** in status *and* message | `test_login_does_not_enumerate_users` |
| LOGIN-26 | N | Missing OAuth client header | 401 "Full authentication is required" | `test_login_requires_oauth_client_header` |
| LOGIN-27 | N | `grant_type=client_credentials` | 401 `invalid_client` "Unauthorized grant type" | `test_login_rejects_unsupported_grant_type` |

No token is issued in any negative case — asserted explicitly.

### Post-login profile

| ID | Type | Case | Expected | Test |
|---|---|---|---|---|
| LOGIN-30 | P | Profile resolves by uuid | 200; exactly 1 user; uuid + tenant match | `test_user_search_returns_logged_in_profile` |
| LOGIN-31 | P | Roles consistent | `/user/_search` roles == login-response roles (guards permission drift) | `test_user_search_roles_match_login_response` |
| LOGIN-32 | N | Forged auth token | 401 | `test_user_search_rejects_invalid_token` |
| LOGIN-33 | N | Search with no criteria | 400 `InvalidUserSearchCriteriaException` — prevents dumping the user table | `test_user_search_requires_criteria` |

### Role-based actions

| ID | Type | Case | Expected | Test |
|---|---|---|---|---|
| LOGIN-40 | P | Actions returned for the account's roles | 200; non-empty (354 on hcm-demo) | `test_authorized_actions_returned_for_roles` |
| LOGIN-41 | P | Actions are usable | each has `id`, `tenantId`, and one of `name`/`url`/`displayName`/`navigationURL`/`path` | `test_authorized_actions_are_well_formed` |
| LOGIN-42 | N | Empty `roleCodes` | 400 `accesscontrol.0012` "Atleast One Role..." | `test_authorized_actions_requires_at_least_one_role` |
| LOGIN-43 | N | Unknown role | 200 with **zero** actions — fails closed | `test_unknown_role_grants_no_actions` |
| LOGIN-44 | N | Unknown `actionMaster` | 200/400 with zero actions — does not widen access | `test_unknown_action_master_grants_no_actions` |

---

## 5. Findings from this run

1. **`LOCALE` was wrong.** `.env` said `en_MZ`; this environment serves
   `en_DEMO`. Fixed.
2. **Two requested i18n bundles are empty.** The shell asks for
   `digit-tenants` and `rainmaker-demo`; both return 0 messages at
   `tenantId=demo` for every locale tried. Confirmed not a result truncation —
   querying each module alone still returns 0. Login is unaffected, so LOGIN-02
   asserts only the required modules and reports these. Worth raising with the
   platform team as a data gap.
3. **`/user/_search` is called twice** on login. Harmless duplication.
4. **`RequestInfo.ts` must be numeric** for the access-control service —
   a null/empty value produces a server-side NPE surfaced as a 400. Anyone
   hand-rolling this call will hit it.
5. **GA `collect` requests return 503.** Analytics only; ignore.
6. **`xlsx` is loaded twice** — once unpinned, once at `0.18.5`. A supply-chain
   and bundle-size smell rather than a functional bug.

## 6. Not covered

- The browser UI itself (field validation, the Privacy Policy checkbox gating
  the Continue button, "Forgot password?"). This suite is API-level.
- Token refresh via `refresh_token`, and logout / token invalidation.
- Rate limiting or lockout after repeated failed sign-ins — worth adding once
  the intended policy is known.
