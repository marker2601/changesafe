import { useState } from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { FieldCombobox } from "../src/components/FieldCombobox";
import type { SchemaField } from "../src/types";

const fields: SchemaField[] = [
  { name: "cust_email", data_type: "TEXT", nullable: false },
  { name: "order_total", data_type: "FLOAT", nullable: false },
  { name: "optional_note", data_type: "VARCHAR", nullable: true },
];

function ClickOnlyHarness({ onChange }: { onChange: (field: SchemaField) => void }) {
  const [value, setValue] = useState("cust_email");
  return (
    <FieldCombobox
      disabled={false}
      fields={fields}
      onChange={(field) => {
        onChange(field);
        setValue(field.name);
      }}
      value={value}
    />
  );
}

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

  it("commits an option through click-only activation", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<ClickOnlyHarness onChange={onChange} />);

    const input = screen.getByRole("combobox", { name: "Current field" });
    await user.click(input);
    await user.clear(input);
    await user.type(input, "order");
    const option = screen.getByRole("option", { name: /order_total.*float.*required/i });
    fireEvent.click(option);

    expect(onChange).toHaveBeenCalledTimes(1);
    expect(onChange).toHaveBeenCalledWith(fields[1]);
    expect(screen.getByRole("combobox", { name: "Current field" })).toHaveValue("order_total");
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

  it("uses the parent value whenever a closed combobox is rerendered", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    const { rerender } = render(
      <FieldCombobox disabled={false} fields={fields} onChange={onChange} value="cust_email" />,
    );
    const input = screen.getByRole("combobox", { name: "Current field" });
    await user.click(input);
    await user.clear(input);
    await user.type(input, "not-a-field");
    fireEvent.blur(input);
    await waitFor(() => expect(input).toHaveValue("cust_email"));

    rerender(<FieldCombobox disabled={false} fields={fields} onChange={onChange} value="order_total" />);
    expect(input).toHaveValue("order_total");
    await user.click(input);
    expect(screen.getByRole("option", { name: /order_total/i })).toHaveAttribute(
      "aria-selected",
      "true",
    );
  });

  it("keeps no-result status outside the option list", async () => {
    const user = userEvent.setup();
    render(<FieldCombobox disabled={false} fields={fields} onChange={vi.fn()} value="cust_email" />);
    const input = screen.getByRole("combobox", { name: "Current field" });
    await user.click(input);
    await user.clear(input);
    await user.type(input, "not-a-field");

    const status = screen.getByRole("status");
    expect(status).toHaveTextContent("No matching DataHub fields.");
    expect(screen.getByRole("listbox")).not.toContainElement(status);
  });

  it("scrolls the active option into the nearest visible edge for a long field list", async () => {
    const user = userEvent.setup();
    const scrollIntoView = vi.fn();
    const originalScrollIntoView = Object.getOwnPropertyDescriptor(
      HTMLElement.prototype,
      "scrollIntoView",
    );
    Object.defineProperty(HTMLElement.prototype, "scrollIntoView", {
      configurable: true,
      value: scrollIntoView,
    });
    try {
      const longFields = Array.from({ length: 55 }, (_, index) => ({
        name: `field_${String(index).padStart(2, "0")}`,
        data_type: "TEXT",
        nullable: false,
      }));
      render(<FieldCombobox disabled={false} fields={longFields} onChange={vi.fn()} value="field_00" />);

      await user.click(screen.getByRole("combobox", { name: "Current field" }));
      await user.keyboard("{ArrowDown}{ArrowDown}");

      expect(scrollIntoView).toHaveBeenCalledWith({ block: "nearest" });
    } finally {
      if (originalScrollIntoView) {
        Object.defineProperty(
          HTMLElement.prototype,
          "scrollIntoView",
          originalScrollIntoView,
        );
      } else {
        delete (HTMLElement.prototype as { scrollIntoView?: unknown }).scrollIntoView;
      }
    }
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
