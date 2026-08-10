# Devpost submission draft

## Title

ChangeSafe

## Tagline

Evidence-led safety for analytics schema changes before merge.

## Inspiration

Small schema edits cause disproportionate outages because code review rarely includes the real organizational context: semantic models, reports, governance labels, owners, query usage, and the teams relying on a field. We wanted an agent that pauses before editing, asks the catalog what the change means, and produces a migration people can verify instead of silently applying code.

## What it does

ChangeSafe starts with an allowlisted DataHub schema, so a reviewer selects any returned field instead of typing an email-only demo value. It retrieves field-scoped context through DataHub's Agent Context Kit, traces exact metadata routes, classifies six impact areas, computes a deterministic factor score, generates a conservative seven-file dbt/SQL compatibility package, and verifies twelve blocking properties against the exact bytes. When configured, a separate read-only validator checks aggregate non-production warehouse safety. The workflow always pauses for the accountable owner.

The organizer-provided `showcase-ecommerce` catalog exposes exactly 55 concrete `Order Entry Analytics.order_details` fields. The judge flows are:

- Rename `cust_email` to `primary_email`: six upstream and 25 downstream relationships.
- Remove `order_status`: six upstream and 27 downstream relationships.
- Change `order_total` to `VARCHAR(320)`: six upstream and 31 downstream relationships.

Every operation uses the actual keyboard-accessible field combobox. The selected field binds the request, context, risk factors, route labels, generated paths, manifest, and warehouse policy evidence. The score is derived from the factor ledger; it is not a field-name branch.

Routes are truthful about their precision. Exact field routes name both returned endpoint columns. Endpoint-only multi-hop routes disclose that an intermediate mapping was not returned. Dataset-level relationships never receive an invented field name. ChangeSafe also does not infer a personal-data label from a name such as `cust_email` when the field-scoped governance evidence is absent.

Credential-free mode replays a SHA-256-verified DataHub snapshot through the same API, persistence, event stream, policy, generation, verification, approval, and patch-download pipeline. The UI calls this **Recorded DataHub evidence checked**, labels the receipt `NOT WRITTEN — SNAPSHOT MODE`, and says **Production rows not queried**. Replay proves deterministic application behavior; it does not prove current DataHub state or warehouse values.

Owner-enabled live mode can create one GitHub pull request and write an idempotent decision record to the allowlisted DataHub target. Publication is bound to the request, destinations, exact artifact hash, durable checkpoints, and an explicit owner approval.

## Warehouse and data boundary

The Snowflake path is deliberately narrow. Reviewed query plans return aggregate counts only. Raw rows, raw values, relation names, query text, credentials, and private service URLs do not enter the browser or public smoke summary. The adapter validates read-only identity and an allowlisted relation before the aggregate phase.

A timeout, missing field, unsafe conversion, empty/all-null result, stale evidence, relation drift, or required validation that was not run blocks approval. **Warehouse values checked** appears only for current request-bound aggregate evidence with live DataHub provenance that passed every policy check.

No Snowflake credentials were supplied for the final public proof. **Production rows not queried**, and no live warehouse pass is claimed.

## Why it is different

DataHub already helps people discover metadata. ChangeSafe turns that context into a fail-closed pre-merge decision and a directly reviewable code package. It does not merely summarize a catalog or generate unverified SQL. It binds evidence, deterministic policy, exact artifact hashes, optional aggregate value proof, human authorization, crash-safe publication checkpoints, and durable receipts into one workflow.

## How we built it

- React 19, TypeScript, Vite, semantic HTML, Lucide icons, and a responsive command-center interface.
- FastAPI, Pydantic, SQLite, UUIDv7 run IDs, and resumable server-sent events.
- `datahub-agent-context` for live schema discovery and field-scoped governance, ownership, usage, and lineage context.
- A SHA-256-checked replay adapter with the same strict context contract.
- A deterministic risk engine, six-category impact classifier, and reviewed templates for every generated artifact.
- `sqlglot`, safe YAML parsing, semantic SQL type validation, path confinement, SHA-256 manifests, and dbt materialization tests.
- A read-only Snowflake adapter with identity checks, allowlisted aggregate plans, deadlines, and count-only evidence.
- GitHub Git Data API publication plus idempotent DataHub writeback and durable side-effect reconciliation.
- Playwright, Vitest, pytest, Ruff, mypy, dbt, Docker, and GitHub Actions.

## Challenges

