# ChangeSafe: rename `customer_email` to `primary_email`

This change introduces primary_email as a compatibility alias for customer_email in analytics.dim_customers and retains the existing customer_email field. The migration follows the required two-phase compatibility strategy for a critical-risk rename with score 90, four downstream assets, an executive dashboard, PII governance, high usage, and cross-domain impact. Downstream consumers should migrate to primary_email during the 30-day deprecation period; removal of customer_email requires a separate approved phase.

## Deterministic risk: 90/100 — Critical

- **+25** Column rename
- **+20** 4 downstream assets
- **+15** Dashboard or executive report downstream
- **+10** Governed, confidential, or PII field
- **+10** High query usage
- **+10** Cross-domain impact

## Impact

4 downstream assets across 4 domains were found in DataHub.

## Validation

Publication remains blocked until SQL, YAML, compatibility, path, rollback, and manifest checks pass.
