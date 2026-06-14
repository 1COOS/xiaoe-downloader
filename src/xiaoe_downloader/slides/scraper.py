"""High-level orchestration for the ``slides`` command."""
from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

from playwright.async_api import BrowserContext, Page, async_playwright

from .browser import configure_page, open_mobile_context
from .catalog import filter_catalog_items, get_course_title, load_chapter_children, load_full_catalog
from .collector import (
    build_detail_url,
    click_intro_tab,
    collect_slide_resources,
    course_id_from_url,
    detect_slides_input_type,
    origin_from_url,
    video_resource_id_from_url,
)
from .downloads import download_slide_images
from .manifest import add_item_to_summary, build_success_manifest, create_root_summary, write_json, write_skipped_manifest
from .models import CatalogItem, SlideScrapeOptions
from .naming import make_unique_name, sanitize_name
from .pdf import generate_pdfs


class SlideScraper:
    """Scrape intro-tab slide images from course catalogs or single video pages."""

    def __init__(self, options: SlideScrapeOptions) -> None:
        self.options = options
        self.origin = origin_from_url(options.course_url)
        self.course_id = course_id_from_url(options.course_url)

    async def scrape(self) -> dict:
        input_type = detect_slides_input_type(
            self.options.course_url,
            requested=self.options.input_type,
        )
        if input_type == "video":
            return await self._scrape_single_video()
        return await self._scrape_catalog()

    async def _scrape_catalog(self) -> dict:
        output_base = Path(self.options.output_dir)
        output_base.mkdir(parents=True, exist_ok=True)
        summary = create_root_summary(self.options.course_url, input_type="catalog")

        async with async_playwright() as playwright:
            context = await open_mobile_context(playwright, self.options)
            list_page = configure_page(
                context.pages[0] if context.pages else await context.new_page(),
                self.options,
            )
            detail_page = configure_page(await context.new_page(), self.options)

            catalog_items = await load_full_catalog(list_page, self.options)
            course_title = sanitize_name(await get_course_title(list_page))
            course_output_dir = output_base / course_title
            course_output_dir.mkdir(parents=True, exist_ok=True)
            summary["output_root"] = str(course_output_dir.resolve())

            selected_items, skipped_items = filter_catalog_items(
                catalog_items,
                skip_title=self.options.skip_title,
            )
            summary["catalog"] = {
                "total": len(catalog_items),
                "skipped_by_title": len(skipped_items),
                "selected": len(selected_items),
            }
            if not selected_items:
                await context.close()
                raise RuntimeError(
                    "No catalog items were found. If the page requires login, rerun with --headed "
                    "and complete login in the opened browser."
                )

            used_names: dict[str, int] = {}
            for position, catalog_item in enumerate(selected_items, start=1):
                item_summary = await self._scrape_catalog_item(
                    context=context,
                    list_page=list_page,
                    detail_page=detail_page,
                    item=catalog_item,
                    position=position,
                    total=len(selected_items),
                    root=course_output_dir,
                    used_names=used_names,
                )
                add_item_to_summary(summary, item_summary)
                write_json(course_output_dir / "summary.json", summary)

            summary["finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
            write_json(course_output_dir / "summary.json", summary)
            if self.options.pdf_enabled:
                summary["pdf"] = generate_pdfs(course_output_dir).to_dict()
                write_json(course_output_dir / "summary.json", summary)
            await context.close()
            return summary

    async def _scrape_single_video(self) -> dict:
        output_base = Path(self.options.output_dir)
        output_base.mkdir(parents=True, exist_ok=True)
        summary = create_root_summary(self.options.course_url, input_type="video")
        summary["detail_url"] = self.options.course_url
        summary["catalog"] = {
            "total": 1,
            "skipped_by_title": 0,
            "selected": 1,
        }

        resource_id = video_resource_id_from_url(self.options.course_url) or "video"
        item = CatalogItem(
            index=1,
            title=resource_id,
            resource_id=resource_id,
            jump_url="",
        )
        video_output_dir = output_base / (sanitize_name(resource_id) or "video")
        summary["output_root"] = str(video_output_dir.resolve())

        async with async_playwright() as playwright:
            context = await open_mobile_context(playwright, self.options)
            try:
                detail_page = configure_page(
                    context.pages[0] if context.pages else await context.new_page(),
                    self.options,
                )
                self._prepare_output_dir(video_output_dir)
                try:
                    result = await self._scrape_detail(
                        context,
                        detail_page,
                        item,
                        video_output_dir,
                        detail_url=self.options.course_url,
                    )
                except Exception as exc:
                    result = {
                        "status": "failed",
                        "reason": "EXCEPTION",
                        "image_count": 0,
                        "error": repr(exc),
                        "detail_url": self.options.course_url,
                    }
                    write_json(
                        video_output_dir / "failed.json",
                        {**_catalog_item_json(item), **result},
                    )

                item_summary = {
                    "index": 1,
                    "title": item.title,
                    "resource_id": item.resource_id,
                    "jump_url": item.jump_url,
                    "output_dir": str(video_output_dir.resolve()),
                    **result,
                }
                add_item_to_summary(summary, item_summary)
                summary["finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
                write_json(video_output_dir / "summary.json", summary)
                if self.options.pdf_enabled:
                    summary["pdf"] = generate_pdfs(video_output_dir).to_dict()
                    write_json(video_output_dir / "summary.json", summary)
                return summary
            finally:
                await context.close()

    async def _scrape_catalog_item(
        self,
        *,
        context: BrowserContext,
        list_page: Page,
        detail_page: Page,
        item: CatalogItem,
        position: int,
        total: int,
        root: Path,
        used_names: dict[str, int],
    ) -> dict:
        output_name = make_unique_name(item.title, used_names)
        item_output_dir = root / output_name

        print(f"[{position:02d}/{total}] {item.title}", flush=True)
        try:
            if item.has_detail_page:
                self._prepare_output_dir(item_output_dir)
                result = await self._scrape_detail(context, detail_page, item, item_output_dir)
            elif item.is_chapter:
                result = await self._scrape_chapter(
                    context=context,
                    list_page=list_page,
                    detail_page=detail_page,
                    item=item,
                    chapter_dir=item_output_dir,
                )
            else:
                self._prepare_output_dir(item_output_dir)
                result = write_skipped_manifest(
                    item_output_dir,
                    item,
                    reason="NO_DETAIL_OR_NO_INTRO_IMAGES",
                )
        except Exception as exc:
            self._prepare_output_dir(item_output_dir)
            result = {
                "status": "failed",
                "reason": "EXCEPTION",
                "image_count": 0,
                "error": repr(exc),
            }
            write_json(item_output_dir / "failed.json", {**_catalog_item_json(item), **result})

        print(
            f"    -> {result['status']} images={result.get('image_count', 0)} "
            f"reason={result.get('reason', '')}",
            flush=True,
        )
        return {
            "index": position,
            "title": item.title,
            "resource_id": item.resource_id,
            "jump_url": item.jump_url,
            "output_dir": str(item_output_dir.resolve()),
            **result,
        }

    async def _scrape_chapter(
        self,
        *,
        context: BrowserContext,
        list_page: Page,
        detail_page: Page,
        item: CatalogItem,
        chapter_dir: Path,
    ) -> dict:
        self._prepare_output_dir(chapter_dir)
        children = await load_chapter_children(list_page, item, self.options)
        children, _ = filter_catalog_items(children, skip_title=self.options.skip_title)
        if not children:
            return write_skipped_manifest(
                chapter_dir,
                item,
                reason="NO_DETAIL_OR_NO_INTRO_IMAGES",
            )

        chapter_manifest = {
            "title": item.title,
            "resource_id": item.resource_id,
            "child_count": len(children),
            "items": [],
            "success_count": 0,
            "skipped_count": 0,
            "failed_count": 0,
            "image_count": 0,
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        used_names: dict[str, int] = {}
        for child_position, child in enumerate(children, start=1):
            child_output_dir = chapter_dir / make_unique_name(child.title, used_names)
            self._prepare_output_dir(child_output_dir)
            child_result = await self._scrape_detail(context, detail_page, child, child_output_dir)

            chapter_manifest["items"].append(
                {
                    "index": child_position,
                    "title": child.title,
                    "resource_id": child.resource_id,
                    "jump_url": child.jump_url,
                    "output_dir": str(child_output_dir.resolve()),
                    **child_result,
                }
            )
            chapter_manifest["image_count"] += int(child_result.get("image_count") or 0)
            if child_result["status"] == "success":
                chapter_manifest["success_count"] += 1
            elif child_result["status"] == "skipped":
                chapter_manifest["skipped_count"] += 1
            else:
                chapter_manifest["failed_count"] += 1

        chapter_manifest["finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        write_json(chapter_dir / "manifest.json", chapter_manifest)

        if chapter_manifest["failed_count"]:
            status = "failed"
        elif chapter_manifest["skipped_count"]:
            status = "skipped"
        else:
            status = "success"
        return {
            "status": status,
            "image_count": chapter_manifest["image_count"],
            "child_count": chapter_manifest["child_count"],
            "success_child_count": chapter_manifest["success_count"],
            "skipped_child_count": chapter_manifest["skipped_count"],
            "failed_child_count": chapter_manifest["failed_count"],
            "chapter_manifest": str((chapter_dir / "manifest.json").resolve()),
        }

    async def _scrape_detail(
        self,
        context: BrowserContext,
        page: Page,
        item: CatalogItem,
        output_dir: Path,
        *,
        detail_url: str | None = None,
    ) -> dict:
        detail_url = detail_url or build_detail_url(
            item,
            origin=self.origin,
            course_id=self.course_id,
        )
        await page.goto(
            detail_url,
            wait_until="domcontentloaded",
            timeout=self.options.navigation_timeout_ms,
        )
        await page.wait_for_timeout(self.options.detail_load_wait_ms)
        clicked_intro = await click_intro_tab(page, self.options)
        image_entries = await collect_slide_resources(page, self.options)
        if not image_entries and clicked_intro:
            await page.wait_for_timeout(self.options.detail_retry_wait_ms)
            image_entries = await collect_slide_resources(page, self.options)

        if not image_entries:
            return write_skipped_manifest(
                output_dir,
                item,
                reason="NO_DETAIL_OR_NO_INTRO_IMAGES",
                detail_url=detail_url,
                clicked_intro=clicked_intro,
            )

        download_results = await download_slide_images(
            context,
            image_entries,
            output_dir,
            referer=detail_url,
            concurrency=self.options.resource_concurrency,
            user_agent=self.options.user_agent,
            request_timeout_ms=self.options.image_request_timeout_ms,
            retries=self.options.image_download_retries,
            retry_backoff_seconds=self.options.image_retry_backoff_seconds,
            min_bytes=self.options.min_image_bytes,
        )
        manifest = build_success_manifest(
            title=item.title,
            resource_id=item.resource_id,
            detail_url=detail_url,
            clicked_intro=clicked_intro,
            entries=image_entries,
            results=download_results,
            output_dir=output_dir,
            extra={
                "sort_value": item.sort_value,
                "video_length": item.video_length,
            },
        )
        if manifest["failed_download_count"]:
            return {
                "status": "failed",
                "reason": "IMAGE_DOWNLOAD_FAILED",
                "image_count": manifest["image_count"],
                "failed_downloads": manifest["failed_download_count"],
                "detail_url": detail_url,
            }
        return {
            "status": "success",
            "image_count": manifest["image_count"],
            "detail_url": detail_url,
        }

    def _prepare_output_dir(self, path: Path) -> None:
        if self.options.clear and path.exists():
            shutil.rmtree(path)
        path.mkdir(parents=True, exist_ok=True)


def _catalog_item_json(item: CatalogItem) -> dict:
    return {
        "title": item.title,
        "resource_id": item.resource_id,
        "jump_url": item.jump_url,
        "section_count": item.section_count,
    }
