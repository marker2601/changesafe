import type { RiskResult } from "../types";

interface RiskCardProps {
  risk: RiskResult;
}

export function RiskCard({ risk }: RiskCardProps) {
  return (
    <section className="risk-section" aria-labelledby="risk-heading">
      <div className="risk-score-panel">
        <div className="risk-score" aria-label={`${risk.score} out of 100`}>
          <strong>{risk.score}</strong>
          <span>/ 100</span>
        </div>
        <h3 id="risk-heading">{`${risk.band[0].toUpperCase()}${risk.band.slice(1)} risk`}</h3>
        <p>{risk.recommended_strategy.replaceAll("_", " ")}</p>
      </div>

      <div className="factor-ledger">
        <h3>Evidence-backed factor ledger</h3>
        <div className="factor-header" aria-hidden="true">
          <span>Factor</span>
          <span>Evidence</span>
          <span>Points</span>
        </div>
        <ul>
          {risk.factors.map((factor) => (
            <li data-testid="risk-factor" key={factor.code}>
              <span>{factor.label}</span>
              <span>{factor.evidence_urns.length} linked reference(s)</span>
              <strong>+{factor.points}</strong>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
