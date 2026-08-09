"""Deterministic, evidence-led impact classifications for a proposed change."""

from __future__ import annotations

from collections.abc import Iterable

from changesafe.domain import (
    ChangeOperation,
    ChangeRequest,
    ContextBundle,
    EvidenceConfidence,
    ImpactAssessment,
    ImpactCategory,
    ImpactSeverity,
)


def _unique(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _change_action(change: ChangeRequest, context: ContextBundle) -> str:
    if change.operation is ChangeOperation.RENAME:
        return f"Renaming {change.field} to {change.new_field}"
    if change.operation is ChangeOperation.TYPE_CHANGE:
        old_type = change.old_type or context.field_type
        return f"Changing {change.field} from {old_type} to {change.new_type}"
    return f"Removing {change.field}"


def classify_impacts(
    change: ChangeRequest, context: ContextBundle
) -> list[ImpactAssessment]:
    """Classify six stable impact dimensions without inventing business values."""

    target = context.target_urn
    action = _change_action(change, context)
    downstream_urns = _unique(asset.urn for asset in context.downstream_assets)
    governed_urns = _unique([*context.field_tags, *context.glossary_terms])
    usage_urns = _unique(
        evidence.urn for evidence in context.evidence if evidence.kind == "usage"
    )
    owner_urns = _unique(owner.urn for owner in context.owners)
    pii = any(
        marker in urn.casefold()
        for urn in governed_urns
        for marker in ("pii", "personal", "privacy")
    )
    authoritative = any(
        "authoritative" in urn.casefold() for urn in context.field_tags
    )
    business_assets = [
        asset
        for asset in context.downstream_assets
        if asset.entity_type.casefold()
        in {"dashboard", "report", "semantic_model", "view", "explore"}
        or any(
            platform in asset.urn.casefold()
            for platform in ("powerbi", "looker", "tableau")
        )
    ]
    domains = {
        domain
        for domain in [
            context.target_domain,
            *(asset.domain for asset in context.downstream_assets),
        ]
        if domain
    }

    integrity_severity = (
        ImpactSeverity.CRITICAL
        if authoritative or len(downstream_urns) >= 5
        else ImpactSeverity.HIGH
        if downstream_urns
        else ImpactSeverity.MEDIUM
    )
    privacy_severity = (
        ImpactSeverity.CRITICAL if pii else ImpactSeverity.INFORMATIONAL
    )
    privacy_confidence = (
        EvidenceConfidence.DIRECT if pii else EvidenceConfidence.UNAVAILABLE
    )
    operational_severity = (
        ImpactSeverity.HIGH
        if context.usage_tier == "high" or len(downstream_urns) >= 3
        else ImpactSeverity.MEDIUM
        if downstream_urns
        else ImpactSeverity.INFORMATIONAL
    )
    operational_confidence = (
        EvidenceConfidence.DIRECT
        if downstream_urns or context.usage_tier != "none"
        else EvidenceConfidence.UNAVAILABLE
    )
    trust_severity = (
        ImpactSeverity.HIGH
        if authoritative and business_assets
        else ImpactSeverity.MEDIUM
        if business_assets
        else ImpactSeverity.INFORMATIONAL
    )
    trust_confidence = (
        EvidenceConfidence.DIRECT
        if authoritative or business_assets
        else EvidenceConfidence.UNAVAILABLE
    )
    financial_supported = bool(business_assets) and context.usage_tier in {
        "medium",
        "high",
    }
    organizational_supported = bool(owner_urns) and len(domains) >= 2

    return [
        ImpactAssessment(
            category=ImpactCategory.DATA_INTEGRITY,
            label="Data integrity",
            severity=integrity_severity,
            confidence=EvidenceConfidence.DIRECT,
            summary=(
                f"{action} can alter the contract consumed by "
                f"{len(downstream_urns)} recorded dependencies."
            ),
            basis=(
                "DataHub schema and field-level lineage identify the current field "
                "and its recorded consumers."
            ),
            evidence_urns=_unique([target, *downstream_urns]),
        ),
        ImpactAssessment(
            category=ImpactCategory.PRIVACY_COMPLIANCE,
            label="Privacy & compliance",
            severity=privacy_severity,
            confidence=privacy_confidence,
            summary=(
                f"{action} affects a field with direct personal-data governance "
                "evidence."
                if pii
                else f"{action} has no personal-data classification in this context."
            ),
            basis=(
                "DataHub field tags and glossary terms are the sole basis for this "
                "classification."
            ),
            evidence_urns=_unique([target, *governed_urns]),
        ),
        ImpactAssessment(
            category=ImpactCategory.OPERATIONAL_CONTINUITY,
            label="Operational continuity",
            severity=operational_severity,
            confidence=operational_confidence,
            summary=(
                f"{action} requires a coordinated compatibility window to keep "
                "recorded consumers and frequent queries operating."
            ),
            basis=(
                (
                    "DataHub has no recorded query usage and "
                    if context.usage_tier == "none"
                    else f"DataHub reports {context.usage_tier} query usage and "
                )
                + f"{len(downstream_urns)} downstream dependencies."
            ),
            evidence_urns=_unique([target, *usage_urns, *downstream_urns]),
        ),
        ImpactAssessment(
            category=ImpactCategory.TRUST_DECISION_QUALITY,
            label="Trust & decision quality",
            severity=trust_severity,
            confidence=trust_confidence,
            summary=(
                f"{action} can make business-facing semantic and analytics assets "
                "stale or incomplete if their contracts diverge."
            ),
            basis=(
                f"{len(business_assets)} recorded BI or semantic consumers"
                + (
                    " depend on a field tagged as an authoritative source."
                    if authoritative
                    else " are present in the lineage evidence."
                )
            ),
            evidence_urns=_unique(
                [target, *(asset.urn for asset in business_assets)]
            ),
        ),
        ImpactAssessment(
            category=ImpactCategory.FINANCIAL_EXPOSURE,
            label="Financial exposure",
            severity=(
                ImpactSeverity.HIGH
                if financial_supported
                else ImpactSeverity.INFORMATIONAL
            ),
            confidence=(
                EvidenceConfidence.INFERRED
                if financial_supported
                else EvidenceConfidence.UNAVAILABLE
            ),
            summary=(
                f"{action} may disrupt business workflows or require rework, but "
                "metadata cannot establish a monetary amount."
            ),
            qualifier=(
                "Potentially high, not quantified"
                if financial_supported
                else "Not quantified from available metadata"
            ),
            basis=(
                "This is an inference from usage and business-facing dependencies; "
                "no revenue, cost, or transaction values were queried."
            ),
            evidence_urns=(
                _unique(
                    [
                        target,
                        *usage_urns,
                        *(asset.urn for asset in business_assets),
                    ]
                )
                if financial_supported
                else [target]
            ),
        ),
        ImpactAssessment(
            category=ImpactCategory.ORGANIZATIONAL_IMPACT,
            label="Organizational impact",
            severity=(
                ImpactSeverity.HIGH
                if organizational_supported
                else ImpactSeverity.MEDIUM
                if owner_urns
                else ImpactSeverity.INFORMATIONAL
            ),
            confidence=(
                EvidenceConfidence.DIRECT
                if owner_urns
                else EvidenceConfidence.UNAVAILABLE
            ),
            summary=(
                f"{action} requires accountable coordination across the recorded "
                "owners and consuming domains."
            ),
            basis=(
                f"DataHub records {len(owner_urns)} owners and "
                f"{len(domains)} represented domains."
            ),
            evidence_urns=_unique([target, *owner_urns, *downstream_urns]),
        ),
    ]
