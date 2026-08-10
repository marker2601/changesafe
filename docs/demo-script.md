# ChangeSafe judge demo (about 3 minutes)

## 0:00–0:25 — Establish the evidence boundary

Open the temporary review URL and point to the two separate truth labels in the hero.

> ChangeSafe lets a reviewer select any field returned by the allowlisted DataHub schema. It traces exact metadata routes, computes a deterministic factor score, generates a compatibility shim, verifies the exact bytes, optionally checks aggregate non-production warehouse safety, and pauses for the accountable owner.

For the credential-free walkthrough, show **Recorded DataHub evidence checked**, **Preview only**, and **Production rows not queried**.

> This replay uses a SHA-256-verified recording of DataHub metadata. It exercises the real API, event store, policy, generator, verifier, approval, and patch download, but it is not a current DataHub read and it does not prove warehouse values. No raw production values or query text enter the browser.

## 0:25–1:10 — Rename `cust_email` to `primary_email`

Focus **Current field**, type `cust_email`, and press Enter. Confirm the returned native type and nullability, leave **Rename field** selected, enter `primary_email`, and choose **Analyze change**.

> The active catalog contains exactly 55 concrete `order_details` fields. The selected field—not a hard-coded email branch—binds the request, context, risk factors, routes, generated paths, and warehouse policy record.

Follow the persisted process events. Show the six upstream routes, the 25 downstream routes, and the factor ledger. Open a direct route with the keyboard, close the evidence drawer with Escape, and show that focus returns to the same route.

> Exact routes name both endpoints. Multi-hop routes disclose when DataHub did not return an intermediate column mapping. Dataset-level relationships never receive an invented field suffix.

Inspect the seven-file package and the **12 / 12** static validation result.

> The generated dbt model is a separately named phase-one compatibility shim. The base `order_details` model stays unchanged while old and new fields coexist. Every displayed file is the exact hashed byte sequence that approval would publish.

## 1:10–1:45 — Remove `order_status`

Choose **New analysis**. Select `order_status` with the keyboard, choose **Remove field**, and analyze.

> Remove does not drop the field immediately. The generated package retains it during phase one, adds an operation-specific compatibility test, and requires every recorded consumer to migrate before final removal.

Show the six upstream and 27 downstream field-scoped relationships, the deterministic factor ledger, seven artifacts, 12 / 12 static checks, and **Production rows not queried**.

## 1:45–2:15 — Change `order_total` to `VARCHAR(320)`

Choose **New analysis**. Select `order_total` with the keyboard, choose **Change type**, enter `VARCHAR(320)`, and analyze.

> ChangeSafe generates a temporary casted compatibility field and a comparison test. Metadata and static SQL validation can prove the package structure; only configured read-only aggregate warehouse validation can establish current value compatibility.

Show the six upstream and 31 downstream relationships and the operation-specific `cast(order_total as VARCHAR(320))` bytes.

## 2:15–2:35 — Show fail-closed invalid cases

Start a rename and enter the existing destination `ORDER_TOTAL`.

> Destination checks are case-insensitive. A collision is rejected before a run starts.

Type a field that is not in the returned catalog without committing a selection.

> Analyze remains disabled; ChangeSafe cannot silently submit the previously selected field.

Explain the automated acceptance cases: an unsafe type aggregate result, a warehouse timeout, or required warehouse evidence that was not run all preserve inspectable evidence but block approval. In `auto` mode, a live DataHub outage pauses at **Live DataHub is unavailable** and continues with recorded evidence only after **Continue with labeled snapshot** is chosen.

## 2:35–2:55 — Approve the replay truthfully

Return to a passing replay result and choose **Approve preview**. Show **Preview ready**, **NOT WRITTEN — SNAPSHOT MODE**, and download the patch.

> Approval is enabled only for a persisted policy pass. Replay approval creates a downloadable patch and no external mutation. A lost approval response is reconciled from the durable receipt instead of repeating the side effect.

## 2:55–3:00 — State the live proof precisely

> The final local smoke read the live 55-field DataHub schema and completed three no-mutation preview operations with live provenance, seven artifacts, and 12 / 12 static checks. Snowflake credentials were not supplied: **Production rows not queried**. The public address is a temporary rotating QA tunnel, not stable judge hosting.

Never show a token, private service URL, raw row, query text, relation name, or warehouse identifier. Never call a replay receipt a live DataHub or warehouse pass.
