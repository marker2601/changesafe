# ChangeSafe design QA

## Status

**Passed locally on 2026-08-10.** The Browser-plugin-first baseline confirmed the app identity, meaningful content, empty console, screenshot rendering, and keyboard field change on the isolated baseline origin. The final production bundle was then exercised by the committed Playwright acceptance suite and its replay screenshots were regenerated after the last web source change.

## Judge contract

- The field picker exposes the active allowlisted schema before **Analyze change** can enable. It shows the returned field name, native type, and nullability.
- Rename `cust_email` → `primary_email`, Remove `order_status`, and Change type `order_total` → `VARCHAR(320)` all use keyboard selection through the real combobox.
- Exact field routes name both endpoints. Endpoint-only routes disclose `intermediate column mapping not returned by DataHub`. Dataset-only routes disclose the missing endpoint instead of inventing a field.
- The risk result is the sum of the displayed deterministic factor ledger. Generated paths and exact bytes are operation- and field-specific.
- Seven generated files must pass 12 / 12 static checks. Warehouse validation is a separate optional proof and never inflates the static count.
- Approval is available only for a persisted policy pass. Required, timed-out, unsafe, stale, mismatched, or inconclusive warehouse evidence blocks it.
- Replay and disabled warehouse states say **Production rows not queried**. No public screenshot implies a Snowflake pass.

## Automated browser acceptance

`tests/e2e/competition-flow.spec.ts` proves:

- all three judge operations with real keyboard combobox selection;
- 1440 × 1024 and 430 × 932 page containment with no horizontal overflow;
- less than 1 px hero-height change before and after analysis;
- every Rename route button opens its evidence drawer from the keyboard, Escape closes it, and focus returns to the originating route;
- mobile keyboard route/drawer/focus return;
- reduced motion preserves the static directional arrow and removes the travelling light;
- case-insensitive rename collision and a typed missing field are blocked before submission;
- unsafe type aggregate evidence, warehouse timeout, required-not-run evidence, and approval policy remain fail-closed;
- explicit snapshot confirmation after a simulated live outage;
- refresh recovery during `validating_warehouse`, with approval unavailable until a passed result is persisted;
- terminal SSE EOF and lost approval response reconciliation;
- empty browser console-error and page-error arrays for the final operation, geometry, focus, motion, and terminal-stream flows.

Focused final result: **10 / 10 passed**. The updated golden workflow result is **5 / 5 passed**. Web component coverage is **20 files / 148 tests passed**.

## Final live DataHub evidence

The exact judge trio was rerun through normal Settings, the real HTTP API/orchestrator, and preview approval with external mutation and warehouse flags forced off.

| Operation | Field | Returned type | Upstream | Downstream | Score | Factor ledger |
| --- | --- | --- | ---: | ---: | ---: | --- |
| Rename | `cust_email` | `TEXT` | 6 | 25 | 85 | `base_rename` 25; `downstream_assets` 25; `executive_downstream` 15; `high_usage` 10; `cross_domain` 10 |
| Remove | `order_status` | `NUMBER` | 6 | 27 | 90 | `base_removal` 40; `downstream_assets` 25; `executive_downstream` 15; `cross_domain` 10 |
| Change type | `order_total` | `FLOAT` | 6 | 31 | 85 | `base_type_change` 35; `downstream_assets` 25; `executive_downstream` 15; `cross_domain` 10 |

Every result had `live` DataHub provenance, seven sealed artifacts, 12 / 12 static checks, a preview receipt, and warehouse status `not_run`. Schema discovery returned exactly 55 concrete unique fields.

**Production rows not queried.** Snowflake credentials were not supplied, so no live warehouse pass, counts, or screenshot is claimed.

## Final raster proof

The explicit capture run passed **1 / 1** and the four PNG files were opened at original resolution for visual inspection.

| File | Dimensions | Captured (America/Chicago) | Visible truth |
| --- | ---: | --- | --- |
| `docs/screenshots/changesafe-desktop-replay.png` | 1440 × 1024 | 2026-08-10 01:56:48.102 -05:00 | Recorded DataHub evidence; Rename `cust_email`; production rows not queried |
| `docs/screenshots/changesafe-desktop-proof.png` | 1440 × 1024 | 2026-08-10 01:56:48.544 -05:00 | Seven exact artifacts; 12 / 12; preview receipt; production rows not queried |
| `docs/screenshots/changesafe-mobile-replay.png` | 430 × 932 | 2026-08-10 01:56:50.103 -05:00 | Recorded `order_total` type-change lineage without horizontal clipping |
| `docs/screenshots/changesafe-mobile-proof.png` | 430 × 932 | 2026-08-10 01:56:50.552 -05:00 | 12 / 12; type-change scope; preview receipt; production rows not queried |

`changesafe-desktop-live-validation.png` and `changesafe-mobile-live-validation.png` were deliberately not created. Without passed Snowflake evidence, those filenames would imply a warehouse validation result that does not exist.

## Final temporary-origin proof

The release image was rebuilt after the final web change and exercised through an anonymous rotating tunnel. Public root, health, and capability endpoints returned 200. The browser discovered 55 live DataHub fields, blocked an unknown field even after blur, completed all three keyboard-selected judge operations, recovered the same run after refresh, approved a preview, downloaded the patch, and loaded three privacy-limited activity rows. Every operation showed seven artifacts, 12 / 12 static checks, warehouse `not_run`, and **Production rows not queried**. Page-level horizontal overflow, console errors, and page errors were all zero.

The rotating URL is recorded in the private task report rather than committed as a durable submission link.

## Remaining deployment boundary

The final shared origin is a temporary rotating QA tunnel only. Stable judge hosting requires the owner's hosting account or custom tunnel domain. Mutation flags remain false, and warehouse validation remains disabled until complete owner-controlled read-only Snowflake credentials and an allowlisted target relation are supplied.

No P0, P1, or P2 browser or raster defect remained in the completed local checks.
