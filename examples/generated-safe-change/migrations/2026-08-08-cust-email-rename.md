# Migration: rename `cust_email` to `primary_email`

**Owner:** Ian Chen  
**Risk:** 80/100 — Critical  
**Deprecation window:** through 2026-09-07

## Phase one

Keep `cust_email` and introduce `primary_email` during phase one. Update the dbt contract and enforce the operation-specific compatibility invariant.

`cust_email` remains available for a 30-day deprecation window and is removed only after every recorded downstream consumer migrates.

## Downstream evidence

- `ORDER_DETAILS` — Ecommerce Operations — `urn:li:dataset:(urn:li:dataPlatform:snowflake,b2fd91.order_entry_db.analytics.order_details,PROD)`
- `ORDER_DETAILS_REPLICA` — Unassigned — `urn:li:dataset:(urn:li:dataPlatform:snowflake,b2fd91.order_entry_db.analytics.order_details_replica,PROD)`
- `Customer Analytics Measures` — Unassigned — `urn:li:dataset:(urn:li:dataPlatform:powerbi,b2fd91.datahub_order_entries.Customer_Analytics_Measures,PROD)`
- `Geographic Measures` — Unassigned — `urn:li:dataset:(urn:li:dataPlatform:powerbi,b2fd91.datahub_order_entries.Geographic_Measures,PROD)`
- `Essential KPI Measures` — Unassigned — `urn:li:dataset:(urn:li:dataPlatform:powerbi,b2fd91.datahub_order_entries.Essential_KPI_Measures,PROD)`
- `order_details` — Data Platform Team — `urn:li:dataset:(urn:li:dataPlatform:looker,b2fd91.order-entry-looker.view.order_details,PROD)`
- `Order Details` — Data Platform Team — `urn:li:dataset:(urn:li:dataPlatform:looker,b2fd91.order-entry.explore.order_details,PROD)`

## Exit criteria

All 7 recorded consumers must complete migration, the operation-specific compatibility test must remain green, and the accountable owner must approve phase two.
