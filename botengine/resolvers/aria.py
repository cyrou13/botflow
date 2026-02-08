"""Aria label resolver."""

from __future__ import annotations

from typing import TYPE_CHECKING

from botengine.resolvers import BaseResolver

if TYPE_CHECKING:
    from playwright.async_api import ElementHandle, Page

    from botengine.models import TargetSelector


class AriaResolver(BaseResolver):
    """Resolve elements by aria-label attribute."""

    @property
    def name(self) -> str:
        return "aria"

    async def resolve(
        self, page: Page, target: TargetSelector
    ) -> ElementHandle | None:
        if not target.aria_label:
            return None
        locator = page.get_by_label(target.aria_label)
        count = await locator.count()
        if count == 1:
            return await locator.element_handle()
        return None
