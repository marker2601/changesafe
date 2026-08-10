import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { pathToFileURL } from "node:url";

import { chromium } from "@playwright/test";

import {
  assertSafeBaseUrl,
  overlayModel,
  validateTimingManifest,
} from "./capture_contract.mjs";

const OFFICIAL_TARGET =
  "urn:li:dataset:(urn:li:dataPlatform:dbt,b2fd91.ORDER_ENTRY_DB.analytics.order_details,PROD)";
const REPOSITORY_URL = "https://github.com/marker2601/changesafe";

function parseArgs(values) {
  const result = {};
  for (let index = 0; index < values.length; index += 2) {
    const key = values[index];
    const value = values[index + 1];
    if (!key?.startsWith("--") || !value) {
      throw new Error("Capture arguments must be supplied as --name value pairs.");
    }
    result[key.slice(2)] = value;
  }
  for (const required of ["base-url", "timing", "work-dir"]) {
    if (!result[required]) throw new Error(`Missing required --${required}.`);
  }
  return result;
}

function sleep(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

async function publicJson(url) {
  const response = await fetch(url, {
    headers: { Accept: "application/json" },
    redirect: "error",
    signal: AbortSignal.timeout(60_000),
  });
  if (!response.ok) throw new Error(`Hosted preflight failed with HTTP ${response.status}.`);
  return response.json();
}

async function preflight(baseUrl) {
  const schemaUrl = new URL("/api/schema-fields", baseUrl);
  schemaUrl.searchParams.set("asset_urn", OFFICIAL_TARGET);
  schemaUrl.searchParams.set("source", "active");
  const [health, config, schema] = await Promise.all([
    publicJson(new URL("/healthz", baseUrl)),
    publicJson(new URL("/api/public-config", baseUrl)),
    publicJson(schemaUrl),
  ]);
  if (health.status !== "ok") throw new Error("Hosted health check is not ok.");
  if (
    config.mode !== "replay" ||
    config.live_context_available !== false ||
    config.github_publication_available !== false ||
    config.datahub_writeback_available !== false ||
    config.warehouse_validation_available !== false ||
    config.warehouse_validation_required !== false
  ) {
    throw new Error("Hosted safety configuration does not match competition replay mode.");
  }
  if (
    schema?.provenance?.mode !== "snapshot" ||
    !Array.isArray(schema.schema_fields) ||
    schema.schema_fields.length !== 55
  ) {
    throw new Error("Hosted schema evidence is not the approved 55-field snapshot.");
  }
  return {
    schemaFieldCount: schema.schema_fields.length,
    snapshotHash: schema.provenance.snapshot_hash,
  };
}

export function titlePage({ closing = false } = {}) {
  const eyebrow = closing ? "DATAHUB CHANGE INTELLIGENCE" : "CHANGE SAFE / BEFORE YOU SHIP";
  const title = closing
    ? "Evidence-bound. Fail-closed. Human-approved."
    : "A column rename is never just a rename.";
  const detail = closing
    ? "DataHub context keeps every dependency in view."
    : "Trace the contract. Generate the migration. Prove the change. Then ask the owner.";
  const footer = closing
    ? `${REPOSITORY_URL.replace("https://", "")}  ·  changesafe-competition.onrender.com`
    : "DataHub context  →  ChangeSafe  →  verified migration decision";
  return `<!doctype html>
<html><head><meta charset="utf-8"><style>
*{box-sizing:border-box}html,body{width:100%;height:100%;margin:0;overflow:hidden}
body{font-family:Inter,ui-sans-serif,system-ui;background:#00141d;color:#f3edda}
.grid{position:absolute;inset:0;background-image:linear-gradient(rgba(39,216,198,.07) 1px,transparent 1px),linear-gradient(90deg,rgba(39,216,198,.07) 1px,transparent 1px);background-size:56px 56px;mask-image:linear-gradient(to bottom,black,transparent)}
.halo{position:absolute;width:760px;height:760px;border:1px solid rgba(39,216,198,.28);border-radius:50%;right:-150px;top:-220px;box-shadow:0 0 90px rgba(39,216,198,.12)}
.mark{position:absolute;left:112px;top:76px;display:flex;align-items:center;gap:18px;font-weight:900;letter-spacing:.1em;font-size:27px}.mark i{display:block;width:38px;height:38px;border:5px solid #27d8c6;border-radius:9px;transform:rotate(45deg);box-shadow:0 0 28px rgba(39,216,198,.55)}
main{position:absolute;left:112px;right:180px;top:240px}.eyebrow{color:#27d8c6;font-size:18px;font-weight:850;letter-spacing:.18em}h1{font-size:72px;line-height:1.03;letter-spacing:-.045em;max-width:1250px;margin:28px 0 24px}p{font-size:26px;line-height:1.5;color:#a9c3c6;max-width:1080px}.flow{position:absolute;left:112px;right:112px;bottom:180px;display:flex;gap:18px;align-items:center;color:#a9c3c6;font-size:20px}.flow span{border:1px solid rgba(39,216,198,.38);background:rgba(6,40,48,.85);padding:17px 24px;border-radius:12px}.flow b{color:#b8f36a;font-size:26px}.pulse{width:14px;height:14px;border-radius:50%;background:#b8f36a;box-shadow:0 0 24px #b8f36a;animation:travel 3s ease-in-out infinite}@keyframes travel{0%,100%{transform:translateX(0);opacity:.4}50%{transform:translateX(210px);opacity:1}}
</style></head><body><div class="grid"></div><div class="halo"></div><div class="mark"><i></i> CHANGESAFE</div><main><div class="eyebrow">${eyebrow}</div><h1>${title}</h1><p>${detail}</p></main><div class="flow"><span>${footer}</span><b>→</b><div class="pulse"></div></div></body></html>`;
}

async function setOverlay(page, model) {
  await page.evaluate(({ caption, callout }) => {
    let root = document.getElementById("changesafe-video-overlay");
    if (!root) {
      root = document.createElement("section");
      root.id = "changesafe-video-overlay";
      root.setAttribute("aria-label", "Video narration");
      root.style.cssText = [
        "position:fixed",
        "left:50%",
        "bottom:38px",
        "transform:translateX(-50%)",
        "width:min(1380px,calc(100vw - 96px))",
        "z-index:2147483647",
        "pointer-events:none",
        "font-family:Inter,ui-sans-serif,system-ui",
      ].join(";");
      const chip = document.createElement("strong");
      chip.dataset.role = "callout";
      chip.style.cssText = [
        "display:inline-block",
        "background:#b8f36a",
        "color:#00141d",
        "padding:7px 13px",
        "border-radius:999px",
        "font-size:16px",
        "letter-spacing:.045em",
        "text-transform:uppercase",
        "margin:0 0 8px 18px",
      ].join(";");
      const text = document.createElement("div");
      text.dataset.role = "caption";
      text.style.cssText = [
        "background:rgba(0,20,29,.94)",
        "border-top:4px solid #27d8c6",
        "border-radius:12px",
        "box-shadow:0 18px 70px rgba(0,0,0,.4)",
        "color:#f3edda",
        "font-size:28px",
        "font-weight:760",
        "line-height:1.28",
        "padding:18px 26px 20px",
        "text-align:center",
      ].join(";");
      root.append(chip, text);
      document.body.append(root);
    }
    root.querySelector('[data-role="caption"]').textContent = caption;
    const chip = root.querySelector('[data-role="callout"]');
    chip.textContent = callout;
    chip.style.display = callout ? "inline-block" : "none";
  }, model);
}

async function selectFieldByKeyboard(page, field) {
  const combobox = page.getByRole("combobox", { name: "Current field" });
  await combobox.fill(field);
  await page.getByRole("option", { name: new RegExp(`^${field}\\b`, "i") }).waitFor();
  await combobox.press("Enter");
  if ((await combobox.inputValue()) !== field) {
    throw new Error(`Field ${field} was not committed by keyboard.`);
  }
}

async function waitForAnalysis(page) {
  await page.getByText("12 / 12", { exact: true }).waitFor({ timeout: 30_000 });
  if ((await page.getByTestId("artifact-file").count()) !== 7) {
    throw new Error("Hosted analysis did not produce seven verified files.");
  }
  if ((await page.getByTestId("impact-category").count()) !== 6) {
    throw new Error("Hosted analysis did not produce six impact classifications.");
  }
}

async function approveAndReset(page) {
  await page.getByRole("button", { name: "Approve preview" }).click();
  await page.getByText("Preview ready", { exact: true }).waitFor();
  await page.getByRole("button", { name: "New analysis" }).click();
}

async function record() {
  const args = parseArgs(process.argv.slice(2));
  const baseUrl = assertSafeBaseUrl(args["base-url"]);
  const timingPath = path.resolve(args.timing);
  const workDir = path.resolve(args["work-dir"]);
  const timing = validateTimingManifest(
    JSON.parse(await fs.readFile(timingPath, "utf8")),
    workDir,
  );
  const evidence = await preflight(baseUrl);
  const captureDir = path.join(workDir, "capture");
  const rawVideoDir = path.join(captureDir, `raw-${Date.now()}`);
  await fs.mkdir(rawVideoDir, { recursive: true });

  const browserErrors = [];
  const pageErrors = [];
  let assertions = 7;
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    acceptDownloads: true,
    deviceScaleFactor: 1,
    recordVideo: { dir: rawVideoDir, size: { width: 1920, height: 1080 } },
    viewport: { width: 1920, height: 1080 },
  });
  const page = await context.newPage();
  page.on("console", (message) => {
    if (message.type() === "error") browserErrors.push(message.text());
  });
  page.on("pageerror", (error) => pageErrors.push(error.message));

  const screenshotPaths = [];
  async function runScene(sceneId, callout, action) {
    const scene = timing.scenes.find((item) => item.scene_id === sceneId);
    const cues = timing.captions.filter((cue) => cue.scene_id === sceneId);
    const started = Date.now();
    const captionTask = (async () => {
      for (const cue of cues) {
        const relativeStart = cue.start_ms - scene.start_ms;
        const remaining = relativeStart - (Date.now() - started);
        if (remaining > 0) await sleep(remaining);
        await setOverlay(page, overlayModel(cue.text, callout));
      }
    })();
    await action();
    await captionTask;
    const screenshotPath = path.join(captureDir, `${sceneId}.png`);
    await page.screenshot({ path: screenshotPath });
    screenshotPaths.push(screenshotPath);
    const remaining = scene.duration_ms - (Date.now() - started);
    if (remaining < 0) throw new Error(`Scene ${sceneId} exceeded its timing contract.`);
    await sleep(remaining);
  }

  await runScene("problem", "CHANGE CONTRACT INTELLIGENCE", async () => {
    await page.setContent(titlePage());
  });

  await runScene("truth-boundary", "RECORDED DATAHUB EVIDENCE", async () => {
    await page.goto(baseUrl, { waitUntil: "networkidle", timeout: 60_000 });
    await page.getByText("Recorded DataHub schema").first().waitFor();
    await page.getByText("Preview only", { exact: true }).waitFor();
    await page.getByText("Production rows not queried").first().waitFor();
    assertions += 3;
  });

  await runScene("schema-request", "55 DATAHUB SCHEMA FIELDS", async () => {
    await selectFieldByKeyboard(page, "cust_email");
    await page.getByLabel("New field").fill("primary_email");
    await page.getByRole("button", { name: "Analyze change" }).click();
    await waitForAnalysis(page);
    assertions += 4;
  });

  let routeButton;
  await runScene("lineage", "6 UPSTREAM · 25 DOWNSTREAM", async () => {
    await page.locator("#dependency-evidence-map").scrollIntoViewIfNeeded();
    routeButton = page
      .getByRole("button", {
        name: /^order_details\.cust_email.*ORDER_DETAILS\.cust_email, direct field route/i,
      })
      .first();
    await routeButton.click();
    const drawer = page.getByRole("dialog", { name: /evidence for/i });
    await drawer.waitFor();
    await drawer.getByText("Source field", { exact: true }).waitFor();
    await drawer.getByText("Destination field", { exact: true }).waitFor();
    assertions += 3;
  });

  await runScene("impact", "6 EVIDENCE-LED IMPACT AREAS", async () => {
    await page.keyboard.press("Escape");
    if (!(await routeButton.evaluate((element) => element === document.activeElement))) {
      throw new Error("Evidence drawer did not restore route focus.");
    }
    await page.locator(".impact-classification").scrollIntoViewIfNeeded();
    await page.getByText("Evidence factor ledger", { exact: true }).click();
    await page
      .getByRole("button", { name: /Trace supporting evidence for Data integrity/i })
      .click();
    await page.getByText("Critical technical risk", { exact: true }).waitFor();
    assertions += 3;
  });

  await runScene("artifacts", "7 FILES · 12 BLOCKING CHECKS", async () => {
    await page.locator("#artifacts").scrollIntoViewIfNeeded();
    await page
      .getByRole("button", { name: /order_details__changesafe\.sql/i })
      .click();
    await page.getByText("Exact generated bytes", { exact: true }).waitFor();
    await page.getByText("12 / 12", { exact: true }).waitFor();
    assertions += 2;
  });

  await runScene("multi-field", "NOT EMAIL-ONLY", async () => {
    await approveAndReset(page);
    await selectFieldByKeyboard(page, "order_status");
    await page.getByLabel("Operation").selectOption("remove");
    await page.getByRole("button", { name: "Analyze change" }).click();
    await waitForAnalysis(page);
    await approveAndReset(page);
    await selectFieldByKeyboard(page, "order_total");
    await page.getByLabel("Operation").selectOption("type_change");
    await page.getByLabel("New type").fill("VARCHAR(320)");
    await page.getByRole("button", { name: "Analyze change" }).click();
    await waitForAnalysis(page);
    await page.getByText(/cast\(order_total as VARCHAR\(320\)\)/i).waitFor();
    assertions += 5;
  });

  await runScene("approval", "HUMAN APPROVAL · NON-MUTATING", async () => {
    await approveAndReset(page);
    await selectFieldByKeyboard(page, "cust_email");
    await page.getByLabel("Operation").selectOption("rename");
    await page.getByLabel("New field").fill("primary_email");
    await page.getByRole("button", { name: "Analyze change" }).click();
    await waitForAnalysis(page);
    await page.getByRole("button", { name: "Approve preview" }).click();
    await page.getByText("Preview ready", { exact: true }).waitFor();
    await page.getByText(/NOT WRITTEN.*SNAPSHOT MODE/).waitFor();
    const downloadPromise = page.waitForEvent("download");
    await page.getByRole("link", { name: "Download patch" }).click();
    const download = await downloadPromise;
    const downloadPath = await download.path();
    if (!downloadPath || (await fs.stat(downloadPath)).size === 0) {
      throw new Error("Approved preview patch download was empty.");
    }
    assertions += 4;
  });

  await runScene("closing", "CHANGESAFE", async () => {
    await page.goto("about:blank");
    await page.setContent(titlePage({ closing: true }));
  });

  if (browserErrors.length || pageErrors.length) {
    throw new Error("Browser capture reported a page or console error.");
  }
  const video = page.video();
  await page.close({ runBeforeUnload: false });
  await context.close();
  if (!video) throw new Error("Playwright did not produce a capture video.");
  const videoPath = path.join(captureDir, "changesafe-demo.webm");
  await video.saveAs(videoPath);
  await browser.close();

  const report = {
    version: 1,
    hosted_url: baseUrl,
    repository_url: REPOSITORY_URL,
    scene_ids: timing.scenes.map((scene) => scene.scene_id),
    schema_field_count: evidence.schemaFieldCount,
    snapshot_hash: evidence.snapshotHash,
    assertion_count: assertions,
    video_path: path.relative(workDir, videoPath).replaceAll("\\", "/"),
    screenshots: screenshotPaths.map((item) =>
      path.relative(workDir, item).replaceAll("\\", "/"),
    ),
    browser_errors: browserErrors,
    page_errors: pageErrors,
  };
  await fs.writeFile(
    path.join(captureDir, "capture-report.json"),
    `${JSON.stringify(report, null, 2)}\n`,
    "utf8",
  );
  console.log(videoPath);
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  record().catch((error) => {
    console.error(error instanceof Error ? error.message : "Capture failed safely.");
    process.exitCode = 1;
  });
}
