from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from app.agent.investigation import ConnectedInvestigationAgent
from app.agent.prompt import build_system_prompt
from app.delivery.publish_findings.formatters.infrastructure import build_investigation_trace
from app.delivery.publish_findings.report_context import build_report_context
from app.agent.result import InvestigationResult


@pytest.fixture
def feature_workflow_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    config_path = tmp_path / "feature_workflow.yml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "features": {
                    "nightly_batch_settlement": {"service": "payments-api"},
                },
                "endpoints": [
                    {
                        "pattern": "/api/v1/settlement/run",
                        "match": "exact",
                        "tags": ["nightly_batch_settlement"],
                    },
                ],
                "operator_hints": [
                    {
                        "tag": "nightly_batch_settlement",
                        "kind": "scheduled_workflow",
                        "weight": 0.2,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("OPENSRE_FEATURE_WORKFLOW_CONFIG", str(config_path))
    return config_path


def _investigation_state() -> dict:
    return {
        "alert_name": "Settlement batch delayed",
        "pipeline_name": "payments-api",
        "severity": "high",
        "alert_source": "grafana",
        "raw_alert": {
            "commonAnnotations": {
                "service": "payments-api",
                "endpoint": "/api/v1/settlement/run",
                "correlation_id": "corr-99",
                "operator_hints": [
                    {"tag": "nightly_batch_settlement", "kind": "scheduled_workflow"},
                ],
            }
        },
        "context": {"correlation_id": "corr-99", "service": "payments-api"},
        "evidence": {},
        "incident_window": {"confidence": 0.9},
        "resolved_integrations": {},
    }


@patch("app.agent.investigation.get_agent_llm")
@patch("app.agent.investigation.parse_diagnosis")
@patch("app.agent.investigation.get_registered_tools", return_value=[])
def test_investigation_agent_populates_feature_workflow_fields(
    _tools: MagicMock,
    mock_parse: MagicMock,
    mock_llm_factory: MagicMock,
    feature_workflow_config: Path,
) -> None:
    del feature_workflow_config
    mock_parse.return_value = InvestigationResult(
        root_cause="Batch settlement workflow lag",
        root_cause_category="unknown",
    )
    mock_llm = MagicMock()
    mock_response = MagicMock()
    mock_response.has_tool_calls = False
    mock_response.tool_calls = []
    mock_response.content = "done"
    mock_llm.invoke.return_value = mock_response
    mock_llm.tool_schemas.return_value = []
    mock_llm_factory.return_value = mock_llm

    result = ConnectedInvestigationAgent().run(_investigation_state())

    top = result.get("top_feature_workflow_candidate")
    assert top is not None
    assert top["feature_tag"] == "nightly_batch_settlement"
    assert top["confidence"] > 0
    assert result.get("correlation_pathway")
    assert "hint:scheduled_workflow" in top.get("evidence_drivers", [])


def test_build_system_prompt_includes_feature_workflow_section(
    feature_workflow_config: Path,
) -> None:
    del feature_workflow_config
    from app.rca.feature_workflow.state_fields import build_feature_workflow_state_fields

    state = {
        **_investigation_state(),
        **build_feature_workflow_state_fields(
            raw_alert=_investigation_state()["raw_alert"],
            context=_investigation_state()["context"],
            evidence=_investigation_state()["evidence"],
            incident_window=_investigation_state()["incident_window"],
        ),
    }
    prompt = build_system_prompt(state)

    assert "Feature/workflow hypothesis" in prompt
    assert "nightly_batch_settlement" in prompt
    assert "confidence" in prompt.lower()


def test_build_investigation_trace_includes_feature_workflow_confidence(
    feature_workflow_config: Path,
) -> None:
    del feature_workflow_config
    from app.rca.feature_workflow.state_fields import build_feature_workflow_state_fields

    state = {
        **_investigation_state(),
        "root_cause": "Workflow lag",
        **build_feature_workflow_state_fields(
            raw_alert=_investigation_state()["raw_alert"],
            context=_investigation_state()["context"],
            evidence=_investigation_state()["evidence"],
            incident_window=_investigation_state()["incident_window"],
        ),
    }
    ctx = build_report_context(state)  # type: ignore[arg-type]
    trace = build_investigation_trace(ctx)

    assert any("Feature/workflow hypothesis" in step for step in trace)
    assert any("nightly_batch_settlement" in step for step in trace)
    assert any("confidence" in step for step in trace)
    assert any("driven by:" in step for step in trace)
