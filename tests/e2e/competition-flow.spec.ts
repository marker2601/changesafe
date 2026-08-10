import {
  expect,
  request as playwrightRequest,
  type Page,
  type Request,
  test,
} from "@playwright/test";

import type {
  PublicConfig,
  RunEvent,
  RunState,
  RunView,
  SchemaCatalog,
  WarehouseValidationResult,
} from "../../apps/web/src/types";

const port = Number(process.env.CHANGESAFE_E2E_PORT ?? "8765");
const baseURL = `http://127.0.0.1:${port}`;
const runSessionKey = "changesafe.active-run.v1";

const scenarios = [
  {
    field: "cust_email",
    operation: "Rename",
    destination: "primary_email",
    viewport: { width: 1440, height: 1024 },
  },
  {
    field: "order_status",
    operation: "Remove",
    viewport: { width: 430, height: 932 },
    reducedMotion: true,
  },
  {
    field: "order_total",
    operation: "Change type",
    newType: "VARCHAR(320)",
    viewport: { width: 1440, height: 1024 },
    reducedMotion: true,
  },
] as const;

let canonicalRun: RunView;
let canonicalConfig: PublicConfig;
let canonicalSchema: SchemaCatalog;

function clone<T>(value: T): T {
  return structuredClone(value);
}

function collectBrowserErrors(page: Page) {
  const consoleErrors: string[] = [];
  const pageErrors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  page.on("pageerror", (error) => pageErrors.push(error.message));
  return { consoleErrors, pageErrors };
}

async function selectFieldByKeyboard(page: Page, field: string) {
  const combobox = page.getByRole("combobox", { name: "Current field" });
  await combobox.fill(field);
  await expect(page.getByRole("option", { name: new RegExp(`^${field}\\b`, "i") })).toBeVisible();
  await combobox.press("Enter");
  await expect(combobox).toHaveValue(field);
  await expect(combobox).toHaveAttribute("aria-expanded", "false");
}

async function chooseOperation(page: Page, operation: (typeof scenarios)[number]["operation"]) {
  const value =
    operation === "Rename"
      ? "rename"
      : operation === "Remove"
        ? "remove"
        : "type_change";
  await page.getByLabel("Operation").selectOption(value);
}

async function completeOperationFields(
  page: Page,
  scenario: (typeof scenarios)[number],
) {
  if ("destination" in scenario) {
    await page.getByLabel("New field").fill(scenario.destination);
  }
  if ("newType" in scenario) {
    await page.getByLabel("New type").fill(scenario.newType);
  }
}

async function expectNoHorizontalOverflow(page: Page) {
  await expect
    .poll(() =>
      page.evaluate(() => ({
        clientWidth: document.documentElement.clientWidth,
        scrollWidth: document.documentElement.scrollWidth,
      })),
    )
    .toEqual(
      await page.evaluate(() => ({
        clientWidth: document.documentElement.clientWidth,
        scrollWidth: document.documentElement.clientWidth,
      })),
    );
}

function createdRun(finalRun: RunView): RunView {
  return {
    ...clone(finalRun),
    state: "created",
    analysis: null,
    publication: null,
    error: null,
  };
}

function runEvent(
  run: RunView,
  sequence: number,
  state: RunState,
  publicMessage: string,
): RunEvent {
  return {
    run_id: run.run_id,
    sequence,
    state,
    public_message: publicMessage,
    evidence: [],
    created_at: run.updated_at,
  };
}

function sseBody(events: RunEvent[]): string {
  return events
    .map(
      (event) =>
        `id: ${event.sequence}\nevent: run_state\ndata: ${JSON.stringify(event)}\n\n`,
    )
    .join("");
}

async function fulfillJson(route: Parameters<Parameters<Page["route"]>[1]>[0], body: unknown, status = 200) {
  await route.fulfill({
    body: JSON.stringify(body),
    contentType: "application/json",
    status,
  });
}

