"""Manifest and summary JSON writers."""
from __future__ import annotations

import json
import time
from pathlib import Path

from .models import CatalogItem, DownloadResult


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def build_success_manifest(
    *,
    title: str,
    resource_id: str,
    detail_url: str,
    clicked_intro: bool,
    entries: list[dict],
    results: list[DownloadResult],
    output_dir: Path,
    extra: dict | None = None,
) -> dict:
    images = []
    failed_downloads = []

    for index, (entry, result) in enumerate(zip(entries, results), start=1):
        record = {
            "index": index,
            "file": f"{index:03d}.jpg",
            "alt": entry.get("alt") or "",
            "natural_width": entry.get("natural_width") or 0,
            "natural_height": entry.get("natural_height") or 0,
            "bytes": result.bytes,
            "url": entry.get("src") or "",
        }
        if result.ok:
            images.append(record)
        else:
            record["error"] = result.error
            failed_downloads.append(record)

    manifest = {
        "title": title,
        "resource_id": resource_id,
        "detail_url": detail_url,
        "clicked_intro": clicked_intro,
        "image_count": len(images),
        "failed_download_count": len(failed_downloads),
        "images": images,
        "failed_downloads": failed_downloads,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    if extra:
        manifest.update(extra)

    write_json(output_dir / "manifest.json", manifest)
    return manifest


def write_skipped_manifest(
    output_dir: Path,
    item: CatalogItem,
    *,
    reason: str,
    detail_url: str = "",
    clicked_intro: bool | None = None,
) -> dict:
    payload = {
        "title": item.title,
        "resource_id": item.resource_id,
        "detail_url": detail_url,
        "reason": reason,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    if clicked_intro is not None:
        payload["clicked_intro"] = clicked_intro
    write_json(output_dir / "skipped.json", payload)
    return {"status": "skipped", "reason": reason, "image_count": 0}


def create_root_summary(course_url: str) -> dict:
    return {
        "course_url": course_url,
        "output_root": "",
        "catalog": {},
        "items": [],
        "success_count": 0,
        "skipped_count": 0,
        "failed_count": 0,
        "image_count": 0,
        "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }


def add_item_to_summary(summary: dict, item_summary: dict) -> None:
    summary["items"].append(item_summary)
    summary["image_count"] += int(item_summary.get("image_count") or 0)
    status = item_summary["status"]
    if status == "success":
        summary["success_count"] += 1
    elif status == "skipped":
        summary["skipped_count"] += 1
    else:
        summary["failed_count"] += 1
