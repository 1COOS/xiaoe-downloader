"""Shared data models for slide/resource scraping."""
from __future__ import annotations

from dataclasses import dataclass

from ..config import DEFAULT_PROFILE, DEFAULT_USER_AGENT


@dataclass(frozen=True)
class SlideScrapeOptions:
    """Runtime options for the ``slides`` command."""

    course_url: str
    output_dir: str = "./slides"
    profile: str = DEFAULT_PROFILE
    headed: bool = False
    skip_title: str = "测试题"
    clear: bool = True
    resource_concurrency: int = 6
    catalog_max_scrolls: int = 120
    image_max_scrolls: int = 200
    user_agent: str = DEFAULT_USER_AGENT
    viewport_width: int = 390
    viewport_height: int = 844
    default_timeout_ms: int = 15000
    navigation_timeout_ms: int = 60000
    catalog_initial_wait_ms: int = 2200
    catalog_scroll_wait_ms: int = 850
    catalog_stable_cycles: int = 5
    chapter_response_checks: int = 20
    chapter_response_wait_ms: int = 500
    chapter_expand_wait_ms: int = 1200
    more_click_timeout_ms: int = 2000
    more_click_wait_ms: int = 700
    detail_load_wait_ms: int = 1500
    detail_retry_wait_ms: int = 1500
    intro_before_click_wait_ms: int = 1000
    intro_click_timeout_ms: int = 5000
    intro_after_click_wait_ms: int = 1000
    image_initial_wait_ms: int = 600
    image_scroll_wait_ms: int = 420
    image_scroll_step_min_px: int = 360
    image_scroll_viewport_ratio: float = 0.72
    image_end_hits: int = 5
    exclude_url_tokens: tuple[str, ...] = (
        "commonresource",
        "sprite",
        "icon",
        "avatar",
        "qlogo",
        "headimg",
        "loading",
    )
    include_url_tokens: tuple[str, ...] = (
        "xiaoe-materials",
        "wechatapppro-cos",
        "xiaoeknow",
        "xet-pic",
    )
    min_image_width: int = 900
    min_image_height: int = 450
    min_image_bytes: int = 1024
    slide_alt_prefix: str = "幻灯片"
    image_request_timeout_ms: int = 60000
    image_download_retries: int = 3
    image_retry_backoff_seconds: float = 0.8


@dataclass(frozen=True)
class CatalogItem:
    """A normalized catalog row from a xiaoe course page."""

    index: int
    title: str
    resource_id: str
    jump_url: str = ""
    chapter_type: int | None = None
    resource_type: int | None = None
    section_count: int = 0
    sort_value: int | None = None
    video_length: int | None = None
    parent_id: str = ""

    @property
    def has_detail_page(self) -> bool:
        return bool(self.jump_url)

    @property
    def is_chapter(self) -> bool:
        return self.section_count > 0 and not self.jump_url


@dataclass(frozen=True)
class DownloadResult:
    """Result of one image download attempt."""

    ok: bool
    bytes: int = 0
    error: str | None = None
