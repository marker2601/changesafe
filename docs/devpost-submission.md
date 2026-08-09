# Devpost submission draft

## Title

ChangeSafe

## Tagline

Evidence-led safety for analytics schema changes before merge.

## Inspiration

Small schema edits cause disproportionate outages because code review rarely includes the real organizational context: semantic models, reports, governance labels, owners, query usage, and the teams relying on a field. We wanted an agent that pauses before editing, asks the catalog what the change means, and produces a migration people can verify instead of silently applying code.

## What it does

ChangeSafe accepts a proposed column rename, removal, or type change. It retrieves normalized context through DataHub's Agent Context Kit, classifies six business and technical impact areas, computes an immutable risk score, generates a conservative seven-file dbt/SQL migration package, and runs twelve blocking validations. A reviewer can follow directional lineage signals, trace each impact finding to its evidence, inspect exact artifact bytes and explanations, review rollback guidance, and see the accountable approval stop.

The golden demonstration uses the organizer-provided `showcase-ecommerce` datapack: `Order Entry Analytics.order_details.cust_email` becomes `primary_email`. The recorded graph contains seven Snowflake, Power BI, and Looker dependents plus ownership, PII/governance metadata, high query usage, and cross-domain evidence.

The credential-free mode replays a SHA-256-verified snapshot through the same API, persistence, event stream, policy, generation, verification, and approval pipeline. The UI calls this **Recorded DataHub evidence**, reports measured server-event timing, labels its output `NOT WRITTEN — SNAPSHOT MODE`, and produces a downloadable patch. Owner-enabled live mode can create a GitHub pull request and write an idempotent decision document, structured properties, and a deprecation tag to an allowlisted DataHub target.

## Why it is different

DataHub already helps people discover metadata. ChangeSafe turns that context into a fail-closed pre-merge decision and a directly reviewable code package. It does not merely summarize a catalog or generate unverified SQL. It binds evidence, deterministic policy, exact artifact hashes, human authorization, crash-safe publication checkpoints, and durable receipts into one workflow.

## How we built it

- React 19, TypeScript, Vite, semantic HTML, Lucide icons, and a responsive command-center interface.
- FastAPI, Pydantic, SQLite, UUIDv7 run IDs, and resumable server-sent events.
- `datahub-agent-context` for live schema, governance, ownership, query, and lineage context, with a contract-compatible replay adapter.
- A deterministic risk engine and an evidence-led six-category impact classifier; the LLM cannot change either policy result.
- OpenAI Responses structured output for optional bounded planning fields, with deterministic fallback and a project cost reservation ledger.
- `sqlglot`, safe YAML parsing, semantic SQL type validation, path confinement, and SHA-256 manifests.
- GitHub Git Data API publication with artifact/tree reconciliation and a destination-bound durable idempotency ledger.
- Playwright, Vitest, pytest, Ruff, mypy, dbt, Docker, and GitHub Actions.

## Challenges

The hardest part was preserving truth across live and replay modes. A polished demo is not useful if it implies that recorded evidence or preview writes happened live. We use one strict context contract, prominent evidence provenance and checksums, measured event timing, safe catalog links, and unambiguous receipts.

The second challenge was safe partial publication. A GitHub PR can succeed before a DataHub writeback fails, or a service can restart between checkpoints. ChangeSafe persists immutable intent, destinations, artifact identity, and each side effect, then resumes only the missing step for the original run.

The third challenge was explaining impact without inventing facts. Each impact category names its evidence confidence and URNs. Financial exposure is marked `Potentially high, not quantified`; no unsupported dollar estimate is shown.

## Accomplishments

- The official ecommerce rename deterministically finds seven recorded consumers and scores 80/Critical.
- Six impact categories translate metadata into language a nontechnical reviewer can understand.
- Seven generated files pass twelve blocking SQL, YAML, compatibility, path, rollback, relation, collision, context, and manifest checks.
- Reviewers can complete the workflow without credentials on desktop or mobile while persisted backend events update the page.
- A private, owner-token-protected view shows hashed anonymous review sessions without storing identity or IP data.
- Replay, live DataHub 1.7 mapping, crash/retry publication, hostile rendering, hard cost accounting, and browser recovery are automated.

## What we learned

Metadata becomes more valuable when it is executable decision context rather than a passive catalog. A trustworthy agent needs explicit provenance, bounded authority, deterministic policy, semantic validation, human approval, and durable receipts as much as it needs generation quality.

## What's next

- Run the final owner-controlled live proof against a DataHub instance loaded with `showcase-ecommerce`.
- Add organization authentication and move jobs/ledger storage to shared infrastructure for multi-replica hosting.
- Add additional catalog-backed policy profiles for contracts, quality assertions, and production ML changes.
- Contribute generalized Agent Context Kit envelope fixtures and documentation back to the DataHub ecosystem.

## Technologies

DataHub Agent Context Kit, official `showcase-ecommerce` datapack, OpenAI Responses API, Python, FastAPI, Pydantic, SQLite, React, TypeScript, Vite, sqlglot, PyYAML, httpx, Playwright, Vitest, pytest, Ruff, mypy, dbt, Docker, Docker Compose, and GitHub Actions.

## Testing instructions

1. Run `docker compose up --build` from a clean clone.
2. Open `http://localhost:8000`.
3. Confirm **Recorded DataHub evidence**, **Preview only**, and **Official DataHub showcase-ecommerce**.
4. Click **Analyze change**.
5. Confirm 80/Critical, six impact categories, seven recorded dependents, seven files, and 12/12 validations.
6. Trace an impact finding, open a dependency to inspect evidence, read an artifact explanation, then click **Approve preview**.
7. Confirm `NOT WRITTEN — SNAPSHOT MODE` and download the patch.

No DataHub token is needed for these judging steps. A token is needed only for an operator-controlled live DataHub run.

## Submission links

- Hosted app: `PENDING_HOSTED_URL`
- Source repository: `https://github.com/marker2601/changesafe`
- Demo video: `PENDING_VIDEO_URL`
- Live GitHub pull request: `PENDING_SAMPLE_PR_URL`
- Live DataHub decision evidence: `PENDING_DATAHUB_EVIDENCE_URL`

Do not replace a remaining placeholder until the external artifact exists and has been verified.
