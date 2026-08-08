# ChangeSafe: migrate `customer_email` to `primary_email`

This phase-one migration preserves the existing interface, adds the new contracted field, and includes deterministic validation and rollback evidence.

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
