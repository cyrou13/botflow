"""Navigate action."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from botengine.actions import BaseAction, ExecutionContext, _make_result, render_template
from botengine.models import FlowStep, StepResult

if TYPE_CHECKING:
    from playwright.async_api import Page


class NavigateAction(BaseAction):
    """Navigate to a URL."""

    async def execute(
        self, page: Page, step: FlowStep, context: ExecutionContext
    ) -> StepResult:
        start = time.monotonic()
        url = step.url or ""
        url = render_template(url, {"params": context.params, "extracted": context.extracted})
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=step.timeout_ms)
            return _make_result(step, "success", start)
        except Exception as exc:
            return _make_result(step, "failed", start, error=str(exc))
