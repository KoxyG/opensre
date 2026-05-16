"""Load feature/workflow configuration from YAML."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from app.rca.feature_workflow.models import FeatureWorkflowConfig

logger = logging.getLogger(__name__)

_ENV_CONFIG_PATH = "OPENSRE_FEATURE_WORKFLOW_CONFIG"
_DEFAULT_RELATIVE_PATH = Path("config") / "feature_workflow.yml"


class FeatureWorkflowConfigError(Exception):
    """Raised when feature/workflow configuration cannot be loaded or validated."""


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def get_default_config_path() -> Path:
    """Return the repository default ``config/feature_workflow.yml`` path."""
    return _repo_root() / _DEFAULT_RELATIVE_PATH


def resolve_config_path(path: Path | None = None) -> Path:
    """Resolve explicit path, env override, or repository default."""
    if path is not None:
        return path.expanduser().resolve()
    env_path = os.getenv(_ENV_CONFIG_PATH, "").strip()
    if env_path:
        return Path(env_path).expanduser().resolve()
    return get_default_config_path()


def load_feature_workflow_config(
    path: Path | None = None,
    *,
    allow_missing: bool = False,
) -> FeatureWorkflowConfig:
    """Load and validate feature/workflow config from YAML.

    Args:
        path: Optional explicit config path. When omitted, uses
            ``OPENSRE_FEATURE_WORKFLOW_CONFIG`` or the repo default file.
        allow_missing: When True, a missing file yields an empty config instead of
            raising. Intended for optional rollout; tests should pass explicit paths.
    """
    resolved = resolve_config_path(path)
    if not resolved.exists():
        if allow_missing:
            logger.debug("Feature/workflow config not found at %s; using empty config", resolved)
            return FeatureWorkflowConfig.empty()
        raise FeatureWorkflowConfigError(f"Feature/workflow config not found: {resolved}")

    try:
        raw = yaml.safe_load(resolved.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise FeatureWorkflowConfigError(f"Invalid YAML in {resolved}: {exc}") from exc
    except OSError as exc:
        raise FeatureWorkflowConfigError(f"Cannot read {resolved}: {exc}") from exc

    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise FeatureWorkflowConfigError(
            f"Feature/workflow config root must be a mapping, got {type(raw).__name__}"
        )

    try:
        return FeatureWorkflowConfig.model_validate(_normalize_raw_document(raw))
    except ValidationError as exc:
        raise FeatureWorkflowConfigError(
            f"Invalid feature/workflow config in {resolved}: {exc}"
        ) from exc


def _normalize_raw_document(raw: dict[str, Any]) -> dict[str, Any]:
    """Accept legacy-style flat maps in YAML and normalize to model field names."""
    normalized = dict(raw)
    if "endpoint_tags" in normalized and "endpoints" not in normalized:
        endpoints: list[dict[str, Any]] = []
        flat = normalized.pop("endpoint_tags")
        if isinstance(flat, dict):
            for pattern, value in flat.items():
                if isinstance(value, list):
                    endpoints.append({"pattern": pattern, "tags": value})
                elif isinstance(value, dict):
                    entry = {"pattern": pattern, **value}
                    endpoints.append(entry)
        normalized["endpoints"] = endpoints

    if "feature_services" in normalized and "features" not in normalized:
        services = normalized.pop("feature_services")
        if isinstance(services, dict):
            normalized["features"] = {
                tag: {"service": service} if isinstance(service, str) else service
                for tag, service in services.items()
            }
    return normalized
