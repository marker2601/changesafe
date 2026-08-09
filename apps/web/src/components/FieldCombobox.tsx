import { useId, useMemo, useState } from "react";

import type { SchemaField } from "../types";

interface FieldComboboxProps {
  disabled: boolean;
  fields: SchemaField[];
  onChange: (field: SchemaField) => void;
  value: string;
}

export function FieldCombobox({
  disabled,
  fields,
  onChange,
  value,
}: FieldComboboxProps) {
  const listId = useId();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState(value);
  const [activeIndex, setActiveIndex] = useState(0);
  const selected = fields.find((field) => field.name === value) ?? null;
  const matches = useMemo(() => {
    const term = query.trim().toLowerCase();
    if (!term) return fields;
    return fields.filter(
      (field) =>
        field.name.toLowerCase().includes(term) ||
        field.data_type.toLowerCase().includes(term),
    );
  }, [fields, query]);
  const active = matches[Math.min(activeIndex, Math.max(matches.length - 1, 0))];

  const close = () => {
    setOpen(false);
    setQuery(selected?.name ?? "");
    setActiveIndex(0);
  };
  const select = (field: SchemaField) => {
    onChange(field);
    setQuery(field.name);
    setOpen(false);
    setActiveIndex(0);
  };

  return (
    <div className="field-combobox">
      <input
        aria-activedescendant={open && active ? `${listId}-${active.name}` : undefined}
        aria-autocomplete="list"
        aria-controls={listId}
        aria-expanded={open}
        aria-haspopup="listbox"
        aria-label="Current field"
        autoComplete="off"
        disabled={disabled}
        onBlur={() => window.setTimeout(close, 0)}
        onChange={(event) => {
          setQuery(event.target.value);
          setOpen(true);
          setActiveIndex(0);
        }}
        onClick={() => setOpen(true)}
        onFocus={() => setOpen(true)}
        onKeyDown={(event) => {
          if (event.key === "Escape") {
            event.preventDefault();
            close();
          } else if (event.key === "ArrowDown") {
            event.preventDefault();
            setOpen(true);
            setActiveIndex((current) => Math.min(current + 1, Math.max(matches.length - 1, 0)));
          } else if (event.key === "ArrowUp") {
            event.preventDefault();
            setOpen(true);
            setActiveIndex((current) => Math.max(current - 1, 0));
          } else if (event.key === "Enter" && open && active) {
            event.preventDefault();
            select(active);
          }
        }}
        role="combobox"
        value={query}
      />
      {open ? (
        <ul className="field-combobox-list" id={listId} role="listbox">
          {matches.length === 0 ? (
            <li className="field-combobox-empty" role="status">
              No matching DataHub fields.
            </li>
          ) : (
            matches.map((field, index) => (
              <li
                aria-selected={field.name === value}
                className={`field-option${index === activeIndex ? " is-active" : ""}`}
                id={`${listId}-${field.name}`}
                key={field.name}
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => select(field)}
                role="option"
              >
                <span>{field.name}</span>
                <small>
                  {field.data_type} · {field.nullable ? "nullable" : "required"}
                </small>
              </li>
            ))
          )}
        </ul>
      ) : null}
    </div>
  );
}
