"""Tests for selector resolvers and the cascade."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from botengine.exceptions import SelectorResolutionError
from botengine.models import TargetSelector
from botengine.resolver import ResolverCascade
from botengine.resolvers import BaseResolver
from botengine.resolvers.css import CSSResolver
from botengine.resolvers.xpath import XPathResolver
from botengine.resolvers.text import TextResolver
from botengine.resolvers.aria import AriaResolver
from botengine.resolvers.fuzzy import FuzzyTextResolver
from botengine.resolvers.llm_vision import LLMVisionResolver


def _make_mock_page() -> AsyncMock:
    """Create a mock Playwright page."""
    page = AsyncMock()
    page.query_selector = AsyncMock(return_value=None)
    return page


def _make_element() -> AsyncMock:
    """Create a mock element handle."""
    el = AsyncMock()
    el.is_visible = AsyncMock(return_value=True)
    return el


class TestCSSResolver:
    async def test_finds_by_css(self) -> None:
        page = _make_mock_page()
        element = _make_element()
        page.query_selector = AsyncMock(return_value=element)
        target = TargetSelector(css="#my-btn")

        resolver = CSSResolver()
        result = await resolver.resolve(page, target)
        assert result is element
        page.query_selector.assert_called_once_with("#my-btn")

    async def test_returns_none_when_no_css(self) -> None:
        page = _make_mock_page()
        target = TargetSelector()
        result = await CSSResolver().resolve(page, target)
        assert result is None

    async def test_returns_none_when_not_found(self) -> None:
        page = _make_mock_page()
        target = TargetSelector(css="#nonexistent")
        result = await CSSResolver().resolve(page, target)
        assert result is None

    async def test_returns_none_when_hidden(self) -> None:
        page = _make_mock_page()
        element = _make_element()
        element.is_visible = AsyncMock(return_value=False)
        page.query_selector = AsyncMock(return_value=element)
        target = TargetSelector(css="#hidden-btn")

        result = await CSSResolver().resolve(page, target)
        assert result is None


class TestXPathResolver:
    async def test_finds_by_xpath(self) -> None:
        page = _make_mock_page()
        element = _make_element()
        page.query_selector = AsyncMock(return_value=element)
        target = TargetSelector(xpath="//button[@id='submit']")

        result = await XPathResolver().resolve(page, target)
        assert result is element
        page.query_selector.assert_called_once_with("xpath=//button[@id='submit']")

    async def test_returns_none_when_no_xpath(self) -> None:
        page = _make_mock_page()
        target = TargetSelector()
        result = await XPathResolver().resolve(page, target)
        assert result is None

    async def test_returns_none_when_hidden(self) -> None:
        page = _make_mock_page()
        element = _make_element()
        element.is_visible = AsyncMock(return_value=False)
        page.query_selector = AsyncMock(return_value=element)
        target = TargetSelector(xpath="//button[@id='hidden']")

        result = await XPathResolver().resolve(page, target)
        assert result is None


class TestTextResolver:
    async def test_finds_by_text(self) -> None:
        page = _make_mock_page()
        element = _make_element()
        locator = AsyncMock()
        locator.count = AsyncMock(return_value=1)
        locator.element_handle = AsyncMock(return_value=element)
        page.get_by_text = MagicMock(return_value=locator)
        target = TargetSelector(text_content="Login")

        result = await TextResolver().resolve(page, target)
        assert result is element
        page.get_by_text.assert_called_once_with("Login", exact=True)

    async def test_returns_none_on_multiple_matches(self) -> None:
        page = _make_mock_page()
        locator = AsyncMock()
        locator.count = AsyncMock(return_value=3)
        page.get_by_text = MagicMock(return_value=locator)
        target = TargetSelector(text_content="Button")

        result = await TextResolver().resolve(page, target)
        assert result is None

    async def test_returns_none_when_hidden(self) -> None:
        page = _make_mock_page()
        element = _make_element()
        element.is_visible = AsyncMock(return_value=False)
        locator = AsyncMock()
        locator.count = AsyncMock(return_value=1)
        locator.element_handle = AsyncMock(return_value=element)
        page.get_by_text = MagicMock(return_value=locator)
        target = TargetSelector(text_content="Hidden")

        result = await TextResolver().resolve(page, target)
        assert result is None


class TestAriaResolver:
    async def test_finds_by_aria_label(self) -> None:
        page = _make_mock_page()
        element = _make_element()
        locator = AsyncMock()
        locator.count = AsyncMock(return_value=1)
        locator.element_handle = AsyncMock(return_value=element)
        page.get_by_label = MagicMock(return_value=locator)
        target = TargetSelector(aria_label="Submit form")

        result = await AriaResolver().resolve(page, target)
        assert result is element

    async def test_returns_none_when_no_label(self) -> None:
        page = _make_mock_page()
        target = TargetSelector()
        result = await AriaResolver().resolve(page, target)
        assert result is None


class TestFuzzyTextResolver:
    async def test_finds_by_fuzzy_text(self) -> None:
        page = _make_mock_page()
        element = _make_element()
        locator = AsyncMock()
        locator.count = AsyncMock(return_value=1)
        locator.element_handle = AsyncMock(return_value=element)
        page.get_by_text = MagicMock(return_value=locator)
        target = TargetSelector(text_content="Logi")

        result = await FuzzyTextResolver().resolve(page, target)
        assert result is element
        page.get_by_text.assert_called_once_with("Logi", exact=False)


class TestLLMVisionResolver:
    async def test_returns_none_without_client(self) -> None:
        resolver = LLMVisionResolver(client=None)
        page = _make_mock_page()
        target = TargetSelector(css="#btn")
        result = await resolver.resolve(page, target)
        assert result is None

    def test_name(self) -> None:
        assert LLMVisionResolver().name == "llm_vision"

    def test_build_prompt(self) -> None:
        target = TargetSelector(css="#old-btn", text_content="Submit")
        prompt = LLMVisionResolver._build_prompt(target, "<html></html>")
        assert "#old-btn" in prompt
        assert "Submit" in prompt


class TestResolverCascade:
    async def test_returns_first_successful_resolver(self) -> None:
        page = _make_mock_page()
        element = _make_element()

        r1 = AsyncMock(spec=BaseResolver)
        r1.name = "fail"
        r1.resolve = AsyncMock(return_value=None)

        r2 = AsyncMock(spec=BaseResolver)
        r2.name = "success"
        r2.resolve = AsyncMock(return_value=element)

        cascade = ResolverCascade(resolvers=[r1, r2])
        target = TargetSelector(css="#test")
        result, name = await cascade.resolve(page, target)
        assert result is element
        assert name == "success"

    async def test_raises_when_all_fail(self) -> None:
        page = _make_mock_page()

        r1 = AsyncMock(spec=BaseResolver)
        r1.name = "r1"
        r1.resolve = AsyncMock(return_value=None)

        r2 = AsyncMock(spec=BaseResolver)
        r2.name = "r2"
        r2.resolve = AsyncMock(return_value=None)

        cascade = ResolverCascade(resolvers=[r1, r2])
        target = TargetSelector(css="#nope")

        with pytest.raises(SelectorResolutionError):
            await cascade.resolve(page, target)

    async def test_skips_on_timeout(self) -> None:
        import asyncio

        page = _make_mock_page()
        element = _make_element()

        r_slow = AsyncMock(spec=BaseResolver)
        r_slow.name = "slow"

        async def slow_resolve(*args, **kwargs):
            await asyncio.sleep(10)

        r_slow.resolve = slow_resolve

        r_fast = AsyncMock(spec=BaseResolver)
        r_fast.name = "fast"
        r_fast.resolve = AsyncMock(return_value=element)

        cascade = ResolverCascade(resolvers=[r_slow, r_fast])
        target = TargetSelector(css="#test")
        result, name = await cascade.resolve(page, target)
        assert result is element
        assert name == "fast"

    async def test_default_resolvers_order(self) -> None:
        cascade = ResolverCascade()
        names = [r.name for r in cascade.resolvers]
        assert names == ["xpath", "css", "text", "aria", "fuzzy_text"]
