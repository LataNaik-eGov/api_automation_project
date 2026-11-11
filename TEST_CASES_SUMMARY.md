# API Automation Test Cases Summary

## Overview

| Metric | Count |
|--------|-------|
| Total Services | 17 |
| Total Test Cases | 107 |
| Positive Tests | 72 |
| Negative Tests | 35 |

## Test Coverage by Operation

| Operation | Count |
|-----------|-------|
| Create | 33 |
| Search | 38 |
| Update | 17 |
| Delete | 13 |
| Upsert | 2 |
| Workflow | 1 |
| Other | 3 |

---

## Detailed Test Cases by Service

### 1. Boundary Service (2 tests)
| Test Case | Type | Operation |
|-----------|------|-----------|
| test_search_boundary | Positive | Search |
| test_search_boundary_with_invalid_tenant_id | Negative | Search |

### 2. Facility Service (6 tests)
| Test Case | Type | Operation |
|-----------|------|-----------|
| test_create_facility | Positive | Create |
| test_search_facility | Positive | Search |
| test_update_facility | Positive | Update |
| test_delete_facility | Positive | Delete |
| test_create_facility_with_invalid_tenant_id | Negative | Create |
| test_search_facility_with_invalid_tenant_id | Negative | Search |

### 3. Household Service (12 tests)
| Test Case | Type | Operation |
|-----------|------|-----------|
| test_create_household | Positive | Create |
| test_create_householdMember | Positive | Create |
| test_search_household | Positive | Search |
| test_search_householdMember_by_id | Positive | Search |
| test_update_household | Positive | Update |
| test_update_household_member | Positive | Update |
| test_delete_household | Positive | Delete |
| test_delete_household_member | Positive | Delete |
| test_create_householdMember_without_householdId | Negative | Create |
| test_create_householdMember_without_individualId | Negative | Create |
| test_create_household_with_invalid_tenant_id | Negative | Create |
| test_create_householdMember_with_invalid_tenant_id | Negative | Create |
| test_search_household_with_invalid_tenant_id | Negative | Search |
| test_search_householdMember_with_invalid_tenant_id | Negative | Search |

### 4. Individual Service (6 tests)
| Test Case | Type | Operation |
|-----------|------|-----------|
| test_create_individual | Positive | Create |
| test_search_individual | Positive | Search |
| test_update_individual | Positive | Update |
| test_delete_individual | Positive | Delete |
| test_create_individual_with_invalid_tenant_id | Negative | Create |
| test_search_individual_with_invalid_tenant_id | Negative | Search |

### 5. HRMS Service (5 tests)
| Test Case | Type | Operation |
|-----------|------|-----------|
| test_create_employee | Positive | Create |
| test_search_employee | Positive | Search |
| test_update_employee | Positive | Update |
| test_create_hrms_with_invalid_tenant_id | Negative | Create |
| test_search_employee_with_invalid_tenant_id | Negative | Search |

### 6. Localization Service (4 tests)
| Test Case | Type | Operation |
|-----------|------|-----------|
| test_upsert_localization | Positive | Upsert |
| test_search_localization | Positive | Search |
| test_upsert_localization_with_invalid_tenant_id | Negative | Upsert |
| test_search_localization_with_invalid_tenant_id | Positive | Search |

### 7. MDMS Service (12 tests)
| Test Case | Type | Operation |
|-----------|------|-----------|
| test_project_types | Positive | Search |
| test_roles | Positive | Search |
| test_app_config | Positive | Search |
| test_backend_interface | Positive | Search |
| test_state_info | Positive | Search |
| test_create_schema_definition | Positive | Create |
| test_search_schema_definition | Positive | Search |
| test_add_mdms_data | Positive | Create |
| test_search_added_mdms_data | Positive | Search |
| test_create_schema_definition_with_invalid_tenant_id | Negative | Create |
| test_search_schema_definition_with_invalid_tenant_id | Negative | Search |
| test_search_mdms_data_with_invalid_tenant_id | Negative | Search |

### 8. PGR Service (5 tests)
| Test Case | Type | Operation |
|-----------|------|-----------|
| test_create_complaint | Positive | Create |
| test_resolve_complaint | Positive | Update |
| test_search_complaint | Positive | Search |
| test_assign_complaint | Positive | Update |
| test_complete_pgr_workflow | Positive | Workflow |

### 9. Product Service (11 tests)
| Test Case | Type | Operation |
|-----------|------|-----------|
| test_create_product | Positive | Create |
| test_create_product_variant | Positive | Create |
| test_search_product | Positive | Search |
| test_search_product_variant | Positive | Search |
| test_update_product | Positive | Update |
| test_update_product_variant | Positive | Update |
| test_create_product_with_invalid_tenant_id | Negative | Create |
| test_create_product_variant_with_invalid_tenant_id | Negative | Create |
| test_create_product_variant_without_productId | Negative | Create |
| test_search_product_with_invalid_tenant_id | Negative | Search |
| test_search_product_variant_with_invalid_tenant_id | Negative | Search |

### 10. Project Service (6 tests)
| Test Case | Type | Operation |
|-----------|------|-----------|
| test_create_project | Positive | Create |
| test_search_project | Positive | Search |
| test_update_project | Positive | Update |
| test_create_project_with_invalid_tenant_id | Negative | Create |
| test_search_project_with_invalid_tenant_id | Negative | Search |

