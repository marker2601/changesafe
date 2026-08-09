import { expect, test } from "@playwright/test";

test("user completes the credential-free golden workflow", async ({ page }) => {
  const consoleErrors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });

  await page.goto("/");

  await expect(
    page.getByRole("heading", {
      name: "Change data safely, with every dependency in view.",
    }),
  ).toBeVisible();
  await expect(page.getByText("Official DataHub showcase-ecommerce")).toBeVisible();
  await expect(page.getByText("order_details").first()).toBeVisible();
  await expect(page.getByText("Recorded DataHub evidence", { exact: true })).toBeVisible();
  await expect(page.getByText("Preview only", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "Analyze change" }).click();

  await expect(page.getByText("80", { exact: true })).toBeVisible();
  await expect(page.getByText("Critical technical risk", { exact: true })).toBeVisible();
  await expect(page.getByTestId("impact-category")).toHaveCount(6);
  await expect(page.getByTestId("lineage-flow")).toHaveCount(2);
  await expect(page.getByTestId("process-step")).toHaveCount(7);
  await expect(page.locator('[data-testid="process-step"].is-complete')).toHaveCount(5);
  await expect(page.getByText("Waiting for the accountable owner")).toBeVisible();
  await expect(page.getByText("Customer Analytics Measures").first()).toBeVisible();
  await expect(page.getByTestId("artifact-file")).toHaveCount(7);
  await expect(page.getByText("What this file does", { exact: true })).toBeVisible();
  await expect(page.getByText("Failure this prevents", { exact: true })).toBeVisible();
  await expect(page.getByText(/^Completed in /)).toBeVisible();
  await expect(
    page.getByText("Same request + same evidence = same verified result.", {
      exact: true,
    }),
  ).toBeVisible();
  await expect(page.getByText("12 / 12", { exact: true })).toBeVisible();
  await expect(page.locator(".product-hero")).not.toHaveClass(/is-compact/);

  await page.getByRole("button", { name: "Approve preview" }).click();
  await expect(page.getByText("Preview ready", { exact: true })).toBeVisible();
  await expect(
    page.getByText("NOT WRITTEN — SNAPSHOT MODE", { exact: true }),
  ).toBeVisible();

  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("link", { name: "Download patch" }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toMatch(/^changesafe-.*\.patch$/);
  expect(consoleErrors).toEqual([]);
});

test("completed workflow remains contained on a phone viewport", async ({ page }) => {
  await page.setViewportSize({ width: 430, height: 932 });
  await page.goto("/");
  await page.getByRole("button", { name: "Analyze change" }).click();
  await expect(page.getByText("Critical technical risk", { exact: true })).toBeVisible();

  const dimensions = await page.evaluate(() => ({
    clientWidth: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
  }));

  expect(dimensions.scrollWidth).toBe(dimensions.clientWidth);
  await expect(page.getByTestId("impact-category")).toHaveCount(6);
  await expect(page.getByTestId("artifact-file")).toHaveCount(7);
});
