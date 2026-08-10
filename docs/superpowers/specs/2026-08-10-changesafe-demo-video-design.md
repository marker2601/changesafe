# ChangeSafe Competition Demo Video Design

**Date:** 2026-08-10  
**Target runtime:** 2:35–2:45; hard maximum 2:55  
**Format:** 1920×1080, 16:9, 30 fps, H.264 MP4  
**Primary source:** <https://changesafe-competition.onrender.com>  
**Narration:** Generated, calm, confident, neutral English voice

## Purpose

Produce a public competition video that makes the problem, DataHub integration,
real product workflow, safety proof, and human-approval boundary understandable
to a non-technical reviewer in under three minutes.

The video must feel like a product story rather than a tutorial. It will combine
real hosted interactions with restrained title cards, captions, smooth zooms,
and brand-matched callouts. It must never imply that recorded evidence or an
unexecuted warehouse check was live.

## Success criteria

- The finished MP4 is shorter than three minutes and remains legible at 1080p.
- Every visible product result comes from the permanent hosted application.
- The story explains why DataHub context matters before it explains generated
  code.
- The selected-field workflow is visibly schema-driven, not email-specific.
- The evidence map, seven artifacts, 12/12 checks, owner pause, preview receipt,
  and patch download are all shown.
- Captions match the narration and remain inside title-safe bounds.
- The hosted replay is labeled as recorded DataHub evidence, preview only, and
  production rows not queried.
- No token, credential, private endpoint, raw query, relation fingerprint, raw
  warehouse value, or private operator detail appears in any frame or metadata.

## Production approach

Use a hybrid live-product-story format:

1. A short animated problem statement establishes the stakes.
2. A real fresh browser session demonstrates the main rename workflow.
3. Purposeful cuts and zooms reveal evidence, artifacts, and policy proof.
4. Two brief alternate-field shots prove the product is not email-only.
5. A real preview approval and patch download close the workflow.
6. A branded end card provides the hosted application and public repository.

A continuous screen recording is rejected because scrolling and repeated actions
would make the core idea hard to follow. A mostly animated explainer is rejected
because it would weaken proof that the submitted product works.

## Visual and audio language

- Preserve ChangeSafe's dark navy, teal, cream, and lime palette.
- Use one large idea per title card and no more than two short callouts per shot.
- Crop unnecessary browser chrome while retaining enough context to show this is
  a real hosted application.
- Use smooth cursor movement, short ease-in zooms, and direct cuts. Avoid fake
  loading, fake percentages, stock footage, exaggerated glitch effects, and
  repeated decorative transitions.
- Use sentence-case captions in a high-contrast lower safe area. Highlight only
  important nouns such as `DataHub`, `55 fields`, `7 artifacts`, and `12 / 12`.
- Generated narration should be approximately 145–155 words per minute, with
  brief pauses after the problem, evidence result, and approval receipt.
- The first cut will be voice-first without background music. Music may be added
  only if a clearly licensed or original quiet bed is available and never masks
  narration.

## Timestamped shot design

| Time | Picture and interaction | On-screen emphasis |
| --- | --- | --- |
| 0:00–0:12 | Open on the moving dependency map, then reveal the product name and problem statement. | `One field. Many dependencies.` |
| 0:12–0:27 | Show the stable hero, permanent hosted URL, and the three truth labels. | `DataHub evidence · Preview only · Production rows not queried` |
| 0:27–0:45 | Open Current field, show returned options, select `cust_email`, keep Rename, enter `primary_email`, and analyze. | `55 schema fields` and `cust_email → primary_email` |
| 0:45–1:12 | Follow persisted events into the animated evidence map. Open one exact field route and one limited multi-hop route. | `Exact route` versus `Intermediate mapping not returned` |
| 1:12–1:34 | Show impact classification and deterministic factor ledger. | `Evidence-led impact` and the displayed score |
| 1:34–1:58 | Cut to the generated shim, artifact list, and validation summary. | `7 verified files` and `12 / 12 blocking checks` |
| 1:58–2:14 | Use two fast fresh-run cuts: `order_status` Remove and `order_total` Change type. Do not replay their full workflows. | `Not email-only` and `Field-specific evidence` |
| 2:14–2:33 | Return to the passing rename run, approve preview, show the non-mutating receipt, and activate Download patch. | `NOT WRITTEN — SNAPSHOT MODE` |
| 2:33–2:42 | End card over the dependency signal with product tagline, hosted URL, repository, and DataHub attribution. | `Evidence-bound. Human-approved.` |