async function installCatalogRoutes(
  page: Page,
  config: PublicConfig = canonicalConfig,
  schema: SchemaCatalog = canonicalSchema,
) {
  await page.route("**/api/public-config", (route) => fulfillJson(route, config));
  await page.route("**/api/schema-fields?*", (route) => fulfillJson(route, schema));
}

async function installTerminalRunFlow(page: Page, finalRun: RunView) {
  const accepted = createdRun(finalRun);
  await page.route(/\/api\/runs$/, (route) => fulfillJson(route, accepted, 202));
  await page.route(/\/api\/runs\/[^/]+$/, (route) => fulfillJson(route, finalRun));
  await page.route(/\/api\/runs\/[^/]+\/events(?:\?.*)?$/, (route) =>
    route.fulfill({
      body: sseBody([
        runEvent(finalRun, 1, finalRun.state, finalRun.error?.message ?? "Run settled"),
      ]),
      contentType: "text/event-stream",
      headers: { "Cache-Control": "no-cache" },
      status: 200,
    }),
  );
}

function liveRunWithWarehouse(
  warehouse: WarehouseValidationResult,
  overrides: Partial<RunView> = {},
): RunView {
  const run = clone(canonicalRun);
  if (!run.analysis) throw new Error("Canonical replay analysis is missing.");
  run.analysis.context.provenance = {
    ...run.analysis.context.provenance,
    mode: "live",
    snapshot_hash: null,
  };
  run.analysis.warehouse_validation = warehouse;
  return { ...run, ...overrides };
}

test.beforeAll(async () => {
  const api = await playwrightRequest.newContext({ baseURL });
  try {
    canonicalConfig = await (await api.get("/api/public-config")).json();
    const accepted = await api.post("/api/runs", {
      data: {
        asset_urn:
          "urn:li:dataset:(urn:li:dataPlatform:dbt,b2fd91.ORDER_ENTRY_DB.analytics.order_details,PROD)",
        operation: "rename",
        field: "cust_email",
        new_field: "primary_email",
        old_type: null,
        new_type: null,
        source_commit: "showcase-ecommerce-safe-rename",
        requested_by: "competition-e2e-fixture",
      },
    });
    expect(accepted.status()).toBe(202);
    const created = (await accepted.json()) as RunView;
    await expect
      .poll(
        async () => {
          canonicalRun = (await (
            await api.get(`/api/runs/${created.run_id}`)
          ).json()) as RunView;
          return canonicalRun.state;
        },
        { timeout: 20_000 },
      )
      .toBe("awaiting_approval");
    canonicalSchema = {
      target_urn: canonicalRun.analysis!.context.target_urn,
      target_name: canonicalRun.analysis!.context.target_name,
      schema_fields: canonicalRun.analysis!.context.schema_fields,
      provenance: canonicalRun.analysis!.context.provenance,
    };
    expect(canonicalSchema.schema_fields).toHaveLength(55);
  } finally {
    await api.dispose();
  }
});

