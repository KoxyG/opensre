"""Shared confidence scoring for feature/workflow RCA candidates."""

from __future__ import annotations

from dataclasses import dataclass

from app.rca.feature_workflow.matching import match_endpoint_tags
from app.rca.feature_workflow.models import FeatureWorkflowConfig, OperatorHint
from app.rca.feature_workflow.signals import (
    EndpointMatch,
    InvestigationSignals,
    RuntimeOperatorHint,
)

# Weighted sum caps at 1.0; breakdown fields are individual signal strengths (0–1).
WEIGHT_CORRELATION = 0.35
WEIGHT_TOPOLOGY = 0.30
WEIGHT_FEATURE_WORKFLOW = 0.35

_EXACT_MATCH_STRENGTH = 1.0
_PREFIX_MATCH_STRENGTH = 0.7


@dataclass(frozen=True)
class ConfidenceBreakdown:
    correlation: float
    topology: float
    feature_workflow: float

    def combined(self) -> float:
        raw = (
            WEIGHT_CORRELATION * self.correlation
            + WEIGHT_TOPOLOGY * self.topology
            + WEIGHT_FEATURE_WORKFLOW * self.feature_workflow
        )
        return round(min(1.0, raw), 4)


def _endpoint_match_strength(
    config: FeatureWorkflowConfig,
    tag: str,
    endpoint: str | None,
    *,
    http_method: str | None,
) -> float:
    if not endpoint or tag not in match_endpoint_tags(config, endpoint, method=http_method):
        return 0.0
    strength = 0.0
    for mapping in config.endpoints:
        if tag not in mapping.tags:
            continue
        matched = match_endpoint_tags(config, endpoint, method=http_method)
        if tag not in matched:
            continue
        if mapping.match == "exact":
            strength = max(strength, _EXACT_MATCH_STRENGTH)
        else:
            strength = max(strength, _PREFIX_MATCH_STRENGTH)
    return strength


def _score_correlation(signals: InvestigationSignals) -> tuple[float, list[str]]:
    score = 0.0
    drivers: list[str] = []
    if (
        signals.correlation_id
        and signals.context_correlation_id
        and signals.correlation_id == signals.context_correlation_id
    ):
        score += 0.5
        drivers.append("correlation_id_match")
    if signals.incident_window_confidence >= 0.5:
        score += 0.35
        drivers.append("incident_window_confident")
    if signals.has_deploy_timeline:
        score += 0.25
        drivers.append("deploy_timeline_in_evidence")
    return min(1.0, score), drivers


def _score_topology(
    config: FeatureWorkflowConfig,
    tag: str,
    signals: InvestigationSignals,
) -> tuple[float, list[str]]:
    service = config.service_for_tag(tag)
    if not service:
        return 0.0, []
    score = 0.0
    drivers: list[str] = []
    for observed in (signals.alert_service, signals.context_service):
        if observed and observed == service:
            score = max(score, 1.0)
            drivers.append(f"service_match:{observed}")
    if signals.namespace and signals.namespace == service:
        score = max(score, 0.5)
        drivers.append(f"namespace_match:{signals.namespace}")
    return score, drivers


def _active_runtime_hints(
    tag: str,
    runtime_hints: tuple[RuntimeOperatorHint, ...],
) -> list[RuntimeOperatorHint]:
    return [hint for hint in runtime_hints if hint.tag == tag]


def _hint_weight_for_tag(
    config: FeatureWorkflowConfig,
    tag: str,
    runtime_hints: tuple[RuntimeOperatorHint, ...],
) -> tuple[float, list[str]]:
    """Apply config hint weights only when the same kind is present at runtime."""
    active = _active_runtime_hints(tag, runtime_hints)
    if not active:
        return 0.0, []

    by_kind: dict[str, OperatorHint] = {hint.kind: hint for hint in config.hints_for_tag(tag)}
    total = 0.0
    drivers: list[str] = []
    for runtime in active:
        configured = by_kind.get(runtime.kind)
        weight = configured.weight if configured is not None else 0.1
        total += weight
        drivers.append(f"hint:{runtime.kind}")
        if configured and configured.note:
            drivers.append(f"hint_note:{configured.note}")
    return min(1.0, total), drivers


def _score_feature_workflow(
    config: FeatureWorkflowConfig,
    tag: str,
    signals: InvestigationSignals,
    endpoint_matches: tuple[EndpointMatch, ...],
) -> tuple[float, list[str], list[str]]:
    """Return (score, matched_on, evidence_drivers)."""
    matched_on: list[str] = []
    if tag in signals.explicit_feature_tags:
        matched_on.append("annotation:feature_tag")

    tag_endpoint_matches = [match for match in endpoint_matches if match.tag == tag]
    for match in tag_endpoint_matches:
        matched_on.append(f"endpoint:{match.pattern} ({match.match_kind})")

    base = _endpoint_match_strength(config, tag, signals.endpoint, http_method=signals.http_method)
    if tag in signals.explicit_feature_tags and base < _PREFIX_MATCH_STRENGTH:
        base = _PREFIX_MATCH_STRENGTH

    hint_boost, hint_drivers = _hint_weight_for_tag(config, tag, signals.runtime_hints)
    score = min(1.0, base + hint_boost)
    drivers = list(hint_drivers)
    if base > 0:
        drivers.append(f"endpoint_match_strength:{base:.2f}")
    return score, matched_on, drivers


def score_feature_workflow_tag(
    config: FeatureWorkflowConfig,
    tag: str,
    signals: InvestigationSignals,
    *,
    endpoint_matches: tuple[EndpointMatch, ...] = (),
) -> tuple[float, ConfidenceBreakdown, list[str], list[str]]:
    """Score a single feature tag; returns confidence, breakdown, rationale, drivers."""
    correlation, corr_drivers = _score_correlation(signals)
    topology, topo_drivers = _score_topology(config, tag, signals)
    feature, matched_on, feature_drivers = _score_feature_workflow(
        config, tag, signals, endpoint_matches
    )

    breakdown = ConfidenceBreakdown(
        correlation=round(correlation, 4),
        topology=round(topology, 4),
        feature_workflow=round(feature, 4),
    )
    confidence = breakdown.combined()

    rationale: list[str] = []
    if matched_on:
        rationale.append(f"Matched via {', '.join(matched_on)}")
    if corr_drivers:
        rationale.append(f"Correlation: {', '.join(corr_drivers)}")
    if topo_drivers:
        rationale.append(f"Topology: {', '.join(topo_drivers)}")
    if feature_drivers:
        rationale.append(f"Feature/workflow: {', '.join(feature_drivers)}")

    evidence_drivers = corr_drivers + topo_drivers + feature_drivers
    return confidence, breakdown, rationale, evidence_drivers
