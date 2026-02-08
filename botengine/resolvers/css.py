"""CSS selector resolver."""

from __future__ import annotations

from typing import TYPE_CHECKING

from botengine.resolvers import BaseResolver

if TYPE_CHECKING:
    from playwright.async_api import ElementHandle, Page

    from botengine.models import TargetSelector


class CSSResolver(BaseResolver):
    """Resolve elements using CSS selectors."""

    @property
    def name(self) -> str:
        return "css"

    async def resolve(
        self, page: Page, target: TargetSelector
    ) -> ElementHandle | None:
        if not target.css:
            return None
        element = await page.query_selector(target.css)
        if element and await element.is_visible():
            return element
        return None
