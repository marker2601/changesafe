import { describe, expect, it, vi } from "vitest";

import {
  BrowserChangeSafeApi,
  JUDGE_SESSION_KEY,
} from "../src/api";
import { goldenRun } from "./fixtures";

function jsonResponse(value: unknown): Response {
  return new Response(JSON.stringify(value), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

describe("BrowserChangeSafeApi", () => {
  it("sends one opaque browser session only when creating runs", async () => {
    const fetchStub = vi
      .fn<typeof fetch>()
      .mockImplementation(async () => jsonResponse(goldenRun));
    vi.stubGlobal("fetch", fetchStub);
    const api = new BrowserChangeSafeApi("https://changesafe.example");

    await api.createRun(goldenRun.request);
    await api.getRun(goldenRun.run_id);

    const createHeaders = new Headers(fetchStub.mock.calls[0][1]?.headers);
    const sessionId = createHeaders.get("X-ChangeSafe-Session-ID");
    const getHeaders = new Headers(fetchStub.mock.calls[1][1]?.headers);
    expect(sessionId).toMatch(/^[A-Za-z0-9_-]{16,128}$/);
    expect(window.sessionStorage.getItem(JUDGE_SESSION_KEY)).toBe(sessionId);
    expect(getHeaders.has("X-ChangeSafe-Session-ID")).toBe(false);
  });

  it("sends only the supplied owner token to the activity endpoint", async () => {
    const fetchStub = vi
      .fn<typeof fetch>()
      .mockResolvedValue(jsonResponse([]));
    vi.stubGlobal("fetch", fetchStub);
    const api = new BrowserChangeSafeApi("https://changesafe.example");

    await api.getOwnerActivity("owner-only-secret");

    const [url, init] = fetchStub.mock.calls[0];
    const headers = new Headers(init?.headers);
    expect(url).toBe("https://changesafe.example/api/owner/activity");
    expect(headers.get("X-ChangeSafe-Admin-Token")).toBe(
      "owner-only-secret",
    );
    expect(headers.has("X-ChangeSafe-Session-ID")).toBe(false);
  });
});
