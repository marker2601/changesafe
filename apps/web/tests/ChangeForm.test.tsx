import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ComponentProps } from "react";
import { describe, expect, it, vi } from "vitest";

import { ChangeForm } from "../src/components/ChangeForm";
import {
  DEFAULT_CHANGE_DRAFT,
  sourceCommitForOperation,
} from "../src/changeDraft";
import type { ChangeDraft } from "../src/changeDraft";
import { goldenRun } from "./fixtures";

function renderForm(
  draft: ChangeDraft = DEFAULT_CHANGE_DRAFT,
  overrides: Partial<ComponentProps<typeof ChangeForm>> = {},
) {
  return render(
    <ChangeForm
      busy={false}
      draft={draft}
      onDraftChange={vi.fn()}
      onSubmit={vi.fn()}
      {...overrides}
    />,
  );
}

describe("ChangeForm", () => {
  it("seeds the golden rename and submits its exact contract", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    renderForm(DEFAULT_CHANGE_DRAFT, { onSubmit });

    expect(screen.getByLabelText("Current field")).toHaveValue("cust_email");
    expect(screen.getByLabelText("New field")).toHaveValue("primary_email");
    await user.click(screen.getByRole("button", { name: "Analyze change" }));

    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        operation: "rename",
        asset_urn: expect.stringContaining("ORDER_ENTRY_DB.analytics.order_details"),
        field: "cust_email",
        new_field: "primary_email",
        old_type: null,
        new_type: null,
        source_commit: "showcase-ecommerce-safe-rename",
        requested_by: "changesafe-web",
      }),
    );
  });

  it("reports operation-specific draft and source commit changes", async () => {
    const user = userEvent.setup();
    const onDraftChange = vi.fn();
    renderForm(DEFAULT_CHANGE_DRAFT, { onDraftChange });

    await user.selectOptions(screen.getByLabelText("Operation"), "remove");

    expect(onDraftChange).toHaveBeenCalledWith({
      ...DEFAULT_CHANGE_DRAFT,
      operation: "remove",
      source_commit: sourceCommitForOperation("remove"),
    });
  });

  it("shows type controls and guidance only for a type change", () => {
    renderForm({
      ...DEFAULT_CHANGE_DRAFT,
      operation: "type_change",
      source_commit: sourceCommitForOperation("type_change"),
    });

    expect(screen.getByLabelText("Current type")).toBeVisible();
    expect(screen.getByLabelText("New type")).toBeVisible();
    expect(screen.queryByLabelText("New field")).not.toBeInTheDocument();
    expect(
      screen.getByText(
        "Keep cust_email and add a safely cast VARCHAR(320) compatibility field during phase one.",
      ),
    ).toBeVisible();
  });

  it("locks the submitted request into a compact evidence summary", () => {
    renderForm(DEFAULT_CHANGE_DRAFT, {
      submittedRequest: {
        asset_urn: DEFAULT_CHANGE_DRAFT.asset_urn,
        operation: "rename",
        field: "cust_email",
        new_field: "primary_email",
        old_type: null,
        new_type: null,
        source_commit: DEFAULT_CHANGE_DRAFT.source_commit,
        requested_by: "changesafe-web",
      },
    });

    expect(screen.getAllByText("cust_email").length).toBeGreaterThan(0);
    expect(screen.getAllByText("primary_email").length).toBeGreaterThan(0);
    expect(screen.getByText("Request locked to this evidence set")).toBeVisible();
    expect(screen.queryByLabelText("Operation")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Analyze change" }),
    ).not.toBeInTheDocument();
  });

  it("uses neutral pending facts when the draft is not the official preset", () => {
    renderForm({
      ...DEFAULT_CHANGE_DRAFT,
      asset_urn:
        "urn:li:dataset:(urn:li:dataPlatform:snowflake,finance.customers,PROD)",
      field: "account_status",
      new_field: "customer_status",
    });

    expect(screen.getByText("Custom change request")).toBeVisible();
    expect(screen.getAllByText("Pending DataHub context")).toHaveLength(3);
    expect(screen.queryByText("Official ecommerce scenario")).not.toBeInTheDocument();
    expect(screen.queryByText("PII · Governed")).not.toBeInTheDocument();
  });

  it("derives submitted facts from returned DataHub context", () => {
    const context = {
      ...goldenRun.analysis!.context,
      target_urn:
        "urn:li:dataset:(urn:li:dataPlatform:snowflake,finance.payments,PROD)",
      target_name: "payments",
      target_domain: "Finance Data",
      field: "account_status",
      field_tags: [],
      glossary_terms: [],
    };
    const request = {
      ...goldenRun.request,
      asset_urn: context.target_urn,
      field: "account_status",
      new_field: "customer_status",
      source_commit: "custom-finance-change",
    };

    renderForm(DEFAULT_CHANGE_DRAFT, {
      context,
      submittedRequest: request,
    });

    expect(screen.getByText("Evidence-backed change")).toBeVisible();
    expect(screen.getByText("payments")).toBeVisible();
    expect(screen.getByText("No field policy recorded")).toBeVisible();
    expect(screen.getByText("Snowflake")).toBeVisible();
    expect(screen.queryByText("Order Entry Analytics")).not.toBeInTheDocument();
    expect(screen.queryByText("PII · Governed")).not.toBeInTheDocument();
  });
});
