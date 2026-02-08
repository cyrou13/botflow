"""All Pydantic models for BotFlow."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


# --- Core flow models ---


class TargetSelector(BaseModel):
    """Element selector with multiple resolution strategies."""

    css: str | None = None
    xpath: str | None = None
    text_content: str | None = None
    aria_label: str | None = None
    visual_anchor: str | None = None
    screenshot_crop: str | None = None
    dom_neighborhood: str | None = None


class DynamicTarget(BaseModel):
    """Dynamic target resolved at runtime."""

    strategy: Literal["find_by_text", "dynamic", "css", "xpath"]
    mapping: dict[str, str] | None = None
    key: str | None = None
    text: str | None = None
    container: str | None = None


class PreConditions(BaseModel):
    """Conditions that must hold before a step executes."""

    url_pattern: str | None = None
    expected_elements: list[str] = Field(default_factory=list)


class PostConditions(BaseModel):
    """Conditions to verify after a step executes."""

    url_changed_to: str | None = None
    element_appears: str | None = None
    element_disappears: str | None = None
    timeout_ms: int = 5000


class FlowParam(BaseModel):
    """Parameter definition for a flow."""

    type: Literal["string", "number", "boolean", "enum"]
    required: bool = True
    default: Any = None
    values: list[str] | None = None
    min: float | None = None
    max: float | None = None


class FlowReturn(BaseModel):
    """Return value definition for a flow."""

    type: Literal["string", "number", "boolean", "object", "array"]


class StepAction(str, Enum):
    """Available step actions."""

    NAVIGATE = "navigate"
    CLICK = "click"
    FILL = "fill"
    EXTRACT = "extract"
    WAIT = "wait"
    SCREENSHOT = "screenshot"
    SELECT = "select"
    HOVER = "hover"
    SCROLL = "scroll"
    TYPE = "type"


class FlowStep(BaseModel):
    """A single step in a flow."""

    id: str
    action: StepAction
    description: str | None = None
    target: TargetSelector | DynamicTarget | None = None
    url: str | None = None
    value: str | None = None
    save_as: str | None = None
    pre_conditions: PreConditions | None = None
    post_conditions: PostConditions | None = None
    timeout_ms: int = 10000
    optional: bool = False


class Flow(BaseModel):
    """A complete automation flow definition."""

    flow_id: str
    site: str
    version: int = 1
    params: dict[str, FlowParam] = Field(default_factory=dict)
    returns: dict[str, FlowReturn] = Field(default_factory=dict)
    steps: list[FlowStep] = Field(min_length=1)
    returns_mapping: dict[str, Any] = Field(default_factory=dict)


# --- Execution models ---


class StepResult(BaseModel):
    """Result of executing a single step."""

    step_id: str
    status: Literal["success", "fallback", "healed", "failed", "skipped"]
    resolution_strategy: str | None = None
    duration_ms: float
    extracted_value: Any = None
    error: str | None = None
    screenshot_path: str | None = None


class RunResult(BaseModel):
    """Result of executing a complete flow."""

    flow_id: str
    status: Literal["success", "partial", "failed"]
    started_at: datetime
    finished_at: datetime
    duration_ms: float
    step_results: list[StepResult]
    returns: dict[str, Any] = Field(default_factory=dict)
    heals_triggered: int = 0


# --- Healing models ---


class HealProposal(BaseModel):
    """A proposed fix for a broken selector."""

    step_id: str
    old_target: TargetSelector
    new_target: TargetSelector
    confidence_score: float = Field(ge=0, le=100)
    reasoning: str
    screenshot_before: str | None = None
    screenshot_after: str | None = None


class HealMode(str, Enum):
    """Auto-heal operating mode."""

    OFF = "off"
    SUPERVISED = "supervised"
    AUTO = "auto"


class FlowHealth(BaseModel):
    """Health status of a flow."""

    flow_id: str
    last_run: RunResult | None = None
    success_rate_7d: float = 0.0
    heals_count_7d: int = 0
    auto_heal_threshold: float = 100.0
    heal_mode: HealMode = HealMode.SUPERVISED


# --- Confidence tracking ---


class ConfidenceState(BaseModel):
    """Confidence tracking state for a flow's auto-heal system."""

    flow_id: str
    auto_threshold: float = 100.0
    consecutive_successful_heals: int = 0
    consecutive_failed_heals: int = 0
    total_successful_heals: int = 0
    total_failed_heals: int = 0
