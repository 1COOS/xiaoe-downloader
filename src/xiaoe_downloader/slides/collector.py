"""Video detail-page intro tab slide/resource collection helpers."""
from __future__ import annotations

import html
import re
from urllib.parse import parse_qs, urljoin, urlparse

from playwright.async_api import Page

from .models import CatalogItem, SlideScrapeOptions

SLIDE_NUM_RE = re.compile(r"幻灯片\s*(\d+)", re.I)
SLIDES_INPUT_TYPES = {"auto", "catalog", "video"}


def build_detail_url(item: CatalogItem, *, origin: str, course_id: str) -> str:
    url = urljoin(origin, item.jump_url)
    if not course_id or ("product_id=" in url and "course_id=" in url):
        return url
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}product_id={course_id}&course_id={course_id}&sub_course_id="


def detect_slides_input_type(url: str, requested: str = "auto") -> str:
    """Resolve whether ``slides`` should treat ``url`` as a catalog or detail page."""
    requested = (requested or "auto").strip().lower()
    if requested not in SLIDES_INPUT_TYPES:
        raise ValueError("input_type must be one of: auto, catalog, video")
    if requested != "auto":
        return requested

    parsed = urlparse(canonical_url(url))
    path = parsed.path.lower()
    if "/p/course/video/" in path or video_resource_id_from_url(url):
        return "video"
    return "catalog"


def video_resource_id_from_url(url: str) -> str:
    """Return the ``v_...`` resource id from a video detail URL, if present."""
    parsed = urlparse(canonical_url(url))
    for segment in parsed.path.split("/"):
        if segment.startswith("v_"):
            return segment
    return ""


def canonical_url(url: str) -> str:
    url = html.unescape((url or "").strip())
    if url.startswith("//"):
        return "https:" + url
    return url


def is_slide_resource_candidate(
    entry: dict,
    options: SlideScrapeOptions | None = None,
) -> bool:
    src = canonical_url(entry.get("src") or "")
    if not src or src.startswith(("data:", "blob:")):
        return False

    options = options or SlideScrapeOptions(course_url="")
    low = src.lower()
    if any(token in low for token in options.exclude_url_tokens):
        return False

    alt = (entry.get("alt") or "").strip()
    if alt.startswith(options.slide_alt_prefix):
        return True

    natural_w = int(entry.get("natural_width") or 0)
    natural_h = int(entry.get("natural_height") or 0)
    looks_like_course_asset = any(token in low for token in options.include_url_tokens)
    return (
        looks_like_course_asset
        and natural_w >= options.min_image_width
        and natural_h >= options.min_image_height
    )


def slide_number(entry: dict) -> int | None:
    match = SLIDE_NUM_RE.search(entry.get("alt") or "")
    return int(match.group(1)) if match else None


def sort_slide_resources(entries: list[dict]) -> list[dict]:
    numeric_count = sum(1 for entry in entries if slide_number(entry) is not None)
    if entries and numeric_count >= max(3, int(len(entries) * 0.6)):
        return sorted(
            entries,
            key=lambda entry: (
                slide_number(entry) if slide_number(entry) is not None else 10**9,
                entry.get("first_seen_step", 0),
                entry.get("top", 0),
            ),
        )
    return entries


async def click_intro_tab(page: Page, options: SlideScrapeOptions) -> bool:
    await page.wait_for_timeout(options.intro_before_click_wait_ms)
    try:
        locator = page.get_by_text("介绍", exact=True)
        if await locator.count():
            await locator.first.click(timeout=options.intro_click_timeout_ms)
            await page.wait_for_timeout(options.intro_after_click_wait_ms)
            return True
    except Exception:
        pass

    clicked = await page.evaluate("""
    () => {
      function visible(el) {
        const rect = el.getBoundingClientRect();
        const style = window.getComputedStyle(el);
        return rect.width > 0 && rect.height > 0 &&
          style.visibility !== 'hidden' && style.display !== 'none';
      }
      const nodes = Array.from(document.querySelectorAll('div, span, a, button'))
        .filter(el => ((el.innerText || el.textContent || '').trim() === '介绍') && visible(el));
      const node = nodes[0] || nodes[nodes.length - 1];
      if (!node) return false;
      node.scrollIntoView({block: 'center'});
      node.click();
      return true;
    }
    """)
    await page.wait_for_timeout(options.intro_after_click_wait_ms)
    return bool(clicked)


async def collect_slide_resources(page: Page, options: SlideScrapeOptions) -> list[dict]:
    seen: set[str] = set()
    entries: list[dict] = []
    end_hits = 0
    last_height = 0
    await page.evaluate("window.scrollTo(0, 0)")
    await page.wait_for_timeout(options.image_initial_wait_ms)

    # The intro tab lazy-loads slides while scrolling and may virtualize content,
    # so collect images at each viewport instead of only inspecting the final DOM.
    for step in range(options.image_max_scrolls):
        candidates = await page.evaluate("""
        () => {
          const srcAttrs = ['data-src', 'data-original', 'data-lazy-src', 'data-url', 'src'];
          const pageY = window.scrollY || document.documentElement.scrollTop || 0;
          return Array.from(document.images).map((img, order) => {
            const rect = img.getBoundingClientRect();
            const attrSrc = srcAttrs.map(name => img.getAttribute(name)).find(Boolean) || '';
            const src = img.currentSrc || img.src || attrSrc;
            return {
              order,
              src,
              alt: img.getAttribute('alt') || '',
              natural_width: img.naturalWidth || 0,
              natural_height: img.naturalHeight || 0,
              display_width: Math.round(rect.width || 0),
              display_height: Math.round(rect.height || 0),
              top: Math.round(pageY + rect.top),
              left: Math.round(rect.left || 0),
            };
          });
        }
        """)
        candidates.sort(
            key=lambda item: (
                item.get("top") or 0,
                item.get("left") or 0,
                item.get("order") or 0,
            )
        )
        for candidate in candidates:
            candidate["src"] = canonical_url(candidate.get("src") or "")
            if not is_slide_resource_candidate(candidate, options):
                continue
            if candidate["src"] in seen:
                continue
            seen.add(candidate["src"])
            candidate["first_seen_step"] = step
            entries.append(candidate)

        metrics = await page.evaluate("""
        () => ({
          y: window.scrollY || document.documentElement.scrollTop || 0,
          inner: window.innerHeight || 0,
          height: Math.max(document.body.scrollHeight, document.documentElement.scrollHeight),
        })
        """)
        height = int(metrics["height"] or 0)
        y_bottom = int(metrics["y"] or 0) + int(metrics["inner"] or 0)
        if y_bottom >= height - 12 and height == last_height:
            end_hits += 1
        else:
            end_hits = 0
            last_height = height
        if end_hits >= options.image_end_hits:
            break
        await page.evaluate(
            """
            ({minStep, viewportRatio}) => {
              window.scrollBy(0, Math.max(minStep, Math.floor(window.innerHeight * viewportRatio)));
            }
            """,
            {
                "minStep": options.image_scroll_step_min_px,
                "viewportRatio": options.image_scroll_viewport_ratio,
            },
        )
        await page.wait_for_timeout(options.image_scroll_wait_ms)

    return sort_slide_resources(entries)


def origin_from_url(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def course_id_from_url(url: str) -> str:
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    for key in ("product_id", "course_id"):
        values = query.get(key)
        if values:
            return values[0]
    for part in parsed.path.split("/"):
        if part.startswith("course_"):
            return part
    return ""
