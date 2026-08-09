# ChangeSafe interface design system

The selected visual reference is `docs/design/changesafe-judge-command-center-v1.png`. The implementation keeps its dark operations-console character while using semantic HTML, real application data, and Lucide icons instead of decorative mock controls.

## Product message

The first viewport must answer four questions without technical knowledge:

1. What is changing? `order_details.cust_email` → `primary_email`.
2. What relies on it? Recorded Snowflake, Power BI, and Looker assets.
3. What kind of harm is supported by evidence? Six labeled impact categories.
4. What happens next? A seven-stage live process that stops for an accountable owner.

The primary headline is **Change data safely, with every dependency in view.** The rejected internal phrase is not used in judge-facing copy. Provenance, inference, and publication status are always explicit.

## Tokens

- Canvas: deep navy `#020b13`; primary surface `#071720`; strong surface `#0a2029`.
- Rules: `#24434d`; emphasized rules: `#3b6871`.
- Primary text: warm ivory `#f5eddd`; muted `#93a8ae`; quiet `#6f858c`.
- Verified/context accent: electric teal `#3ee4d0`; active publication: lime `#d8ef22`.
- Caution: amber `#f3a541`; failure: coral `#ff665f`; informational: blue `#63a8ff`.
- Code surface: `#020910`.
- Spacing follows a compact 4/8 px rhythm suited to evidence-dense operational work.
- Corners stay restrained at 3–10 px. No gradients are used. Shadows are reserved for focused evidence and owner drawers.

## Typography and iconography

- UI and body: Aptos/Segoe UI/Inter-compatible system sans.
- Hero: condensed system display face, uppercase, tightly tracked.
- Code/evidence: `ui-monospace`, Cascadia Code, or Consolas.
- Labels are 7–11 px uppercase only for operational chrome; explanatory copy remains sentence case.
- Icons come from Lucide, pair with text for state, and never carry meaning through color alone.

## Component families

- Sticky product header with truthful provenance, publication mode, and optional private owner activity.
- Scenario request rail with locked official datapack facts and an explicit schema transition.
- Six evidence-led impact cards with severity, confidence, and optional qualifiers.
- Dependency graph with upstream, governed target, recorded consumers, direct/multi-hop labels, accessible fallback list, and evidence drawer.
- Seven-step process rail derived from persisted backend states, not timers.
- Five-stage command rail summarizing context, impact, artifacts, verification, and authorization.
- Seven-file artifact explorer with exact bytes and hashes.
- Twelve-check validation panel plus owner-gated approval/receipt panel.
- Privacy-limited owner activity drawer protected by the server admin token.

## State rules

- `snapshot` and `live` evidence use different visible labels.
- Live reads with disabled sinks say **Preview only / publication disabled**.
- A restored durable publishing run remains labeled live even if startup configuration changed.
- A failed context load is **Interrupted**, never **Complete**.
- Inferred impact evidence is labeled. Missing evidence lowers confidence instead of creating a claim.
- Replay approval says **NOT WRITTEN — SNAPSHOT MODE**.
- Non-retryable publication failures disable automated retry and call for operator action.

## Responsive model

Desktop uses three command-center columns: proposal/impact, evidence graph, and process. The command rail and delivery workspace follow below. At tablet widths the process becomes a horizontal sequence and the delivery workspace stacks. At phone widths every region becomes a single column, graph arrows rotate into flow direction, code scrolls inside its own frame, owner/evidence drawers become full-width, and the page must have no horizontal overflow.

## Accessibility

- Core nodes, impact cards, tabs, approval, fallback, and owner controls are native buttons/links.
- Focus rings are high contrast and not removed.
- Dialogs expose names, modal semantics, and labeled close controls.
- The dependency graph has an accessible text list.
- Progress exposes text statuses: Pending, In progress, Complete, or Interrupted.
- Motion is suppressed under `prefers-reduced-motion`.
