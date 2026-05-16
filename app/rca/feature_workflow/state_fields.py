"""Map investigation state slices to feature/workflow candidate fields."""

from __future__ import annotations

import logging
from typing import Any

from app.rca.feature_workflow.candidates import (
    FeatureWorkflowCandidate,
    build_feature_workflow_candidates,
    top_feature_workflow_candidate,
)
from app.rca.feature_workflow.config_loader import (
    FeatureWorkflowConfigError,
    load_feature_workflow_config,
)

logger = logging.getLogger(__name__)


def _build_correlation_pathway(
    candidates: list[FeatureWorkflowCandidate],
    top: FeatureWorkflowCandidate | None,
) -> list[dict[str, Any]]:
    """Structured correlation-pathway entries for reports and traces."""
    pathway: list[dict[str, Any]] = []
    for rank, candidate in enumerate(candidates, start=1):
        pathway.append(
            {
                "kind": "feature_workflow",
                "rank": rank,
                "feature_tag": candidate.feature_tag,
                "service": candidate.service,
                "confidence": candidate.confidence,
                "confidence_breakdown": {
                    "correlation": candidate.confidence_breakdown.correlation,
                    "topology": candidate.confidence_breakdown.topology,
                    "feature_workflow": candidate.confidence_breakdown.feature_workflow,
                },
                "matched_on": list(candidate.matched_on),
                "rationale": list(candidate.rationale),
                "evidence_drivers": list(candidate.evidence_drivers),
            }
        )
    if top is not None and pathway and pathway[0].get("feature_tag") != top.feature_tag:
        top_entry = next(
            (entry for entry in pathway if entry.get("feature_tag") == top.feature_tag),
            None,
        )
        if top_entry is not None:
            pathway.remove(top_entry)
            pathway.insert(0, top_entry)
    return pathway


def build_feature_workflow_state_fields(
    *,
    raw_alert: dict[str, Any] | str,
    context: dict[str, Any] | None = None,
    evidence: dict[str, Any] | None = None,
    incident_window: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return state update dict for feature/workflow hypothesis fields."""
    empty: dict[str, Any] = {
        "feature_workflow_candidates": [],
        "top_feature_workflow_candidate": None,
        "correlation_pathway": [],
    }
    try:
        config = load_feature_workflow_config(allow_missing=True)
    except FeatureWorkflowConfigError as exc:
        logger.warning("Feature/workflow config unavailable: %s", exc)
        return empty

    if not config.features:
        return empty

    candidates = build_feature_workflow_candidates(
        config=config,
        raw_alert=raw_alert,
        context=context,
        evidence=evidence,
        incident_window=incident_window,
    )
    top = top_feature_workflow_candidate(candidates)
    return {
        "feature_workflow_candidates": [candidate.to_dict() for candidate in candidates],
        "top_feature_workflow_candidate": top.to_dict() if top is not None else None,
        "correlation_pathway": _build_correlation_pathway(candidates, top),
    }
