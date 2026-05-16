"""Endpoint and feature-tag matching helpers for workflow config."""

from __future__ import annotations

from app.rca.feature_workflow.models import EndpointMapping, FeatureWorkflowConfig


def _normalize_path(path: str) -> str:
    stripped = path.strip()
    if not stripped:
        return "/"
    return stripped if stripped.startswith("/") else f"/{stripped}"


def endpoint_mapping_matches(
    mapping: EndpointMapping, path: str, *, method: str | None = None
) -> bool:
    """Return whether ``path`` matches a single endpoint mapping rule."""
    return _endpoint_matches(mapping, path, method=method)


def _endpoint_matches(mapping: EndpointMapping, path: str, *, method: str | None) -> bool:
    normalized = _normalize_path(path)
    pattern = _normalize_path(mapping.pattern)

    if mapping.methods:
        if method is None:
            return False
        if method.strip().upper() not in mapping.methods:
            return False

    if mapping.match == "exact":
        return normalized == pattern
    return normalized.startswith(pattern)


def match_endpoint_tags(
    config: FeatureWorkflowConfig,
    endpoint: str,
    *,
    method: str | None = None,
) -> list[str]:
    """Return feature tags whose endpoint rules match ``endpoint`` (deduped, stable order)."""
    matched: list[str] = []
    seen: set[str] = set()
    for mapping in config.endpoints:
        if not _endpoint_matches(mapping, endpoint, method=method):
            continue
        for tag in mapping.tags:
            if tag in seen:
                continue
            seen.add(tag)
            matched.append(tag)
    return matched


def resolve_feature_service(config: FeatureWorkflowConfig, tag: str) -> str | None:
    """Return the service name for a feature tag, if configured."""
    return config.service_for_tag(tag)
