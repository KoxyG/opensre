from __future__ import annotations

import pytest

from app.rca.feature_workflow.candidates import (
    build_feature_workflow_candidates,
    top_feature_workflow_candidate,
)
from app.rca.feature_workflow.models import FeatureWorkflowConfig
from app.rca.feature_workflow.scoring import (
    ConfidenceBreakdown,
    _endpoint_match_strength,
    _score_topology,
    score_feature_workflow_tag,
)
from app.rca.feature_workflow.signals import InvestigationSignals, extract_investigation_signals


def _two_tag_config() -> FeatureWorkflowConfig:
    return FeatureWorkflowConfig.model_validate(
        {
            "version": 1,
            "features": {
                "tag_a": {"service": "payments-api"},
                "tag_b": {"service": "payments-api"},
            },
            "endpoints": [
                {
                    "pattern": "/api/v1/settlement",
                    "match": "prefix",
                    "tags": ["tag_a"],
                },
            ],
            "operator_hints": [
                {"tag": "tag_a", "kind": "scheduled_workflow", "weight": 0.25},
                {"tag": "tag_b", "kind": "scheduled_workflow", "weight": 0.25},
            ],
        }
    )


def _shared_signals_alert(*, operator_hints: list[dict[str, str]] | None = None) -> dict:
    annotations: dict[str, object] = {
        "service": "payments-api",
        "endpoint": "/api/v1/settlement/run",
        "correlation_id": "corr-123",
        "feature_tags": "tag_b",
    }
    if operator_hints is not None:
        annotations["operator_hints"] = operator_hints
    return {"annotations": annotations}


def test_operator_hint_changes_ranking() -> None:
    config = _two_tag_config()
    context = {"correlation_id": "corr-123", "service": "payments-api"}
    evidence = {"git_deploy_timeline": [{"sha": "abc"}]}
    incident_window = {"confidence": 0.9}

    without_hint = build_feature_workflow_candidates(
        config=config,
        raw_alert=_shared_signals_alert(),
        context=context,
        evidence=evidence,
        incident_window=incident_window,
    )
    with_hint = build_feature_workflow_candidates(
        config=config,
        raw_alert=_shared_signals_alert(
            operator_hints=[{"tag": "tag_a", "kind": "scheduled_workflow"}]
        ),
        context=context,
        evidence=evidence,
        incident_window=incident_window,
    )

    assert [candidate.feature_tag for candidate in without_hint] == ["tag_a", "tag_b"]
    top_without = top_feature_workflow_candidate(without_hint)
    top_with = top_feature_workflow_candidate(with_hint)
    assert top_without is not None and top_with is not None

    assert top_without.feature_tag == "tag_a"
    assert top_with.feature_tag == "tag_a"
    assert top_with.confidence_breakdown.feature_workflow > (
        top_without.confidence_breakdown.feature_workflow
    )
    assert top_with.confidence > top_without.confidence
    assert "hint:scheduled_workflow" in top_with.evidence_drivers


def test_equal_correlation_and_topology_breakdown_without_hint_boost() -> None:
    config = _two_tag_config()
    signals = extract_investigation_signals(
        raw_alert=_shared_signals_alert(),
        context={"correlation_id": "corr-123", "service": "payments-api"},
        evidence={"git_deploy_timeline": [{"sha": "abc"}]},
        incident_window={"confidence": 0.9},
    )

    _, breakdown_a, _, _ = score_feature_workflow_tag(config, "tag_a", signals)
    _, breakdown_b, _, _ = score_feature_workflow_tag(config, "tag_b", signals)

    assert breakdown_a.correlation == breakdown_b.correlation
    assert breakdown_a.topology == breakdown_b.topology
    assert breakdown_a.correlation > 0
    assert breakdown_a.topology > 0


def test_runtime_hint_flips_winner_when_base_scores_close() -> None:
    config = FeatureWorkflowConfig.model_validate(
        {
            "version": 1,
            "features": {
                "tag_a": {"service": "payments-api"},
                "tag_b": {"service": "payments-api"},
            },
            "endpoints": [],
            "operator_hints": [
                {"tag": "tag_b", "kind": "scheduled_workflow", "weight": 0.3},
            ],
        }
    )
    alert = {
        "annotations": {
            "service": "payments-api",
            "feature_tags": "tag_a, tag_b",
            "correlation_id": "corr-123",
        }
    }
    context = {"correlation_id": "corr-123", "service": "payments-api"}

    baseline = build_feature_workflow_candidates(
        config=config,
        raw_alert=alert,
        context=context,
    )
    boosted = build_feature_workflow_candidates(
        config=config,
        raw_alert={
            "annotations": {
                **alert["annotations"],
                "operator_hints": [{"tag": "tag_b", "kind": "scheduled_workflow"}],
            }
        },
        context=context,
    )

    assert top_feature_workflow_candidate(baseline) is not None
    assert top_feature_workflow_candidate(boosted) is not None
    top_baseline = top_feature_workflow_candidate(baseline)
    top_boosted = top_feature_workflow_candidate(boosted)
    assert top_baseline is not None and top_boosted is not None
    assert top_baseline.feature_tag == "tag_a"
    assert top_boosted.feature_tag == "tag_b"
    tag_b_baseline = next(c for c in baseline if c.feature_tag == "tag_b")
    assert top_boosted.confidence > tag_b_baseline.confidence


def test_score_topology_dedupes_service_match_when_alert_and_context_agree() -> None:
    config = _two_tag_config()
    signals = InvestigationSignals(
        alert_service="payments-api",
        context_service="payments-api",
    )

    score, drivers = _score_topology(config, "tag_a", signals)

    assert score == 1.0
    assert drivers.count("service_match:payments-api") == 1


def test_endpoint_match_strength_prefix_only_when_exact_rule_does_not_match() -> None:
    """Prefix-only hits must not inherit exact strength from another mapping for the same tag."""
    config = FeatureWorkflowConfig.model_validate(
        {
            "version": 1,
            "features": {"nightly_batch_settlement": {"service": "payments-api"}},
            "endpoints": [
                {
                    "pattern": "/api/v1/settlement/run",
                    "match": "exact",
                    "tags": ["nightly_batch_settlement"],
                    "methods": ["POST"],
                },
                {
                    "pattern": "/api/v1/settlement",
                    "match": "prefix",
                    "tags": ["nightly_batch_settlement"],
                },
            ],
        }
    )

    assert _endpoint_match_strength(
        config,
        "nightly_batch_settlement",
        "/api/v1/settlement/sub",
        http_method="GET",
    ) == pytest.approx(0.7)

    assert _endpoint_match_strength(
        config,
        "nightly_batch_settlement",
        "/api/v1/settlement/run",
        http_method="POST",
    ) == pytest.approx(1.0)


def test_confidence_breakdown_combined_respects_weights() -> None:
    breakdown = ConfidenceBreakdown(correlation=1.0, topology=1.0, feature_workflow=1.0)
    assert breakdown.combined() == 1.0

    partial = ConfidenceBreakdown(correlation=0.0, topology=0.0, feature_workflow=1.0)
    assert partial.combined() == pytest.approx(0.35)
