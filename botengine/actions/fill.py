"""Fill action."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from botengine.actions import BaseAction, ExecutionContext, _make_result, render_template
from botengine.exceptions import SelectorResolutionError
from botengine.models import FlowStep, StepResult, TargetSelector

if TYPE_CHECKING:
    from playwright.async_api import Page


class FillAction(BaseAction):
    """Fill an input field with a value."""

    async def execute(
        self, page: Page, step: FlowStep, context: ExecutionContext
    ) -> StepResult:
        start = time.monotonic()
        if not step.target or not isinstance(step.target, TargetSelector):
            return _make_result(step, "failed", start, error="No target selector")
        value = render_template(
            step.value or "",
            {"params": context.params, "extracted": context.extracted},
        )
        try:
            element, strategy = await context.resolver.resolve(page, step.target)
            await element.fill(value, timeout=step.timeout_ms)
            return _make_result(step, "success", start, resolution_strategy=strategy)
        except SelectorResolutionError:
            raise
        except Exception as exc:
            return _make_result(step, "failed", start, error=str(exc))
