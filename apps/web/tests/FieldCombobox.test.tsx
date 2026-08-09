import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { FieldCombobox } from "../src/components/FieldCombobox";
import type { SchemaField } from "../src/types";

const fields: SchemaField[] = [
  { name: "cust_email", data_type: "TEXT", nullable: false },
  { name: "order_total", data_type: "FLOAT", nullable: false },
  { name: "optional_note", data_type: "VARCHAR", nullable: true },
];

describe("FieldCombobox", () => {
  it("selects only a returned field with its schema type and nullability", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<FieldCombobox disabled={false} fields={fields} onChange={onChange} value="cust_email" />);

    const input = screen.getByRole("combobox", { name: "Current field" });
    await user.click(input);
    await user.clear(input);
    await user.type(input, "order");

    const option = screen.getByRole("option", { name: /order_total.*float.*required/i });
    expect(option).toHaveAttribute("aria-selected", "false");
    expect(input).toHaveAttribute("aria-controls");
    expect(input).toHaveAttribute("aria-expanded", "true");
    expect(input).toHaveAttribute("aria-activedescendant", option.id);

    await user.keyboard("{ArrowDown}{Enter}");
    expect(onChange).toHaveBeenCalledWith({ name: "order_total", data_type: "FLOAT", nullable: false });
  });

  it("restores the exact selected field when a typed value is not a returned option", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<FieldCombobox disabled={false} fields={fields} onChange={onChange} value="cust_email" />);

    const input = screen.getByRole("combobox", { name: "Current field" });
    await user.click(input);
    await user.clear(input);
    await user.type(input, "invented_column");
    expect(screen.getByText("No matching DataHub fields.")).toBeVisible();
    await user.keyboard("{Escape}");

    expect(input).toHaveValue("cust_email");
    expect(onChange).not.toHaveBeenCalled();
  });

  it("does not open disabled or loading selection controls", async () => {
    const user = userEvent.setup();
    render(<FieldCombobox disabled fields={fields} onChange={vi.fn()} value="cust_email" />);

    const input = screen.getByRole("combobox", { name: "Current field" });
    await user.click(input);
    expect(input).toBeDisabled();
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
  });
});
