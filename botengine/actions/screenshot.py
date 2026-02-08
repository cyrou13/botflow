"""Screenshot action."""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING

from botengine.actions import BaseAction, ExecutionContext, _make_result
from botengine.models import FlowStep, StepResult

if TYPE_CHECKING:
    from playwright.async_api import Page


class ScreenshotAction(BaseAction):
    """Take a screenshot of the current page."""

    async def execute(
        self, page: Page, step: FlowStep, context: ExecutionContext
    ) -> StepResult:
        start = time.monotonic()
        try:
            screenshots_dir = context.screenshots_dir or Path("screenshots")
            screenshots_dir.mkdir(parents=True, exist_ok=True)
            path = screenshots_dir / f"{step.id}.png"
            await page.screenshot(path=str(path), full_page=False, type="png")
            return _make_result(
                step, "success", start, screenshot_path=str(path)
            )
        except Exception as exc:
            return _make_result(step, "failed", start, error=str(exc))
