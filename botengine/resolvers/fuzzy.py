"""Fuzzy text resolver."""

from __future__ import annotations

from typing import TYPE_CHECKING

from botengine.resolvers import BaseResolver

if TYPE_CHECKING:
    from playwright.async_api import ElementHandle, Page

    from botengine.models import TargetSelector


class FuzzyTextResolver(BaseResolver):
    """Resolve elements by fuzzy text matching (non-exact)."""

    @property
    def name(self) -> str:
        return "fuzzy_text"

    async def resolve(
        self, page: Page, target: TargetSelector
    ) -> ElementHandle | None:
        if not target.text_content:
            return None
        locator = page.get_by_text(target.text_content, exact=False)
        count = await locator.count()
        if count == 1:
            return await locator.element_handle()
        if count > 1:
            # Return the first visible one
            for i in range(count):
                el = await locator.nth(i).element_handle()
                if el and await el.is_visible():
                    return el
        return None
