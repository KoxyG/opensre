"""Build and rank feature/workflow RCA candidates."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from app.rca.feature_workflow.matching import match_endpoint_tags
from app.rca.feature_workflow.models import FeatureWorkflowConfig
from app.rca.feature_workflow.scoring import ConfidenceBreakdown, score_feature_workflow_tag
from app.rca.feature_workflow.signals import (
    EndpointMatch,
    InvestigationSignals,
    extract_investigation_signals,
)


@dataclass(frozen=True)
class FeatureWorkflowCandidate:
    feature_tag: str
    service: str | None
    confidence: float
    confidence_breakdown: ConfidenceBreakdown
    matched_on: tuple[str, ...]
    rationale: tuple[str, ...]
    evidence_drivers: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "feature_tag": self.feature_tag,
            "service": self.service,
            "confidence": self.confidence,
            "confidence_breakdown": asdict(self.confidence_breakdown),
            "matched_on": list(self.matched_on),
            "rationale": list(self.rationale),
            "evidence_drivers": list(self.evidence_drivers),
        }


def _discover_endpoint_matches(
    config: FeatureWorkflowConfig,
    endpoint: str | None,
    *,
    http_method: str | None,
) -> tuple[EndpointMatch, ...]:
    if not endpoint:
        return ()
    matched_tags = set(match_endpoint_tags(config, endpoint, method=http_method))
    matches: list[EndpointMatch] = []
    for mapping in config.endpoints:
        if not any(tag in matched_tags for tag in mapping.tags):
            continue
        for tag in mapping.tags:
            if tag in matched_tags:
                matches.append(
                    EndpointMatch(tag=tag, pattern=mapping.pattern, match_kind=mapping.match)
                )
    return tuple(matches)


def _matched_on_for_tag(
    tag: str,
    signals: InvestigationSignals,
    endpoint_matches: tuple[EndpointMatch, ...],
) -> tuple[str, ...]:
    entries: list[str] = []
    if tag in signals.explicit_feature_tags:
        entries.append("annotation:feature_tag")
    for match in endpoint_matches:
        if match.tag == tag:
            entries.append(f"endpoint:{match.pattern} ({match.match_kind})")
    return tuple(entries)


def _discover_candidate_tags(
    config: FeatureWorkflowConfig,
    endpoint_matches: tuple[EndpointMatch, ...],
    signals: InvestigationSignals,
) -> list[str]:
    tags: list[str] = []
    seen: set[str] = set()

    def add(tag: str) -> None:
        if tag in seen or tag not in config.features:
            return
        seen.add(tag)
        tags.append(tag)

    for tag in signals.explicit_feature_tags:
        add(tag)
    for match in endpoint_matches:
        add(match.tag)
    for hint in signals.runtime_hints:
        add(hint.tag)
    return tags


def build_feature_workflow_candidates(
    *,
    config: FeatureWorkflowConfig,
    raw_alert: dict[str, Any] | str,
    context: dict[str, Any] | None = None,
    evidence: dict[str, Any] | None = None,
    incident_window: dict[str, Any] | None = None,
) -> list[FeatureWorkflowCandidate]:
    """Discover feature tags and return candidates ranked by confidence (desc)."""
    signals = extract_investigation_signals(
        raw_alert=raw_alert,
        context=context,
        evidence=evidence,
        incident_window=incident_window,
    )
    endpoint_matches = _discover_endpoint_matches(
        config,
        signals.endpoint,
        http_method=signals.http_method,
    )
    tag_names = _discover_candidate_tags(config, endpoint_matches, signals)

    candidates: list[FeatureWorkflowCandidate] = []
    for tag in tag_names:
        confidence, breakdown, rationale, drivers = score_feature_workflow_tag(
            config,
            tag,
            signals,
            endpoint_matches=endpoint_matches,
        )
        candidates.append(
            FeatureWorkflowCandidate(
                feature_tag=tag,
                service=config.service_for_tag(tag),
                confidence=confidence,
                confidence_breakdown=breakdown,
                matched_on=_matched_on_for_tag(tag, signals, endpoint_matches),
                rationale=tuple(rationale),
                evidence_drivers=tuple(drivers),
            )
        )

    candidates.sort(key=lambda item: (-item.confidence, item.feature_tag))
    return candidates


def top_feature_workflow_candidate(
    candidates: list[FeatureWorkflowCandidate],
) -> FeatureWorkflowCandidate | None:
    """Return the highest-confidence candidate, if any."""
    return candidates[0] if candidates else None
