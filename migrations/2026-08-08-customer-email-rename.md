# Migration: rename `customer_email` to `primary_email`

**Owner:** Customer Analytics  
**Risk:** 90/100 — Critical  
**Deprecation window:** through 2026-09-07

## Phase one

At source commit 4533489e14d4b63e598c17b77a1906abcb9e9d2a, add primary_email as a STRING-compatible alias of customer_email in analytics.dim_customers while retaining customer_email. Coordinate migration of customer_360, campaign_audiences, customer_contact_queue, and customer_retention_dashboard to primary_email. Maintain both fields for at least 30 days before separately approving any removal of customer_email.

customer_email is deprecated but remains available during the required 30-day compatibility period. Consumers must migrate to primary_email before customer_email is removed in a later approved phase. The field remains PII-governed under urn:li:tag:PII and associated with urn:li:glossaryTerm:CustomerEmail.

## Downstream evidence

- `customer_360` — Analytics — `urn:li:dataset:(urn:li:dataPlatform:snowflake,analytics.customer_360,PROD)`
- `campaign_audiences` — Marketing — `urn:li:dataset:(urn:li:dataPlatform:snowflake,marketing.campaign_audiences,PROD)`
- `customer_contact_queue` — Support — `urn:li:dataset:(urn:li:dataPlatform:snowflake,support.customer_contact_queue,PROD)`
- `customer_retention_dashboard` — Executive Reporting — `urn:li:dashboard:(looker,customer_retention_dashboard)`

## Exit criteria

All 4 recorded consumers must complete migration, the operation-specific compatibility test must remain green, and the accountable owner must approve phase two.