for (const scenario of scenarios) {
  test(`${scenario.operation} uses selected-field evidence`, async ({ page }) => {
    const browserErrors = collectBrowserErrors(page);
    await page.setViewportSize(scenario.viewport);
    if ("reducedMotion" in scenario) {
      await page.emulateMedia({ reducedMotion: "reduce" });
    }
    await page.goto("/");
    const heroBefore = await page.locator(".product-hero").boundingBox();
    expect(heroBefore).not.toBeNull();

    await selectFieldByKeyboard(page, scenario.field);
    await chooseOperation(page, scenario.operation);
    await completeOperationFields(page, scenario);
    await page.getByRole("button", { name: "Analyze change" }).click();

    await expect(page.getByText(new RegExp(scenario.field, "i")).first()).toBeVisible();
    await expect(
      page.getByRole("heading", { name: /Warehouse validation/i }),
    ).toBeVisible();
    await expect(page.getByText("Production rows not queried").first()).toBeVisible();
    await expect(page.getByTestId("artifact-file")).toHaveCount(7);
    await expect(page.getByText("12 / 12", { exact: true })).toBeVisible();

    const heroAfter = await page.locator(".product-hero").boundingBox();
    expect(heroAfter).not.toBeNull();
    expect(Math.abs(heroAfter!.height - heroBefore!.height)).toBeLessThan(1);
    await expectNoHorizontalOverflow(page);

    const routes = page.locator("#dependency-evidence-map button");
    expect(await routes.count()).toBeGreaterThan(0);
    const routeChecks = await routes.count();
    for (let index = 0; index < routeChecks; index += 1) {
      const route = routes.nth(index);
      await route.focus();
      await expect(route).toBeFocused();
      await route.press("Enter");
      const drawer = page.getByRole("dialog", { name: /Evidence for/i });
      await expect(drawer).toBeVisible();
      await expect(page.getByRole("button", { name: "Close evidence" })).toBeFocused();
      await page.keyboard.press("Escape");
      await expect(drawer).toBeHidden();
      await expect(route).toBeFocused();
    }

    if ("reducedMotion" in scenario) {
      await expect(page.locator(".lineage-flow-light").first()).toHaveCSS(
        "display",
        "none",
      );
      await expect(page.locator(".field-route-arrow").first()).toBeVisible();
    }

    if (scenario.operation === "Rename") {
      const saved = await page.evaluate((key) => sessionStorage.getItem(key), runSessionKey);
      expect(saved).not.toBeNull();
      const runId = (JSON.parse(saved!) as { runId: string }).runId;
      let approvalReachedServer = false;
      await page.route(`**/api/runs/${runId}/approve`, async (route) => {
        const response = await route.fetch();
        approvalReachedServer = response.ok();
        await route.fulfill({
          body: "",
          contentType: "application/json",
          status: 200,
        });
      });
      await page.getByRole("button", { name: "Approve preview" }).click();
      await expect(page.getByText("Preview ready", { exact: true })).toBeVisible();
      expect(approvalReachedServer).toBe(true);
      await expect(page.getByRole("alert")).toHaveCount(0);
    }

    expect(browserErrors.consoleErrors).toEqual([]);
    expect(browserErrors.pageErrors).toEqual([]);
  });
}

test("invalid rename collision is blocked before a run starts", async ({ page }) => {
  await page.goto("/");
  await selectFieldByKeyboard(page, "cust_email");
  await page.getByLabel("New field").fill("ORDER_TOTAL");

  await expect(page.getByRole("alert")).toContainText(/already exists/i);
  await expect(page.getByRole("button", { name: "Analyze change" })).toBeDisabled();
});

test("missing field cannot submit the previously selected field", async ({ page }) => {
  await page.goto("/");
  const field = page.getByRole("combobox", { name: "Current field" });
  await field.fill("field_that_does_not_exist");

  await expect(page.getByText("No matching DataHub fields.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Analyze change" })).toBeDisabled();
  await field.press("Tab");
  await expect(page.getByRole("button", { name: "Analyze change" })).toBeDisabled();
});

