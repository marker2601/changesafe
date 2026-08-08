import { defineConfig, devices } from "@playwright/test";

const port = Number(process.env.CHANGESAFE_E2E_PORT ?? "8765");
const baseURL = `http://127.0.0.1:${port}`;
const python = process.env.CHANGESAFE_E2E_PYTHON ??
  (process.platform === "win32" ? ".venv\\Scripts\\python.exe" : "python");

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: false,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 2 : 0,
  workers: 1,
  reporter: process.env.CI ? [["html", { open: "never" }], ["github"]] : "list",
  use: {
    baseURL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: {
    command: `"${python}" -m uvicorn changesafe.main:app --app-dir apps/api/src --host 127.0.0.1 --port ${port}`,
    url: `${baseURL}/healthz`,
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
    env: {
      CHANGESAFE_MODE: "replay",
      CHANGESAFE_DATA_PATH: "data/e2e/changesafe.db",
    },
  },
});
