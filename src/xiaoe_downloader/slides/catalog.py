"""Course catalog loading and normalization."""
from __future__ import annotations

from playwright.async_api import Page

from .models import CatalogItem, SlideScrapeOptions


def catalog_item_from_raw(raw: dict, *, index: int) -> CatalogItem:
    """Normalize the many field names used by xiaoe catalog payloads."""
    title = (
        raw.get("title")
        or raw.get("resource_title")
        or raw.get("chapter_title")
        or raw.get("name")
        or ""
    )
    resource_id = (
        raw.get("resource_id")
        or raw.get("rid")
        or raw.get("resourceId")
        or raw.get("chapter_id")
        or raw.get("id")
        or ""
    )
    return CatalogItem(
        index=index,
        title=title,
        resource_id=str(resource_id),
        jump_url=raw.get("jump_url") or raw.get("jumpUrl") or "",
        chapter_type=raw.get("chapter_type"),
        resource_type=raw.get("resource_type"),
        section_count=int(raw.get("section_num") or raw.get("section_count") or 0),
        sort_value=raw.get("sort_value"),
        video_length=raw.get("video_length"),
        parent_id=raw.get("p_id") or "",
    )


def filter_catalog_items(
    items: list[CatalogItem],
    *,
    skip_title: str,
) -> tuple[list[CatalogItem], list[CatalogItem]]:
    if not skip_title:
        return items, []
    selected = [item for item in items if skip_title not in item.title]
    skipped = [item for item in items if skip_title in item.title]
    return selected, skipped


def parse_chapter_children(payload: dict, *, parent_resource_id: str) -> list[CatalogItem]:
    children = []
    for raw in payload.get("data", {}).get("list", []):
        if raw.get("p_id") != parent_resource_id:
            continue
        child = catalog_item_from_raw(raw, index=len(children))
        if child.title and child.resource_id and child.jump_url:
            children.append(child)
    children.sort(key=lambda child: child.sort_value or 0)
    return children


async def load_full_catalog(page: Page, options: SlideScrapeOptions) -> list[CatalogItem]:
    await page.goto(
        options.course_url,
        wait_until="domcontentloaded",
        timeout=options.navigation_timeout_ms,
    )
    await page.wait_for_timeout(options.catalog_initial_wait_ms)
    await maybe_click_more(page, options)

    last_len = -1
    stable_count = 0
    records: list[CatalogItem] = []
    for _ in range(options.catalog_max_scrolls):
        records = await read_catalog(page)
        total = await page.evaluate(
            "() => document.querySelector('.catalog_box')?.__vue__?.catalogListTotal || 0"
        )
        if len(records) == last_len:
            stable_count += 1
        else:
            stable_count = 0
            last_len = len(records)
        if (
            records
            and stable_count >= options.catalog_stable_cycles
            and (not total or len(records) >= int(total))
        ):
            break
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(options.catalog_scroll_wait_ms)
        await maybe_click_more(page, options)
    return records


async def read_catalog(page: Page) -> list[CatalogItem]:
    # The H5 page virtualizes rows; Vue state is more complete than the DOM.
    rows = await page.evaluate("""
    () => {
      const box = document.querySelector('.catalog_box');
      const vm = box && box.__vue__;
      const list = vm && Array.isArray(vm.courseCatalogList) ? vm.courseCatalogList : [];
      return list.map((item, idx) => ({
        index: idx,
        title: item.title || '',
        resource_title: item.resource_title || '',
        chapter_title: item.chapter_title || '',
        name: item.name || '',
        resource_id: item.resource_id || '',
        rid: item.rid || '',
        resourceId: item.resourceId || '',
        chapter_id: item.chapter_id || '',
        id: item.id || '',
        jump_url: item.jump_url || '',
        jumpUrl: item.jumpUrl || '',
        chapter_type: item.chapter_type,
        resource_type: item.resource_type,
        section_num: item.section_num || 0,
        sort_value: item.sort_value,
        video_length: item.video_length,
        p_id: item.p_id || '',
      }));
    }
    """)
    return [catalog_item_from_raw(row, index=index) for index, row in enumerate(rows)]


async def load_chapter_children(
    page: Page,
    item: CatalogItem,
    options: SlideScrapeOptions,
) -> list[CatalogItem]:
    found: dict[str, CatalogItem] = {}

    async def on_response(response) -> None:
        if "resource_catalog_list.get" not in response.url:
            return
        try:
            payload = await response.json()
        except Exception:
            return
        for child in parse_chapter_children(payload, parent_resource_id=item.resource_id):
            found[child.resource_id] = child

    page.on("response", on_response)
    try:
        await click_chapter(page, item.title, options)
        for _ in range(options.chapter_response_checks):
            if found:
                break
            await page.wait_for_timeout(options.chapter_response_wait_ms)
    finally:
        page.remove_listener("response", on_response)

    children = list(found.values())
    children.sort(key=lambda child: child.sort_value or 0)
    return children


async def click_chapter(page: Page, title: str, options: SlideScrapeOptions) -> None:
    # Chapter children are loaded only after the sticky chapter header is opened.
    clicked = await page.evaluate(
        """
        (title) => {
          function visible(el) {
            const rect = el.getBoundingClientRect();
            const style = window.getComputedStyle(el);
            return rect.width > 0 && rect.height > 0 &&
              style.visibility !== 'hidden' && style.display !== 'none';
          }
          const nodes = Array.from(document.querySelectorAll('*'))
            .filter(el => visible(el) && (el.innerText || '').trim().startsWith(title));
          const node = nodes
            .sort((a, b) => {
              const ar = a.getBoundingClientRect();
              const br = b.getBoundingClientRect();
              return (ar.width * ar.height) - (br.width * br.height);
            })[0];
          const target = node?.closest('.chapter_info') || node;
          if (!target) return false;
          target.scrollIntoView({block: 'center'});
          target.click();
          return true;
        }
        """,
        title,
    )
    if not clicked:
        raise RuntimeError(f"Could not expand chapter: {title}")
    await page.wait_for_timeout(options.chapter_expand_wait_ms)


async def maybe_click_more(page: Page, options: SlideScrapeOptions) -> bool:
    for label in ("查看更多", "展开更多", "更多"):
        try:
            locator = page.get_by_text(label, exact=False).last
            if await locator.count():
                await locator.click(timeout=options.more_click_timeout_ms)
                await page.wait_for_timeout(options.more_click_wait_ms)
                return True
        except Exception:
            pass
    return False


async def get_course_title(page: Page) -> str:
    title = await page.evaluate("""
    () => {
      const vm = document.querySelector('.catalog_box')?.__vue__;
      const course = vm?.courseInfo || vm?.$store?.state?.courseInfo || {};
      return course.title || course.name || course.resource_title || course.course_name ||
        document.querySelector('.course-title, .goods-title, h1')?.innerText ||
        document.title || 'course';
    }
    """)
    return title or "course"
