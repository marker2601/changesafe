import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { useSchemaCatalog } from "../src/hooks/useSchemaCatalog";
import type { ChangeSafeApi, SchemaCatalog } from "../src/types";
import { OFFICIAL_TARGET, goldenSchemaCatalog } from "./fixtures";

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

function apiWithSchema(
  getSchemaCatalog: ChangeSafeApi["getSchemaCatalog"],
): ChangeSafeApi {
  return {
    getPublicConfig: vi.fn(),
    getSchemaCatalog,
    getOwnerActivity: vi.fn(),
    createRun: vi.fn(),
    getRun: vi.fn(),
    approve: vi.fn(),
    continueWithSnapshot: vi.fn(),
    subscribe: vi.fn(() => () => undefined),
  };
}

describe("useSchemaCatalog", () => {
  it("keeps newer schema options when an older dataset response resolves late", async () => {
    const first = deferred<SchemaCatalog>();
    const second = deferred<SchemaCatalog>();
    const secondCatalog = {
      ...goldenSchemaCatalog,
      target_urn: "urn:li:dataset:second",
      target_name: "second",
    };
    const getSchemaCatalog = vi
      .fn()
      .mockReturnValueOnce(first.promise)
      .mockReturnValueOnce(second.promise);
    const api = apiWithSchema(getSchemaCatalog);
    const { result, rerender } = renderHook(
      ({ urn }) => useSchemaCatalog(api, urn),
      { initialProps: { urn: "urn:li:dataset:cache" } },
    );

    await waitFor(() => expect(getSchemaCatalog).toHaveBeenCalledTimes(1));
    rerender({ urn: "urn:li:dataset:second" });
    await waitFor(() => expect(getSchemaCatalog).toHaveBeenCalledTimes(2));
    second.resolve(secondCatalog);
    await waitFor(() => expect(result.current.catalog).toBe(secondCatalog));
    first.resolve(goldenSchemaCatalog);
    await act(async () => undefined);

    expect(result.current.catalog).toBe(secondCatalog);
  });

  it("suppresses catalog and provenance synchronously when the current source key changes", async () => {
    const firstCatalog = {
      ...goldenSchemaCatalog,
      target_urn: "urn:li:dataset:synchronous-first",
    };
    const getSchemaCatalog = vi
      .fn()
      .mockResolvedValueOnce(firstCatalog)
      .mockReturnValueOnce(deferred<SchemaCatalog>().promise);
    const api = apiWithSchema(getSchemaCatalog);
    const { result, rerender } = renderHook(
      ({ urn }) => useSchemaCatalog(api, urn),
      { initialProps: { urn: firstCatalog.target_urn } },
    );
    await waitFor(() => expect(result.current.catalog).toBe(firstCatalog));

    rerender({ urn: "urn:li:dataset:synchronous-second" });

    expect(result.current.catalog).toBeNull();
    expect(result.current.error).toBeNull();
    expect(result.current.source).toBe("active");
  });

  it("reuses a successful schema response for the same dataset in this session", async () => {
    const getSchemaCatalog = vi.fn(async () => goldenSchemaCatalog);
    const api = apiWithSchema(getSchemaCatalog);
    const { result, rerender } = renderHook(
      ({ urn }) => useSchemaCatalog(api, urn),
      { initialProps: { urn: OFFICIAL_TARGET } },
    );
    await waitFor(() => expect(result.current.catalog).toBe(goldenSchemaCatalog));

    rerender({ urn: "urn:li:dataset:other" });
    await waitFor(() => expect(result.current.catalog).toBe(goldenSchemaCatalog));
    rerender({ urn: OFFICIAL_TARGET });
    await waitFor(() => expect(result.current.catalog).toBe(goldenSchemaCatalog));

    expect(getSchemaCatalog).toHaveBeenCalledTimes(2);
  });

  it("retries a failed schema read instead of accepting the unselected draft", async () => {
    const getSchemaCatalog = vi
      .fn()
      .mockRejectedValueOnce(new Error("DataHub did not return a schema."))
      .mockResolvedValueOnce(goldenSchemaCatalog);
    const retryUrn = "urn:li:dataset:retry";
    const api = apiWithSchema(getSchemaCatalog);
    const { result } = renderHook(() => useSchemaCatalog(api, retryUrn));

    await waitFor(() => expect(result.current.error).toBe("DataHub did not return a schema."));
    act(() => result.current.retry());
    await waitFor(() => expect(result.current.catalog).toBe(goldenSchemaCatalog));

    expect(getSchemaCatalog).toHaveBeenLastCalledWith(retryUrn, "active");
  });

  it("does not request a schema for an invalid dataset URN", async () => {
    const getSchemaCatalog = vi.fn();
    const api = apiWithSchema(getSchemaCatalog);
    const { result } = renderHook(() => useSchemaCatalog(api, "not-a-urn"));

    await act(async () => undefined);
    expect(getSchemaCatalog).not.toHaveBeenCalled();
    expect(result.current.catalog).toBeNull();
  });

  it("requests checksum-verified recorded fields only after the user asks", async () => {
    const getSchemaCatalog = vi.fn(async () => goldenSchemaCatalog);
    const recordedUrn = "urn:li:dataset:recorded";
    const api = apiWithSchema(getSchemaCatalog);
    const { result } = renderHook(() => useSchemaCatalog(api, recordedUrn));
    await waitFor(() => expect(result.current.catalog).toBe(goldenSchemaCatalog));

    act(() => result.current.loadRecorded());
    await waitFor(() => expect(result.current.source).toBe("recorded"));

    expect(getSchemaCatalog).toHaveBeenLastCalledWith(recordedUrn, "recorded");
  });

  it("returns to the active source before reading fields for a changed dataset", async () => {
    const getSchemaCatalog = vi.fn(async () => goldenSchemaCatalog);
    const api = apiWithSchema(getSchemaCatalog);
    const { result, rerender } = renderHook(
      ({ urn }) => useSchemaCatalog(api, urn),
      { initialProps: { urn: "urn:li:dataset:source-one" } },
    );
    await waitFor(() => expect(result.current.catalog).toBe(goldenSchemaCatalog));
    act(() => result.current.loadRecorded());
    await waitFor(() => expect(result.current.source).toBe("recorded"));

    rerender({ urn: "urn:li:dataset:source-two" });
    await waitFor(() => expect(result.current.source).toBe("active"));

    expect(getSchemaCatalog).not.toHaveBeenCalledWith("urn:li:dataset:source-two", "recorded");
    expect(getSchemaCatalog).toHaveBeenLastCalledWith("urn:li:dataset:source-two", "active");
  });

  it("persists the active reset across recorded A to B to A navigation", async () => {
    const getSchemaCatalog = vi.fn(async () => goldenSchemaCatalog);
    const api = apiWithSchema(getSchemaCatalog);
    const first = "urn:li:dataset:source-reset-a";
    const second = "urn:li:dataset:source-reset-b";
    const { result, rerender } = renderHook(
      ({ urn }) => useSchemaCatalog(api, urn),
      { initialProps: { urn: first } },
    );
    await waitFor(() => expect(result.current.catalog).toBe(goldenSchemaCatalog));
    act(() => result.current.loadRecorded());
    await waitFor(() => expect(result.current.source).toBe("recorded"));

    rerender({ urn: second });
    await waitFor(() => expect(result.current.source).toBe("active"));
    await act(async () => undefined);
    rerender({ urn: first });

    expect(result.current.source).toBe("active");
  });
});
