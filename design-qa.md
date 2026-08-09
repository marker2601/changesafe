# ChangeSafe design QA

## Status

**Passed on 2026-08-09.** The final implementation was inspected in the selected in-app Browser after the backend identity-binding and verifier reviews were complete. The four checked-in screenshots were then regenerated from that same production web build and opened at original resolution for final visual inspection.

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
| Non-email `order_total` replay | 430 × 932 | A returned `order_total` schema option, an exact `order_details.order_total → ORDER_DETAILS.order_total` direct route, 75/High, 12/12 blocking checks, and horizontal containment of the picker and dependency map | Field-specific dependency map, then receipt area |

The final explicit capture run passed on 2026-08-09. The capture command keeps `fullPage: false` and writes only these deliberate frames:

- `docs/screenshots/changesafe-desktop-replay.png`
- `docs/screenshots/changesafe-desktop-proof.png`
- `docs/screenshots/changesafe-mobile-replay.png`
- `docs/screenshots/changesafe-mobile-proof.png`

## Final observed evidence

- Recorded schema discovery returned exactly **55 fields**, including `cust_email`, `order_total`, and `order_status`, with checksum `02ef4be4a1a31759c841996456b533126633c35aefe7d69c1a65abafa5816834`.
- Pointer selection of `order_total` and keyboard selection of `order_status` both committed the returned field, closed the combobox, and updated the request before analysis.
- The three completed recorded runs were evidence-specific: `cust_email` was **85 / Critical** with 25 downstream dependencies; `order_total` was **75 / High** with 31; and `order_status` was **75 / High** with 27. Both non-email runs had no `cust_email as primary_email` artifact leak and showed no field-scoped personal-data classification.
- Direct, endpoint-only multi-hop, and dataset-level relationships all appeared together. The exact direct routes named both fields; incomplete routes displayed the corresponding DataHub limitation instead of inventing a column.
- The evidence drawer exposed source and destination fields, full URNs, precision, retrieval time, recorded checksum, and the configured DataHub link. Its full-screen backdrop covered background controls; Escape closed it and returned focus to the originating route.
- The hero measured **403.83 px** before and after analysis at 1440 px (0 px change). Page containment measured **1425 / 1425** at 1440 px, **1265 / 1265** at 1280 px, and **415 / 415** at the 430 px phone viewport (`clientWidth / scrollWidth`).
- AUTO mode was exercised with Live DataHub deliberately unavailable. Analyze stayed disabled until the reviewer explicitly chose recorded fields; analysis then paused at `Live DataHub is unavailable` and completed only after `Continue with labeled snapshot` was confirmed. The final provenance read `Recorded evidence after live fallback`.
- Standard motion showed the directional travelling light. A reduced-motion browser regression confirms the exact route and static arrow remain visible while `.lineage-flow-light` is `display: none`.
- The final in-app Browser console log was empty. The generated package displayed seven exact artifacts, 12 / 12 blocking checks, and a non-mutating `Preview ready` receipt.

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
| Initial schema | Loaded 55-field recorded schema; keyboard and pointer selection work | Passed |
| Multi-field replay | `cust_email` 85/Critical; `order_total` 75/High; `order_status` 75/High, with distinct fields/routes/artifacts | Passed |
| Precision disclosure | Exact, endpoint-only, and dataset-level samples each show the correct limitation | Passed |
| Evidence drawer | Opens from a route, exposes returned endpoint fields/path/provenance, blocks background interaction, closes and restores focus | Passed |
| Responsive containment | 1440 px, 1280 px, and 430 px have no page-level horizontal overflow | Passed |
| Motion and health | Reduced-motion equivalent preserves the route without the travelling light; final console log is empty | Passed |
| Recorded fallback | Live failure is explicit and recorded evidence requires two deliberate confirmations | Passed |
| Final raster proof | All four checked-in PNGs depict the final field-driven routes and compatibility package without cropped panels | Passed |

No P0, P1, or P2 visual defect remained after the final recheck.
