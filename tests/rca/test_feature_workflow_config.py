from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from app.rca.feature_workflow.config_loader import (
    FeatureWorkflowConfigError,
    get_default_config_path,
    load_feature_workflow_config,
)
from app.rca.feature_workflow.matching import match_endpoint_tags, resolve_feature_service
from app.rca.feature_workflow.models import FeatureWorkflowConfig


def _write_config(path: Path, payload: dict) -> None:
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def test_default_config_path_points_at_repo_file() -> None:
    path = get_default_config_path()
    assert path.name == "feature_workflow.yml"
    assert path.parent.name == "config"
    assert path.exists()


def test_load_committed_default_config() -> None:
    config = load_feature_workflow_config()
    assert config.version == 1
    assert "nightly_batch_settlement" in config.features
    assert config.features["nightly_batch_settlement"].service == "payments-api"
    assert len(config.endpoints) >= 1
    assert any(hint.kind == "scheduled_workflow" for hint in config.operator_hints)


def test_load_valid_custom_config(tmp_path: Path) -> None:
    config_path = tmp_path / "feature_workflow.yml"
    _write_config(
        config_path,
        {
            "version": 1,
            "features": {
                "checkout_flow": {"service": "checkout-api"},
            },
            "endpoints": [
                {"pattern": "/checkout", "match": "prefix", "tags": ["checkout_flow"]},
            ],
            "operator_hints": [
                {"tag": "checkout_flow", "kind": "recent_ship", "weight": 0.2},
            ],
        },
    )
    config = load_feature_workflow_config(config_path)
    assert resolve_feature_service(config, "checkout_flow") == "checkout-api"
    assert match_endpoint_tags(config, "/checkout/v2") == ["checkout_flow"]


def test_exact_endpoint_match_respects_method(tmp_path: Path) -> None:
    config_path = tmp_path / "feature_workflow.yml"
    _write_config(
        config_path,
        {
            "version": 1,
            "features": {"batch_job": {"service": "worker"}},
            "endpoints": [
                {
                    "pattern": "/run",
                    "match": "exact",
                    "tags": ["batch_job"],
                    "methods": ["POST"],
                },
            ],
        },
    )
    config = load_feature_workflow_config(config_path)
    assert match_endpoint_tags(config, "/run", method="POST") == ["batch_job"]
    assert match_endpoint_tags(config, "/run", method="GET") == []
    assert match_endpoint_tags(config, "/run") == []


def test_prefix_endpoint_match_without_method_filter(tmp_path: Path) -> None:
    config_path = tmp_path / "feature_workflow.yml"
    _write_config(
        config_path,
        {
            "version": 1,
            "features": {"reports": {"service": "reporting"}},
            "endpoints": [
                {"pattern": "/reports", "match": "prefix", "tags": ["reports"]},
            ],
        },
    )
    config = load_feature_workflow_config(config_path)
    assert match_endpoint_tags(config, "reports/daily") == ["reports"]


def test_unknown_endpoint_tag_rejected(tmp_path: Path) -> None:
    config_path = tmp_path / "feature_workflow.yml"
    _write_config(
        config_path,
        {
            "version": 1,
            "features": {},
            "endpoints": [{"pattern": "/x", "tags": ["missing_tag"]}],
        },
    )
    with pytest.raises(FeatureWorkflowConfigError, match="unknown feature tags"):
        load_feature_workflow_config(config_path)


def test_unknown_operator_hint_tag_rejected(tmp_path: Path) -> None:
    config_path = tmp_path / "feature_workflow.yml"
    _write_config(
        config_path,
        {
            "version": 1,
            "features": {"known": {"service": "svc"}},
            "operator_hints": [{"tag": "unknown", "kind": "operator_note"}],
        },
    )
    with pytest.raises(FeatureWorkflowConfigError, match="unknown feature tag"):
        load_feature_workflow_config(config_path)


def test_invalid_yaml_raises(tmp_path: Path) -> None:
    config_path = tmp_path / "feature_workflow.yml"
    config_path.write_text("features: [\n", encoding="utf-8")
    with pytest.raises(FeatureWorkflowConfigError, match="Invalid YAML"):
        load_feature_workflow_config(config_path)


def test_missing_file_raises_by_default(tmp_path: Path) -> None:
    missing = tmp_path / "missing.yml"
    with pytest.raises(FeatureWorkflowConfigError, match="not found"):
        load_feature_workflow_config(missing)


def test_missing_file_allowed_when_flag_set(tmp_path: Path) -> None:
    missing = tmp_path / "missing.yml"
    config = load_feature_workflow_config(missing, allow_missing=True)
    assert config == FeatureWorkflowConfig.empty()


def test_legacy_flat_maps_normalize(tmp_path: Path) -> None:
    config_path = tmp_path / "feature_workflow.yml"
    _write_config(
        config_path,
        {
            "version": 1,
            "feature_services": {"legacy_feat": "legacy-svc"},
            "endpoint_tags": {
                "/legacy": {"tags": ["legacy_feat"], "match": "exact"},
            },
        },
    )
    config = load_feature_workflow_config(config_path)
    assert resolve_feature_service(config, "legacy_feat") == "legacy-svc"
    assert match_endpoint_tags(config, "/legacy") == ["legacy_feat"]
