# ChangeSafe Render Competition Deployment Design

**Date:** 2026-08-10  
**Status:** Approved direction; implementation pending  
**Target:** Competition-ready pilot deployment

## Objective

Publish ChangeSafe at a stable HTTPS URL before the submission deadline without
weakening its evidence boundaries or pretending that the current build is a
production service. The hosted application must remain fully interactive for
judges and must not require browser-side service credentials.

## Product maturity statement

ChangeSafe is a **competition-ready pilot**: it is more complete and verified
than a hackathon prototype, but it does not claim production availability,
multi-instance scaling, disaster recovery, or a managed production data plane.

## Chosen deployment

Deploy the existing single-origin Docker application as one Render web service.
FastAPI continues to serve the React build, API, downloadable artifacts, and
resumable event stream from the same origin.

The first hosted deployment uses recorded DataHub evidence:

- `CHANGESAFE_MODE=replay`;
- the checksum-pinned, 55-field `showcase-ecommerce` recording included in the
  repository;
- GitHub publication and DataHub writeback disabled;
- warehouse validation disabled and truthfully shown as not run; and
- no DataHub, GitHub, Snowflake, or owner credential in Render.

This is a real execution of ChangeSafe's risk, generation, verification,
approval-preview, event, and artifact paths. Only the metadata read is replayed;
the result is not a pre-rendered page or fixed percentage.

## Hosting tier

Start on Render's free web-service tier to avoid an unapproved charge and obtain
a stable `onrender.com` hostname quickly. Its filesystem is intentionally
treated as ephemeral: a service restart may clear prior run history, but judges
can start and complete a new analysis.

After submission, the same service can be upgraded to a paid instance with a
disk mounted at `/data` without changing the public product flow. That upgrade
is required before claiming durable hosted run history.

## Deployment contract

Add a root `render.yaml` Blueprint that:

- builds the checked-in root `Dockerfile`;
- binds the service to port `8000` on `0.0.0.0`;
- exposes `/healthz` as the health check;
- fixes the safe replay and preview-only environment values;
- keeps all credentials absent;
- deploys the repository's default branch; and
- exposes the normal Render HTTPS subdomain.

Add a README deploy link and a short hosted-demo section that identifies the
competition-ready pilot boundary, possible free-tier cold start, replay
provenance, and the separate live-mode setup path.

## Live DataHub upgrade

The competition resources provide a local DataHub quickstart and public sample
datapacks, not a hosted metadata-service credential. A fully live hosted mode
therefore requires a DataHub GMS endpoint that is reachable from Render plus a
server-side token. Localhost and `host.docker.internal` addresses are not valid
cloud endpoints.

When that endpoint exists, switch the service to `CHANGESAFE_MODE=auto`, add the
DataHub URL and token as Render secrets, and rerun the live competition smoke
test. Do not expose those values to the browser or commit them to Git.

## Rejected approaches

### Vercel-only

Vercel can execute FastAPI, but its function filesystem is read-only except for
temporary scratch space, invocations have bounded lifetimes, and the current
background/SSE/SQLite recovery model is process-oriented. A safe migration
would require an external durable database and job system, so it is not the
deadline-safe path.

### Netlify-only

Netlify can host the static React build, but the FastAPI service, SQLite ledger,
and resumable processing would still need a separate backend. Splitting the
single-origin application now adds deployment and CORS risk without improving
the judging experience.

### Local tunnel

Anonymous tunnel URLs rotate, depend on this laptop remaining awake, and have
already disconnected. They remain useful for private QA only and must not be the
submission URL.

## Verification

Implementation must prove:

1. the Blueprint contains only the safe replay/preview configuration;
2. no credential-shaped value is added to the repository;
3. the Docker image still builds and passes `/healthz`;
4. the hosted root, public config, schema catalog, analysis, preview approval,
   artifact download, and SSE recovery work at the Render URL; and
5. the UI clearly says recorded DataHub evidence and production rows not
   queried.

The permanent URL is added to the README and submission only after this hosted
walkthrough passes.
