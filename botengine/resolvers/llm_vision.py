"""LLM vision resolver — last resort, uses Claude API."""

from __future__ import annotations

import base64
import json
from typing import TYPE_CHECKING

from botengine.logger import get_logger
from botengine.resolvers import BaseResolver

if TYPE_CHECKING:
    import anthropic
    from playwright.async_api import ElementHandle, Page

    from botengine.models import TargetSelector

log = get_logger(__name__)


class LLMVisionResolver(BaseResolver):
    """Resolve elements using Claude vision API as last resort."""

    def __init__(
        self,
        client: anthropic.AsyncAnthropic | None = None,
        model: str = "claude-sonnet-4-20250514",
    ) -> None:
        self._client = client
        self._model = model

    @property
    def name(self) -> str:
        return "llm_vision"

    async def resolve(
        self, page: Page, target: TargetSelector
    ) -> ElementHandle | None:
        if not self._client:
            return None

        try:
            screenshot = await page.screenshot(type="png")
            screenshot_b64 = base64.b64encode(screenshot).decode()

            # Get simplified DOM for context
            html = await page.content()

            prompt = self._build_prompt(target, html[:20000])

            response = await self._client.messages.create(
                model=self._model,
                max_tokens=500,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/png",
                                    "data": screenshot_b64,
                                },
                            },
                            {"type": "text", "text": prompt},
                        ],
                    }
                ],
            )

            result_text = response.content[0].text
            selector_data = json.loads(result_text)
            css = selector_data.get("css")
            if css:
                el = await page.query_selector(css)
                if el:
                    return el

            xpath = selector_data.get("xpath")
            if xpath:
                el = await page.query_selector(f"xpath={xpath}")
                if el:
                    return el

        except Exception as exc:
            log.warning("llm_vision_resolve_failed", error=str(exc))

        return None

    @staticmethod
    def _build_prompt(target: TargetSelector, dom: str) -> str:
        parts = ["Find an element on this page matching the following description:"]
        if target.css:
            parts.append(f"Previous CSS: {target.css}")
        if target.xpath:
            parts.append(f"Previous XPath: {target.xpath}")
        if target.text_content:
            parts.append(f"Text content: {target.text_content}")
        if target.aria_label:
            parts.append(f"Aria label: {target.aria_label}")
        if target.visual_anchor:
            parts.append(f"Visual description: {target.visual_anchor}")
        parts.append(f"\nDOM (truncated):\n{dom[:10000]}")
        parts.append(
            '\nReturn ONLY a JSON object with keys "css" and "xpath" for the element.'
        )
        return "\n".join(parts)
