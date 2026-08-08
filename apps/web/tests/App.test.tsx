import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { App } from "../src/App";
import { createGoldenApi } from "./fixtures";

describe("ChangeSafe workspace", () => {
  it("renders the real golden analysis from ordered run events", async () => {
    const user = userEvent.setup();
    render(<App api={createGoldenApi()} />);

    await user.click(screen.getByRole("button", { name: "Analyze change" }));

    expect(await screen.findByText("90")).toBeVisible();
    expect(screen.getByText("Critical risk")).toBeVisible();
    expect(screen.getAllByTestId("risk-factor")).toHaveLength(6);
    expect(screen.getByText("executive_customer_health")).toBeVisible();
    expect(screen.getByText("10 / 10")).toBeVisible();
    expect(
      screen.getByRole("button", { name: "Approve preview" }),
    ).toBeEnabled();
  });

  it("approves without credentials and labels snapshot writeback truthfully", async () => {
    const user = userEvent.setup();
    render(<App api={createGoldenApi()} />);
    await user.click(screen.getByRole("button", { name: "Analyze change" }));
    await user.click(
      await screen.findByRole("button", { name: "Approve preview" }),
    );

    expect(await screen.findByText("Preview ready")).toBeVisible();
    expect(screen.getByText("NOT WRITTEN — SNAPSHOT MODE")).toBeVisible();
    expect(
      screen.getByText("No external systems were changed."),
    ).toBeVisible();
  });

  it("renders generated code as text rather than injected HTML", async () => {
    const user = userEvent.setup();
    const api = createGoldenApi();
    render(<App api={api} />);
    await user.click(screen.getByRole("button", { name: "Analyze change" }));

    expect(await screen.findByText(/customer_email as primary_email/)).toBeVisible();
    await user.click(screen.getByRole("tab", { name: "PR_BODY.md" }));
    expect(screen.getByText(/<img src=x onerror=/)).toBeVisible();
    expect(document.querySelector(".artifact-code img")).toBeNull();
  });
});
