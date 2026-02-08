"""Tests for BrowserManager."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from botengine.browser import BrowserManager
from botengine.exceptions import BrowserError


class TestBrowserManagerLifecycle:
    async def test_start_and_stop(self) -> None:
        mgr = BrowserManager()
        with patch("botengine.browser.async_playwright") as mock_pw:
            mock_playwright_inst = AsyncMock()
            mock_browser = AsyncMock()
            mock_context = AsyncMock()
            mock_page = AsyncMock()
            mock_page.is_closed.return_value = False

            mock_pw.return_value.start = AsyncMock(return_value=mock_playwright_inst)
            mock_playwright_inst.chromium.launch = AsyncMock(return_value=mock_browser)
            mock_browser.new_context = AsyncMock(return_value=mock_context)
            mock_context.new_page = AsyncMock(return_value=mock_page)

            await mgr.start(headless=True)
            assert mgr._browser is mock_browser
            assert mgr._page is mock_page

            await mgr.stop()
            assert mgr._browser is None
            assert mgr._page is None

    async def test_get_page_before_start_raises(self) -> None:
        mgr = BrowserManager()
        with pytest.raises(BrowserError, match="not started"):
            await mgr.get_page()

    async def test_get_page_returns_existing(self) -> None:
        mgr = BrowserManager()
        mock_page = AsyncMock()
        mock_page.is_closed = MagicMock(return_value=False)
        mgr._page = mock_page
        mgr._context = AsyncMock()
        result = await mgr.get_page()
        assert result is mock_page

    async def test_screenshot_calls_page(self) -> None:
        mgr = BrowserManager()
        mock_page = AsyncMock()
        mock_page.is_closed = MagicMock(return_value=False)
        mock_page.screenshot = AsyncMock(return_value=b"PNG")
        mgr._page = mock_page
        mgr._context = AsyncMock()
        data = await mgr.screenshot()
        assert data == b"PNG"


class TestDomSimplification:
    def test_strips_script_tags(self) -> None:
        html = '<html><body><script>alert("hi")</script><p>Hello</p></body></html>'
        result = BrowserManager._simplify_dom(html)
        assert "<script>" not in result
        assert "alert" not in result
        assert "<p>Hello</p>" in result

    def test_strips_style_tags(self) -> None:
        html = "<html><body><style>body{color:red}</style><p>Hi</p></body></html>"
        result = BrowserManager._simplify_dom(html)
        assert "<style>" not in result
        assert "color:red" not in result

    def test_strips_inline_styles(self) -> None:
        html = '<div style="color: red; font-size: 12px;">Text</div>'
        result = BrowserManager._simplify_dom(html)
        assert 'style="' not in result
        assert ">Text</div>" in result

    def test_strips_comments(self) -> None:
        html = "<div><!-- This is a comment --><p>Content</p></div>"
        result = BrowserManager._simplify_dom(html)
        assert "comment" not in result
        assert "<p>Content</p>" in result

    def test_strips_svg(self) -> None:
        html = '<body><svg xmlns="http://www.w3.org/2000/svg"><circle/></svg><p>OK</p></body>'
        result = BrowserManager._simplify_dom(html)
        assert "<svg" not in result
        assert "<p>OK</p>" in result

    def test_preserves_semantic_attrs(self) -> None:
        html = '<input id="email" class="form-input" aria-label="Email" name="email" placeholder="Enter email">'
        result = BrowserManager._simplify_dom(html)
        assert 'id="email"' in result
        assert 'aria-label="Email"' in result
        assert 'name="email"' in result

    def test_truncates_large_dom(self) -> None:
        html = "<div>" + "x" * 60_000 + "</div>"
        result = BrowserManager._simplify_dom(html)
        assert len(result) <= 50_000 + 50  # allow for truncation marker
        assert "[truncated]" in result

    def test_collapses_whitespace(self) -> None:
        html = "<div>\n\n\n\n<p>Text</p>\n\n\n</div>"
        result = BrowserManager._simplify_dom(html)
        assert "\n\n\n" not in result