## Word-for-word narration

> A column rename looks simple. But in analytics, one field can feed models,
> metrics, dashboards, and the teams making decisions from them. Change it
> without context, and the failure appears far downstream.
>
> ChangeSafe turns DataHub context into a verified migration decision before
> anything is published. This hosted demonstration uses checksum-pinned recorded
> DataHub evidence, exercises the real application pipeline, and clearly states
> that production rows were not queried.
>
> We start from the allowlisted `order_details` schema. DataHub returns fifty-five
> concrete fields with their native types and nullability. We select
> `cust_email`, propose `primary_email`, and analyze the change.
>
> Persisted events show each real phase. ChangeSafe retrieves field-scoped
> metadata, traces upstream and downstream dependencies, and labels the precision
> of every relationship. Exact routes name both returned fields. Multi-hop and
> dataset-level evidence disclose what DataHub did not return instead of
> inventing a connection. For this field, six upstream and twenty-five downstream
> relationships show how widely one contract change can travel.
>
> The same evidence drives six impact classifications and a deterministic factor
> score, with every point traceable to the factor ledger. Then ChangeSafe creates
> a conservative phase-one migration: the governed model stays intact while a
> compatibility shim exposes the old and new contract together.
>
> The result is seven reviewable files with exact hashes, rollback guidance, and
> an operation-specific compatibility test. Twelve blocking checks verify the
> request, metadata, SQL, YAML, output contract, paths, rollback, and manifest.
>
> This is not an email-only workflow. Selecting `order_status` rebuilds the
> evidence for removal. Selecting `order_total` rebuilds it for a type change.
> The chosen field and operation bind the assessment and every generated byte.
> Unknown fields and destination collisions are blocked before a run can start.
>
> Finally, ChangeSafe pauses for the accountable owner. In this competition-safe
> mode, approval creates a non-mutating receipt and a downloadable patch. Nothing
> is silently written.
>
> ChangeSafe makes schema change review evidence-bound, fail-closed, and human
> approved—using DataHub to keep every dependency in view.

## Capture architecture

The production workflow has four isolated stages:

1. **Evidence setup:** verify `/healthz`, public replay configuration, and the
   55-field schema before recording.
2. **Browser capture:** drive fresh hosted sessions with deterministic assertions
   for every state shown. Record the selected viewport without exposing local
   browser or account details.
3. **Narration and composition:** synthesize the approved script, normalize audio,
   add captions/callouts, and compose the final 1080p timeline.
4. **Verification and delivery:** inspect every scene, run media probes, verify
   runtime/resolution/audio, and produce the MP4 plus script and subtitle file in
   a local submission folder outside tracked source history.

Each captured state must come from an asserted application state. If the free
Render service is sleeping, the capture waits for health before recording; the
wake-up delay is not presented as product processing. If a run fails or returns
unexpected evidence, that take is discarded rather than edited to look passing.

## Deliverables

- `changesafe-competition-demo.mp4` — final public upload candidate.
- `changesafe-competition-demo.srt` — synchronized captions.
- `changesafe-video-script.md` — narration and timestamped presenter guide.
- `changesafe-video-poster.png` — readable 16:9 thumbnail/poster frame.
- A short verification report listing duration, resolution, codecs, file size,
  hosted-flow assertions, and visual/audio review results.

The binary deliverables remain outside Git history unless explicitly requested.
The script, design, and repeatable capture tooling may be committed.

## Acceptance and review

- Runtime is between 2:25 and 2:55.
- Video is 1920×1080, 16:9, 30 fps, H.264 with AAC audio.
- Narration is intelligible at normal laptop volume with no clipping.
- Captions contain no transcription mismatch and remain readable at 100% scale.
- The first 15 seconds state the problem; the first 30 seconds identify DataHub.
- The principal rename flow is real and continuous enough to establish trust.
- Alternate fields are visible without repeating the full main flow.
- The approval receipt and patch download are real hosted actions.
- The end card includes the permanent hosted URL and public repository.
- Frame-by-frame secret and private-detail scan passes.
- The public upload is manually tested without authentication before submission.

## Documentation corrections included with production

The existing demo script and Devpost draft still describe the old temporary
tunnel and a pending hosted URL. Production will update those lines to the
verified Render URL and will not change the underlying evidence claims.
