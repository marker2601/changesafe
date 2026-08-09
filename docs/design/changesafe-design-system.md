# ChangeSafe interface design system

The selected visual reference is the historical concept image `docs/design/changesafe-judge-command-center-v1.png`. The implementation keeps its dark operations-console character while using semantic HTML, real application data, and Lucide icons instead of decorative mock controls.

## Product message

The first viewport must answer four questions without technical knowledge:

1. What is changing? `order_details.cust_email` → `primary_email`.
2. What relies on it? Recorded Snowflake, Power BI, and Looker assets.
3. What kind of harm is supported by evidence? Six labeled impact categories.
4. What happens next? A seven-stage live process that stops for an accountable owner.

The primary headline is **Change data safely, with every dependency in view.** Product copy is written for any reviewer, not for a competition-specific audience. Provenance, inference, and publication status are always explicit.

## Tokens

- Canvas: deep navy `#020b13`; primary surface `#071720`; strong surface `#0a2029`.
- Rules: `#24434d`; emphasized rules: `#3b6871`.
- Primary text: warm ivory `#f5eddd`; muted `#93a8ae`; quiet `#6f858c`.
- Verified/context accent: electric teal `#3ee4d0`; active publication: lime `#d8ef22`.
- Caution: amber `#f3a541`; failure: coral `#ff665f`; informational: blue `#63a8ff`.
- Code surface: `#020910`.
- Spacing follows a compact 4/8 px rhythm suited to evidence-dense operational work.
- Corners stay restrained at 3–10 px. A restrained gradient is limited to the provenance fact surface; shadows are reserved for focused evidence and review drawers.

## Typography and iconography

- UI and body: Aptos/Segoe UI/Inter-compatible system sans.
- Hero: condensed system display face, uppercase, tightly tracked.
- Code/evidence: `ui-monospace`, Cascadia Code, or Consolas.
- Labels are 7–11 px uppercase only for operational chrome; explanatory copy remains sentence case.
- Icons come from Lucide, pair with text for state, and never carry meaning through color alone.

## Component families

- Sticky brand header with an optional, functional private **Review activity** control.
- Prominent run-provenance facts for evidence source, publication mode, measured elapsed time, and evidence ID.
- Scenario request rail with locked official datapack facts and an explicit schema transition.
- Six evidence-led impact findings with severity, confidence, qualifiers, and dedicated evidence-trace controls.
- Dependency graph with upstream, governed target, recorded consumers, directional moving lineage signals, direct/multi-hop labels, accessible fallback list, and evidence drawer.
- Seven-step process rail derived from persisted backend event sequence and timestamps, not timers.
- Five-stage command rail summarizing context, impact, artifacts, verification, and authorization.
- Seven-file artifact explorer with exact bytes, hashes, purpose, and the failure each file prevents.
- Twelve-check validation panel plus owner-gated approval/receipt panel.
- Privacy-limited review activity drawer protected by the server admin token.

## State rules

- Recorded snapshot and live evidence use different visible labels.
- Recorded evidence says **Recorded DataHub evidence** and **Preview only**; details disclose snapshot replay and its checksum.
- Live reads with disabled sinks say **Live DataHub evidence** and **Preview only**.
- A restored durable publishing run remains labeled live even if startup configuration changed.
- A failed context load is **Interrupted**, never **Complete**.
- Inferred impact evidence is labeled. Missing evidence lowers confidence instead of creating a claim.
- Replay approval says **NOT WRITTEN — SNAPSHOT MODE**.
- Non-retryable publication failures disable automated retry and call for operator action.

## Responsive model

Desktop uses three command-center columns: proposal/impact, evidence graph, and process. The command rail and delivery workspace follow below. At 980 px and below, the command center stacks in reading order: request and impact, dependency map, then process. At phone widths every region becomes a single column, graph rails rotate into flow direction, code scrolls inside its own frame, review/evidence drawers become full-width, and the page must have no horizontal overflow.

## Accessibility

- Core nodes, evidence-trace controls, tabs, approval, fallback, and review controls are native buttons/links. Impact findings themselves are noninteractive articles.
- Focus rings are high contrast and not removed.
- Dialogs expose names, modal semantics, and labeled close controls.
- The dependency graph has an accessible text list.
- Progress exposes text statuses: Pending, In progress, Complete, or Interrupted.
- Motion is suppressed under `prefers-reduced-motion`.