The hardest part was preserving truth across live and replay modes. A polished demo is harmful if it implies that recorded evidence, preview writes, or warehouse checks happened live. The UI separates DataHub provenance, static artifact proof, warehouse execution status, and publication mode.

The second challenge was incomplete lineage. Real catalogs can return an endpoint or asset path without every intermediate column mapping. The graph, accessible list, and drawer share one route model and carry explicit precision labels instead of guessing.

The third challenge was safe partial publication. A GitHub PR can succeed before a DataHub writeback fails, or a process can restart between checkpoints. ChangeSafe persists immutable intent, destinations, artifact identity, and each side effect, then resumes only the missing step for the original run.

The fourth challenge was recovery at browser boundaries. Refresh during `validating_warehouse`, terminal SSE EOF, and a lost approval response all reconcile from durable server state. Progress is event-driven; there are no fake percentages or timed UI stages.

## Accomplishments

- Exactly 55 official schema fields with native type/nullability and keyboard selection.
- Three operation-specific judge flows with six upstream routes and 25/27/31 downstream relationships.
- Case-insensitive rename collision blocking and protection against submitting a stale selection after an unknown field query.
- Exact, endpoint-only, and dataset-level lineage rendered consistently across graph, drawer, and accessible list.
- Six evidence-led impact categories and a deterministic factor ledger.
- Seven exact generated artifacts and twelve blocking static checks.
- Optional aggregate-only warehouse validation with request identity, freshness, and approval policy binding.
- Durable browser recovery, approval reconciliation, no-mutation preview receipts, and patch download.
- Responsive 1440 px and 430 px acceptance with no page-level horizontal overflow, keyboard drawer/focus return, reduced-motion support, and clean console/page-error arrays.
- A final local live DataHub smoke with 55-field discovery, live provenance, no mutation, seven artifacts, and 12 / 12 static checks for every operation; warehouse status remained `not_run`.

## What we learned

Metadata becomes more valuable when it is executable decision context rather than a passive catalog. A trustworthy agent needs explicit provenance, bounded authority, deterministic policy, semantic validation, human approval, durable receipts, and honest uncertainty as much as it needs generation quality.

## What's next

- Add stable judge hosting under the owner's deployment account or custom tunnel domain; the anonymous QA tunnel is intentionally temporary.
- Supply owner-controlled read-only Snowflake credentials to produce a real aggregate warehouse pass.
- Add organization authentication and move jobs/ledger storage to shared infrastructure for multi-replica hosting.
- Add more catalog-backed policy profiles for contracts, quality assertions, and production ML changes.

## Technologies

DataHub Agent Context Kit, official `showcase-ecommerce` datapack, Snowflake connector, Python, FastAPI, Pydantic, SQLite, React, TypeScript, Vite, sqlglot, PyYAML, httpx, Playwright, Vitest, pytest, Ruff, mypy, dbt, Docker, Docker Compose, and GitHub Actions.

## Testing instructions

1. Run `docker compose up --build` from a clean clone and open `http://localhost:8000`.
2. Confirm **Recorded DataHub schema**, **Preview only**, the `order_details` dataset, and **Production rows not queried**.
3. Select `cust_email` with the keyboard, keep **Rename field**, enter `primary_email`, and analyze. Confirm six upstream / 25 downstream relationships, seven files, and 12 / 12 static checks.
4. Open a direct route, a multi-hop route, and a dataset-level route. Confirm the different precision labels, close the drawer with Escape, and verify focus returns.
5. Start a new analysis, select `order_status`, choose **Remove field**, and confirm six upstream / 27 downstream evidence plus the retained-field compatibility test.
6. Start a third analysis, select `order_total`, choose **Change type**, enter `VARCHAR(320)`, and confirm six upstream / 31 downstream evidence plus the operation-specific cast bytes.
7. Try `ORDER_TOTAL` as a rename destination and an unknown Current field. Confirm both are blocked before submission.
8. Read an artifact explanation, choose **Approve preview**, confirm `NOT WRITTEN — SNAPSHOT MODE`, and download the patch.

No DataHub token is needed for replay. A token is needed only for an operator-controlled live DataHub run. Snowflake credentials are needed only for aggregate warehouse validation; none were available for this proof.

## Submission links

- Hosted app: stable hosting blocked pending the owner's hosting account or custom tunnel domain
- Source repository: `https://github.com/marker2601/changesafe`
- Demo video: pending external recording
- Live GitHub pull request: not created; mutation flags remained disabled
- Live DataHub decision evidence: not written; mutation flags remained disabled
