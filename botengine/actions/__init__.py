"""Step action interface, registry, and template substitution."""

from __future__ import annotations

import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TYPE_CHECKING

from botengine.models import FlowStep, StepResult
from botengine.resolver import ResolverCascade

if TYPE_CHECKING:
    from playwright.async_api import Page


def render_template(template: str, context: dict[str, Any]) -> str:
    """Replace {{params.xxx}} and {{extracted.xxx}} in a string."""
    def replacer(match: re.Match) -> str:
        path = match.group(1).strip()
        parts = path.split(".")
        value: Any = context
        for part in parts:
            if isinstance(value, dict):
                value = value[part]
            else:
                value = getattr(value, part)
        return str(value)
    return re.sub(r"\{\{(.+?)\}\}", replacer, template)


@dataclass
class ExecutionContext:
    """Runtime context for step execution."""

    params: dict[str, Any] = field(default_factory=dict)
    extracted: dict[str, Any] = field(default_factory=dict)
    screenshots_dir: Path | None = None
    resolver: ResolverCascade = field(default_factory=ResolverCascade)


class BaseAction(ABC):
    """Base class for step actions."""

    @abstractmethod
    async def execute(
        self, page: Page, step: FlowStep, context: ExecutionContext
    ) -> StepResult:
        """Execute the step action."""


def _make_result(
    step: FlowStep,
    status: str,
    start_time: float,
    resolution_strategy: str | None = None,
    extracted_value: Any = None,
    error: str | None = None,
    screenshot_path: str | None = None,
) -> StepResult:
    """Helper to create a StepResult with duration calculated."""
    return StepResult(
        step_id=step.id,
        status=status,
        resolution_strategy=resolution_strategy,
        duration_ms=(time.monotonic() - start_time) * 1000,
        extracted_value=extracted_value,
        error=error,
        screenshot_path=screenshot_path,
    )
