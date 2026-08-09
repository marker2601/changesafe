# ChangeSafe design QA

Reference: `docs/design/changesafe-judge-command-center-v1.png`
Implementation state: official `showcase-ecommerce` replay, awaiting approval
Comparison viewport: 1487 × 1058 at device scale 1

## Visual comparison

The reference and implementation were inspected together at the same viewport and workflow state. The implementation retains the reference's dark evidence-command-center composition: a strong product statement, three primary evidence zones, six impact categories, a dependency-centered canvas, a persisted seven-step process, and five linked decision gates.

Intentional truthfulness differences:

- Replay is labeled `Snapshot replay`; the interface never calls recorded evidence live.
- Official dataset entity names replace illustrative entities from the concept image.
- Generic DataHub asset icons replace unverified vendor logos.
- The dependency view uses accessible interactive asset cards instead of decorative curved connectors.
- The deterministic risk score and generated artifact proof remain available below the primary command view.

## Findings and resolutions

- P1 — The analyzed-state headline exceeded its grid column and approached the replay-context card. Resolved by constraining compact desktop typography and verifying it at both 1440 and 1487 pixels.
- P1 — The command gates sat below the first desktop view, weakening the command-center hierarchy. Resolved by compacting only the analyzed desktop hero, impact cards, and risk ledger while retaining readable text and mobile touch targets.
- P1 — The five command gates looked informational rather than actionable. Resolved by linking Observe, Understand, Prepare, Prove, and Authorize to their corresponding evidence sections and covering all links with tests.
- P2 — Recorded replay lineage was labeled as live evidence. Resolved with provenance-aware `Recorded dependency evidence` copy.
- P2 — A missing publication timestamp appeared as the unexplained value `07`. Resolved with the explicit fallback `Step 07`.
- P2 — Full-page mobile capture could preserve a scrolled sticky-header state. Resolved by restoring scroll position before both public proof captures.

## Interaction and responsive QA

- Desktop golden flow: six impact categories, seven process steps, seven artifacts, 12/12 blocking checks, and preview authorization verified.
- Phone flow: no horizontal overflow at 430 × 932; touch targets, dependency stacking, artifact tabs, validation, and approval remain usable.
- Core controls verified: change inputs, analysis, asset evidence cards, impact evidence cards, validation details, artifact tabs/copy, command-gate links, authorization, download, new analysis, and owner activity.
- Browser console: no application warnings or errors during the golden flow.

No unresolved P0, P1, or P2 findings remain.

final result: passed