test("unsafe type warehouse evidence blocks approval after aggregate counts", async ({ page }) => {
  const warehouse: WarehouseValidationResult = {
    ...clone(canonicalRun.analysis!.warehouse_validation),
    status: "blocked",
    mode: "aggregate",
    operation: "type_change",
    field: "order_total",
    aggregate_query_started: true,
    started_at: "2026-08-10T12:00:00Z",
    completed_at: "2026-08-10T12:00:00.018Z",
    rows_evaluated: 20,
    populated_row_count: 20,
    unsafe_row_count: 2,
    query_ids: ["aggregate-query-redacted"],
    elapsed_ms: 18,
    checks: [
      {
        code: "unsafe_conversion",
        label: "Safe type conversion",
        passed: false,
        retryable: false,
        detail: "Aggregate evidence found values that cannot be converted safely.",
        observed_count: 2,
      },
    ],
  };
  const failed = liveRunWithWarehouse(warehouse, {
    state: "failed",
    request: {
      ...canonicalRun.request,
      operation: "type_change",
      field: "order_total",
      new_field: null,
      old_type: "FLOAT",
      new_type: "VARCHAR(320)",
    },
    error: {
      code: "WAREHOUSE_VALIDATION_FAILED",
      message: "Warehouse validation did not pass.",
      retryable: false,
    },
  });
  failed.analysis!.context.field = "order_total";
  failed.analysis!.context.field_type = "FLOAT";
  failed.analysis!.publication_eligible = false;
  failed.analysis!.approval_blockers = [
    {
      code: "WAREHOUSE_VALIDATION_FAILED",
      message: "Warehouse validation did not pass.",
      retryable: false,
    },
  ];
  await installCatalogRoutes(page);
  await installTerminalRunFlow(page, failed);
  await page.goto("/");
  await selectFieldByKeyboard(page, "order_total");
  await chooseOperation(page, "Change type");
  await page.getByLabel("New type").fill("VARCHAR(320)");
  await page.getByRole("button", { name: "Analyze change" }).click();

  await expect(page.getByText("Unsafe rows").locator("..")).toContainText("2");
  await expect(page.getByText("Safe type conversion")).toBeVisible();
  await expect(page.getByText("Warehouse validation did not pass.")).toBeVisible();
  await expect(page.getByRole("button", { name: /Approve|Publish/ })).toHaveCount(0);
});

test("live outage requires explicit recorded fallback", async ({ page }) => {
  const autoConfig: PublicConfig = {
    ...canonicalConfig,
    mode: "auto",
    live_context_available: true,
  };
  let phase: "fallback" | "continued" = "fallback";
  const fallbackRun: RunView = {
    ...createdRun(canonicalRun),
    state: "context_fallback_required",
    error: {
      code: "LIVE_CONTEXT_UNAVAILABLE",
      message: "Live metadata context is unavailable. Snapshot replay requires confirmation.",
      retryable: true,
    },
  };
  await page.route("**/api/public-config", (route) => fulfillJson(route, autoConfig));
  await page.route("**/api/schema-fields?*", (route) => {
    const url = new URL(route.request().url());
    if (url.searchParams.get("source") === "recorded") {
      return fulfillJson(route, canonicalSchema);
    }
    return fulfillJson(route, { detail: "DataHub schema could not be loaded" }, 502);
  });
  await page.route(/\/api\/runs$/, (route) => fulfillJson(route, createdRun(canonicalRun), 202));
  await page.route(/\/api\/runs\/[^/]+\/continue-with-snapshot$/, async (route) => {
    phase = "continued";
    await fulfillJson(route, { ...createdRun(canonicalRun), state: "loading_context" }, 202);
  });
  await page.route(/\/api\/runs\/[^/]+$/, (route) =>
    fulfillJson(route, phase === "fallback" ? fallbackRun : canonicalRun),
  );
  await page.route(/\/api\/runs\/[^/]+\/events(?:\?.*)?$/, (route) => {
    const event =
      phase === "fallback"
        ? runEvent(fallbackRun, 1, "context_fallback_required", "Live context unavailable; confirmation required")
        : runEvent(canonicalRun, 2, "awaiting_approval", "Waiting for the accountable owner");
    return route.fulfill({
      body: sseBody([event]),
      contentType: "text/event-stream",
      status: 200,
    });
  });

  await page.goto("/");
  await expect(page.getByRole("alert")).toContainText(/DataHub schema could not be loaded/i);
  await page.getByRole("button", { name: "Use recorded fields" }).click();
  await page.getByRole("button", { name: "Analyze change" }).click();
  await expect(page.getByRole("heading", { name: "Live DataHub is unavailable" })).toBeVisible();
  await expect(page.getByText(/requires confirmation/i)).toBeVisible();
  await page.getByRole("button", { name: "Continue with labeled snapshot" }).click();
  await expect(page.getByText("Recorded DataHub evidence checked").first()).toBeVisible();
  await page.getByText("About this run", { exact: true }).click();
  await expect(
    page.getByText(/A live DataHub read was attempted but could not complete/i),
  ).toBeVisible();
  await expect(page.getByText(/continued with checksum-verified recorded metadata/i)).toBeVisible();
  await expect(page.getByText("Production rows not queried").first()).toBeVisible();
});

