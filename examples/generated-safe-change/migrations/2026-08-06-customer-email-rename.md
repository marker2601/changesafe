# Migration: rename `customer_email` to `primary_email`

**Owner:** Customer Analytics  
**Risk:** 90/100 — Critical  
**Deprecation window:** through 2026-09-05

## Phase one

Keep `customer_email` and introduce `primary_email` during phase one. Update the dbt contract and enforce the operation-specific compatibility invariant.

`customer_email` remains available for a 30-day deprecation window and is removed only after every recorded downstream consumer migrates.

## Downstream evidence

- `customer_360` — Analytics — `urn:li:dataset:(urn:li:dataPlatform:snowflake,analytics.customer_360,PROD)`
- `campaign_audiences` — Marketing — `urn:li:dataset:(urn:li:dataPlatform:snowflake,marketing.campaign_audiences,PROD)`
- `customer_contact_queue` — Support — `urn:li:dataset:(urn:li:dataPlatform:snowflake,support.customer_contact_queue,PROD)`
- `customer_retention_dashboard` — Executive Reporting — `urn:li:dashboard:(looker,customer_retention_dashboard)`

## Exit criteria

All 4 recorded consumers must complete migration, the operation-specific compatibility test must remain green, and the accountable owner must approve phase two.
