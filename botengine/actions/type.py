"""Type action — simulates individual key presses."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from botengine.actions import BaseAction, ExecutionContext, _make_result, render_template
from botengine.exceptions import SelectorResolutionError
from botengine.models import FlowStep, StepResult, TargetSelector

if TYPE_CHECKING:
    from playwright.async_api import Page


class TypeAction(BaseAction):
    """Type text into an element using individual key presses.

    Unlike ``fill``, this triggers keydown/keypress/keyup events for each
    character, which is required by some sites (e.g. date-of-birth fields).
    """

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
            await element.click(timeout=step.timeout_ms)
            await page.keyboard.type(value, delay=50)
            return _make_result(step, "success", start, resolution_strategy=strategy)
        except SelectorResolutionError:
            raise
        except Exception as exc:
            return _make_result(step, "failed", start, error=str(exc))
