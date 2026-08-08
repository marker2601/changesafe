# ChangeSafe demo script (about 2 minutes 30 seconds)

## 0:00-0:20 - Frame the problem

Open ChangeSafe at the replay URL.

> A column rename can look harmless in a pull request while breaking dashboards, campaigns, support workflows, and models. ChangeSafe checks organizational metadata before code is published.

Point to **Snapshot replay** and **Preview only / snapshot mode**.

> This run uses a checksummed DataHub snapshot, so judges need no accounts and every replay is honest about its evidence source.

## 0:20-0:45 - Submit the unsafe change

Show the preloaded `dim_customers.customer_email` to `primary_email` rename and click **Analyze change**.

> The API assigns an opaque run ID and streams explicit states while it loads context, scores risk, generates artifacts, and validates them.

## 0:45-1:20 - Explain evidence and risk

Show 90/Critical, the factor ledger, and the four lineage cards.

> The score is deterministic: 25 for rename, 20 for four downstream assets, 15 for an executive report, and 10 each for PII, high usage, and cross-domain impact. The LLM cannot change a point.

Name the Analytics, Marketing, Support, and Executive Reporting consumers. Point to the checksummed snapshot label.

## 1:20-1:55 - Inspect the safe migration

Show the SQL file and switch briefly to YAML, the compatibility test, rollback, and PR body.

> ChangeSafe generates exactly seven allowlisted files. Phase one keeps the old field and adds the new field, so consumers have a deprecation window. Every artifact has an exact hash.

Expand validation.

> Twelve blocking checks also require DataHub/request alignment and case-insensitively unique SQL/YAML outputs, then parse SQL, validate dbt YAML, reject SELECT star, confirm compatibility, verify rollback content, and recompute the manifest. Publication stays locked if any check fails.

## 1:55-2:20 - Approve safely

Click **Approve preview**.

> Approval in replay prepares a patch, but performs no external write.

Point to **Preview ready** and **NOT WRITTEN - SNAPSHOT MODE**, then download the patch.

> In owner-enabled live mode, the same verified bytes can create a GitHub pull request and an allowlisted DataHub decision record. Both steps share an artifact-bound idempotency key, so retries do not duplicate completed work.

## 2:20-2:30 - Close with reproducibility

> The repository includes the snapshot checksum, DataHub seed scenario, tests, Docker image, CI, architecture, and this exact credential-free workflow. A clean clone starts with `docker compose up --build`.

If live credentials are available, use the remaining time to show the real PR and DataHub receipt. Do not describe a replay receipt as a live write.
