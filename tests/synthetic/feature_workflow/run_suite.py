"""Run feature/workflow synthetic scenarios (deterministic hypothesis gates)."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from app.delivery.publish_findings.formatters.infrastructure import build_investigation_trace
from app.delivery.publish_findings.report_context import build_report_context
from app.rca.feature_workflow.state_fields import build_feature_workflow_state_fields
from tests.synthetic.feature_workflow.scenario_loader import (
    SUITE_DIR,
    FeatureWorkflowScenarioFixture,
    load_all_scenarios,
    load_scenario,
)


@dataclass(frozen=True)
class FeatureWorkflowScenarioScore:
    scenario_id: str
    passed: bool
    top_feature_tag: str
    top_confidence: float
    missing_keywords: list[str]
    missing_evidence_drivers: list[str]
    failure_reason: str = ""
    correlation_pathway_steps: int = 0
    trace_contains_confidence: bool = False


def score_feature_workflow_scenario(
    fixture: FeatureWorkflowScenarioFixture,
) -> FeatureWorkflowScenarioScore:
    fields = build_feature_workflow_state_fields(
        raw_alert=fixture.alert,
        context=fixture.context,
        evidence=fixture.evidence,
        incident_window=fixture.incident_window,
    )
    top = fields.get("top_feature_workflow_candidate") or {}
    pathway = fields.get("correlation_pathway") or []

    top_tag = str(top.get("feature_tag") or "")
    try:
        top_confidence = float(top.get("confidence", 0.0))
    except (TypeError, ValueError):
        top_confidence = 0.0

    failures: list[str] = []
    if top_tag != fixture.answer_key.required_feature_tag:
        failures.append(
            f"top feature tag {top_tag!r} != required {fixture.answer_key.required_feature_tag!r}"
        )
    if top_confidence < fixture.answer_key.min_confidence:
        failures.append(
            f"confidence {top_confidence:.2f} < min {fixture.answer_key.min_confidence:.2f}"
        )

    rationale_blob = " ".join(top.get("rationale") or []).lower()
    drivers = [str(d) for d in top.get("evidence_drivers") or []]
    matched_on_blob = " ".join(top.get("matched_on") or []).lower()
    searchable = " ".join(
        [rationale_blob, " ".join(drivers).lower(), matched_on_blob, top_tag.lower()]
    )
    missing_keywords = [
        keyword
        for keyword in fixture.answer_key.required_keywords
        if keyword.lower() not in searchable
    ]
    if missing_keywords:
        failures.append(f"missing required keywords in rationale/tag: {missing_keywords}")

    missing_drivers = [
        driver for driver in fixture.answer_key.required_evidence_drivers if driver not in drivers
    ]
    if missing_drivers:
        failures.append(f"missing evidence drivers: {missing_drivers}")

    if not pathway:
        failures.append("correlation_pathway is empty")

    report_state = {
        "pipeline_name": "feature-workflow-synthetic",
        "alert_name": fixture.alert.get("title", fixture.scenario_id),
        "root_cause": "Synthetic feature/workflow validation",
        **fields,
    }
    ctx = build_report_context(report_state)  # type: ignore[arg-type]
    trace = build_investigation_trace(ctx)
    trace_has_confidence = any(
        "Feature/workflow hypothesis" in step and "confidence" in step for step in trace
    )
    if not trace_has_confidence:
        failures.append("investigation trace missing feature/workflow confidence line")

    return FeatureWorkflowScenarioScore(
        scenario_id=fixture.scenario_id,
        passed=not failures,
        top_feature_tag=top_tag,
        top_confidence=top_confidence,
        missing_keywords=missing_keywords,
        missing_evidence_drivers=missing_drivers,
        failure_reason="; ".join(failures),
        correlation_pathway_steps=len(pathway),
        trace_contains_confidence=trace_has_confidence,
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run feature/workflow synthetic RCA scenarios.")
    parser.add_argument(
        "--scenario",
        default="",
        help="Run one scenario directory name, e.g. 004-periodic-workflow.",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON results.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.scenario:
        fixtures = [load_scenario(SUITE_DIR / args.scenario)]
    else:
        fixtures = load_all_scenarios()

    scores = [score_feature_workflow_scenario(fixture) for fixture in fixtures]
    if args.json:
        print(json.dumps([asdict(score) for score in scores], indent=2))
    else:
        for score in scores:
            status = "PASS" if score.passed else "FAIL"
            print(
                f"{status} {score.scenario_id}: tag={score.top_feature_tag!r} "
                f"confidence={score.top_confidence:.2f}"
            )
            if score.failure_reason:
                print(f"  {score.failure_reason}")

    return 0 if all(score.passed for score in scores) else 1


if __name__ == "__main__":
    raise SystemExit(main())
