import {
  BadgeDollarSign,
  BriefcaseBusiness,
  DatabaseZap,
  LockKeyhole,
  Network,
  Settings2,
  ShieldCheck,
  type LucideIcon,
} from "lucide-react";

import type { ImpactAssessment, ImpactCategory } from "../types";

const ICONS: Record<ImpactCategory, LucideIcon> = {
  data_integrity: DatabaseZap,
  privacy_compliance: LockKeyhole,
  operational_continuity: Settings2,
  trust_decision_quality: ShieldCheck,
  financial_exposure: BadgeDollarSign,
  organizational_impact: BriefcaseBusiness,
};

interface ImpactClassificationProps {
  impacts: ImpactAssessment[];
  selected: ImpactAssessment | null;
  onSelect: (impact: ImpactAssessment) => void;
}

export function ImpactClassification({
  impacts,
  selected,
  onSelect,
}: ImpactClassificationProps) {
  return (
    <section className="impact-classification" aria-labelledby="impact-heading">
      <header className="panel-heading">
        <span>Evidence-led assessment</span>
        <h2 id="impact-heading">Impact classification</h2>
      </header>
      <ul>
        {impacts.map((impact) => {
          const Icon = ICONS[impact.category];
          const active = selected?.category === impact.category;
          return (
            <li data-testid="impact-category" key={impact.category}>
              <article className="impact-finding">
                <header>
                  <span className="impact-icon">
                    <Icon aria-hidden="true" />
                  </span>
                  <span className="impact-copy">
                    <strong>{impact.label}</strong>
                    <small>
                      {impact.confidence === "inferred"
                        ? "Inferred evidence"
                        : impact.confidence === "direct"
                          ? "Direct evidence"
                          : "Evidence unavailable"}
                    </small>
                  </span>
                  <span className={`severity severity-${impact.severity}`}>
                    {impact.severity}
                  </span>
                </header>
                <p>{impact.summary}</p>
                <dl>
                  <div>
                    <dt>Evidence basis</dt>
                    <dd>{impact.basis}</dd>
                  </div>
                </dl>
                {impact.qualifier ? (
                  <p className="impact-qualifier">{impact.qualifier}</p>
                ) : null}
                <button
                  aria-controls="dependency-evidence-map"
                  aria-expanded={active}
                  aria-label={`${active ? "Clear evidence trace" : "Trace supporting evidence"} for ${impact.label}`}
                  className={`impact-trace${active ? " is-active" : ""}`}
                  onClick={() => onSelect(impact)}
                  type="button"
                >
                  <Network aria-hidden="true" />
                  {active ? "Clear evidence trace" : "Trace supporting evidence"}
                </button>
              </article>
            </li>
          );
        })}
      </ul>
      <p className="impact-footnote">
        Classifications use DataHub metadata, lineage, ownership, governance, and
        usage signals. Inferences are labeled.
      </p>
    </section>
  );
}
