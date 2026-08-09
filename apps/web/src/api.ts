import type {
  ChangeRequest,
  ChangeSafeApi,
  ReviewActivity,
  PublicConfig,
  PublicationReceipt,
  SchemaCatalog,
  SchemaEvidenceSource,
  RunEvent,
  RunEventHandler,
  RunView,
  SubscriptionErrorHandler,
} from "./types";

export const REVIEW_SESSION_KEY = "changesafe.judge-session.v1";
const OPAQUE_SESSION_PATTERN = /^[A-Za-z0-9_-]{16,128}$/;

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function responseJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let message = `Request failed with HTTP ${response.status}.`;
    try {
      const payload = (await response.json()) as { detail?: unknown };
      if (typeof payload.detail === "string") message = payload.detail;
      if (
        typeof payload.detail === "object" &&
        payload.detail !== null &&
        "message" in payload.detail &&
        typeof payload.detail.message === "string"
      ) {
        message = payload.detail.message;
      }
    } catch {
      // Keep the stable status-based message for non-JSON errors.
    }
    throw new ApiError(response.status, message);
  }
  return (await response.json()) as T;
}

export class BrowserChangeSafeApi implements ChangeSafeApi {
  private volatileSessionId: string | null = null;

  constructor(private readonly baseUrl = "") {}

  private reviewSessionId(): string {
    if (this.volatileSessionId) return this.volatileSessionId;
    try {
      const existing = window.sessionStorage.getItem(REVIEW_SESSION_KEY);
      if (existing && OPAQUE_SESSION_PATTERN.test(existing)) {
        this.volatileSessionId = existing;
        return existing;
      }
    } catch {
      // Continue with a memory-only opaque identifier.
    }
    const created = globalThis.crypto.randomUUID();
    this.volatileSessionId = created;
    try {
      window.sessionStorage.setItem(REVIEW_SESSION_KEY, created);
    } catch {
      // The server still receives the memory-only session identifier.
    }
    return created;
  }

  async getPublicConfig(): Promise<PublicConfig> {
    return responseJson<PublicConfig>(
      await fetch(`${this.baseUrl}/api/public-config`),
    );
  }

  async getSchemaCatalog(
    assetUrn: string,
    source: SchemaEvidenceSource = "active",
  ): Promise<SchemaCatalog> {
    const query = new URLSearchParams({ asset_urn: assetUrn, source });
    return responseJson<SchemaCatalog>(
      await fetch(`${this.baseUrl}/api/schema-fields?${query}`),
    );
  }

  async getOwnerActivity(adminToken: string): Promise<ReviewActivity[]> {
    return responseJson<ReviewActivity[]>(
      await fetch(`${this.baseUrl}/api/owner/activity`, {
        headers: { "X-ChangeSafe-Admin-Token": adminToken },
      }),
    );
  }

  async createRun(change: ChangeRequest): Promise<RunView> {
    return responseJson<RunView>(
      await fetch(`${this.baseUrl}/api/runs`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-ChangeSafe-Session-ID": this.reviewSessionId(),
        },
        body: JSON.stringify(change),
      }),
    );
  }

  async getRun(runId: string): Promise<RunView> {
    return responseJson<RunView>(
      await fetch(`${this.baseUrl}/api/runs/${encodeURIComponent(runId)}`),
    );
  }

  async approve(
    runId: string,
    adminToken?: string,
  ): Promise<PublicationReceipt> {
    const headers: Record<string, string> = {};
    if (adminToken) headers["X-ChangeSafe-Admin-Token"] = adminToken;
    return responseJson<PublicationReceipt>(
      await fetch(
        `${this.baseUrl}/api/runs/${encodeURIComponent(runId)}/approve`,
        { method: "POST", headers },
      ),
    );
  }

  async continueWithSnapshot(runId: string): Promise<RunView> {
    return responseJson<RunView>(
      await fetch(
        `${this.baseUrl}/api/runs/${encodeURIComponent(runId)}/continue-with-snapshot`,
        { method: "POST" },
      ),
    );
  }

  subscribe(
    runId: string,
    afterSequence: number,
    onEvent: RunEventHandler,
    onError?: SubscriptionErrorHandler,
  ): () => void {
    const query = afterSequence > 0 ? `?after=${afterSequence}` : "";
    const source = new EventSource(
      `${this.baseUrl}/api/runs/${encodeURIComponent(runId)}/events${query}`,
    );
    source.addEventListener("run_state", (rawEvent) => {
      const message = rawEvent as MessageEvent<string>;
      onEvent(JSON.parse(message.data) as RunEvent);
    });
    if (onError) source.addEventListener("error", onError);
    return () => source.close();
  }

  patchUrl = (runId: string): string =>
    `${this.baseUrl}/api/runs/${encodeURIComponent(runId)}/publication.patch`;
}

export const browserApi = new BrowserChangeSafeApi();
