# ChangeSafe demo script (about 2 minutes 35 seconds)

## 0:00–0:20 — Frame the problem

Open ChangeSafe at the shared review URL.

> A field rename can pass code review and still damage reports, operations, privacy controls, and trust in decisions. ChangeSafe asks DataHub what the field means and who depends on it before any code can be published.

Point to **Recorded DataHub evidence**, **Preview only**, the evidence ID, and the reproducibility note.

> Reviewers need no accounts or API keys. This run uses a checksummed DataHub evidence snapshot and labels that provenance clearly. The same request plus the same evidence produces the same verified result.

## 0:20–0:45 — Use the organizer-provided scenario

Point to **Official DataHub showcase-ecommerce**, the `Order Entry Analytics` product, and the preloaded `order_details.cust_email` to `primary_email` rename. Click **Analyze change**.

> This is not an invented toy graph. The hackathon's ecommerce datapack contains 1,049 entities across dbt, Snowflake, Looker, Power BI, Tableau, Spark, PostgreSQL, and S3. Our replay preserves the exact contract and evidence used by this workflow.

## 0:45–1:25 — Watch the real process

Follow the **Change process** rail as server events arrive: read the contract, find dependencies, classify impact, prepare the migration, prove it safe, and stop for the owner.

> These are persisted backend events, not a pre-timed animation. The sequence number and relative time come from the server. A local recorded run can complete in a fraction of a second because it has no catalog network wait; refreshing the browser restores the run and rebuilds its history.

Follow the moving lineage signal from the upstream inputs through `order_details` to its consumers, then open **Customer Analytics Measures**.

> ChangeSafe records seven Snowflake, Power BI, and Looker dependents. Direct and multi-hop relationships are labeled separately, and the evidence drawer shows the underlying URNs. A DataHub link appears only when the operator supplies a safe catalog origin.

Click **Trace supporting evidence** on two or three impact findings and watch unrelated nodes dim.

> The deterministic score is 80/Critical: 25 for the rename, 25 for seven downstream assets, and 10 each for governed PII, high usage, and cross-domain impact. The six impact cards explain data integrity, privacy, operations, decision trust, financial exposure, and organizational impact. Financial harm is deliberately marked “Potentially high, not quantified” because metadata cannot prove a dollar amount.

## 1:25–1:55 — Inspect the safe migration

Show the SQL file, YAML, compatibility test, rollback guide, migration note, PR body, and manifest. For each tab, point to **What this file does** and **Failure this prevents**.

> Phase one keeps `cust_email` and introduces `primary_email`, giving consumers a deprecation window. Every one of the seven allowed files has an exact hash.

If demonstrating **Remove**, open the singular SQL guard:

> The `where false` query is intentional. It returns no rows while `cust_email` still compiles, but fails compilation if someone removes the field before phase one is complete. It is a release guard, not a business-data test.

Expand validation.

> Twelve blocking checks compare the request to DataHub, reject duplicate outputs, parse SQL, validate dbt YAML, forbid unqualified star selection, verify compatibility and rollback guidance, and recompute the manifest. One failure keeps publication locked.

## 1:55–2:20 — Approve without pretending to publish

Click **Approve preview**.

> Replay approval produces the exact patch but makes no external write.

Point to **Preview ready** and **NOT WRITTEN — SNAPSHOT MODE**, then download the patch.

> With owner-enabled live settings, the same verified bytes can create one GitHub pull request and write an idempotent decision record to the allowlisted DataHub asset. Crash-safe checkpoints prevent duplicate or mixed publication.

## 2:20–2:35 — Close with accountability

If the private operator control is enabled, open **Review activity** without exposing the token on screen.

> The operator can see privacy-limited anonymous review sessions and current states. ChangeSafe stores no reviewer identity, IP address, or browser fingerprint. The repository includes the official scenario snapshot, sample artifacts, tests, Docker image, CI, architecture, and this credential-free workflow.

If live credentials are available, show only already-verified live receipts. Never describe a replay receipt as a DataHub or GitHub write.
