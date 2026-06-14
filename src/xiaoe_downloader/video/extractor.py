"""Course metadata extraction through a real browser session."""
from __future__ import annotations

import asyncio
import base64
import json
import sys
from urllib.parse import urljoin

from playwright.async_api import Page, async_playwright

from ..config import BrowserConfig, ExtractConfig

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


class CourseExtractor:
    """Extract video metadata from a xiaoe-tech course or column page."""

    def __init__(
        self,
        course_url: str,
        password: str | None = None,
        cdp_url: str | None = None,
        headless: bool | None = None,
        *,
        browser_config: BrowserConfig | None = None,
        extract_config: ExtractConfig | None = None,
        navigation_timeout_ms: int | None = None,
        initial_wait_ms: int | None = None,
        password_button_wait_ms: int | None = None,
        password_input_wait_ms: int | None = None,
        password_submit_wait_ms: int | None = None,
        catalog_tab_wait_ms: int | None = None,
        max_scrolls: int | None = None,
        scroll_wait_ms: int | None = None,
        stable_after_scroll: int | None = None,
        min_stable_items: int | None = None,
        video_url_template: str | None = None,
    ) -> None:
        browser_config = browser_config or BrowserConfig()
        extract_config = extract_config or ExtractConfig()
        self.course_url = course_url
        self.password = extract_config.password if password is None else password
        self.cdp_url = browser_config.cdp_url if cdp_url is None else cdp_url
        self.headless = extract_config.headless if headless is None else headless
        self.navigation_timeout_ms = (
            browser_config.navigation_timeout_ms
            if navigation_timeout_ms is None
            else navigation_timeout_ms
        )
        self.initial_wait_ms = (
            extract_config.initial_wait_ms if initial_wait_ms is None else initial_wait_ms
        )
        self.password_button_wait_ms = (
            extract_config.password_button_wait_ms
            if password_button_wait_ms is None
            else password_button_wait_ms
        )
        self.password_input_wait_ms = (
            extract_config.password_input_wait_ms
            if password_input_wait_ms is None
            else password_input_wait_ms
        )
        self.password_submit_wait_ms = (
            extract_config.password_submit_wait_ms
            if password_submit_wait_ms is None
            else password_submit_wait_ms
        )
        self.catalog_tab_wait_ms = (
            extract_config.catalog_tab_wait_ms
            if catalog_tab_wait_ms is None
            else catalog_tab_wait_ms
        )
        self.max_scrolls = extract_config.max_scrolls if max_scrolls is None else max_scrolls
        self.scroll_wait_ms = (
            extract_config.scroll_wait_ms if scroll_wait_ms is None else scroll_wait_ms
        )
        self.stable_after_scroll = (
            extract_config.stable_after_scroll
            if stable_after_scroll is None
            else stable_after_scroll
        )
        self.min_stable_items = (
            extract_config.min_stable_items
            if min_stable_items is None
            else min_stable_items
        )
        self.video_url_template = (
            extract_config.video_url_template
            if video_url_template is None
            else video_url_template
        )

    async def extract(self) -> list[dict]:
        """Return dictionaries with ``id``, ``name`` and an optional ``video_url``."""
        async with async_playwright() as playwright:
            page = await self._connect(playwright)
            await self._navigate_and_unlock(page)
            await self._scroll_to_load_all(page)
            return await self._read_items_from_vue(page)

    async def _connect(self, playwright) -> Page:
        if self.headless:
            browser = await playwright.chromium.launch(headless=True)
            context = await browser.new_context()
            context.set_default_navigation_timeout(self.navigation_timeout_ms)
            return await context.new_page()

        browser = await playwright.chromium.connect_over_cdp(self.cdp_url)
        context = browser.contexts[0] if browser.contexts else await browser.new_context()
        context.set_default_navigation_timeout(self.navigation_timeout_ms)
        return context.pages[0] if context.pages else await context.new_page()

    async def _navigate_and_unlock(self, page: Page) -> None:
        print(f"[extract] loading {self.course_url}")
        await page.goto(
            self.course_url,
            wait_until="networkidle",
            timeout=self.navigation_timeout_ms,
        )
        await asyncio.sleep(self.initial_wait_ms / 1000)

        if not self.password:
            return

        state = await page.evaluate("""
            JSON.stringify((()=>{
                try {
                    let vm = document.getElementById('common_template_mounted_el_container').children[0].__vue__;
                    let g = vm.$store.state.goodsInfo;
                    let p = vm.$store.state.permission;
                    return {pw: g?g.have_password:0, visit: p?p.permission_visit:1};
                } catch(e) { return {error: e.message}; }
            })())
        """)
        try:
            info = json.loads(state)
            needs_password = info.get("pw") == 1 and info.get("visit") == 0
        except Exception:
            needs_password = False

        if not needs_password:
            print("[extract] no password needed")
            return

        print("[extract] entering password ...")
        try:
            button = await page.query_selector("text=输入密码")
            if button and await button.is_visible():
                await button.click()
                await asyncio.sleep(self.password_button_wait_ms / 1000)
        except Exception:
            pass

        password_input = await page.query_selector("input")
        if password_input and await password_input.is_visible():
            await password_input.fill(self.password)
            await asyncio.sleep(self.password_input_wait_ms / 1000)
            for selector in ["button:has-text('确认')", "button:has-text('确定')"]:
                confirm_button = await page.query_selector(selector)
                if confirm_button and await confirm_button.is_visible():
                    await confirm_button.click()
                    break
            await asyncio.sleep(self.password_submit_wait_ms / 1000)
        print("[extract] password submitted")

    async def _scroll_to_load_all(self, page: Page) -> int:
        print("[extract] scrolling to load all courses ...")
        try:
            catalog_tab = await page.query_selector("text=目录")
            if catalog_tab:
                await catalog_tab.click()
                await asyncio.sleep(self.catalog_tab_wait_ms / 1000)
        except Exception:
            pass

        previous_count = 0
        current_count = 0
        for scroll_index in range(self.max_scrolls):
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(self.scroll_wait_ms / 1000)
            current_count = await page.evaluate(
                "document.querySelectorAll('.content-list .list-item').length"
            )
            sys.stdout.write(f"\r  scroll {scroll_index + 1}: {current_count} items")
            sys.stdout.flush()
            if (
                current_count == previous_count
                and current_count > self.min_stable_items
                and scroll_index >= self.stable_after_scroll
            ):
                break
            previous_count = current_count
        print(f"\n[extract] {current_count} courses loaded")
        return current_count

    async def _read_items_from_vue(self, page: Page) -> list[dict]:
        # The legacy extractor targets pages whose catalog lives in SingleItemList.
        raw_items = await page.evaluate("""
            JSON.stringify((()=>{
                let el = document.querySelector('.content-list .list-item');
                if (!el) return [];
                let p = el.parentElement;
                while (p && !p.__vue__) p = p.parentElement;
                if (!p || !p.__vue__) return [];
                return p.__vue__.SingleItemList.map(i => ({
                    id: i.resource_id || '',
                    name: i.resource_title || '',
                    video_url: i.video_url || i.videoUrl || '',
                    jump_url: i.jump_url || i.jumpUrl || '',
                    url: i.url || i.href || ''
                }));
            })())
        """)
        items = json.loads(raw_items)

        titles_b64 = await page.evaluate("""
            JSON.stringify(
                Array.from(document.querySelectorAll('.content-list .list-item .content-title'))
                     .map(el => {
                         try { return btoa(unescape(encodeURIComponent(el.textContent.trim()))); }
                         catch(_) { return btoa(el.textContent.trim()); }
                     })
            )
        """)
        dom_titles = [
            base64.b64decode(value).decode("utf-8")
            for value in json.loads(titles_b64)
        ]

        extracted_items = []
        for index, item in enumerate(items):
            dom_title = dom_titles[index] if index < len(dom_titles) else None
            extracted_items.append(
                build_extracted_item(
                    item,
                    index=index + 1,
                    dom_title=dom_title,
                    course_url=self.course_url,
                    video_url_template=self.video_url_template,
                )
            )
        return extracted_items


def build_extracted_item(
    raw_item: dict,
    *,
    index: int,
    course_url: str,
    video_url_template: str,
    dom_title: str | None = None,
) -> dict:
    item = {
        "id": raw_item.get("id", "") or raw_item.get("resource_id", ""),
        "name": dom_title or raw_item.get("name", "") or raw_item.get("resource_title", ""),
    }

    # Prefer URLs supplied by the current page. Templates are an explicit
    # compatibility escape hatch for old pages that expose only resource IDs.
    page_url = _first_non_empty(
        raw_item.get("video_url"),
        raw_item.get("videoUrl"),
        raw_item.get("jump_url"),
        raw_item.get("jumpUrl"),
        raw_item.get("url"),
        raw_item.get("href"),
    )
    if page_url:
        item["video_url"] = urljoin(course_url, page_url)
    elif video_url_template:
        item["video_url"] = urljoin(
            course_url,
            video_url_template.format(resource_id=item["id"], index=index),
        )
    return item


def _first_non_empty(*values) -> str:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


XiaoeExtractor = CourseExtractor
