import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { OwnerActivity } from "../src/components/OwnerActivity";
import type { ReviewActivity } from "../src/types";

const activity: ReviewActivity = {
  run_id: "019fe233-1111-7000-8000-000000000001",
  session_label: "session-7a31f0",
  scenario: "Rename cust_email to primary_email",
  state: "awaiting_approval",
  context_mode: "snapshot",
  publication_mode: null,
  created_at: "2026-08-08T20:00:00Z",
  updated_at: "2026-08-08T20:00:08Z",
};

describe("OwnerActivity", () => {
  beforeEach(() => window.sessionStorage.clear());

  it("loads privacy-limited sessions only after an owner token is submitted", async () => {
    const user = userEvent.setup();
    const loadActivity = vi.fn(async () => [activity]);
    render(
      <OwnerActivity loadActivity={loadActivity} onClose={vi.fn()} />,
    );

    expect(
      screen.getByRole("heading", { name: "Review activity" }),
    ).toBeVisible();
    expect(loadActivity).not.toHaveBeenCalled();
    const token = screen.getByLabelText("Owner token");
    expect(token).toHaveAttribute("type", "password");
    await user.type(token, "owner-only-secret");
    await user.click(screen.getByRole("button", { name: "Load activity" }));

    expect(loadActivity).toHaveBeenCalledWith("owner-only-secret");
    expect(await screen.findByText("Session 7A31F0")).toBeVisible();
    expect(screen.getByText("Rename cust_email to primary_email")).toBeVisible();
    expect(screen.getByText("Awaiting Approval")).toBeVisible();
    expect(window.sessionStorage.length).toBe(0);
    expect(screen.queryByText(/judge/i)).not.toBeInTheDocument();
  });

  it("shows authorization errors next to the token control", async () => {
    const user = userEvent.setup();
    const loadActivity = vi.fn(async () => {
      throw new Error("Owner token was not accepted (403).");
    });
    render(
      <OwnerActivity loadActivity={loadActivity} onClose={vi.fn()} />,
    );

    await user.type(screen.getByLabelText("Owner token"), "wrong-token");
    await user.click(screen.getByRole("button", { name: "Load activity" }));

    expect(
      await screen.findByRole("alert", { name: "Review activity error" }),
    ).toHaveTextContent("Owner token was not accepted (403).");
  });
});
