import { describe, expect, it, vi } from "vitest";

import {
  ApiError,
  BrowserChangeSafeApi,
  REVIEW_SESSION_KEY,
} from "../src/api";
import { goldenRun, OFFICIAL_TARGET } from "./fixtures";

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
    expect(window.sessionStorage.getItem(REVIEW_SESSION_KEY)).toBe(sessionId);
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

  it("loads a schema catalog with the requested evidence source and no credentials", async () => {
    const fetchStub = vi.fn<typeof fetch>().mockResolvedValue(
      jsonResponse({
        target_urn: OFFICIAL_TARGET,
        target_name: "order_details",
        schema_fields: [
          { name: "cust_email", data_type: "TEXT", nullable: false },
        ],
        provenance: {
          mode: "snapshot",
          retrieved_at: "2026-08-09T00:00:00Z",
          adapter_version: "datahub-agent-context/1.7.0",
          snapshot_hash: "a".repeat(64),
        },
      }),
    );
    vi.stubGlobal("fetch", fetchStub);
    const api = new BrowserChangeSafeApi();

    await api.getSchemaCatalog(OFFICIAL_TARGET, "recorded");

    const [url, init] = fetchStub.mock.calls[0];
    expect(url).toBe(
      `/api/schema-fields?${new URLSearchParams({
        asset_urn: OFFICIAL_TARGET,
        source: "recorded",
      })}`,
    );
    const headers = new Headers(init?.headers);
    expect([...headers.keys()].some((header) => header.includes("token"))).toBe(
      false,
    );
    expect(headers.has("Authorization")).toBe(false);
  });

  it("preserves safe schema API detail messages", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn<typeof fetch>().mockResolvedValue(
        new Response(
          JSON.stringify({ detail: "DataHub schema could not be loaded" }),
          { status: 502, headers: { "Content-Type": "application/json" } },
        ),
      ),
    );
    const api = new BrowserChangeSafeApi();

    await expect(api.getSchemaCatalog(OFFICIAL_TARGET)).rejects.toEqual(
      new ApiError(502, "DataHub schema could not be loaded"),
    );
  });
});