test("warehouse timeout and required-not-run evidence remain non-approvable", async ({ page }) => {
  const requiredConfig: PublicConfig = {
    ...canonicalConfig,
    mode: "live",
    live_context_available: true,
    live_evidence_required: true,
    warehouse_validation_available: true,
    warehouse_validation_required: true,
  };
  const timeoutWarehouse: WarehouseValidationResult = {
    ...clone(canonicalRun.analysis!.warehouse_validation),
    status: "blocked",
    mode: "aggregate",
    aggregate_query_started: true,
    started_at: "2026-08-10T12:00:00Z",
    completed_at: "2026-08-10T12:00:00.100Z",
    elapsed_ms: 100,
    checks: [
      {
        code: "warehouse_timeout",
        label: "Warehouse validation timeout",
        passed: false,
        retryable: true,
        detail: "Warehouse validation timed out.",
        observed_count: null,
      },
    ],
  };
  const timedOut = liveRunWithWarehouse(timeoutWarehouse, {
    state: "failed",
    error: {
      code: "WAREHOUSE_VALIDATION_FAILED",
      message: "Warehouse validation did not pass.",
      retryable: true,
    },
  });
  timedOut.analysis!.publication_eligible = false;
  timedOut.analysis!.approval_blockers = [
    {
      code: "WAREHOUSE_VALIDATION_FAILED",
      message: "Warehouse validation did not pass.",
      retryable: true,
    },
  ];
  await installCatalogRoutes(page, requiredConfig);
  await installTerminalRunFlow(page, timedOut);
  await page.goto("/");
  await page.getByRole("button", { name: "Analyze change" }).click();

  await expect(page.getByText("Warehouse validation timeout")).toBeVisible();
  await expect(page.getByText("Warehouse validation timed out.")).toBeVisible();
  await expect(page.getByText("Warehouse validation did not pass.")).toBeVisible();
  await expect(page.getByRole("button", { name: /Approve|Publish/ })).toHaveCount(0);

  const requiredNotRun = liveRunWithWarehouse(
    clone(canonicalRun.analysis!.warehouse_validation),
    {
      state: "failed",
      error: {
        code: "WAREHOUSE_EVIDENCE_REQUIRED",
        message: "Warehouse validation evidence is required for approval.",
        retryable: true,
      },
    },
  );
  requiredNotRun.analysis!.publication_eligible = false;
  requiredNotRun.analysis!.approval_blockers = [requiredNotRun.error!];
  await page.unroute(/\/api\/runs\/[^/]+$/);
  await page.route(/\/api\/runs\/[^/]+$/, (route) => fulfillJson(route, requiredNotRun));
  await page.evaluate(
    ({ key, runId }) => sessionStorage.setItem(key, JSON.stringify({ runId, lastSequence: 0 })),
    { key: runSessionKey, runId: requiredNotRun.run_id },
  );
  await page.reload();
  await expect(page.getByText("Production rows not queried").first()).toBeVisible();
  await expect(
    page.getByText("Warehouse validation evidence is required for approval."),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: /Approve|Publish/ })).toHaveCount(0);
});

