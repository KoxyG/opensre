"""Extract investigation signals from alert, context, and evidence dicts."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from app.rca.feature_workflow.models import OperatorHintKind


@dataclass(frozen=True)
class EndpointMatch:
    tag: str
    pattern: str
    match_kind: str


@dataclass(frozen=True)
class RuntimeOperatorHint:
    tag: str
    kind: OperatorHintKind


@dataclass(frozen=True)
class InvestigationSignals:
    """Normalized inputs for feature/workflow candidate scoring."""

    endpoint: str | None = None
    http_method: str | None = None
    alert_service: str | None = None
    context_service: str | None = None
    namespace: str | None = None
    correlation_id: str | None = None
    context_correlation_id: str | None = None
    incident_window_confidence: float = 0.0
    has_deploy_timeline: bool = False
    endpoint_matches: tuple[EndpointMatch, ...] = ()
    explicit_feature_tags: tuple[str, ...] = ()
    runtime_hints: tuple[RuntimeOperatorHint, ...] = ()


def _as_dict(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _annotations(raw_alert: dict[str, Any] | str) -> dict[str, Any]:
    alert = _as_dict(raw_alert) if not isinstance(raw_alert, dict) else raw_alert
    for key in ("annotations", "commonAnnotations"):
        value = alert.get(key)
        if isinstance(value, dict):
            return value
    for key in ("labels", "commonLabels"):
        value = alert.get(key)
        if isinstance(value, dict):
            return value
    return {}


def _first_str(*values: object) -> str | None:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _parse_runtime_hints(annotations: dict[str, Any]) -> list[RuntimeOperatorHint]:
    hints: list[RuntimeOperatorHint] = []
    raw = annotations.get("operator_hints")
    if isinstance(raw, list):
        for entry in raw:
            if not isinstance(entry, dict):
                continue
            tag = _first_str(entry.get("tag"))
            kind = _first_str(entry.get("kind"))
            if tag and kind in ("scheduled_workflow", "recent_ship", "operator_note"):
                hints.append(RuntimeOperatorHint(tag=tag, kind=kind))  # type: ignore[arg-type]
        return hints

    for kind, key in (
        ("scheduled_workflow", "scheduled_workflows"),
        ("recent_ship", "recently_shipped_features"),
    ):
        raw_tags = annotations.get(key)
        if raw_tags is None:
            continue
        if isinstance(raw_tags, str):
            tags = [part.strip() for part in raw_tags.split(",") if part.strip()]
        elif isinstance(raw_tags, list):
            tags = [str(part).strip() for part in raw_tags if str(part).strip()]
        else:
            continue
        hints.extend(RuntimeOperatorHint(tag=tag, kind=kind) for tag in tags)  # type: ignore[arg-type]

    workflow = _first_str(annotations.get("workflow"), annotations.get("workflow_name"))
    if workflow:
        hints.append(RuntimeOperatorHint(tag=workflow, kind="scheduled_workflow"))
    return hints


def _explicit_tags(annotations: dict[str, Any]) -> list[str]:
    tags: list[str] = []
    for key in ("feature_tags", "feature_tag", "initiating_feature"):
        raw = annotations.get(key)
        if raw is None:
            continue
        if isinstance(raw, str):
            parts = [part.strip() for part in raw.split(",") if part.strip()]
            tags.extend(parts)
        elif isinstance(raw, list):
            tags.extend(str(part).strip() for part in raw if str(part).strip())
    return tags


def extract_investigation_signals(
    *,
    raw_alert: dict[str, Any] | str,
    context: dict[str, Any] | None = None,
    evidence: dict[str, Any] | None = None,
    incident_window: dict[str, Any] | None = None,
) -> InvestigationSignals:
    """Collect correlation, topology, and feature signals from investigation state slices."""
    ctx = context or {}
    ev = evidence or {}
    annotations = _annotations(raw_alert)

    endpoint = _first_str(
        annotations.get("http_path"),
        annotations.get("endpoint"),
        annotations.get("route"),
        ctx.get("endpoint"),
        ctx.get("http_path"),
        ctx.get("route"),
    )
    http_method = _first_str(
        annotations.get("http_method"),
        annotations.get("method"),
        ctx.get("http_method"),
        ctx.get("method"),
    )

    alert_service = _first_str(
        annotations.get("service"),
        annotations.get("service_name"),
        _as_dict(raw_alert).get("service") if isinstance(raw_alert, dict) else None,
    )
    context_service = _first_str(
        ctx.get("service"), ctx.get("service_name"), ctx.get("pipeline_name")
    )

    correlation_id = _first_str(
        annotations.get("correlation_id"),
        annotations.get("correlationId"),
    )
    context_correlation_id = _first_str(ctx.get("correlation_id"), ctx.get("correlationId"))

    window_confidence = 0.0
    if isinstance(incident_window, dict):
        try:
            window_confidence = float(incident_window.get("confidence", 0.0) or 0.0)
        except (TypeError, ValueError):
            window_confidence = 0.0

    deploy_count = ev.get("git_deploy_timeline_count")
    has_deploy = bool(ev.get("git_deploy_timeline")) or (
        isinstance(deploy_count, int) and deploy_count > 0
    )

    return InvestigationSignals(
        endpoint=endpoint,
        http_method=http_method,
        alert_service=alert_service,
        context_service=context_service,
        namespace=_first_str(annotations.get("namespace"), ctx.get("namespace")),
        correlation_id=correlation_id,
        context_correlation_id=context_correlation_id,
        incident_window_confidence=max(0.0, min(1.0, window_confidence)),
        has_deploy_timeline=has_deploy,
        explicit_feature_tags=tuple(_explicit_tags(annotations)),
        runtime_hints=tuple(_parse_runtime_hints(annotations)),
    )
