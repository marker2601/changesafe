import {
  BadgeDollarSign,
  BriefcaseBusiness,
  DatabaseZap,
  LockKeyhole,
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
              <button
                aria-pressed={active}
                className={active ? "is-selected" : ""}
                onClick={() => onSelect(impact)}
                type="button"
              >
                <Icon aria-hidden="true" />
                <span className="impact-copy">
                  <strong>{impact.label}</strong>
                  <small>
                    {impact.confidence === "inferred"
                      ? "Inferred evidence"
                      : impact.confidence === "direct"
                        ? "Direct evidence"
                        : "Evidence unavailable"}
                  </small>
                  {impact.qualifier ? <em>{impact.qualifier}</em> : null}
                </span>
                <span className={`severity severity-${impact.severity}`}>
                  {impact.severity}
                </span>
              </button>
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
