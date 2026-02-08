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
    """Wait for a selector, URL, or fixed delay.

    When a target is provided, builds a combined Playwright locator from all
    available selector strategies (CSS, XPath, text) joined with `or_()`.
    This makes waits resilient to any single selector strategy failing.
    """

    async def execute(
        self, page: Page, step: FlowStep, context: ExecutionContext
    ) -> StepResult:
        start = time.monotonic()
        try:
            if step.target and isinstance(step.target, TargetSelector):
                locator = self._build_locator(page, step.target)
                if locator is not None:
                    # Use .first to avoid strict mode violation when
                    # multiple elements match — for wait, we only need
                    # at least one to be present/visible.
                    await locator.first.wait_for(timeout=step.timeout_ms)
                elif step.url:
                    await page.wait_for_url(step.url, timeout=step.timeout_ms)
            elif step.url:
                await page.wait_for_url(step.url, timeout=step.timeout_ms)
            else:
                # Fixed delay (use value as ms or default to timeout_ms)
                delay_ms = int(step.value) if step.value else step.timeout_ms
                await asyncio.sleep(delay_ms / 1000)

            return _make_result(step, "success", start)
        except Exception as exc:
            return _make_result(step, "failed", start, error=str(exc))

    @staticmethod
    def _build_locator(page: Page, target: TargetSelector):
        """Build a combined locator from all non-null target selectors."""
        locator = None
        if target.css:
            locator = page.locator(target.css)
        if target.xpath:
            xpath_loc = page.locator(f"xpath={target.xpath}")
            locator = locator.or_(xpath_loc) if locator else xpath_loc
        if target.text_content and target.text_content.strip():
            text_loc = page.get_by_text(target.text_content, exact=True)
            locator = locator.or_(text_loc) if locator else text_loc
        return locator
