"""Video downloading through m3u8 capture and ffmpeg."""
from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from pathlib import Path

from playwright.async_api import async_playwright

from ..config import BrowserConfig, DownloadConfig, FfmpegConfig
from .naming import sanitize_filename

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


class VideoDownloader:
    """Download course videos by opening pages and capturing signed m3u8 URLs."""

    def __init__(
        self,
        items: list[dict],
        output_dir: str | Path | None = None,
        cdp_url: str | None = None,
        concurrency: int | None = None,
        skip_existing: bool | None = None,
        filename_template: str | None = None,
        page_timeout_ms: int | None = None,
        page_wait_ms: int | None = None,
        m3u8_match: str | None = None,
        fallback_video_url_template: str | None = None,
        ffmpeg_executable: str | None = None,
        ffmpeg_protocol_whitelist: str | None = None,
        ffmpeg_timeout_seconds: int | None = None,
        ffmpeg_extra_args: tuple[str, ...] | None = None,
        *,
        browser_config: BrowserConfig | None = None,
        download_config: DownloadConfig | None = None,
        ffmpeg_config: FfmpegConfig | None = None,
    ) -> None:
        browser_config = browser_config or BrowserConfig()
        download_config = download_config or DownloadConfig()
        ffmpeg_config = ffmpeg_config or FfmpegConfig()
        self.items = items
        self.output_dir = Path(output_dir or download_config.output_dir)
        self.cdp_url = browser_config.cdp_url if cdp_url is None else cdp_url
        self.concurrency = (
            download_config.concurrency if concurrency is None else concurrency
        )
        self.skip_existing = (
            download_config.skip_existing if skip_existing is None else skip_existing
        )
        self.filename_template = (
            download_config.filename_template
            if filename_template is None
            else filename_template
        )
        self.page_timeout_ms = (
            download_config.page_timeout_ms if page_timeout_ms is None else page_timeout_ms
        )
        self.page_wait_ms = download_config.page_wait_ms if page_wait_ms is None else page_wait_ms
        self.m3u8_match = download_config.m3u8_match if m3u8_match is None else m3u8_match
        self.fallback_video_url_template = (
            download_config.fallback_video_url_template
            if fallback_video_url_template is None
            else fallback_video_url_template
        )
        self.ffmpeg_executable = (
            ffmpeg_config.executable if ffmpeg_executable is None else ffmpeg_executable
        )
        self.ffmpeg_protocol_whitelist = (
            ffmpeg_config.protocol_whitelist
            if ffmpeg_protocol_whitelist is None
            else ffmpeg_protocol_whitelist
        )
        self.ffmpeg_timeout_seconds = (
            ffmpeg_config.timeout_seconds
            if ffmpeg_timeout_seconds is None
            else ffmpeg_timeout_seconds
        )
        self.ffmpeg_extra_args = tuple(
            ffmpeg_config.extra_args if ffmpeg_extra_args is None else ffmpeg_extra_args
        )

    async def download_all(self) -> dict:
        self.output_dir.mkdir(parents=True, exist_ok=True)

        async with async_playwright() as playwright:
            browser = await playwright.chromium.connect_over_cdp(self.cdp_url)
            context = browser.contexts[0] if browser.contexts else await browser.new_context()
            page = context.pages[0] if context.pages else await context.new_page()

            captured_m3u8 = [None]

            def on_request(request):
                if self.m3u8_match in request.url:
                    captured_m3u8[0] = request.url

            page.on("request", on_request)
            stats = {"success": 0, "failed": 0, "skipped": 0}

            for index, item in enumerate(self.items):
                resource_id = item.get("id", "")
                name = item.get("name", f"video_{index + 1}")
                filename = self._filename(index=index, title=name, resource_id=resource_id)
                output_path = self.output_dir / filename

                if self.skip_existing and output_path.exists():
                    print(f"[{index + 1}/{len(self.items)}] {name}  (skip - exists)")
                    stats["skipped"] += 1
                    continue

                captured_m3u8[0] = None
                try:
                    url = self._resolve_video_url(item)
                    await page.goto(url, wait_until="networkidle", timeout=self.page_timeout_ms)
                    await asyncio.sleep(self.page_wait_ms / 1000)

                    if captured_m3u8[0]:
                        print(f"[{index + 1}/{len(self.items)}] {name}")
                        if self._ffmpeg(captured_m3u8[0], output_path):
                            stats["success"] += 1
                        else:
                            stats["failed"] += 1
                    else:
                        print(f"[{index + 1}/{len(self.items)}] {name}  (no m3u8)")
                        stats["failed"] += 1
                except Exception as exc:
                    print(f"[{index + 1}/{len(self.items)}] {name}  ERROR: {exc}")
                    stats["failed"] += 1

            print(
                f"\nDone - success: {stats['success']}, "
                f"failed: {stats['failed']}, skipped: {stats['skipped']}"
            )
            return stats

    def _filename(self, *, index: int, title: str, resource_id: str) -> str:
        return self.filename_template.format(
            index=index + 1,
            index_02=f"{index + 1:02d}",
            title=sanitize_filename(title),
            resource_id=resource_id,
        )

    def _build_url(self, resource_id: str) -> str:
        if not self.fallback_video_url_template:
            raise ValueError(
                "Missing video_url for item "
                f"{resource_id!r}; set download.fallback_video_url_template "
                "only if this site cannot expose real detail URLs."
            )
        return self.fallback_video_url_template.format(resource_id=resource_id)

    def _resolve_video_url(self, item: dict) -> str:
        video_url = item.get("video_url")
        if isinstance(video_url, str) and video_url.strip():
            return video_url.strip()
        resource_id = item.get("id", "")
        if not self.fallback_video_url_template:
            item_label = item.get("name") or resource_id or "<unknown>"
            raise ValueError(
                f"Missing video_url for item {item_label!r}; "
                "set download.fallback_video_url_template only if this site "
                "cannot expose real detail URLs."
            )
        return self._build_url(resource_id)

    def _ffmpeg(self, m3u8_url: str, output_path: Path) -> bool:
        command = [
            self.ffmpeg_executable, "-y",
            "-protocol_whitelist",
            self.ffmpeg_protocol_whitelist,
            "-i", m3u8_url,
            *self.ffmpeg_extra_args,
            "-c", "copy",
            "-bsf:a", "aac_adtstoasc",
            str(output_path),
        ]
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=self.ffmpeg_timeout_seconds,
            )
            if result.returncode == 0:
                size_mb = os.path.getsize(output_path) / (1024 * 1024)
                print(f"  [OK] {size_mb:.1f} MB")
                return True
            error_lines = result.stderr.strip().split("\n")[-3:]
            print(f"  [FAIL] {' | '.join(error_lines)}")
            return False
        except subprocess.TimeoutExpired:
            print("  [FAIL] timeout (>1 h)")
            return False
        except Exception as exc:
            print(f"  [FAIL] {exc}")
            return False


XiaoeDownloader = VideoDownloader
