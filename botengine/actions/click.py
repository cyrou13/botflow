"""Click action."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from botengine.actions import BaseAction, ExecutionContext, _make_result
from botengine.exceptions import SelectorResolutionError
from botengine.models import FlowStep, StepResult, TargetSelector

if TYPE_CHECKING:
    from playwright.async_api import Page


class ClickAction(BaseAction):
    """Click on a resolved element."""

    async def execute(
        self, page: Page, step: FlowStep, context: ExecutionContext
    ) -> StepResult:
        start = time.monotonic()
        if not step.target or not isinstance(step.target, TargetSelector):
            return _make_result(step, "failed", start, error="No target selector")
        try:
            element, strategy = await context.resolver.resolve(page, step.target)
            await element.click(timeout=step.timeout_ms)

            # Check post conditions
            if step.post_conditions:
                pc = step.post_conditions
                if pc.element_appears:
                    await page.wait_for_selector(
                        pc.element_appears, timeout=pc.timeout_ms
                    )
                if pc.element_disappears:
                    await page.wait_for_selector(
                        pc.element_disappears, state="hidden", timeout=pc.timeout_ms
                    )

            return _make_result(step, "success", start, resolution_strategy=strategy)
        except SelectorResolutionError:
            raise
        except Exception as exc:
            return _make_result(step, "failed", start, error=str(exc))
