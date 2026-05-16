"""Load feature/workflow synthetic RCA scenario fixtures."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

SUITE_DIR = Path(__file__).resolve().parent


@dataclass(frozen=True)
class FeatureWorkflowAnswerKey:
    required_feature_tag: str
    required_keywords: list[str]
    required_evidence_drivers: list[str]
    min_confidence: float = 0.5
    root_cause_category: str = ""
    model_response: str = ""


@dataclass(frozen=True)
class FeatureWorkflowScenarioFixture:
    scenario_id: str
    scenario_dir: Path
    alert: dict[str, Any]
    context: dict[str, Any]
    evidence: dict[str, Any]
    incident_window: dict[str, Any] | None
    answer_key: FeatureWorkflowAnswerKey
    problem_md: str


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return payload


def _read_yaml(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected YAML object in {path}")
    return payload


def _build_problem_md(alert: dict[str, Any], scenario_id: str) -> str:
    annotations = alert.get("commonAnnotations") or alert.get("annotations") or {}
    summary = annotations.get("summary") or alert.get("title") or scenario_id
    return f"# Incident\n\n{summary}\n"


def load_scenario(scenario_dir: Path) -> FeatureWorkflowScenarioFixture:
    scenario_yml = _read_yaml(scenario_dir / "scenario.yml")
    scenario_id = str(scenario_yml.get("scenario_id") or scenario_dir.name)
    alert = _read_json(scenario_dir / "alert.json")
    context = (
        _read_json(scenario_dir / "context.json")
        if (scenario_dir / "context.json").exists()
        else {}
    )
    evidence = (
        _read_json(scenario_dir / "evidence.json")
        if (scenario_dir / "evidence.json").exists()
        else {}
    )
    incident_window: dict[str, Any] | None = None
    if (scenario_dir / "incident_window.json").exists():
        incident_window = _read_json(scenario_dir / "incident_window.json")

    answer_raw = _read_yaml(scenario_dir / "answer.yml")
    answer_key = FeatureWorkflowAnswerKey(
        required_feature_tag=str(answer_raw["required_feature_tag"]),
        required_keywords=[str(k) for k in answer_raw.get("required_keywords", [])],
        required_evidence_drivers=[str(d) for d in answer_raw.get("required_evidence_drivers", [])],
        min_confidence=float(answer_raw.get("min_confidence", 0.5)),
        root_cause_category=str(answer_raw.get("root_cause_category", "")),
        model_response=str(answer_raw.get("model_response", "")),
    )
    return FeatureWorkflowScenarioFixture(
        scenario_id=scenario_id,
        scenario_dir=scenario_dir,
        alert=alert,
        context=context,
        evidence=evidence,
        incident_window=incident_window,
        answer_key=answer_key,
        problem_md=_build_problem_md(alert, scenario_id),
    )


def load_all_scenarios(suite_dir: Path | None = None) -> list[FeatureWorkflowScenarioFixture]:
    root = suite_dir or SUITE_DIR
    fixtures: list[FeatureWorkflowScenarioFixture] = []
    for path in sorted(root.iterdir()):
        if not path.is_dir() or path.name.startswith("_"):
            continue
        if not (path / "answer.yml").exists():
            continue
        fixtures.append(load_scenario(path))
    return fixtures
