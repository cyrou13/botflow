"""Selector resolver interface and implementations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.async_api import ElementHandle, Page

    from botengine.models import TargetSelector


class BaseResolver(ABC):
    """Base class for element resolvers."""

    @abstractmethod
    async def resolve(
        self, page: Page, target: TargetSelector
    ) -> ElementHandle | None:
        """Try to find the element on the page. Return None if not found."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Resolver name for logging."""
