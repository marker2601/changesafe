# ChangeSafe: rename `cust_email` to `primary_email`

This phase-one compatibility layer preserves the existing interface and includes deterministic validation, deprecation evidence, and rollback steps.

## Phase-one compatibility relation

The governed base model remains unchanged in phase one: `order_details`. This package adds compatibility relation `order_details__changesafe`. Downstream owners must switch to `order_details__changesafe` and migrate to `primary_email`.

## Deterministic risk: 85/100 — Critical

- **+25** Column rename
- **+25** 25 downstream assets
- **+15** Dashboard or executive report downstream
- **+10** High query usage
- **+10** Cross-domain impact

## Impact

25 downstream assets across 3 domains were found in DataHub.

## Validation

Publication remains blocked until SQL, YAML, compatibility, path, rollback, and manifest checks pass.
