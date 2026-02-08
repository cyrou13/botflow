"""Playwright browser manager for BotFlow."""

from __future__ import annotations

import re
from pathlib import Path

from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from botengine.exceptions import BrowserError
from botengine.logger import get_logger

log = get_logger(__name__)

# Tags to strip from DOM snapshots
_STRIP_TAGS = re.compile(
    r"<(script|style|svg|noscript)\b[^>]*>[\s\S]*?</\1>",
    re.IGNORECASE,
)
_STRIP_COMMENTS = re.compile(r"<!--[\s\S]*?-->")
_STRIP_INLINE_STYLE = re.compile(r'\s+style="[^"]*"', re.IGNORECASE)
_MAX_DOM_SIZE = 50_000


class BrowserManager:
    """Manages Playwright browser lifecycle."""

    def __init__(self) -> None:
        self._playwright = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    async def start(self, headless: bool = True) -> None:
        """Launch browser."""
        try:
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(headless=headless)
            self._context = await self._browser.new_context()
            self._page = await self._context.new_page()
            log.info("browser_started", headless=headless)
        except Exception as exc:
            raise BrowserError(f"Failed to start browser: {exc}") from exc

    async def stop(self) -> None:
        """Close browser and cleanup."""
        try:
            if self._page and not self._page.is_closed():
                await self._page.close()
            if self._context:
                await self._context.close()
            if self._browser:
                await self._browser.close()
            if self._playwright:
                await self._playwright.stop()
        except Exception as exc:
            log.warning("browser_stop_error", error=str(exc))
        finally:
            self._page = None
            self._context = None
            self._browser = None
            self._playwright = None
            log.info("browser_stopped")

    async def new_context(
        self, cookies: list[dict] | None = None
    ) -> BrowserContext:
        """Create a new browser context, optionally with cookies."""
        if not self._browser:
            raise BrowserError("Browser not started")
        ctx = await self._browser.new_context()
        if cookies:
            await ctx.add_cookies(cookies)
        return ctx

    async def get_page(self) -> Page:
        """Get the current page, restarting if needed."""
        if self._page and not self._page.is_closed():
            return self._page
        if self._context:
            self._page = await self._context.new_page()
            return self._page
        raise BrowserError("Browser not started — call start() first")

    async def screenshot(self, path: str | None = None) -> bytes:
        """Take a screenshot of the current page."""
        page = await self.get_page()
        kwargs: dict = {"full_page": False, "type": "png"}
        if path:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            kwargs["path"] = path
        return await page.screenshot(**kwargs)

    async def get_dom_snapshot(self) -> str:
        """Return a simplified DOM snapshot for LLM consumption."""
        page = await self.get_page()
        html = await page.content()
        return self._simplify_dom(html)

    async def get_page_text(self) -> str:
        """Get visible text content of the page."""
        page = await self.get_page()
        return await page.inner_text("body")

    @property
    def current_url(self) -> str:
        """Current page URL."""
        if self._page and not self._page.is_closed():
            return self._page.url
        return ""

    @staticmethod
    def _simplify_dom(html: str) -> str:
        """Strip noise from HTML, keeping semantic structure.

        Removes scripts, styles, SVGs, comments, and inline styles.
        Keeps tag names, ids, classes, aria attrs, data attrs, hrefs,
        form-related attrs, and text content.
        """
        result = _STRIP_TAGS.sub("", html)
        result = _STRIP_COMMENTS.sub("", result)
        result = _STRIP_INLINE_STYLE.sub("", result)

        # Collapse whitespace
        result = re.sub(r"\n\s*\n+", "\n", result)
        result = result.strip()

        # Truncate if too large
        if len(result) > _MAX_DOM_SIZE:
            half = _MAX_DOM_SIZE // 2
            result = result[:half] + "\n... [truncated] ...\n" + result[-half:]

        return result
