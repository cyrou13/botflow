"""Extract action."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from botengine.actions import BaseAction, ExecutionContext, _make_result
from botengine.exceptions import SelectorResolutionError
from botengine.models import FlowStep, StepResult, TargetSelector

if TYPE_CHECKING:
    from playwright.async_api import Page


class ExtractAction(BaseAction):
    """Extract text content from an element."""

    async def execute(
        self, page: Page, step: FlowStep, context: ExecutionContext
    ) -> StepResult:
        start = time.monotonic()
        if not step.target or not isinstance(step.target, TargetSelector):
            return _make_result(step, "failed", start, error="No target selector")
        try:
            element, strategy = await context.resolver.resolve(page, step.target)
            text = await element.text_content() or ""
            text = text.strip()

            if step.save_as:
                context.extracted[step.save_as] = text

            return _make_result(
                step, "success", start,
                resolution_strategy=strategy,
                extracted_value=text,
            )
        except SelectorResolutionError:
            raise
        except Exception as exc:
            return _make_result(step, "failed", start, error=str(exc))
