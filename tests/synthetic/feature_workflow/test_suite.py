"""Feature/workflow synthetic suite (issue #1441)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.nodes.root_cause_diagnosis.node import diagnose_root_cause
from tests.synthetic.feature_workflow.run_suite import score_feature_workflow_scenario
from tests.synthetic.feature_workflow.scenario_loader import SUITE_DIR, load_scenario


@pytest.mark.synthetic
def test_periodic_workflow_scenario_passes_feature_workflow_gates() -> None:
    fixture = load_scenario(SUITE_DIR / "004-periodic-workflow")
    score = score_feature_workflow_scenario(fixture)

    assert score.passed, score.failure_reason
    assert score.top_feature_tag == "nightly_batch_settlement"
    assert score.top_confidence >= fixture.answer_key.min_confidence
    assert score.correlation_pathway_steps >= 1
    assert score.trace_contains_confidence


@pytest.mark.synthetic
@patch("app.nodes.root_cause_diagnosis.node.get_llm_for_reasoning")
@patch("app.nodes.root_cause_diagnosis.node.parse_root_cause")
@patch("app.nodes.root_cause_diagnosis.node.is_clearly_healthy", return_value=False)
@patch(
    "app.nodes.root_cause_diagnosis.node.check_evidence_availability",
    return_value=(True, True, True),
)
@patch(
    "app.nodes.root_cause_diagnosis.node.validate_and_categorize_claims",
    return_value=([], []),
)
@patch("app.nodes.root_cause_diagnosis.node.calculate_validity_score", return_value=0.85)
@patch("app.nodes.root_cause_diagnosis.node.check_vendor_evidence_missing", return_value=False)
def test_periodic_workflow_diagnose_retains_top_candidate(
    _vendor: MagicMock,
    _validity: MagicMock,
    _validate: MagicMock,
    _availability: MagicMock,
    _healthy: MagicMock,
    mock_parse: MagicMock,
    mock_llm: MagicMock,
) -> None:
    fixture = load_scenario(SUITE_DIR / "004-periodic-workflow")
    mock_parse.return_value = MagicMock(
        root_cause="Nightly batch settlement workflow latency during scheduled cron window.",
        root_cause_category=fixture.answer_key.root_cause_category or "workflow_latency",
        causal_chain=["Scheduled workflow started", "Latency SLO breached"],
        validated_claims=[],
        non_validated_claims=[],
        remediation_steps=[],
    )
    mock_llm.return_value.with_config.return_value.invoke.return_value = MagicMock(
        content=fixture.answer_key.model_response
    )

    state = {
        "alert_name": fixture.alert.get("title", fixture.scenario_id),
        "pipeline_name": "payments-api",
        "severity": "high",
        "raw_alert": fixture.alert,
        "context": fixture.context,
        "evidence": fixture.evidence,
        "incident_window": fixture.incident_window,
        "problem_md": fixture.problem_md,
        "hypotheses": [],
        "investigation_loop_count": 0,
        "available_sources": {},
    }
    result = diagnose_root_cause(state)  # type: ignore[arg-type]

    top = result.get("top_feature_workflow_candidate") or {}
    assert top.get("feature_tag") == fixture.answer_key.required_feature_tag
    assert float(top.get("confidence", 0)) >= fixture.answer_key.min_confidence
    assert result.get("correlation_pathway")
