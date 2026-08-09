import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ChangeForm } from "../src/components/ChangeForm";

describe("ChangeForm", () => {
  it("seeds the golden rename and submits its exact contract", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    render(<ChangeForm busy={false} onSubmit={onSubmit} />);

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
      }),
    );
  });

  it("shows type controls only for a type change", async () => {
    const user = userEvent.setup();
    render(<ChangeForm busy={false} onSubmit={vi.fn()} />);

    await user.selectOptions(screen.getByLabelText("Operation"), "type_change");

    expect(screen.getByLabelText("Current type")).toBeVisible();
    expect(screen.getByLabelText("New type")).toBeVisible();
    expect(screen.queryByLabelText("New field")).not.toBeInTheDocument();
  });
});
