"""Application configuration loading for xiaoe-downloader."""
from __future__ import annotations

from dataclasses import dataclass, field, fields, is_dataclass, replace
from pathlib import Path
from typing import Any

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - covered on Python 3.10
    import tomli as tomllib

DEFAULT_CONFIG_FILENAME = "config.toml"
DEFAULT_PROFILE = "/tmp/xiaoe-playwright-profile"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 "
    "Mobile/15E148 Safari/604.1"
)


class ConfigError(ValueError):
    """Raised when the TOML config contains an invalid shape."""


@dataclass(frozen=True)
class BrowserConfig:
    cdp_url: str = "http://localhost:9222"
    profile: str = DEFAULT_PROFILE
    headed: bool = False
    viewport_width: int = 390
    viewport_height: int = 844
    user_agent: str = DEFAULT_USER_AGENT
    default_timeout_ms: int = 15000
    navigation_timeout_ms: int = 60000


@dataclass(frozen=True)
class ExtractConfig:
    course_url: str = ""
    password: str = ""
    output_json: str = "items.json"
    headless: bool = False
    initial_wait_ms: int = 3000
    password_button_wait_ms: int = 1000
    password_input_wait_ms: int = 500
    password_submit_wait_ms: int = 3000
    catalog_tab_wait_ms: int = 1000
    max_scrolls: int = 15
    scroll_wait_ms: int = 1500
    stable_after_scroll: int = 3
    min_stable_items: int = 8
    video_url_template: str = ""


@dataclass(frozen=True)
class DownloadConfig:
    items_json: str = "items.json"
    output_dir: str = "./videos"
    concurrency: int = 1
    skip_existing: bool = True
    filename_template: str = "{index_02}_{title}.mp4"
    page_timeout_ms: int = 30000
    page_wait_ms: int = 3000
    m3u8_match: str = ".m3u8"
    fallback_video_url_template: str = ""


@dataclass(frozen=True)
class FfmpegConfig:
    executable: str = "ffmpeg"
    protocol_whitelist: str = "file,http,https,tcp,tls,crypto,httpproxy"
    timeout_seconds: int = 3600
    extra_args: tuple[str, ...] = ()


@dataclass(frozen=True)
class SlidesTimingConfig:
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


@dataclass(frozen=True)
class SlidesResourceFilterConfig:
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
    min_width: int = 900
    min_height: int = 450
    min_bytes: int = 1024
    slide_alt_prefix: str = "幻灯片"


@dataclass(frozen=True)
class SlidesDownloadConfig:
    request_timeout_ms: int = 60000
    retries: int = 3
    retry_backoff_seconds: float = 0.8


@dataclass(frozen=True)
class SlidesPdfConfig:
    enabled: bool = False


@dataclass(frozen=True)
class SlidesConfig:
    course_url: str = ""
    output_dir: str = "./out/slides"
    skip_title: str = "测试题"
    clear: bool = True
    resource_concurrency: int = 6
    catalog_max_scrolls: int = 120
    image_max_scrolls: int = 200
    timing: SlidesTimingConfig = field(default_factory=SlidesTimingConfig)
    resource_filter: SlidesResourceFilterConfig = field(
        default_factory=SlidesResourceFilterConfig
    )
    download: SlidesDownloadConfig = field(default_factory=SlidesDownloadConfig)
    pdf: SlidesPdfConfig = field(default_factory=SlidesPdfConfig)


@dataclass(frozen=True)
class AppConfig:
    browser: BrowserConfig = field(default_factory=BrowserConfig)
    extract: ExtractConfig = field(default_factory=ExtractConfig)
    download: DownloadConfig = field(default_factory=DownloadConfig)
    ffmpeg: FfmpegConfig = field(default_factory=FfmpegConfig)
    slides: SlidesConfig = field(default_factory=SlidesConfig)


def load_app_config(base_dir: str | Path | None = None) -> AppConfig:
    """Load ``config.toml`` from ``base_dir`` or return defaults."""
    root = Path.cwd() if base_dir is None else Path(base_dir)
    config_path = root / DEFAULT_CONFIG_FILENAME
    config = AppConfig()
    if not config_path.exists():
        return config
    with config_path.open("rb") as file:
        raw_config = tomllib.load(file)
    if not isinstance(raw_config, dict):
        raise ConfigError("Config root must be a TOML table")
    return _merge_dataclass(config, raw_config, path="")


def _merge_dataclass(instance: Any, raw_values: dict[str, Any], *, path: str) -> Any:
    field_map = {field_info.name: field_info for field_info in fields(instance)}
    updates = {}
    for key, value in raw_values.items():
        current_path = f"{path}.{key}" if path else key
        if key not in field_map:
            raise ConfigError(f"Unknown config key: {current_path}")
        current_value = getattr(instance, key)
        if is_dataclass(current_value):
            if not isinstance(value, dict):
                raise ConfigError(f"Config key {current_path} must be a table")
            updates[key] = _merge_dataclass(current_value, value, path=current_path)
        else:
            updates[key] = _coerce_value(current_value, value, current_path)
    return replace(instance, **updates)


def _coerce_value(default_value: Any, value: Any, path: str) -> Any:
    if isinstance(default_value, tuple):
        if not isinstance(value, list):
            raise ConfigError(f"Config key {path} must be a list")
        return tuple(str(item) for item in value)
    expected_type = type(default_value)
    if expected_type is float and isinstance(value, int):
        return float(value)
    if not isinstance(value, expected_type):
        expected_name = expected_type.__name__
        raise ConfigError(f"Config key {path} must be {expected_name}")
    return value
