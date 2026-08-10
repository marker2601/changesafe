# syntax=docker/dockerfile:1.8

FROM node:24-bookworm-slim AS web-builder

WORKDIR /build
RUN corepack enable && corepack prepare pnpm@11.16.0 --activate

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/web apps/web
RUN pnpm install --frozen-lockfile

RUN pnpm --filter @changesafe/web build


FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    CHANGESAFE_MODE=replay \
    CHANGESAFE_DATA_PATH=/data/changesafe.db \
    CHANGESAFE_WEB_DIST=/app/web \
    CHANGESAFE_SNAPSHOT_PATH=/app/fixtures/datahub/golden-context.json \
    CHANGESAFE_SNAPSHOT_CHECKSUM_PATH=/app/fixtures/datahub/golden-context.sha256

WORKDIR /app

RUN addgroup --system --gid 10001 changesafe \
    && adduser --system --uid 10001 --ingroup changesafe --home /nonexistent changesafe

COPY pyproject.toml README.md ./
COPY apps/api/src apps/api/src
RUN python -m pip install --no-cache-dir ".[live,warehouse]"

COPY --from=web-builder --chown=changesafe:changesafe /build/apps/web/dist /app/web
COPY --chown=changesafe:changesafe fixtures/datahub /app/fixtures/datahub
RUN mkdir -p /data && chown changesafe:changesafe /data

USER changesafe
EXPOSE 8000
VOLUME ["/data"]

HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=5 \
  CMD ["python", "-c", "import json,urllib.request; assert json.load(urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2))['status'] == 'ok'"]

STOPSIGNAL SIGTERM
CMD ["uvicorn", "changesafe.main:app", "--host", "0.0.0.0", "--port", "8000"]
