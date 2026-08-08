# ChangeSafe interface design system

The visual source of truth is `changesafe-desktop-concept.png`, with
`changesafe-mobile-concept.png` defining the responsive completion state.

## Copy lock

The first viewport uses only the product and workflow copy represented by the
concept: ChangeSafe, Snapshot replay, Preview only / snapshot mode, Propose a schema
change, Change analysis, the selected field transition, the deterministic risk
result, lineage evidence, run progress, generated artifacts, validation, and
approval actions. Status labels are derived from real API states.

## Tokens

- Canvas: warm off-white `#fbfaf7`; surface: `#ffffff`; ink: `#071b3d`.
- Muted ink: `#56637a`; divider: `#ccd3dd`; quiet fill: `#eef4f5`.
- Verified teal: `#087f83`; teal tint: `#e3f2f1`.
- Critical amber: `#c76500`; amber tint: `#fff1dc`.
- Failure red: `#a63b32`; failure tint: `#fbe9e7`.
- Code surface: `#061d3b`; code ink: `#edf5ff`.
- Spacing follows an 8 px rhythm; controls are at least 44 px high.
- Corners are restrained (4–10 px). Shadows are used only for the code frame
  and focused overlays; hierarchy otherwise comes from rules and whitespace.

## Typography and components

- Content/UI: Inter-compatible humanist system sans; 14–16 px chrome,
  20–30 px headings, tabular numerals for score and evidence.
- Evidence/code: `ui-monospace`, 13–14 px with a 1.65 line height.
- Component families: quiet header, request rail, evidence ledger, lineage
  canvas/list, progress spine, artifact rail + code inspector, validation
  checklist, and governed approval/receipt panel.
- Icons: consistent 1.75 px outline, 16–22 px, always paired with text for
  state. Status never relies on color alone.

## Container and responsive model

Desktop uses an open request rail, primary evidence canvas, and progress rail,
followed by one framed artifact inspector and approval column. At 960 px the
rails stack while preserving order. At 640 px, lineage becomes a labeled list,
the progress spine becomes a horizontal/scroll-safe summary, controls become
full width, and code remains horizontally scrollable without page overflow.
