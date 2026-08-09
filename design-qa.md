# ChangeSafe design QA

## Comparison evidence

- Source visual truth: `docs/design/changesafe-judge-command-center-v1.png`
- Desktop overview: `docs/screenshots/changesafe-desktop-replay.png`
- Desktop lower-state proof: `docs/screenshots/changesafe-desktop-proof.png`
- Mobile overview: `docs/screenshots/changesafe-mobile-replay.png`
- Mobile lower-state proof: `docs/screenshots/changesafe-mobile-proof.png`
- State: official DataHub `showcase-ecommerce` recorded evidence, analysis complete, then preview approved for the receipt captures

The 1487 x 1058 source raster and 1425 x 1013 desktop implementation raster
have the same near-1.4 content aspect ratio and were compared together at their
original density. The desktop browser override was 1440 x 1024 CSS pixels at
device scale 1; the in-app surface produced a 1425 x 1013 page bitmap after
accounting for its scrollbar and browser-surface inset. The phone override was
430 x 932 CSS pixels at device scale 1 and produced 415 x 899 page bitmaps.

The full-view comparison covered overall hierarchy, three-zone command-center
composition, impact rail, central lineage evidence, persisted process, and the
five decision gates. A separate focused crop was unnecessary because both
original-resolution full views keep the important labels readable and share
the same aspect ratio. The two lower-state frames separately prove generated
code, validation, and receipt behavior that has no counterpart in the concept
image.

## Required fidelity surfaces

- Fonts and typography: the condensed uppercase hero, compact operational labels, weights, line heights, and wrapping preserve the reference hierarchy. Small evidence copy remains readable at both checked viewports.
- Spacing and layout rhythm: the desktop keeps the reference's left evidence, central dependency, and right process rhythm. Tablet and phone layouts stack in reading order without horizontal overflow.
- Colors and visual tokens: deep navy surfaces, cyan evidence/action states, red and amber severity badges, and lime authorization actions map consistently to the source direction.
- Image and asset fidelity: the implementation uses the real ChangeSafe mark and Lucide product icons. It intentionally does not copy unverified vendor logos from the concept. The lineage motion is a live UI effect rather than a raster approximation.
- Copy and content: runtime facts say `Recorded DataHub evidence`, `Preview only`, and `NOT WRITTEN - SNAPSHOT MODE`. No interface copy claims that recorded evidence is a live DataHub query or that replay approval changed an external system.

## Comparison history and resolved findings

- P1 - The hero previously changed footprint after Analyze. The five run facts and a one-line evidence property now occupy the same slots in every state, longer explanations stay inside collapsed details, and the mobile Evidence ID row reserves the copy-control footprint. Desktop and phone browser assertions compare the closed hero bounds before and after analysis.
- P1 - Impact classifications looked like selected form inputs. Finding-card border and background now remain unchanged; only the explicit evidence-trace button becomes active and changes to a clear action.
- P1 - The dependency view read as a static many-to-many inventory. It now separates upstream inputs from recorded dependents, preserves direct/multi-hop degree evidence, and uses two directional moving-light rails with reduced-motion support.
- P1 - Failed analyses could leave the interface locked. Fresh and restored failed runs now expose a working **New analysis** action.
- P2 - Fast replay appeared pre-timed. The process now shows ordered persisted event IDs, relative server timestamps, measured elapsed time, evidence retrieval time, and preview-specific final-step wording. No artificial network delay is presented as work.
- P2 - Custom field or URN edits inherited preset ecommerce claims. Preset facts now appear only for the exact official request; custom drafts show pending context and submitted results use returned metadata.
- P2 - Generated files lacked context and the removal guard was cryptic. Every artifact now states its purpose and prevented failure. Removal copy explains that dbt warehouse execution catches early field removal and that ChangeSafe itself does not execute SQL.
- P2 - Earlier screenshots were top-only and the capture procedure did not prove approval. The current proof is four explicit, non-stitched viewport frames with overview and lower validation/receipt states for desktop and phone.

## Interaction and responsive QA

- Isolated QA used the replay backend on port 8123 and the web app on port 5173 with an empty environment file; no private integration credentials were loaded.
- Rename, remove, and type-change flows produced different impact language, deterministic scores (80, 95, and 90), artifacts, and validation evidence.
- The removal guard visibly explains `warehouse execution fails on the missing column`; the type-change model contains `cast(cust_email as VARCHAR(320)) as cust_email__new_type`.
- Six impact findings, directional lineage, seven process steps, seven generated artifacts, 12/12 blocking checks, preview approval, patch action, and the non-mutating receipt were exercised.
- The 430 px overview frames keep the same hero boundary before and after analysis, and the page shows no horizontal overflow; the code viewer retains its own intentional horizontal scroll.
- A fresh browser tab contained only development connection/info entries and no console warning or error.
- The automated capture script uses the same explicit desktop and phone viewports, anchors overview/lower proof targets in the viewport, and writes the four paths above with `fullPage: false`.

No unresolved P0, P1, or P2 findings remain.

final result: passed
