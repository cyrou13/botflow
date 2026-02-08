"""BotFlow client models."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ParamSpec(BaseModel):
    """Parameter specification for a flow."""

    type: str
    required: bool = True
    default: Any = None
    values: list[str] | None = None


class ReturnSpec(BaseModel):
    """Return value specification for a flow."""

    type: str


class FlowInfo(BaseModel):
    """Flow metadata."""

    flow_id: str
    site: str
    params: dict[str, ParamSpec] = {}
    returns: dict[str, ReturnSpec] = {}
    step_count: int = 0


class StepOutcome(BaseModel):
    """Result of a single step."""

    step_id: str
    status: str  # success | failed | skipped
    duration_ms: float = 0.0
    extracted_value: Any = None
    error: str | None = None


class FlowResult(BaseModel):
    """Full result of a flow execution."""

    flow_id: str
    status: str  # success | partial | failed
    duration_ms: float = 0.0
    steps: list[StepOutcome] = []
    returns: dict[str, Any] = {}
    error: str | None = None