test("refresh in warehouse validation keeps approval disabled until a pass", async ({ page }) => {
  const requiredConfig: PublicConfig = {
    ...canonicalConfig,
    mode: "live",
    live_context_available: true,
    live_evidence_required: true,
    warehouse_validation_available: true,
    warehouse_validation_required: true,
  };
  const passedWarehouse: WarehouseValidationResult = {
    ...clone(canonicalRun.analysis!.warehouse_validation),
    status: "passed",
    mode: "aggregate",
    aggregate_query_started: true,
    started_at: "2026-08-10T12:00:00Z",
    completed_at: "2026-08-10T12:00:00.018Z",
    rows_evaluated: 20,
    populated_row_count: 20,
    unsafe_row_count: 0,
    query_ids: ["aggregate-query-redacted"],
    elapsed_ms: 18,
    checks: [
      {
        code: "aggregate_validation",
        label: "Aggregate validation",
        passed: true,
        retryable: false,
        detail: "Aggregate checks passed.",
        observed_count: 0,
      },
    ],
  };
  const passed = liveRunWithWarehouse(passedWarehouse);
  passed.analysis!.publication_eligible = true;
  passed.analysis!.approval_blockers = [];
  const validating = {
    ...createdRun(passed),
    state: "validating_warehouse" as const,
  };
  let released = false;
  let releaseStream: (() => void) | undefined;
  const streamGate = new Promise<void>((resolve) => {
    releaseStream = () => {
      released = true;
      resolve();
    };
  });
  await installCatalogRoutes(page, requiredConfig);
  await page.route(/\/api\/runs\/[^/]+$/, (route) =>
    fulfillJson(route, released ? passed : validating),
  );
  await page.route(/\/api\/runs\/[^/]+\/events(?:\?.*)?$/, async (route) => {
    await streamGate;
    await route.fulfill({
      body: sseBody([
        runEvent(passed, 7, "awaiting_approval", "Waiting for the accountable owner"),
      ]),
      contentType: "text/event-stream",
      status: 200,
    });
  });
  await page.addInitScript(
    ({ key, runId }) => sessionStorage.setItem(key, JSON.stringify({ runId, lastSequence: 6 })),
    { key: runSessionKey, runId: passed.run_id },
  );

  await page.goto("/");
  await expect(page.getByText("Warehouse validation in progress")).toBeVisible();
  await expect(page.getByRole("button", { name: /Approve|Publish/ })).toHaveCount(0);
  await page.reload();
  await expect(page.getByText("Warehouse validation in progress")).toBeVisible();
  releaseStream?.();
  await expect(page.getByText("Warehouse values checked · competition-non-production").first()).toBeVisible();
  await expect(page.getByRole("button", { name: "Approve preview" })).toBeEnabled();
});

test("terminal SSE EOF reconciles without a false disconnection", async ({ page }) => {
  let durableReads = 0;
  const browserErrors = collectBrowserErrors(page);
  await installCatalogRoutes(page);
  await page.route(/\/api\/runs$/, (route) => fulfillJson(route, createdRun(canonicalRun), 202));
  await page.route(/\/api\/runs\/[^/]+$/, async (route) => {
    durableReads += 1;
    await fulfillJson(route, canonicalRun);
  });
  await page.route(/\/api\/runs\/[^/]+\/events(?:\?.*)?$/, (route) =>
    route.fulfill({
      body: sseBody([
        runEvent(canonicalRun, 6, "awaiting_approval", "Waiting for the accountable owner"),
      ]),
      contentType: "text/event-stream",
      status: 200,
    }),
  );

  await page.goto("/");
  await page.getByRole("button", { name: "Analyze change" }).click();
  await expect(page.getByText("Waiting for the accountable owner").first()).toBeVisible();
  await expect.poll(() => durableReads).toBeGreaterThan(0);
  await expect(page.getByText("Live progress disconnected. Refresh to resume this run.")).toHaveCount(0);
  expect(browserErrors.consoleErrors).toEqual([]);
  expect(browserErrors.pageErrors).toEqual([]);
});
