"""Feature/workflow synthetic suite (issue #1441)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.agent.investigation import ConnectedInvestigationAgent
from app.agent.result import InvestigationResult
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
@patch("app.agent.investigation.get_agent_llm")
@patch("app.agent.investigation.parse_diagnosis")
@patch("app.agent.investigation.get_registered_tools", return_value=[])
def test_periodic_workflow_agent_retains_top_candidate(
    _tools: MagicMock,
    mock_parse: MagicMock,
    mock_llm_factory: MagicMock,
) -> None:
    fixture = load_scenario(SUITE_DIR / "004-periodic-workflow")
    mock_parse.return_value = InvestigationResult(
        root_cause="Nightly batch settlement workflow latency during scheduled cron window.",
        root_cause_category=fixture.answer_key.root_cause_category or "workflow_latency",
    )
    mock_llm = MagicMock()
    mock_response = MagicMock()
    mock_response.has_tool_calls = False
    mock_response.tool_calls = []
    mock_response.content = fixture.answer_key.model_response
    mock_llm.invoke.return_value = mock_response
    mock_llm.tool_schemas.return_value = []
    mock_llm_factory.return_value = mock_llm

    state = {
        "alert_name": fixture.alert.get("title", fixture.scenario_id),
        "pipeline_name": "payments-api",
        "severity": "high",
        "alert_source": "grafana",
        "raw_alert": fixture.alert,
        "context": fixture.context,
        "evidence": fixture.evidence,
        "incident_window": fixture.incident_window,
        "resolved_integrations": {},
    }
    result = ConnectedInvestigationAgent().run(state)

    top = result.get("top_feature_workflow_candidate") or {}
    assert top.get("feature_tag") == fixture.answer_key.required_feature_tag
    assert float(top.get("confidence", 0)) >= fixture.answer_key.min_confidence
    assert result.get("correlation_pathway")
