"""Image download and retry logic."""
from __future__ import annotations

import asyncio
from pathlib import Path

from playwright.async_api import BrowserContext

from .models import DownloadResult


async def download_slide_images(
    context: BrowserContext,
    entries: list[dict],
    output_dir: Path,
    *,
    referer: str,
    concurrency: int,
    user_agent: str,
    request_timeout_ms: int = 60000,
    retries: int = 3,
    retry_backoff_seconds: float = 0.8,
    min_bytes: int = 1024,
) -> list[DownloadResult]:
    semaphore = asyncio.Semaphore(concurrency)

    async def download_one(index: int, entry: dict) -> DownloadResult:
        async with semaphore:
            destination = output_dir / f"{index:03d}.jpg"
            last_error = None
            for attempt in range(1, retries + 1):
                try:
                    response = await context.request.get(
                        entry["src"],
                        headers={"Referer": referer, "User-Agent": user_agent},
                        timeout=request_timeout_ms,
                    )
                    if not response.ok:
                        last_error = f"HTTP {response.status}"
                        await asyncio.sleep(retry_backoff_seconds * attempt)
                        continue
                    body = await response.body()
                    if len(body) < min_bytes:
                        last_error = f"too small: {len(body)} bytes"
                        await asyncio.sleep(retry_backoff_seconds * attempt)
                        continue
                    destination.write_bytes(body)
                    return DownloadResult(ok=True, bytes=len(body))
                except Exception as exc:
                    last_error = repr(exc)
                    await asyncio.sleep(retry_backoff_seconds * attempt)
            return DownloadResult(ok=False, error=last_error)

    return await asyncio.gather(
        *[download_one(index, entry) for index, entry in enumerate(entries, start=1)]
    )
