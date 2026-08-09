import { expect, test } from "@playwright/test";

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
  await desktop.getByRole("button", { name: "Analyze change" }).click();
  await expect(desktop.getByTestId("impact-category")).toHaveCount(6);
  await expect(desktop.getByTestId("artifact-file")).toHaveCount(7);
  await expect(desktop.getByText("12 / 12", { exact: true })).toBeVisible();
  await desktop.setViewportSize({ width: 1487, height: 1058 });
  await desktop.evaluate(() => window.scrollTo(0, 0));
  await desktop.screenshot({
    path: "test-results/changesafe-reference-viewport.png",
  });
  await desktop.setViewportSize({ width: 1440, height: 1024 });
  await desktop.evaluate(() => window.scrollTo(0, 0));
  await desktop.screenshot({
    path: "docs/screenshots/changesafe-desktop-replay.png",
    fullPage: true,
  });
  await desktopContext.close();

  const mobileContext = await browser.newContext({
    viewport: { width: 430, height: 932 },
    deviceScaleFactor: 1,
  });
  const mobile = await mobileContext.newPage();
  await mobile.goto("/");
  await mobile.getByRole("button", { name: "Analyze change" }).click();
  await expect(mobile.getByText("12 / 12", { exact: true })).toBeVisible();
  await mobile.getByRole("button", { name: "Approve preview" }).click();
  await expect(mobile.getByText("Preview ready", { exact: true })).toBeVisible();
  await mobile.evaluate(() => window.scrollTo(0, 0));
  await mobile.screenshot({
    path: "docs/screenshots/changesafe-mobile-replay.png",
    fullPage: true,
  });
  await mobileContext.close();
});
