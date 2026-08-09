import { Activity, LockKeyhole, RefreshCw, X } from "lucide-react";
import { useState, type FormEvent } from "react";

import type { ReviewActivity } from "../types";

interface OwnerActivityProps {
  loadActivity: (adminToken: string) => Promise<ReviewActivity[]>;
  onClose: () => void;
}

function stateLabel(state: ReviewActivity["state"]): string {
  return state
    .split("_")
    .map((part) => `${part.charAt(0).toUpperCase()}${part.slice(1)}`)
    .join(" ");
}

function sessionLabel(label: string): string {
  const value = label.startsWith("session-") ? label.slice("session-".length) : label;
  return `Session ${value.toUpperCase()}`;
}

function timestamp(value: string): string {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "medium",
  }).format(new Date(value));
}

export function OwnerActivity({ loadActivity, onClose }: OwnerActivityProps) {
  const [token, setToken] = useState("");
  const [activity, setActivity] = useState<ReviewActivity[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!token.trim()) return;
    setBusy(true);
    setError(null);
    try {
      setActivity(await loadActivity(token));
      setToken("");
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Review activity could not be loaded.",
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="owner-activity-backdrop">
      <section
        aria-label="Private review activity"
        aria-modal="true"
        className="owner-activity-drawer"
        role="dialog"
      >
        <header>
          <span>
            <Activity aria-hidden="true" />
            Private owner view
          </span>
          <button aria-label="Close review activity" onClick={onClose} type="button">
            <X aria-hidden="true" />
          </button>
        </header>
        <div className="owner-activity-intro">
          <span className="owner-lock">
            <LockKeyhole aria-hidden="true" />
          </span>
          <div>
            <h2>Review activity</h2>
            <p>
              See privacy-limited sessions and operational states. No IP addresses,
              names, tokens, or submitted secrets are stored here.
            </p>
          </div>
        </div>
        <form onSubmit={(event) => void submit(event)}>
          <label htmlFor="owner-activity-token">Owner token</label>
          <div>
            <input
              autoComplete="off"
              id="owner-activity-token"
              onChange={(event) => setToken(event.target.value)}
              placeholder="Enter private owner token"
              type="password"
              value={token}
            />
            <button disabled={busy || !token.trim()} type="submit">
              <RefreshCw aria-hidden="true" />
              {busy ? "Loading" : "Load activity"}
            </button>
          </div>
          {error ? (
            <p aria-label="Review activity error" className="owner-activity-error" role="alert">
              {error}
            </p>
          ) : null}
        </form>
        {activity ? (
          activity.length ? (
            <div className="activity-table-wrap">
              <table>
                <thead>
                  <tr>
                    <th scope="col">Session</th>
                    <th scope="col">Scenario</th>
                    <th scope="col">State</th>
                    <th scope="col">Evidence</th>
                    <th scope="col">Updated</th>
                  </tr>
                </thead>
                <tbody>
                  {activity.map((item) => (
                    <tr key={item.run_id}>
                      <td>
                        <strong>{sessionLabel(item.session_label)}</strong>
                        <code>{item.run_id.slice(0, 8)}</code>
                      </td>
                      <td>{item.scenario}</td>
                      <td>
                        <span className={`activity-state state-${item.state}`}>
                          {stateLabel(item.state)}
                        </span>
                      </td>
                      <td>
                        {item.context_mode ?? "Waiting"}
                        {item.publication_mode
                          ? ` · ${item.publication_mode}`
                          : ""}
                      </td>
                      <td>{timestamp(item.updated_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="activity-empty">No review sessions have been recorded yet.</p>
          )
        ) : (
          <p className="activity-empty">
            Activity is fetched only after the private owner token is submitted.
          </p>
        )}
      </section>
    </div>
  );
}
