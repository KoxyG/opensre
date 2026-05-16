"""Structured outputs for feature/workflow candidate ranking."""

from __future__ import annotations

from app.strict_config import StrictConfigModel


class ConfidenceBreakdown(StrictConfigModel):
    """Per-signal confidence contributions (each bucket capped in scoring)."""

    correlation: float = 0.0
    topology: float = 0.0
    feature_workflow: float = 0.0


class FeatureWorkflowCandidate(StrictConfigModel):
    """A ranked feature/workflow hypothesis with explainable scoring."""

    feature_tag: str
    service: str | None = None
    matched_on: list[str] = []
    confidence: float = 0.0
    confidence_breakdown: ConfidenceBreakdown = ConfidenceBreakdown()
    rationale: list[str] = []
    evidence_drivers: list[str] = []
