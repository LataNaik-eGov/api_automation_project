# hcm-demo Environment Notes

Environment: `https://hcm-demo.digit.org`, tenant `demo`, hierarchy `MICROPLAN`,
locale `en_DEMO`. Recorded 2026-09-05, full-run figures from 2026-09-07.

## 1. Two blocked write endpoints account for most service-suite failures

Full run on 2026-09-07: **160 passed, 112 failed** out of 272.

| Suite | Pass | Fail |
|---|---|---|
| `tests/console` (7 files, BEDNET + MR-DN) | 70 | 0 |
| `tests/test_login_flow.py` | 24 | 0 |
| boundary / facility / individual / product / localization / hrms | 40 | 0 |
| household | 12 | 8 |
| mdms | 8 | 4 |
| project | 1 | 54 |
| referralmanagement | 3 | 24 |
| stock | 2 | 17 |
| pgr | 0 | 5 |

Grouped by the request that actually failed:

| Count | Endpoint | Status |
|---|---|---|
| 95 | `/project/v1/_create` | 401 not authorized |
| 8 | `/household/v1/_create` | 401 not authorized |
| 5 | `/pgr-services/v2/request/_create`, `/egov-hrms/employees/_create` | 400 |
| 4 | `/mdms-v2/v2/_create/...`, mdms searches | 401 / 400 |

**`/project/v1/_create` alone explains 95 of the 112 failures.** The project,
referralmanagement and stock suites each create a project as setup, so one
refused write cascades through all three. Household's 8 are the same shape on
its own create.

To run those suites, the account needs write permission on `/project/v1/_create`
and `/household/v1/_create`. That is an access-control change on the
environment, not a change in this repository. The remaining ~9 failures in pgr
and mdms are 400s with distinct causes and need separate triage.

### A diagnostic that does NOT work

`POST /access/v1/actions/mdms/_get` returns 354 actions for this account and
lists **no** `/household`, `/individual`, `/facility`, `/product` or `/project`
entries. That list is not the authorization gate: facility, individual, product
and localization writes all pass (33 tests) despite being absent from it.

Do not use the action list to predict which endpoints will authorize — it was
used that way once here and gave the wrong answer. Test the endpoint directly.

## 2. Boundary configuration is environment-specific

`.env` shipped with Mozambique values that do not exist in this hierarchy.
`utils/entity_factory.py` uses `BOUNDARY_CODE` as the locality on every
household and individual, so a stale code fails every create with
`Boundary code does not exist in db`.

The MICROPLAN hierarchy here is Tchad-based, and its levels are French:

```
PAYS -> PROVINCE -> DISTRICT -> CENTREDESANTÉ -> SPP/SFD -> VILLAGE/QUARTIER
```

There is no `COUNTRY` or `LOCALITY` level. Corrected:

| Variable | Was | Now |
|---|---|---|
| `BOUNDARY_TYPE` | `LOCALITY` | `PAYS` |
| `BOUNDARY_CODE` | `MICROPLAN_MO` | `MICROPLAN_TC_03_08_20_03_04_CENTRE_BAGA_SOLA_URBAIN` |
| `CONSOLE_ROOT_BOUNDARY_CODE` | `MICROPLAN_MO` | `MICROPLAN_TC` |
| `LOCALE` | `en_MZ` | `en_DEMO` |

`tests/test_boundary_service.py` also hardcoded `boundaryType="COUNTRY"`; it now
reads `BOUNDARY_TYPE` from config so the suite moves between environments.

The console suite was never affected — it resolves boundaries from the boundary
service rather than trusting `.env`.

## 3. Other environment quirks

- `HCM.APP_CONFIG` holds a single record stored under `tenantId=demo` but
  carrying `uniqueIdentifier`/`TENANT_ID` = `mz`; writing it returns 401.
- Localization modules `digit-tenants` and `rainmaker-demo` return zero
  messages for every locale tried.
- Google Analytics `collect` requests return 503. Cosmetic.
