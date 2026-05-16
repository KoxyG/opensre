"""Pydantic models for feature/workflow RCA configuration."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator, model_validator

from app.strict_config import StrictConfigModel

MatchKind = Literal["exact", "prefix"]
OperatorHintKind = Literal["scheduled_workflow", "recent_ship", "operator_note"]


class FeatureDefinition(StrictConfigModel):
    """Maps a feature tag to an owning service."""

    service: str
    description: str = ""


class EndpointMapping(StrictConfigModel):
    """Maps an HTTP path pattern to one or more feature tags."""

    pattern: str
    tags: list[str]
    match: MatchKind = "exact"
    methods: list[str] = Field(default_factory=list)

    @field_validator("pattern")
    @classmethod
    def _pattern_non_empty(cls, value: str) -> str:
        if not value:
            raise ValueError("pattern must be non-empty")
        return value

    @field_validator("tags")
    @classmethod
    def _tags_non_empty(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("tags must contain at least one feature tag")
        return value

    @field_validator("methods", mode="before")
    @classmethod
    def _normalize_methods(cls, value: object) -> list[str]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise TypeError("methods must be a list of HTTP verbs")
        return [str(item).strip().upper() for item in value if str(item).strip()]


class OperatorHint(StrictConfigModel):
    """Optional operator-provided bias for a feature tag during ranking."""

    tag: str
    kind: OperatorHintKind
    weight: float = Field(default=0.1, ge=0.0, le=1.0)
    note: str = ""


class FeatureWorkflowConfig(StrictConfigModel):
    """Top-level feature/workflow configuration document."""

    version: int = 1
    features: dict[str, FeatureDefinition] = Field(default_factory=dict)
    endpoints: list[EndpointMapping] = Field(default_factory=list)
    operator_hints: list[OperatorHint] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_references(self) -> FeatureWorkflowConfig:
        known = set(self.features)
        for mapping in self.endpoints:
            unknown = [tag for tag in mapping.tags if tag not in known]
            if unknown:
                raise ValueError(
                    f"endpoint pattern {mapping.pattern!r} references unknown feature tags: "
                    f"{', '.join(sorted(unknown))}"
                )
        for hint in self.operator_hints:
            if hint.tag not in known:
                raise ValueError(f"operator hint references unknown feature tag {hint.tag!r}")
        return self

    @classmethod
    def empty(cls) -> FeatureWorkflowConfig:
        """Return an empty document (used when config file is absent)."""
        return cls(version=1)

    def hints_for_tag(self, tag: str) -> list[OperatorHint]:
        return [hint for hint in self.operator_hints if hint.tag == tag]

    def service_for_tag(self, tag: str) -> str | None:
        feature = self.features.get(tag)
        return feature.service if feature is not None else None
