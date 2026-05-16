"""Feature/workflow hypothesis wiring for the investigation agent."""

from __future__ import annotations

from typing import Any

from app.rca.feature_workflow.state_fields import build_feature_workflow_state_fields
from app.state import InvestigationState


def resolve_feature_workflow_fields(state: InvestigationState) -> dict[str, Any]:
    """Build feature/workflow candidate fields from the current investigation state."""
    return build_feature_workflow_state_fields(
        raw_alert=state.get("raw_alert", {}),
        context=state.get("context", {}),
        evidence=state.get("evidence", {}),
        incident_window=state.get("incident_window"),
    )
