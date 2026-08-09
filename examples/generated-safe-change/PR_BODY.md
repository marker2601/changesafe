# ChangeSafe: rename `cust_email` to `primary_email`

This phase-one migration preserves the existing interface and includes deterministic validation, deprecation evidence, and rollback steps.

## Deterministic risk: 80/100 — Critical

- **+25** Column rename
- **+25** 7 downstream assets
- **+10** Governed, confidential, or PII field
- **+10** High query usage
- **+10** Cross-domain impact

## Impact

7 downstream assets across 2 domains were found in DataHub.

## Validation

Publication remains blocked until SQL, YAML, compatibility, path, rollback, and manifest checks pass.
