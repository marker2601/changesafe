# Devpost submission draft

## Title

ChangeSafe

## Tagline

Metadata-aware, evidence-backed safety for analytics schema changes before merge.

## Inspiration

Small schema edits cause disproportionate outages because code review rarely includes the real downstream context: dashboards, campaigns, support workflows, ML features, governance labels, owners, and query usage. We wanted an agent that pauses before editing, asks the catalog what depends on the change, and produces a migration that can be reviewed instead of silently applied.

## What it does

ChangeSafe accepts one proposed column rename, removal, or type change. It retrieves normalized context through a DataHub adapter, computes an immutable risk score, generates a conservative seven-file dbt/SQL migration package, and runs twelve blocking validations. A reviewer can inspect evidence, lineage, exact artifact bytes, and rollback guidance before approval.

The credential-free mode replays a checksummed snapshot through the same scoring, generation, verification, persistence, SSE, and approval pipeline. It labels its output `NOT WRITTEN - SNAPSHOT MODE` and produces a downloadable patch. Owner-enabled live mode can create a GitHub pull request and write an idempotent decision record, structured properties, and a deprecation tag back to an allowlisted DataHub target.

## How we built it

- React 19, TypeScript, Vite, semantic HTML, and a responsive lineage workspace.
- FastAPI, Pydantic, SQLite, UUIDv7 run IDs, and resumable server-sent events.
- `datahub-agent-context` for the live metadata port and a contract-compatible replay adapter.
- A deterministic rule engine for risk; the LLM is structurally prevented from changing the score.
- OpenAI Responses API structured output for optional bounded planning fields.
- `sqlglot`, safe YAML parsing, path confinement, and SHA-256 manifests for verification.
- GitHub Git Data API publication with a durable artifact-bound idempotency ledger.
- Playwright, Vitest, pytest, Ruff, mypy, Docker, and GitHub Actions for reproducibility.

## Challenges

The hardest part was preserving truth across live and replay modes. A polished demo is not useful if it implies that replayed evidence or preview writes happened live. We solved this with a shared strict context contract, snapshot provenance and checksums, explicit receipt labels, and separate mutation gates.

The second challenge was safe partial publication. A GitHub PR can succeed before a DataHub writeback fails. ChangeSafe persists each side effect separately and retries only the missing step with the original idempotency key and artifact hash.

The third challenge was keeping AI assistance bounded. Deterministic templates and validators remain authoritative; the optional model receives only relevant JSON and cannot remove files, alter risk, or bypass checks.

## Accomplishments

- The golden rename deterministically finds four downstream consumers and scores 90/Critical.
- The seven-file package passes SQL, YAML, compatibility, path, rollback, relation, and manifest checks.
- The full judge workflow runs without credentials in desktop and mobile browsers.
- The single release image runs unprivileged with a read-only filesystem and persisted SQLite volume.
- Replay, live adapter mapping, publication failure/retry, hostile rendering, and browser behavior are automated.

## What we learned

Metadata becomes far more useful when it is treated as executable decision context rather than a passive catalog. We also learned that a good agent workflow needs explicit provenance, bounded authority, deterministic policy, human approval, and durable receipts just as much as it needs generation quality.

## What's next

- Validate the live seed against the final DataHub environment and capture the public proof receipt.
- Publish a representative ChangeSafe-created pull request.
- Move background analysis and persistence to a shared queue/database for multi-replica hosting.
- Add distributed edge rate limiting, organization authentication, and policy profiles for additional change classes.

## Technologies

DataHub Agent Context Kit, OpenAI Responses API, Python, FastAPI, Pydantic, SQLite, React, TypeScript, Vite, sqlglot, PyYAML, httpx, Playwright, Vitest, pytest, Ruff, mypy, Docker, Docker Compose, and GitHub Actions.

## Testing instructions

1. Run `docker compose up --build` from a clean clone.
2. Open `http://localhost:8000`.
3. Click **Analyze change**.
4. Confirm 90/Critical, four affected assets, seven files, and 12/12 validations.
5. Click **Approve preview**.
6. Confirm `NOT WRITTEN - SNAPSHOT MODE` and download the patch.

## Submission links to fill after external access

- Hosted app: `PENDING_HOSTED_URL`
- Source repository: `PENDING_PUBLIC_REPOSITORY_URL`
- Demo video: `PENDING_VIDEO_URL`
- Live GitHub pull request: `PENDING_SAMPLE_PR_URL`
- Live DataHub decision evidence: `PENDING_DATAHUB_EVIDENCE_URL`

Do not replace these placeholders until each external artifact exists and has been verified.
