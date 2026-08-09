import { useEffect, useId, useMemo, useRef, useState } from "react";

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
  const optionRefs = useRef(new Map<string, HTMLLIElement>());
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState(value);
  const [requestedActiveIndex, setRequestedActiveIndex] = useState(0);
  const matches = useMemo(() => {
    const term = query.trim().toLowerCase();
    if (!term) return fields;
    return fields.filter(
      (field) =>
        field.name.toLowerCase().includes(term) ||
        field.data_type.toLowerCase().includes(term),
    );
  }, [fields, query]);
  const activeIndex = Math.min(
    requestedActiveIndex,
    Math.max(matches.length - 1, 0),
  );
  const active = matches[activeIndex];

  useEffect(() => {
    if (!open || !active) return;
    const option = optionRefs.current.get(active.name);
    if (typeof option?.scrollIntoView === "function") {
      option.scrollIntoView({ block: "nearest" });
    }
  }, [active, open]);

  const close = () => {
    setOpen(false);
    setRequestedActiveIndex(0);
  };
  const select = (field: SchemaField) => {
    onChange(field);
    setOpen(false);
    setRequestedActiveIndex(0);
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
        onBlur={close}
        onChange={(event) => {
          setQuery(event.target.value);
          setOpen(true);
          setRequestedActiveIndex(0);
        }}
        onClick={() => {
          if (open) return;
          setQuery(value);
          setOpen(true);
          setRequestedActiveIndex(0);
        }}
        onFocus={() => {
          setQuery(value);
          setOpen(true);
          setRequestedActiveIndex(0);
        }}
        onKeyDown={(event) => {
          if (event.key === "Escape") {
            event.preventDefault();
            close();
          } else if (event.key === "ArrowDown") {
            event.preventDefault();
            setOpen(true);
            setRequestedActiveIndex((current) =>
              Math.min(current + 1, Math.max(matches.length - 1, 0)),
            );
          } else if (event.key === "ArrowUp") {
            event.preventDefault();
            setOpen(true);
            setRequestedActiveIndex((current) => Math.max(current - 1, 0));
          } else if (event.key === "Enter" && open && active) {
            event.preventDefault();
            select(active);
          }
        }}
        role="combobox"
        value={open ? query : value}
      />
      {open && matches.length === 0 ? (
        <p aria-live="polite" className="field-combobox-empty" role="status">
          No matching DataHub fields.
        </p>
      ) : null}
      {open ? (
        <ul className="field-combobox-list" id={listId} role="listbox">
          {matches.map((field, index) => (
            <li
              aria-selected={field.name === value}
              className={`field-option${index === activeIndex ? " is-active" : ""}`}
              id={`${listId}-${field.name}`}
              key={field.name}
              onMouseDown={(event) => {
                event.preventDefault();
              }}
              onClick={() => select(field)}
              ref={(element) => {
                if (element) optionRefs.current.set(field.name, element);
                else optionRefs.current.delete(field.name);
              }}
              role="option"
            >
              <span>{field.name}</span>
              <small>
                {field.data_type} · {field.nullable ? "nullable" : "required"}
              </small>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
