# Shared review sandbox runbook

This runbook hosts one ChangeSafe instance for reviewers while keeping every service credential on the server. It is intentionally conservative: recorded-evidence review is public, external writes are private and off by default.

## Supported topology

- One HTTPS endpoint and one ChangeSafe service replica.
- One persistent volume mounted at `/data` for `changesafe.db`.
- Read-only container filesystem with `/tmp` as tmpfs.
- Reverse proxy or hosting edge with TLS, request-size enforcement, and distributed rate limiting.
- `CHANGESAFE_MODE=replay` for the public review path.
- `PUBLIC_PR_ENABLED=false` and `PUBLIC_WRITEBACK_ENABLED=false` unless the operator is actively demonstrating an owner-controlled sandbox publication.

SQLite and in-process tasks are safe for this single-replica review topology. Do not scale horizontally without moving runs, events, budget reservations, and jobs to shared transactional/durable infrastructure.

## Reviewer experience

Reviewers open the shared URL and click **Analyze change**. They do not enter a DataHub login, GitHub token, OpenAI key, or owner token. Each browser tab receives an opaque random session ID; the server stores only a one-way hashed session label alongside run state and timestamps.

The public workflow uses a SHA-256-verified snapshot of DataHub's official `showcase-ecommerce` scenario. It runs the real orchestration and stops at preview approval. The receipt explicitly says no DataHub or GitHub write occurred.

## Private operator view

Set `CHANGESAFE_ADMIN_TOKEN` to a long random value. This makes **Review activity** available, but the endpoint still requires the token on every request. Enter it only in the drawer; the browser keeps it in component memory and does not write it to session storage, local storage, a URL, or global application state.

The activity response is intentionally limited to:

- opaque run ID;
- hashed session label;
- scenario;
- run state;
- context/publication mode; and
- created/updated timestamps.

It contains no name, email, IP address, browser fingerprint, or service credential.

## Environment values

Start from `.env.example` in a secret manager or private server environment. For a replay-only shared deployment, set only:

```text
CHANGESAFE_MODE=replay
CHANGESAFE_DATA_PATH=/data/changesafe.db
CHANGESAFE_WEB_DIST=/app/web
CHANGESAFE_ADMIN_TOKEN=<random private owner value>
PUBLIC_PR_ENABLED=false
PUBLIC_WRITEBACK_ENABLED=false
```

Do not upload the laptop's `changesafe.env`. Copy individual values into the hosting provider's encrypted environment settings.

## Optional live DataHub evidence

Live reads need `DATAHUB_GMS_URL` plus a personal access token with schema, entity, ownership, governance, lineage, and query-context read access. `DATAHUB_UI_URL` is a non-secret catalog origin used only to build safe evidence links.

Before enabling live mode:

1. Start or obtain a DataHub instance.
2. Run `datahub datapack load showcase-ecommerce`.
3. Run `scripts/seed_datahub.py --apply` with a token allowed to add the ChangeSafe overlay.
4. Run `scripts/seed_datahub.py --verify-only`.
5. Keep `PUBLIC_WRITEBACK_ENABLED=false` for reviewer traffic unless a dedicated mutation demonstration is required.

## Optional GitHub sandbox

Use a separate repository, not the ChangeSafe source repository. Create a fine-grained token restricted to that one repository with Contents and Pull requests read/write. Set `CHANGESAFE_GITHUB_REPOSITORY=owner/sandbox-repo`, verify `GITHUB_BASE_BRANCH`, and keep `PUBLIC_PR_ENABLED=false` until an operator is present.

When enabled, approval additionally requires `CHANGESAFE_ADMIN_TOKEN`. ChangeSafe binds repository, base branch, artifact hashes, and publication intent in its ledger and fails closed if configuration drifts.

## Health and monitoring

- Probe `GET /healthz`.
- Use the review activity drawer for privacy-limited run state.
- Alert on repeated `publication_failed`, `failed`, 429, or 5xx responses.
- Back up the persistent SQLite volume before maintenance.
- Never log request authorization headers or the private environment.

## Recovery

- Browser refresh restores the full run ID from session storage and replays persisted events from sequence zero.
- After a service restart, a recovered `publishing` or `preparing_preview` run exposes an explicit resume action.
- Retryable publication failures resume only the missing checkpoint.
- Non-retryable authorization, destination, branch-tree, or contract failures require operator correction.

## Reset after review

Disable both mutation flags, revoke temporary DataHub/GitHub tokens, rotate the owner token, archive the sandbox repository, and retain or securely delete the SQLite volume according to the submission record policy.
