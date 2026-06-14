"""Command line interface for xiaoe-downloader."""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Sequence

from . import __version__
from .config import AppConfig, ConfigError, load_app_config
from .slides.models import SlideScrapeOptions
from .slides.pdf import generate_pdfs
from .slides.scraper import SlideScraper
from .video.downloader import VideoDownloader
from .video.extractor import CourseExtractor


def main(argv: Sequence[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        config = load_app_config()
        apply_config(args, config, parser)
    except ConfigError as exc:
        parser.error(str(exc))

    if args.command == "extract":
        asyncio.run(run_extract(args, config))
    elif args.command == "download":
        asyncio.run(run_download(args, config))
    elif args.command == "all":
        asyncio.run(run_all(args, config))
    elif args.command == "slides":
        asyncio.run(run_slides(args, config))
    elif args.command == "slides-pdf":
        run_slides_pdf(args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=f"xiaoe-downloader v{__version__} - one-click course media downloader",
        epilog=(
            "Reads ./config.toml by default. "
            "Command line arguments override config values."
        ),
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    extract_parser = subcommands.add_parser(
        "extract",
        help="extract course metadata from a running Chrome",
    )
    extract_parser.add_argument("url", nargs="?", help="course / column page URL")
    extract_parser.add_argument("--password", "-p", default=None, help="password to unlock the course")
    extract_parser.add_argument("--cdp", default=None, help="Chrome CDP endpoint")
    extract_parser.add_argument("--out", "-o", default=None, help="output JSON path")
    extract_parser.add_argument(
        "--headless",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="run extraction with a headless browser",
    )

    download_parser = subcommands.add_parser(
        "download",
        help="download videos from an items.json file",
    )
    download_parser.add_argument("items_json", nargs="?", help="path to items.json")
    download_parser.add_argument("--out", "-o", default=None, help="output directory")
    download_parser.add_argument("--cdp", default=None, help="Chrome CDP endpoint")

    all_parser = subcommands.add_parser("all", help="extract + download in one shot")
    all_parser.add_argument("url", nargs="?", help="course page URL")
    all_parser.add_argument("--password", "-p", default=None, help="course password")
    all_parser.add_argument("--out", "-o", default=None, help="output directory")
    all_parser.add_argument("--cdp", default=None, help="Chrome CDP endpoint")
    all_parser.add_argument(
        "--headless",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="run extraction with a headless browser",
    )

    slides_parser = subcommands.add_parser(
        "slides",
        help="download slide images from each video detail page's intro tab",
    )
    slides_parser.add_argument(
        "course_url",
        nargs="?",
        metavar="COURSE_URL",
        help="course catalog page URL",
    )
    slides_parser.add_argument("--out", "-o", default=None, help="output directory")
    slides_parser.add_argument(
        "--profile",
        default=None,
        help="Playwright persistent browser profile directory",
    )
    slides_parser.add_argument(
        "--headed",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="show the browser window so you can log in if needed",
    )
    slides_parser.add_argument(
        "--skip-title",
        default=None,
        help="skip catalog items whose title contains this text",
    )
    slides_parser.add_argument(
        "--clear",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="clear existing course/item output directories before writing",
    )
    slides_parser.add_argument(
        "--pdf",
        dest="pdf_enabled",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="generate sibling PDF files from downloaded slide images",
    )

    slides_pdf_parser = subcommands.add_parser(
        "slides-pdf",
        help="generate PDFs from an existing slides output directory",
    )
    slides_pdf_parser.add_argument(
        "slides_root",
        nargs="?",
        metavar="SLIDES_ROOT",
        help="slides root, course root, or chapter directory",
    )
    return parser


def apply_config(args, config: AppConfig, parser: argparse.ArgumentParser) -> None:
    if args.command == "extract":
        args.url = _pick(args.url, config.extract.course_url)
        args.password = _pick(args.password, config.extract.password)
        args.cdp = _pick(args.cdp, config.browser.cdp_url)
        args.out = _pick(args.out, config.extract.output_json)
        args.headless = _pick(args.headless, config.extract.headless)
        _require_value(parser, args.url, "course URL")
    elif args.command == "download":
        args.items_json = _pick(args.items_json, config.download.items_json)
        args.out = _pick(args.out, config.download.output_dir)
        args.cdp = _pick(args.cdp, config.browser.cdp_url)
    elif args.command == "all":
        args.url = _pick(args.url, config.extract.course_url)
        args.password = _pick(args.password, config.extract.password)
        args.out = _pick(args.out, config.download.output_dir)
        args.cdp = _pick(args.cdp, config.browser.cdp_url)
        args.headless = _pick(args.headless, config.extract.headless)
        _require_value(parser, args.url, "course URL")
    elif args.command == "slides":
        args.course_url = _pick(args.course_url, config.slides.course_url)
        args.out = _pick(args.out, config.slides.output_dir)
        args.profile = _pick(args.profile, config.browser.profile)
        args.headed = _pick(args.headed, config.browser.headed)
        args.skip_title = _pick(args.skip_title, config.slides.skip_title)
        args.clear = _pick(args.clear, config.slides.clear)
        args.pdf_enabled = _pick(args.pdf_enabled, config.slides.pdf.enabled)
        _require_value(parser, args.course_url, "course URL")
    elif args.command == "slides-pdf":
        args.slides_root = _pick(args.slides_root, config.slides.output_dir)


def _pick(cli_value, config_value):
    return config_value if cli_value is None else cli_value


def _require_value(parser: argparse.ArgumentParser, value: str, label: str) -> None:
    if not value:
        parser.error(
            f"{label} is required; pass it as an argument or set it in config.toml"
        )


async def run_extract(args, config: AppConfig) -> None:
    extractor = CourseExtractor(
        args.url,
        password=args.password,
        cdp_url=args.cdp,
        headless=args.headless,
        browser_config=config.browser,
        extract_config=config.extract,
        navigation_timeout_ms=config.browser.navigation_timeout_ms,
        initial_wait_ms=config.extract.initial_wait_ms,
        password_button_wait_ms=config.extract.password_button_wait_ms,
        password_input_wait_ms=config.extract.password_input_wait_ms,
        password_submit_wait_ms=config.extract.password_submit_wait_ms,
        catalog_tab_wait_ms=config.extract.catalog_tab_wait_ms,
        max_scrolls=config.extract.max_scrolls,
        scroll_wait_ms=config.extract.scroll_wait_ms,
        stable_after_scroll=config.extract.stable_after_scroll,
        min_stable_items=config.extract.min_stable_items,
        video_url_template=config.extract.video_url_template,
    )
    items = await extractor.extract()
    output_path = Path(args.out)
    output_path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nSaved {len(items)} items to {output_path}")


async def run_download(args, config: AppConfig) -> None:
    items = json.loads(Path(args.items_json).read_text(encoding="utf-8"))
    downloader = build_video_downloader(items, args.out, args.cdp, config)
    await downloader.download_all()


async def run_all(args, config: AppConfig) -> None:
    extractor = CourseExtractor(
        args.url,
        password=args.password,
        cdp_url=args.cdp,
        headless=args.headless,
        browser_config=config.browser,
        extract_config=config.extract,
        navigation_timeout_ms=config.browser.navigation_timeout_ms,
        initial_wait_ms=config.extract.initial_wait_ms,
        password_button_wait_ms=config.extract.password_button_wait_ms,
        password_input_wait_ms=config.extract.password_input_wait_ms,
        password_submit_wait_ms=config.extract.password_submit_wait_ms,
        catalog_tab_wait_ms=config.extract.catalog_tab_wait_ms,
        max_scrolls=config.extract.max_scrolls,
        scroll_wait_ms=config.extract.scroll_wait_ms,
        stable_after_scroll=config.extract.stable_after_scroll,
        min_stable_items=config.extract.min_stable_items,
        video_url_template=config.extract.video_url_template,
    )
    items = await extractor.extract()
    print(f"\nExtracted {len(items)} courses. Starting download ...\n")
    downloader = build_video_downloader(items, args.out, args.cdp, config)
    await downloader.download_all()


def build_video_downloader(
    items: list[dict],
    output_dir: str,
    cdp_url: str,
    config: AppConfig,
) -> VideoDownloader:
    return VideoDownloader(
        items,
        output_dir,
        cdp_url=cdp_url,
        browser_config=config.browser,
        download_config=config.download,
        ffmpeg_config=config.ffmpeg,
        concurrency=config.download.concurrency,
        skip_existing=config.download.skip_existing,
        filename_template=config.download.filename_template,
        page_timeout_ms=config.download.page_timeout_ms,
        page_wait_ms=config.download.page_wait_ms,
        m3u8_match=config.download.m3u8_match,
        fallback_video_url_template=config.download.fallback_video_url_template,
        ffmpeg_executable=config.ffmpeg.executable,
        ffmpeg_protocol_whitelist=config.ffmpeg.protocol_whitelist,
        ffmpeg_timeout_seconds=config.ffmpeg.timeout_seconds,
        ffmpeg_extra_args=config.ffmpeg.extra_args,
    )


async def run_slides(args, config: AppConfig) -> None:
    options = SlideScrapeOptions(
        course_url=args.course_url,
        output_dir=args.out,
        profile=args.profile,
        headed=args.headed,
        skip_title=args.skip_title,
        clear=args.clear,
        pdf_enabled=args.pdf_enabled,
        resource_concurrency=config.slides.resource_concurrency,
        catalog_max_scrolls=config.slides.catalog_max_scrolls,
        image_max_scrolls=config.slides.image_max_scrolls,
        user_agent=config.browser.user_agent,
        viewport_width=config.browser.viewport_width,
        viewport_height=config.browser.viewport_height,
        default_timeout_ms=config.browser.default_timeout_ms,
        navigation_timeout_ms=config.browser.navigation_timeout_ms,
        catalog_initial_wait_ms=config.slides.timing.catalog_initial_wait_ms,
        catalog_scroll_wait_ms=config.slides.timing.catalog_scroll_wait_ms,
        catalog_stable_cycles=config.slides.timing.catalog_stable_cycles,
        chapter_response_checks=config.slides.timing.chapter_response_checks,
        chapter_response_wait_ms=config.slides.timing.chapter_response_wait_ms,
        chapter_expand_wait_ms=config.slides.timing.chapter_expand_wait_ms,
        more_click_timeout_ms=config.slides.timing.more_click_timeout_ms,
        more_click_wait_ms=config.slides.timing.more_click_wait_ms,
        detail_load_wait_ms=config.slides.timing.detail_load_wait_ms,
        detail_retry_wait_ms=config.slides.timing.detail_retry_wait_ms,
        intro_before_click_wait_ms=config.slides.timing.intro_before_click_wait_ms,
        intro_click_timeout_ms=config.slides.timing.intro_click_timeout_ms,
        intro_after_click_wait_ms=config.slides.timing.intro_after_click_wait_ms,
        image_initial_wait_ms=config.slides.timing.image_initial_wait_ms,
        image_scroll_wait_ms=config.slides.timing.image_scroll_wait_ms,
        image_scroll_step_min_px=config.slides.timing.image_scroll_step_min_px,
        image_scroll_viewport_ratio=config.slides.timing.image_scroll_viewport_ratio,
        image_end_hits=config.slides.timing.image_end_hits,
        exclude_url_tokens=config.slides.resource_filter.exclude_url_tokens,
        include_url_tokens=config.slides.resource_filter.include_url_tokens,
        min_image_width=config.slides.resource_filter.min_width,
        min_image_height=config.slides.resource_filter.min_height,
        min_image_bytes=config.slides.resource_filter.min_bytes,
        slide_alt_prefix=config.slides.resource_filter.slide_alt_prefix,
        image_request_timeout_ms=config.slides.download.request_timeout_ms,
        image_download_retries=config.slides.download.retries,
        image_retry_backoff_seconds=config.slides.download.retry_backoff_seconds,
    )
    summary = await SlideScraper(options).scrape()
    print(
        "\nDone - "
        f"success: {summary['success_count']}, "
        f"failed: {summary['failed_count']}, "
        f"skipped: {summary['skipped_count']}, "
        f"images: {summary['image_count']}"
    )
    if summary.get("pdf"):
        pdf_summary = summary["pdf"]
        print(
            "PDFs - "
            f"generated: {pdf_summary['generated_count']}, "
            f"skipped: {pdf_summary['skipped_count']}, "
            f"failed: {pdf_summary['failed_count']}, "
            f"pages: {pdf_summary['page_count']}"
        )
    print(f"Output: {summary['output_root']}")


def run_slides_pdf(args) -> None:
    summary = generate_pdfs(args.slides_root)
    print(
        "PDFs - "
        f"generated: {summary.generated_count}, "
        f"skipped: {summary.skipped_count}, "
        f"failed: {summary.failed_count}, "
        f"pages: {summary.page_count}"
    )


if __name__ == "__main__":
    main()
