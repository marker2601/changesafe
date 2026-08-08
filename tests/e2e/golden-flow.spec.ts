import { expect, test } from "@playwright/test";

test("judge completes the credential-free golden workflow", async ({ page }) => {
  const consoleErrors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });

  await page.goto("/");

  await expect(page.getByText("Snapshot replay", { exact: true })).toBeVisible();
  await expect(
    page.getByText("Preview only / snapshot mode", { exact: true }),
  ).toBeVisible();

  await page.getByRole("button", { name: "Analyze change" }).click();

  await expect(page.getByText("90", { exact: true })).toBeVisible();
  await expect(page.getByText("Critical risk", { exact: true })).toBeVisible();
  await expect(page.getByTestId("affected-asset-row")).toHaveCount(4);
  await expect(page.getByTestId("artifact-file")).toHaveCount(7);
  await expect(page.getByText("12 / 12", { exact: true })).toBeVisible();

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
  await expect(page.getByText("Critical risk", { exact: true })).toBeVisible();

  const dimensions = await page.evaluate(() => ({
    clientWidth: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
  }));

  expect(dimensions.scrollWidth).toBe(dimensions.clientWidth);
  await expect(page.getByTestId("affected-asset-row")).toHaveCount(4);
});
