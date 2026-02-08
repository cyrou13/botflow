"""Text content resolver."""

from __future__ import annotations

from typing import TYPE_CHECKING

from botengine.resolvers import BaseResolver

if TYPE_CHECKING:
    from playwright.async_api import ElementHandle, Page

    from botengine.models import TargetSelector


class TextResolver(BaseResolver):
    """Resolve elements by exact text content."""

    @property
    def name(self) -> str:
        return "text"

    async def resolve(
        self, page: Page, target: TargetSelector
    ) -> ElementHandle | None:
        if not target.text_content:
            return None
        locator = page.get_by_text(target.text_content, exact=True)
        count = await locator.count()
        if count == 1:
            element = await locator.element_handle()
            if element and await element.is_visible():
                return element
        return None
