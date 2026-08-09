# ChangeSafe design QA

## Status

**In progress — final in-app Browser review and checked-in screenshot refresh are deliberately pending.** The capture test has been updated and exercised against a temporary output directory; it must not be treated as final visual sign-off. The controller will perform the final in-app Browser inspection after the complete implementation and verifier review are stable, then authorize the four checked-in PNGs.

## What the final review must prove

- The field picker loads the active allowlisted schema before **Analyze change** is enabled. It shows a returned field name, native type, and nullability; it is not a static email list.
- `cust_email`, `order_total`, and `order_status` produce their own request-bound context. The final reviewer must confirm that a non-email run does not show copied `cust_email` governance or route text.
- Exact field routes visibly name both source and destination fields. Endpoint-only routes disclose `intermediate column mapping not returned by DataHub`; dataset-only routes disclose the missing endpoint field instead of inventing one.
- The graph, evidence drawer, and accessible list use matching directional route language. A DataHub link appears only when a safe catalog origin has been configured.
- The desktop layouts at 1440 px and 1280 px, plus the 430 px phone layout, have no page-level horizontal overflow, cropped controls, or obscured drawers. The code viewer may retain its own deliberate horizontal scroll.
- Moving lineage signals communicate direction without claiming an unknown intermediate mapping; `prefers-reduced-motion` keeps the relationship visible without the continuous motion.

## Automated capture guard prepared

`tests/e2e/capture-screenshots.spec.ts` now performs these checks before writing a proof image:

| State | Viewport | Evidence asserted | Capture anchor |
| --- | ---: | --- | --- |
| Default `cust_email` replay | 1440 × 1024 | A returned `cust_email` schema option, an exact `order_details.cust_email → ORDER_DETAILS.cust_email` direct route, 12/12 blocking checks, and horizontal containment of the picker and dependency map | Top overview, then artifact/receipt area |
| Non-email `order_total` replay | 430 × 932 | A returned `order_total` schema option, an exact `order_details.order_total → ORDER_DETAILS.order_total` direct route, 75/High, 12/12 blocking checks, and horizontal containment of the picker and dependency map | Top overview, then receipt area |

The explicit temporary capture run passed on 2026-08-09. It wrote outside the repository so the checked-in proof images remain unchanged until the final source review is complete. The final capture command keeps `fullPage: false` and writes only these deliberate frames:

- `docs/screenshots/changesafe-desktop-replay.png`
- `docs/screenshots/changesafe-desktop-proof.png`
- `docs/screenshots/changesafe-mobile-replay.png`
- `docs/screenshots/changesafe-mobile-proof.png`

## Evidence vocabulary used in the UI

| Precision | What the reviewer can conclude | Required limitation copy when incomplete |
| --- | --- | --- |
| Exact field route | DataHub returned source and destination field endpoints. | None beyond hop/evidence details. |
| Endpoint-only field route | DataHub returned a known endpoint and asset path, but not every intermediate column mapping. | `intermediate column mapping not returned by DataHub` |
| Dataset-level relationship | DataHub returned the related asset but not the relevant endpoint field. | `Dataset-level relationship; source/destination field not returned by DataHub` |

These labels are evidence precision, not severity. A field name that appears similar on two assets never fills a missing column mapping.

## Final-browser checklist

| Check | Required observation | Status |
| --- | --- | --- |
| Initial schema | Loaded 55-field recorded schema; keyboard and pointer selection work | Pending controller review |
| Multi-field replay | `cust_email` 85/Critical; `order_total` 75/High; `order_status` 75/High, with distinct fields/routes/artifacts | Pending controller review |
| Precision disclosure | Exact, endpoint-only, and dataset-level samples each show the correct limitation | Pending controller review |
| Evidence drawer | Opens from a route, exposes returned endpoint fields/path/provenance, closes and restores focus | Pending controller review |
| Responsive containment | 1440 px, 1280 px, and 430 px have no page-level horizontal overflow | Pending controller review |
| Motion and health | Reduced-motion equivalent is visible; no relevant console or network errors | Pending controller review |
| Final raster proof | All four checked-in PNGs depict the final dropdown/route language without cropped panels | Pending controller authorization |

No final P0/P1/P2 conclusion is claimed until every pending item is observed in the selected in-app Browser and the refreshed PNGs are inspected.
