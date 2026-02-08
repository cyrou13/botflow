"""Click action."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from botengine.actions import BaseAction, ExecutionContext, _make_result
from botengine.exceptions import SelectorResolutionError
from botengine.logger import get_logger
from botengine.models import FlowStep, StepResult, TargetSelector

if TYPE_CHECKING:
    from playwright.async_api import Page

log = get_logger(__name__)


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

            # Use a capped first-attempt timeout so the fallbacks
            # always get a chance within the outer step timeout.
            first_attempt_ms = min(5000, step.timeout_ms // 2)
            remaining_ms = max(3000, step.timeout_ms - first_attempt_ms - 1000)
            try:
                await element.scroll_into_view_if_needed(timeout=3000)
                await element.click(timeout=first_attempt_ms)
            except Exception as click_err:
                log.warning(
                    "click_element_handle_failed",
                    step_id=step.id,
                    original_error=str(click_err)[:120],
                )
                # ElementHandle.click() does NOT auto-wait for visibility.
                # Fallback 1: Locator-based click (auto-waits for visible+stable).
                css = (step.target.css or "").strip()
                if css:
                    try:
                        await page.locator(css).click(timeout=remaining_ms)
                        click_err = None  # type: ignore[assignment]
                    except Exception as loc_err:
                        log.warning(
                            "click_locator_fallback_failed",
                            step_id=step.id,
                            css=css,
                            error=str(loc_err)[:80],
                        )

                # Fallback 2: Role-based locator (button then link).
                if click_err is not None:
                    text = (step.target.text_content or "").strip()
                    if text:
                        log.warning(
                            "click_role_fallback",
                            step_id=step.id,
                            text=text,
                        )
                        try:
                            await page.get_by_role("button", name=text).click(
                                timeout=remaining_ms
                            )
                        except Exception:
                            await page.get_by_role("link", name=text).click(
                                timeout=remaining_ms
                            )
                    else:
                        raise

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
