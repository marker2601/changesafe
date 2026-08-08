import { Check, ChevronRight, X } from "lucide-react";

import type { ValidationReport } from "../types";

interface ValidationPanelProps {
  validation: ValidationReport;
}

export function ValidationPanel({ validation }: ValidationPanelProps) {
  const blocking = validation.checks.filter((check) => check.blocking);
  const passed = blocking.filter((check) => check.passed).length;
  return (
    <section className="validation-panel" aria-labelledby="validation-heading">
      <h2 id="validation-heading">Validation summary</h2>
      <div className={validation.passed ? "validation-score passed" : "validation-score failed"}>
        <span>{validation.passed ? <Check aria-hidden="true" /> : <X aria-hidden="true" />}</span>
        <strong>{passed} / {blocking.length}</strong>
        <p>blocking checks passed</p>
      </div>
      <details>
        <summary>
          View validation details
          <ChevronRight aria-hidden="true" />
        </summary>
        <ul>
          {validation.checks.map((check) => (
            <li key={check.code}>
              {check.passed ? <Check aria-hidden="true" /> : <X aria-hidden="true" />}
              <span>
                <strong>{check.label}</strong>
                <small>{check.detail}</small>
              </span>
            </li>
          ))}
        </ul>
      </details>
    </section>
  );
}
