"""Selector resolution cascade."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from botengine.exceptions import SelectorResolutionError
from botengine.logger import get_logger
from botengine.resolvers import BaseResolver
from botengine.resolvers.aria import AriaResolver
from botengine.resolvers.css import CSSResolver
from botengine.resolvers.fuzzy import FuzzyTextResolver
from botengine.resolvers.text import TextResolver
from botengine.resolvers.xpath import XPathResolver

if TYPE_CHECKING:
    from playwright.async_api import ElementHandle, Page

    from botengine.models import TargetSelector

log = get_logger(__name__)

_RESOLVER_TIMEOUT = 2.0  # seconds per resolver attempt


class ResolverCascade:
    """Tries resolvers in order until one succeeds."""

    def __init__(self, resolvers: list[BaseResolver] | None = None) -> None:
        self.resolvers = resolvers or [
            CSSResolver(),
            XPathResolver(),
            TextResolver(),
            AriaResolver(),
            FuzzyTextResolver(),
        ]

    async def resolve(
        self, page: Page, target: TargetSelector
    ) -> tuple[ElementHandle, str]:
        """Resolve an element using the cascade.

        Returns:
            Tuple of (element_handle, resolver_name).

        Raises:
            SelectorResolutionError: If no resolver can find the element.
        """
        strategies_tried: list[str] = []

        for resolver in self.resolvers:
            try:
                result = await asyncio.wait_for(
                    resolver.resolve(page, target),
                    timeout=_RESOLVER_TIMEOUT,
                )
                strategies_tried.append(resolver.name)
                if result is not None:
                    log.debug(
                        "element_resolved",
                        resolver=resolver.name,
                        target_css=target.css,
                    )
                    return result, resolver.name
            except asyncio.TimeoutError:
                log.warning("resolver_timeout", resolver=resolver.name)
                strategies_tried.append(f"{resolver.name}(timeout)")
            except Exception as exc:
                log.warning(
                    "resolver_error", resolver=resolver.name, error=str(exc)
                )
                strategies_tried.append(f"{resolver.name}(error)")

        raise SelectorResolutionError(
            step_id="unknown", strategies_tried=strategies_tried
        )
