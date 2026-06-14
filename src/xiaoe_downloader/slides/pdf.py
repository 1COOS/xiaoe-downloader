"""Build PDF files from downloaded slide image manifests."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Iterable

import img2pdf


@dataclass(frozen=True)
class PdfItemResult:
    title: str
    input_dir: str
    output_pdf: str
    status: str
    page_count: int = 0
    reason: str = ""
    error: str = ""


@dataclass(frozen=True)
class PdfGenerationSummary:
    root: str
    generated_count: int
    skipped_count: int
    failed_count: int
    page_count: int
    results: list[PdfItemResult]

    def to_dict(self) -> dict:
        return {
            "root": self.root,
            "generated_count": self.generated_count,
            "skipped_count": self.skipped_count,
            "failed_count": self.failed_count,
            "page_count": self.page_count,
            "results": [asdict(result) for result in self.results],
        }


def generate_pdfs(root: str | Path) -> PdfGenerationSummary:
    """Generate sibling PDFs for a slides root, course root, or item directory."""
    root_path = Path(root)
    results = [_generate_for_item(item_dir) for item_dir in _iter_item_dirs(root_path)]
    return PdfGenerationSummary(
        root=str(root_path),
        generated_count=sum(result.status == "generated" for result in results),
        skipped_count=sum(result.status == "skipped" for result in results),
        failed_count=sum(result.status == "failed" for result in results),
        page_count=sum(result.page_count for result in results),
        results=results,
    )


def _iter_item_dirs(root: Path) -> Iterable[Path]:
    if (root / "summary.json").exists():
        yield from _course_item_dirs(root)
        return
    if (root / "manifest.json").exists():
        yield root
        return

    for child in sorted(root.iterdir() if root.is_dir() else (), key=lambda path: path.name):
        if not child.is_dir():
            continue
        if (child / "summary.json").exists():
            yield from _course_item_dirs(child)
        elif (child / "manifest.json").exists():
            yield child


def _course_item_dirs(course_root: Path) -> Iterable[Path]:
    summary = _read_json(course_root / "summary.json")
    for item in _sorted_records(summary.get("items") or []):
        yield _resolve_output_dir(item, course_root)


def _generate_for_item(item_dir: Path) -> PdfItemResult:
    output_pdf = item_dir.parent / f"{item_dir.name}.pdf"
    manifest_path = item_dir / "manifest.json"
    title = item_dir.name
    if not manifest_path.exists():
        _remove_stale_pdf(output_pdf)
        return PdfItemResult(
            title=title,
            input_dir=str(item_dir),
            output_pdf=str(output_pdf),
            status="skipped",
            reason="NO_MANIFEST",
        )

    try:
        manifest = _read_json(manifest_path)
        title = str(manifest.get("title") or title)
        image_paths = _image_paths_for_manifest(item_dir, manifest)
        if not image_paths:
            _remove_stale_pdf(output_pdf)
            return PdfItemResult(
                title=title,
                input_dir=str(item_dir),
                output_pdf=str(output_pdf),
                status="skipped",
                reason="NO_IMAGES",
            )

        output_pdf.write_bytes(img2pdf.convert([str(path) for path in image_paths]))
        return PdfItemResult(
            title=title,
            input_dir=str(item_dir),
            output_pdf=str(output_pdf),
            status="generated",
            page_count=len(image_paths),
        )
    except Exception as exc:
        return PdfItemResult(
            title=title,
            input_dir=str(item_dir),
            output_pdf=str(output_pdf),
            status="failed",
            reason="PDF_GENERATION_FAILED",
            error=repr(exc),
        )


def _image_paths_for_manifest(item_dir: Path, manifest: dict) -> list[Path]:
    if manifest.get("items"):
        return _chapter_child_image_paths(item_dir, manifest)
    return _regular_image_paths(item_dir, manifest)


def _chapter_child_image_paths(chapter_dir: Path, manifest: dict) -> list[Path]:
    image_paths: list[Path] = []
    for child in _sorted_records(manifest.get("items") or []):
        child_dir = _resolve_output_dir(child, chapter_dir)
        child_manifest_path = child_dir / "manifest.json"
        if not child_manifest_path.exists():
            continue
        child_manifest = _read_json(child_manifest_path)
        image_paths.extend(_regular_image_paths(child_dir, child_manifest))
    return image_paths


def _regular_image_paths(item_dir: Path, manifest: dict) -> list[Path]:
    paths = []
    for image in _sorted_records(manifest.get("images") or []):
        file_name = image.get("file")
        if not file_name:
            continue
        image_path = item_dir / str(file_name)
        if image_path.exists():
            paths.append(image_path)
    return paths


def _resolve_output_dir(record: dict, parent_dir: Path) -> Path:
    raw_output_dir = record.get("output_dir")
    if raw_output_dir:
        output_dir = Path(str(raw_output_dir))
        if output_dir.exists():
            return output_dir
    title = str(record.get("title") or "")
    if title:
        fallback = parent_dir / title
        if fallback.exists():
            return fallback
    return parent_dir / title


def _sorted_records(records: list[dict]) -> list[dict]:
    return sorted(records, key=lambda record: int(record.get("index") or 0))


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _remove_stale_pdf(path: Path) -> None:
    if path.exists():
        path.unlink()
