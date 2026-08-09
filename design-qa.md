# ChangeSafe design QA

Reference: `docs/design/changesafe-judge-command-center-v1.png`
Implementation state: official `showcase-ecommerce` recorded evidence, preview completed
Primary comparison viewport: 1440 × 1024 at device scale 1

## Visual comparison

The reference and current implementation were opened together for direct visual comparison. The implementation retains the reference's dark evidence-command-center composition: a strong stable product statement, three primary evidence zones, six impact findings, a dependency-centered canvas, a persisted seven-step process, and five linked decision gates.

Intentional truthfulness differences:

- The primary facts say `Recorded DataHub evidence` and `Preview only`; details disclose the snapshot replay and checksum without presenting it as a live catalog query.
- Official dataset entity names replace illustrative entities from the concept image.
- Generic DataHub asset icons replace unverified vendor logos.
- The dependency view uses accessible interactive asset cards and directional moving lineage signals instead of decorative curved connectors.
- The deterministic risk score and generated artifact proof remain available below the primary command view.

## Findings and resolutions

- P1 — The hero changed size after analysis, making the page feel like a template swap. Resolved by keeping one stable hero in empty and completed states.
- P1 — Tablet layout compressed three dense columns. Resolved by stacking request/impact, dependency map, and process in reading order at 980 px and below.
- P1 — Impact cards looked like preselected user inputs. Resolved by rendering noninteractive evidence findings with a separate **Trace supporting evidence** control.
- P1 — The dependency graph looked like a static inventory. Resolved with two directional animated lineage rails, evidence filtering, and reduced-motion support.
- P2 — Fast replay completion appeared pre-timed. Resolved by showing persisted event sequence numbers, relative server timestamps, and measured total elapsed time.
- P2 — Generated files lacked context, and the removal guard looked cryptic. Resolved with purpose/failure explanations for every artifact and comments explaining the compile-time `where false` guard.
- P2 — Starting a new analysis retained the prior impact trace. Resolved by clearing the evidence filter and covering the reset with a component regression test.
- P2 — The mobile proof capture could begin from a restored scroll position. Resolved by reloading the durable run, scrolling to zero, verifying the header and hero coordinates, and capturing one non-stitched viewport frame.

## Interaction and responsive QA

- Isolated credential-free QA used the replay backend on port 8123 and the web app on port 5173; no private integration credentials were loaded.
- Desktop and responsive layouts were inspected at 1440 × 1024, 1280 × 900, 980 × 900, and 430 × 932.
- Rename, remove, and type-change drafts produced operation-specific request copy, impact language, risk, migration artifacts, and validation evidence.
- Desktop golden flow: six impact findings, seven process steps, seven artifacts, 12/12 blocking checks, evidence tracing, dependency drawers, and preview authorization verified.
- At 980 px the command center stacks in the intended reading order and the lineage rails rotate vertically.
- Phone flow has no horizontal overflow; tested controls meet a 44 px minimum target, and the recorded-evidence facts, graph, artifact tabs, validation, and approval remain usable.
- The preview receipt was verified as `NOT WRITTEN — SNAPSHOT MODE` with `No external systems were changed`.
- Browser console: no application warnings or errors during the completed golden flow.

No unresolved P0, P1, or P2 findings remain.

final result: passed
