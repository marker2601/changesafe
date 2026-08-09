import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ComponentProps } from "react";
import { describe, expect, it, vi } from "vitest";

import { ChangeForm } from "../src/components/ChangeForm";
import type { SchemaCatalogState } from "../src/hooks/useSchemaCatalog";
import {
  DEFAULT_CHANGE_DRAFT,
  sourceCommitForOperation,
} from "../src/changeDraft";
import type { ChangeDraft } from "../src/changeDraft";
import { goldenRun, goldenSchemaCatalog } from "./fixtures";

const loadedSchema: SchemaCatalogState = {
  catalog: goldenSchemaCatalog,
  loading: false,
  error: null,
  source: "active",
  retry: vi.fn(),
  loadRecorded: vi.fn(),
};

function renderForm(
  draft: ChangeDraft = DEFAULT_CHANGE_DRAFT,
  overrides: Partial<ComponentProps<typeof ChangeForm>> = {},
) {
  return render(
    <ChangeForm
      busy={false}
      draft={draft}
      onDraftChange={vi.fn()}
      onCurrentFieldChange={vi.fn()}
      onSubmit={vi.fn()}
      schema={loadedSchema}
      {...overrides}
    />,
  );
}

describe("ChangeForm", () => {
  it("seeds the golden rename and submits its exact contract", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    renderForm(DEFAULT_CHANGE_DRAFT, { onSubmit });

    expect(screen.getByRole("combobox", { name: "Current field" })).toHaveValue("cust_email");
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

    expect(screen.getByLabelText("Current type")).toHaveValue("TEXT");
    expect(screen.getByLabelText("Current type")).toHaveAttribute("readOnly");
    expect(screen.getByLabelText("New type")).toBeVisible();
    expect(screen.queryByLabelText("New field")).not.toBeInTheDocument();
    expect(
      screen.getByText(
        "Keep cust_email and add a safely cast VARCHAR(320) compatibility field during phase one.",
      ),
    ).toBeVisible();
  });

  it("stops analysis until a returned field and required destination are present", () => {
    const { rerender } = renderForm(
      { ...DEFAULT_CHANGE_DRAFT, field: "not_returned", new_field: "" },
    );
    expect(screen.getByRole("button", { name: "Analyze change" })).toBeDisabled();

    rerender(
      <ChangeForm
        busy={false}
        draft={{ ...DEFAULT_CHANGE_DRAFT, new_field: "" }}
        onDraftChange={vi.fn()}
        onCurrentFieldChange={vi.fn()}
        onSubmit={vi.fn()}
        schema={loadedSchema}
      />,
    );
    expect(screen.getByRole("button", { name: "Analyze change" })).toBeDisabled();
  });

  it("explains a safe discovery failure and permits an explicit recorded fallback in auto mode", async () => {
    const user = userEvent.setup();
    const loadRecorded = vi.fn();
    const retry = vi.fn();
    renderForm(DEFAULT_CHANGE_DRAFT, {
      schema: {
        ...loadedSchema,
        catalog: null,
        error: "Live DataHub is unavailable.",
        source: "active",
        retry,
        loadRecorded,
      },
      context: null,
      mode: "auto",
    });

    expect(screen.getByRole("alert")).toHaveTextContent("Live DataHub is unavailable.");
    expect(screen.getByRole("button", { name: "Use recorded fields" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Analyze change" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Retry" }));
    await user.click(screen.getByRole("button", { name: "Use recorded fields" }));
    expect(retry).toHaveBeenCalledOnce();
    expect(loadRecorded).toHaveBeenCalledOnce();
  });

  it("keeps recorded fallback unavailable in live mode and explains a loading schema", () => {
    const { rerender } = renderForm(DEFAULT_CHANGE_DRAFT, {
      schema: { ...loadedSchema, catalog: null, loading: true },
      mode: "live",
    });
    expect(screen.getByRole("textbox", { name: "Current field" })).toHaveValue(
      "Loading fields…",
    );
    expect(screen.getByRole("button", { name: "Analyze change" })).toBeDisabled();

    rerender(<ChangeForm busy={false} draft={DEFAULT_CHANGE_DRAFT} onDraftChange={vi.fn()} onCurrentFieldChange={vi.fn()} onSubmit={vi.fn()} schema={{ ...loadedSchema, catalog: null, error: "Live schema failed." }} mode="live" />);
    expect(screen.queryByRole("button", { name: "Use recorded fields" })).not.toBeInTheDocument();
  });

  it.each(["order_total", "order_status"]) (
    "keeps %s field policy pending until field-scoped context is analyzed",
    (field) => {
      renderForm({ ...DEFAULT_CHANGE_DRAFT, field, new_field: "replacement" });
      expect(screen.getByText("order_details")).toBeVisible();
      expect(screen.getByText("Pending field-scoped policy")).toBeVisible();
      expect(screen.queryByText("PII · Governed")).not.toBeInTheDocument();
    },
  );

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
