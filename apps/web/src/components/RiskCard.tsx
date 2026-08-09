import { ChevronDown, Gauge } from "lucide-react";

import type { RiskResult } from "../types";

interface RiskCardProps {
  risk: RiskResult;
}

export function RiskCard({ risk }: RiskCardProps) {
  const band = `${risk.band[0].toUpperCase()}${risk.band.slice(1)}`;
  return (
    <section className="risk-section" aria-labelledby="risk-heading">
      <header>
        <Gauge aria-hidden="true" />
        <span>
          <small>Deterministic score</small>
          <h2 id="risk-heading">{band} technical risk</h2>
        </span>
        <strong aria-label={`${risk.score} out of 100`}>{risk.score}</strong>
      </header>
      <p>{risk.recommended_strategy.replaceAll("_", " ")}</p>
      <details>
        <summary>
          Evidence factor ledger
          <ChevronDown aria-hidden="true" />
        </summary>
        <ul>
          {risk.factors.map((factor) => (
            <li data-testid="risk-factor" key={factor.code}>
              <span>
                <strong>{factor.label}</strong>
                <small>{factor.evidence_urns.length} evidence reference(s)</small>
              </span>
              <em>+{factor.points}</em>
            </li>
          ))}
        </ul>
      </details>
    </section>
  );
}
