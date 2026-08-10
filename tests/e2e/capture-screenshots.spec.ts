import { expect, type Locator, type Page, test } from "@playwright/test";

const screenshotDirectory =
  process.env.CHANGESAFE_CAPTURE_SCREENSHOTS_DIR ?? "docs/screenshots";

function screenshotPath(filename: string) {
  return `${screenshotDirectory}/${filename}`;
}

async function expectHorizontallyContained(page: Page, target: Locator) {
  const box = await target.boundingBox();
  const viewport = page.viewportSize();
  expect(box).not.toBeNull();
  expect(viewport).not.toBeNull();
  expect(box!.x).toBeGreaterThanOrEqual(0);
  expect(box!.x + box!.width).toBeLessThanOrEqual(viewport!.width);
}

async function anchorInViewport(page: Page, target: Locator) {
  await target.scrollIntoViewIfNeeded();
  const box = await target.boundingBox();
  const viewport = page.viewportSize();
  expect(box).not.toBeNull();
  expect(viewport).not.toBeNull();
  expect(box!.y).toBeGreaterThanOrEqual(0);
  expect(box!.y).toBeLessThan(viewport!.height);
  await expectHorizontallyContained(page, target);
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
  await expect(
    page.getByRole("option", { name: new RegExp(`^${field}\\b`, "i") }),
  ).toBeVisible();
  await combobox.press("Enter");
  await expect(combobox).toHaveValue(field);
}

async function expectNoPageOverflow(page: Page) {
  const dimensions = await page.evaluate(() => ({
    clientWidth: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
  }));
  expect(dimensions.scrollWidth).toBe(dimensions.clientWidth);
}

test.skip(
  process.env.CHANGESAFE_CAPTURE_SCREENSHOTS !== "1",
  "Run explicitly when refreshing checked-in proof images.",
);

test("capture current desktop and mobile replay evidence", async ({ browser }) => {
  const desktopContext = await browser.newContext({
    viewport: { width: 1440, height: 1024 },
    deviceScaleFactor: 1,
  });
  const desktop = await desktopContext.newPage();
  const desktopErrors = collectBrowserErrors(desktop);
  await desktop.goto("/");
  await selectFieldByKeyboard(desktop, "cust_email");
  await expectHorizontallyContained(desktop, desktop.locator(".field-combobox"));
  await desktop.getByRole("button", { name: "Analyze change" }).click();
  await expect(desktop.getByText(/^Completed in /)).toBeVisible();
  await expect(
    desktop.getByRole("button", {
      name: /^order_details\.cust_email.*ORDER_DETAILS\.cust_email, direct field route/i,
    }),
  ).toBeVisible();
  await expect(desktop.getByTestId("impact-category")).toHaveCount(6);
  await expect(desktop.getByTestId("artifact-file")).toHaveCount(7);
  await expect(desktop.getByText("12 / 12", { exact: true })).toBeVisible();
  await expect(desktop.getByText("Production rows not queried").first()).toBeVisible();
  await expectNoPageOverflow(desktop);
  await desktop.evaluate(() => window.scrollTo(0, 0));
  await expectHorizontallyContained(desktop, desktop.locator(".product-hero"));
  await expectHorizontallyContained(desktop, desktop.locator(".command-center"));
  await expectHorizontallyContained(desktop, desktop.locator("#dependency-evidence-map"));
  await desktop.screenshot({
    path: screenshotPath("changesafe-desktop-replay.png"),
    fullPage: false,
  });

  await desktop.getByRole("button", { name: "Approve preview" }).click();
  await expect(desktop.getByText("Preview ready", { exact: true })).toBeVisible();
  await anchorInViewport(desktop, desktop.locator("#artifacts"));
  await expectHorizontallyContained(desktop, desktop.locator(".receipt-panel"));
  await desktop.screenshot({
    path: screenshotPath("changesafe-desktop-proof.png"),
    fullPage: false,
  });
  expect(desktopErrors.consoleErrors).toEqual([]);
  expect(desktopErrors.pageErrors).toEqual([]);
  await desktopContext.close();

  const mobileContext = await browser.newContext({
    viewport: { width: 430, height: 932 },
    deviceScaleFactor: 1,
  });
  const mobile = await mobileContext.newPage();
  const mobileErrors = collectBrowserErrors(mobile);
  await mobile.goto("/");
  await selectFieldByKeyboard(mobile, "order_total");
  await mobile.getByLabel("Operation").selectOption("type_change");
  await mobile.getByLabel("New type").fill("VARCHAR(320)");
  await expectHorizontallyContained(mobile, mobile.locator(".field-combobox"));
  await mobile.getByRole("button", { name: "Analyze change" }).click();
  await expect(mobile.getByText(/^Completed in /)).toBeVisible();
  await expect(
    mobile.getByRole("button", {
      name: /^order_details\.order_total.*ORDER_DETAILS\.order_total, direct field route/i,
    }),
  ).toBeVisible();
  await expect(mobile.getByText("Critical technical risk", { exact: true })).toBeVisible();
  await expect(mobile.getByText("12 / 12", { exact: true })).toBeVisible();
  await expect(mobile.getByText("Production rows not queried").first()).toBeVisible();
  await expectNoPageOverflow(mobile);
  await mobile.evaluate(() => window.scrollTo(0, 0));
  await expect.poll(() => mobile.evaluate(() => window.scrollY)).toBe(0);
  await expectHorizontallyContained(mobile, mobile.locator(".product-hero"));
  await expectHorizontallyContained(mobile, mobile.locator(".command-center"));
  await expectHorizontallyContained(mobile, mobile.locator("#dependency-evidence-map"));
  await mobile.screenshot({
    path: screenshotPath("changesafe-mobile-replay.png"),
    fullPage: false,
  });

  await mobile.getByRole("button", { name: "Approve preview" }).click();
  await expect(mobile.getByText("Preview ready", { exact: true })).toBeVisible();
  await anchorInViewport(mobile, mobile.locator(".receipt-panel"));
  await mobile.screenshot({
    path: screenshotPath("changesafe-mobile-proof.png"),
    fullPage: false,
  });
  expect(mobileErrors.consoleErrors).toEqual([]);
  expect(mobileErrors.pageErrors).toEqual([]);
  await mobileContext.close();
});