### 11. Project Resource (6 tests)
| Test Case | Type | Operation |
|-----------|------|-----------|
| test_create_project_resource | Positive | Create |
| test_search_project_resource | Positive | Search |
| test_update_project_resource | Positive | Update |
| test_delete_project_resource | Positive | Delete |
| test_create_project_resource_with_invalid_tenant_id | Negative | Create |
| test_search_project_resource_with_invalid_tenant_id | Negative | Search |

### 12. Project Staff (6 tests)
| Test Case | Type | Operation |
|-----------|------|-----------|
| test_create_project_staff | Positive | Create |
| test_search_project_staff | Positive | Search |
| test_update_project_staff | Positive | Update |
| test_delete_project_staff | Positive | Delete |
| test_create_project_staff_with_invalid_tenant_id | Negative | Create |
| test_search_project_staff_with_invalid_tenant_id | Negative | Search |

### 13. Project Facility (6 tests)
| Test Case | Type | Operation |
|-----------|------|-----------|
| test_create_project_facility | Positive | Create |
| test_search_project_facility | Positive | Search |
| test_update_project_facility | Positive | Update |
| test_delete_project_facility | Positive | Delete |
| test_create_project_facility_with_invalid_tenant_id | Negative | Create |
| test_search_project_facility_with_invalid_tenant_id | Negative | Search |

### 14. Project Beneficiary (6 tests)
| Test Case | Type | Operation |
|-----------|------|-----------|
| test_create_project_beneficiary | Positive | Create |
| test_search_project_beneficiary | Positive | Search |
| test_update_project_beneficiary | Positive | Update |
| test_delete_project_beneficiary | Positive | Delete |
| test_create_project_beneficiary_with_invalid_tenant_id | Negative | Create |
| test_search_project_beneficiary_with_invalid_tenant_id | Negative | Search |

### 15. Project Task (6 tests)
| Test Case | Type | Operation |
|-----------|------|-----------|
| test_create_project_task | Positive | Create |
| test_search_project_task | Positive | Search |
| test_update_project_task | Positive | Update |
| test_delete_project_task | Positive | Delete |
| test_create_project_task_with_invalid_tenant_id | Negative | Create |
| test_search_project_task_with_invalid_tenant_id | Negative | Search |

### 16. Referral Management Service (12 tests)

#### Referral (6 tests)
| Test Case | Type | Operation |
|-----------|------|-----------|
| test_create_referral | Positive | Create |
| test_search_referral | Positive | Search |
| test_update_referral | Positive | Update |
| test_delete_referral | Positive | Delete |
| test_create_referral_with_invalid_tenant_id | Negative | Create |
| test_search_referral_with_invalid_tenant_id | Negative | Search |

#### HF Referral (6 tests)
| Test Case | Type | Operation |
|-----------|------|-----------|
| test_create_hf_referral | Positive | Create |
| test_search_hf_referral | Positive | Search |
| test_update_hf_referral | Positive | Update |
| test_delete_hf_referral | Positive | Delete |
| test_create_hf_referral_with_invalid_tenant_id | Negative | Create |
| test_search_hf_referral_with_invalid_tenant_id | Negative | Search |

### 17. Stock Service (18 tests)

#### Stock Transactions (13 tests)
| Test Case | Type | Operation |
|-----------|------|-----------|
| test_create_stock_received_between_facilities | Positive | Create |
| test_create_stock_dispatched_between_facilities | Positive | Create |
| test_create_stock_received_from_staff_to_warehouse | Positive | Create |
| test_create_stock_dispatched_from_staff_to_warehouse | Positive | Create |
| test_create_stock_received_from_warehouse_to_staff | Positive | Create |
| test_create_stock_dispatched_from_warehouse_to_staff | Positive | Create |
| test_create_stock_received_between_staff | Positive | Create |
| test_create_stock_dispatched_between_staff | Positive | Create |
| test_search_stock | Positive | Search |
| test_update_stock | Positive | Update |
| test_delete_stock | Positive | Delete |
| test_create_stock_with_invalid_tenant_id | Negative | Create |
| test_search_stock_with_invalid_tenant_id | Negative | Search |

#### Stock Reconciliation (5 tests)
| Test Case | Type | Operation |
|-----------|------|-----------|
| test_create_stock_reconciliation | Positive | Create |
| test_search_stock_reconciliation | Positive | Search |
| test_update_stock_reconciliation | Positive | Update |
| test_delete_stock_reconciliation | Positive | Delete |
| test_create_stock_reconciliation_with_invalid_tenant_id | Negative | Create |
| test_search_stock_reconciliation_with_invalid_tenant_id | Negative | Search |

---

## Test Execution Commands

```bash
# Run all tests
pytest tests/ -v

# Run only positive tests
pytest tests/ -v -m positive

# Run only negative tests
pytest tests/ -v -m negative

# Run tests for a specific service
pytest tests/test_facility_service.py -v
pytest tests/test_household_service.py -v
pytest tests/test_individual_service.py -v
pytest tests/test_project_service.py -v
pytest tests/test_stock_service.py -v

# Run tests with HTML report
pytest tests/ -v --html=reports/report.html
```

---

*Generated on: 2026-01-21*
