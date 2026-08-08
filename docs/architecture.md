# ChangeSafe architecture

## System boundary

ChangeSafe has one browser origin and one server process. The browser owns presentation and short-lived UI state. FastAPI owns credentials, validation, run state, artifact bytes, approval, and all external integration calls.

```mermaid
flowchart TD
    U["Judge or analytics engineer"] --> W["React workspace"]
    W -->|"JSON and SSE"| API["FastAPI boundary"]
    API --> STORE["SQLite run/event/publication ledger"]
    API --> ORCH["ChangeSafe orchestrator"]
    ORCH --> PORT["DataHubContextPort"]
    PORT --> SNAP["Canonical replay adapter"]
    PORT --> LIVE["Live Agent Context adapter"]
    ORCH --> RISK["Deterministic risk rules"]
    ORCH --> GEN["Template-first generator"]
    GEN -.->|"optional strict JSON"| OPENAI["OpenAI planner"]
    ORCH --> VERIFY["Artifact verifier"]
    API --> PUB["Idempotent publication service"]
    PUB -.->|"owner enabled"| GH["GitHub Git Data API"]
    PUB -.->|"owner enabled"| LIVE
```

## Run sequence

```mermaid
sequenceDiagram
    participant UI as Browser
    participant API as FastAPI
    participant O as Orchestrator
    participant C as Context port
    participant V as Verifier
    participant P as Publication

    UI->>API: POST /api/runs
    API-->>UI: 202 + UUIDv7 run_id
    API->>O: analyze(run_id)
    UI->>API: GET /events (SSE)
    O->>C: load normalized metadata context
    C-->>O: context + evidence + provenance
    O->>O: score deterministic risk
    O->>O: generate seven artifacts
    O->>V: validate artifacts and exact hashes
    V-->>O: blocking report
    O-->>UI: awaiting_approval event
    UI->>API: POST /approve
    API->>P: artifact-bound idempotent approval
    alt Replay or publication disabled
        P-->>UI: patch + NOT WRITTEN preview receipt
    else Owner-enabled live publication
        P->>P: GitHub branch, commit, and PR
        P->>C: allowlisted DataHub decision writeback
        P-->>UI: durable live receipts
    end
```

## State machine

```mermaid
stateDiagram-v2
    [*] --> created
    created --> loading_context
    loading_context --> context_fallback_required: eligible live read failure in auto mode
    context_fallback_required --> loading_context: user explicitly accepts snapshot
    loading_context --> scoring_risk
    scoring_risk --> generating
    generating --> validating
    validating --> awaiting_approval: all blocking checks pass
    validating --> failed: validation fails
    awaiting_approval --> preparing_preview: replay or writes disabled
    preparing_preview --> completed
    awaiting_approval --> publishing: owner-gated live writes
    publishing --> completed: all requested receipts persisted
    publishing --> publication_failed: partial or typed failure
    publication_failed --> publishing: retry missing step
```

Every transition is validated and written to `run_events` before it is streamed. Clients resume with the last sequence number. Terminal streams close only after all stored events are delivered.

## Context adapters

Both adapters return the same strict `ContextBundle` contract.

- Replay verifies `fixtures/datahub/golden-context.json` against its committed SHA-256 before parsing it. The resulting provenance is `snapshot` and contains the hash.
- Live uses the `datahub-agent-context` tool surface for entities, the full target schema, bounded upstream and downstream lineage, and query context. Tool evidence records sanitized parameters, duration, result count, and referenced URNs. Calls have a bounded timeout and retry transport/timeouts once; authorization errors are never retried.
- In `auto` mode, an eligible live read failure is persisted as `context_fallback_required`. Only an explicit API/UI action resumes the same run with labeled snapshot provenance; fallback is unavailable once publication begins.
- Live reads and writes reject targets outside `DEMO_URN_ALLOWLIST` before a tool call is made.

No replay code path initializes a network client.

## Generation and verification

Reviewed operation-specific templates derive the seven paths from the target model and define safety invariants for rename, removal, and type-change requests. When an OpenAI key exists, one strict structured-output call may supply bounded narrative and advisory transformation fields; one repair call is allowed only after schema validation failure. Executable SQL remains deterministic. On timeout or planning failure, the template remains available. The planner cannot change the risk score, remove a required file, introduce a relation, or bypass validation.

The verifier operates on in-memory bytes and blocks publication on any failed mandatory check. Generated code is parsed but never executed.

## Publication and idempotency

The publication key hashes the normalized request, source commit, and final artifact manifest. The local ledger checkpoints the GitHub branch, pull request, and each DataHub writeback substep. A retry with the same artifact hash reconciles and resumes only missing work; a conflicting artifact hash fails closed. Transitional runs whose ledger already completed are recovered without replaying external mutations.

Replay approval creates a unified patch and preview receipt only. Live mutation also requires:

1. A matching admin token supplied to the approval request.
2. The relevant server-side feature flag.
3. Integration credentials and target configuration.
4. An allowlisted DataHub URN.
5. A fully passing validation report.

## Trust and security boundaries

- Service credentials stay in environment-backed `SecretStr` settings.
- `/api/public-config` returns capabilities, never credential values.
- HTTP responses receive CSP, clickjacking, MIME-sniffing, referrer, opener, and permissions headers.
- Request bodies larger than 16 KiB are rejected before JSON parsing.
- Pydantic models reject unknown keys and invalid operations.
- Artifact paths are POSIX-normalized and checked against a seven-path allowlist.
- UI code and Markdown are rendered as text; generated HTML is not injected.
- The container runs as UID 10001 with a read-only filesystem and a dedicated `/data` volume.

The app applies a per-client sliding-window run limit in each process. For a public deployment, terminate TLS and add a distributed per-IP limit at the edge. For multiple replicas, replace in-process background work and SQLite with a durable queue and shared transactional store.

## Deployment

The multi-stage image builds React under Node 24, installs Python 3.12 plus the live DataHub adapter, copies only the compiled frontend into the runtime, and exposes port 8000. FastAPI serves static assets after API routes so `/api/*` cannot be shadowed.
