# Migration: `customer_email` to `primary_email`

**Owner:** Customer Analytics  
**Risk:** 90/100 — Critical  
**Deprecation window:** through 2026-09-05

## Phase one

Introduce `primary_email` without removing `customer_email`, update the dbt contract, and enforce value compatibility.

`customer_email` remains available for a 30-day deprecation window and is removed only after every recorded downstream consumer migrates.

## Downstream evidence

- `customer_360` — Analytics — `urn:li:dataset:(urn:li:dataPlatform:snowflake,analytics.customer_360,PROD)`
- `campaign_audiences` — Marketing — `urn:li:dataset:(urn:li:dataPlatform:snowflake,marketing.campaign_audiences,PROD)`
- `customer_contact_queue` — Support — `urn:li:dataset:(urn:li:dataPlatform:snowflake,support.customer_contact_queue,PROD)`
- `customer_retention_dashboard` — Executive Reporting — `urn:li:dashboard:(looker,customer_retention_dashboard)`

## Exit criteria

All four recorded consumers must use the preferred field, the compatibility test must remain green, and the accountable owner must approve phase two.
