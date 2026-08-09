# Contributing to ChangeSafe

Thank you for helping improve ChangeSafe. Keep changes small, evidence-backed, and safe by default.

## Development setup

Use Python 3.12, Node.js 24, and pnpm 11.16.0.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev,live]"
corepack enable
corepack prepare pnpm@11.16.0 --activate
pnpm install --frozen-lockfile
```

Start replay development with `.\scripts\dev.ps1`. Do not require credentials for default tests or examples.

## Change expectations

- Add or update a failing test before changing behavior.
- Preserve strict Pydantic models and the live/replay context contract.
- Keep release artifact generation on reviewed deterministic templates; do not add a runtime planning authority for risk, output paths, validation, or approval.
- Keep external writes disabled by default and behind the admin token, feature flag, and URN allowlist.
- Do not weaken a blocking verifier check without a documented security rationale.
- Do not commit credentials, `.env` files, databases, browser traces, or private metadata exports.
- Update architecture and operator documentation when contracts or configuration change.

## Required checks

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m mypy apps/api/src
.\.venv\Scripts\python.exe -m pytest -q
pnpm --filter @changesafe/web lint
pnpm --filter @changesafe/web typecheck
pnpm --filter @changesafe/web test --run
pnpm --filter @changesafe/web build
pnpm exec playwright test
python scripts/check_secrets.py
```

Run `docker build -t changesafe:local .` when changing dependencies, packaging, runtime configuration, or static serving.

## Pull requests

Describe the user-visible outcome, safety impact, tests run, and any live credentials or external systems intentionally not exercised. Include screenshots for UI changes and never place a real token in logs or review comments.
