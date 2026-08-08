"""Versioned deterministic risk scoring independent of any language model."""

from __future__ import annotations

from changesafe.domain import (
    ChangeOperation,
    ChangeRequest,
    ContextBundle,
    RiskBand,
    RiskFactor,
    RiskResult,
)

ACCOUNTABLE_OWNER_TYPES = {"DATA_OWNER", "BUSINESS_OWNER", "OWNER"}
GOVERNANCE_MARKERS = ("pii", "confidential", "governed", "sensitive")
WIDENING_TYPE_CHANGES = {
    ("SMALLINT", "INT"),
    ("SMALLINT", "BIGINT"),
    ("INT", "BIGINT"),
    ("FLOAT", "DOUBLE"),
    ("VARCHAR", "STRING"),
    ("STRING", "TEXT"),
}


def band_for(score: int) -> RiskBand:
    if not 0 <= score <= 100:
        raise ValueError("risk score must be between 0 and 100")
    if score < 30:
        return RiskBand.LOW
    if score < 60:
        return RiskBand.MEDIUM
    if score < 80:
        return RiskBand.HIGH
    return RiskBand.CRITICAL


def _base_factor(change: ChangeRequest) -> RiskFactor:
    if change.operation is ChangeOperation.RENAME:
        return RiskFactor(
            code="base_rename",
            label="Column rename",
            points=25,
            evidence_urns=[change.asset_urn],
        )
    if change.operation is ChangeOperation.REMOVE:
        return RiskFactor(
            code="base_removal",
            label="Column removal",
            points=40,
            evidence_urns=[change.asset_urn],
        )

    pair = ((change.old_type or "").upper(), (change.new_type or "").upper())
    widening = pair in WIDENING_TYPE_CHANGES
    return RiskFactor(
        code="base_compatible_type_change" if widening else "base_type_change",
        label="Compatible widening type change"
        if widening
        else "Narrowing or incompatible type change",
        points=15 if widening else 35,
        evidence_urns=[change.asset_urn],
    )


def _is_governed(context: ContextBundle) -> bool:
    values = [*context.field_tags, *context.glossary_terms]
    return any(
        marker in value.lower() for value in values for marker in GOVERNANCE_MARKERS
    )


def score_change(change: ChangeRequest, context: ContextBundle) -> RiskResult:
    factors = [_base_factor(change)]
    downstream = context.downstream_assets

    if downstream:
        factors.append(
            RiskFactor(
                code="downstream_assets",
                label=f"{len(downstream)} downstream assets",
                points=min(len(downstream) * 5, 25),
                evidence_urns=[asset.urn for asset in downstream],
            )
        )

    executive = [
        asset
        for asset in downstream
        if asset.is_executive
        or asset.entity_type.lower() in {"dashboard", "executive_report"}
    ]
    if executive:
        factors.append(
            RiskFactor(
                code="executive_downstream",
                label="Dashboard or executive report downstream",
                points=15,
                evidence_urns=[asset.urn for asset in executive],
            )
        )

    production_ml = [asset for asset in downstream if asset.is_production_ml]
    if production_ml:
        factors.append(
            RiskFactor(
                code="production_ml_downstream",
                label="Production ML asset downstream",
                points=15,
                evidence_urns=[asset.urn for asset in production_ml],
            )
        )

    if _is_governed(context):
        governance_evidence = [
            evidence.urn
            for evidence in context.evidence
            if evidence.kind == "governance"
        ] or [context.target_urn]
        factors.append(
            RiskFactor(
                code="governed_field",
                label="Governed, confidential, or PII field",
                points=10,
                evidence_urns=governance_evidence,
            )
        )

    if context.usage_tier == "high":
        usage_evidence = [
            evidence.urn for evidence in context.evidence if evidence.kind == "usage"
        ] or [context.target_urn]
        factors.append(
            RiskFactor(
                code="high_usage",
                label="High query usage",
                points=10,
                evidence_urns=usage_evidence,
            )
        )

    domains = {asset.domain for asset in downstream if asset.domain}
    if context.target_domain:
        domains.add(context.target_domain)
    if len(domains) > 1:
        cross_domain_assets = [
            asset.urn
            for asset in downstream
            if asset.domain and asset.domain != context.target_domain
        ]
        factors.append(
            RiskFactor(
                code="cross_domain",
                label="Cross-domain impact",
                points=10,
                evidence_urns=cross_domain_assets or [context.target_urn],
            )
        )

    has_accountable_owner = any(
        owner.ownership_type.upper() in ACCOUNTABLE_OWNER_TYPES
        for owner in context.owners
    )
    if not has_accountable_owner:
        factors.append(
            RiskFactor(
                code="missing_accountable_owner",
                label="Missing accountable owner",
                points=10,
                evidence_urns=[context.target_urn],
            )
        )

    score = min(sum(factor.points for factor in factors), 100)
    band = band_for(score)
    strategy = (
        "two_phase_compatibility_migration"
        if band in {RiskBand.HIGH, RiskBand.CRITICAL}
        else "reviewed_migration"
        if band is RiskBand.MEDIUM
        else "direct_change_with_tests"
    )
    return RiskResult(
        score=score,
        band=band,
        factors=factors,
        recommended_strategy=strategy,
    )
