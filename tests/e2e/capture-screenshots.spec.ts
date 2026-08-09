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
  await desktop.goto("/");
  const desktopField = desktop.getByRole("combobox", { name: "Current field" });
  await desktopField.fill("cust_email");
  await expect(
    desktop.getByRole("option", { name: /cust_email.*text.*required/i }),
  ).toBeVisible();
  await desktopField.press("Enter");
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
  await desktopContext.close();

  const mobileContext = await browser.newContext({
    viewport: { width: 430, height: 932 },
    deviceScaleFactor: 1,
  });
  const mobile = await mobileContext.newPage();
  await mobile.goto("/");
  const mobileField = mobile.getByRole("combobox", { name: "Current field" });
  await mobileField.fill("order_total");
  await expect(
    mobile.getByRole("option", { name: /order_total.*float.*required/i }),
  ).toBeVisible();
  await mobileField.press("Enter");
  await mobile.getByLabel("New field").fill("preferred_order_total");
  await expectHorizontallyContained(mobile, mobile.locator(".field-combobox"));
  await mobile.getByRole("button", { name: "Analyze change" }).click();
  await expect(mobile.getByText(/^Completed in /)).toBeVisible();
  await expect(
    mobile.getByRole("button", {
      name: /^order_details\.order_total.*ORDER_DETAILS\.order_total, direct field route/i,
    }),
  ).toBeVisible();
  await expect(mobile.getByText("High technical risk", { exact: true })).toBeVisible();
  await expect(mobile.getByText("12 / 12", { exact: true })).toBeVisible();
  await anchorInViewport(mobile, mobile.locator(".target-node"));
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
  await mobileContext.close();
});
