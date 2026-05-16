from __future__ import annotations

from app.rca.feature_workflow.signals import extract_investigation_signals


def test_extract_signals_reads_common_annotations() -> None:
    signals = extract_investigation_signals(
        raw_alert={
            "commonAnnotations": {
                "endpoint": "/api/v1/settlement/run",
                "correlation_id": "corr-1",
                "operator_hints": [
                    {"tag": "nightly_batch_settlement", "kind": "scheduled_workflow"},
                ],
            }
        },
        context={"correlation_id": "corr-1", "service": "payments-api"},
    )
    assert signals.endpoint == "/api/v1/settlement/run"
    assert signals.correlation_id == "corr-1"
    assert len(signals.runtime_hints) == 1
    assert signals.runtime_hints[0].kind == "scheduled_workflow"
