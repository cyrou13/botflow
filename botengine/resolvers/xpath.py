"""XPath selector resolver."""

from __future__ import annotations

from typing import TYPE_CHECKING

from botengine.resolvers import BaseResolver

if TYPE_CHECKING:
    from playwright.async_api import ElementHandle, Page

    from botengine.models import TargetSelector


class XPathResolver(BaseResolver):
    """Resolve elements using XPath selectors."""

    @property
    def name(self) -> str:
        return "xpath"

    async def resolve(
        self, page: Page, target: TargetSelector
    ) -> ElementHandle | None:
        if not target.xpath:
            return None
        return await page.query_selector(f"xpath={target.xpath}")
