"""Playwright browser setup helpers."""
from __future__ import annotations

from playwright.async_api import BrowserContext, Page

from .models import SlideScrapeOptions


async def open_mobile_context(playwright, options: SlideScrapeOptions) -> BrowserContext:
    """Open a persistent mobile-like context so logged-in sessions are reused."""
    context = await playwright.chromium.launch_persistent_context(
        options.profile,
        headless=not options.headed,
        viewport={"width": options.viewport_width, "height": options.viewport_height},
        is_mobile=True,
        user_agent=options.user_agent,
    )
    context.set_default_timeout(options.default_timeout_ms)
    context.set_default_navigation_timeout(options.navigation_timeout_ms)
    return context


def configure_page(page: Page, options: SlideScrapeOptions) -> Page:
    page.set_default_timeout(options.default_timeout_ms)
    page.set_default_navigation_timeout(options.navigation_timeout_ms)
    return page
