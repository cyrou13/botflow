"""Wait action."""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

from botengine.actions import BaseAction, ExecutionContext, _make_result
from botengine.models import FlowStep, StepResult, TargetSelector

if TYPE_CHECKING:
    from playwright.async_api import Page


class WaitAction(BaseAction):
    """Wait for a selector, URL, or fixed delay."""

    async def execute(
        self, page: Page, step: FlowStep, context: ExecutionContext
    ) -> StepResult:
        start = time.monotonic()
        try:
            if step.target and isinstance(step.target, TargetSelector) and step.target.css:
                await page.wait_for_selector(
                    step.target.css, timeout=step.timeout_ms
                )
            elif step.url:
                await page.wait_for_url(step.url, timeout=step.timeout_ms)
            else:
                # Fixed delay (use value as ms or default to timeout_ms)
                delay_ms = int(step.value) if step.value else step.timeout_ms
                await asyncio.sleep(delay_ms / 1000)

            return _make_result(step, "success", start)
        except Exception as exc:
            return _make_result(step, "failed", start, error=str(exc))
