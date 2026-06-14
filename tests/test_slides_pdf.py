import json
import importlib
from importlib.util import find_spec


def _pdf_module():
    assert find_spec("xiaoe_downloader.slides.pdf") is not None
    return importlib.import_module("xiaoe_downloader.slides.pdf")


def _write_manifest(directory, title, files):
    directory.mkdir(parents=True)
    for file_name in files:
        (directory / file_name).write_bytes(b"image")
    (directory / "manifest.json").write_text(
        json.dumps(
            {
                "title": title,
                "image_count": len(files),
                "images": [
                    {"index": index, "file": file_name}
                    for index, file_name in enumerate(files, start=1)
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def test_generate_pdfs_uses_manifest_order_for_single_item(tmp_path, monkeypatch):
    pdf_module = _pdf_module()
    item_dir = tmp_path / "课程一" / "章节A"
    _write_manifest(item_dir, "章节A", ["002.jpg", "001.jpg"])
    calls = []

    monkeypatch.setattr(
        pdf_module.img2pdf,
        "convert",
        lambda files: calls.append(files) or b"%PDF",
    )

    summary = pdf_module.generate_pdfs(item_dir)

    assert summary.generated_count == 1
    assert summary.page_count == 2
    assert summary.skipped_count == 0
    assert (tmp_path / "课程一" / "章节A.pdf").read_bytes() == b"%PDF"
    assert calls == [[str(item_dir / "002.jpg"), str(item_dir / "001.jpg")]]


def test_generate_pdfs_merges_chapter_children_in_manifest_order(tmp_path, monkeypatch):
    pdf_module = _pdf_module()
    course_root = tmp_path / "课程一"
    chapter_dir = course_root / "父章节"
    first_child = chapter_dir / "第二小节目录"
    second_child = chapter_dir / "第一小节目录"
    _write_manifest(first_child, "第二小节", ["001.jpg"])
    _write_manifest(second_child, "第一小节", ["001.jpg", "002.jpg"])
    (chapter_dir / "manifest.json").write_text(
        json.dumps(
            {
                "title": "父章节",
                "items": [
                    {"index": 1, "title": "第一小节", "output_dir": str(second_child)},
                    {"index": 2, "title": "第二小节", "output_dir": str(first_child)},
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (course_root / "summary.json").write_text(
        json.dumps(
            {"items": [{"index": 1, "title": "父章节", "output_dir": str(chapter_dir)}]},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    calls = []

    monkeypatch.setattr(
        pdf_module.img2pdf,
        "convert",
        lambda files: calls.append(files) or b"%PDF",
    )

    summary = pdf_module.generate_pdfs(course_root)

    assert summary.generated_count == 1
    assert summary.page_count == 3
    assert summary.skipped_count == 0
    assert (course_root / "父章节.pdf").read_bytes() == b"%PDF"
    assert calls == [
        [
            str(second_child / "001.jpg"),
            str(second_child / "002.jpg"),
            str(first_child / "001.jpg"),
        ]
    ]


def test_generate_pdfs_processes_multiple_course_roots(tmp_path, monkeypatch):
    slides_root = tmp_path / "slides"
    first_item = slides_root / "课程一" / "章节A"
    second_item = slides_root / "课程二" / "章节B"
    _write_manifest(first_item, "章节A", ["001.jpg"])
    _write_manifest(second_item, "章节B", ["001.jpg"])
    for course_root, item_dir in [
        (slides_root / "课程一", first_item),
        (slides_root / "课程二", second_item),
    ]:
        (course_root / "summary.json").write_text(
            json.dumps(
                {"items": [{"index": 1, "title": item_dir.name, "output_dir": str(item_dir)}]},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    pdf_module = _pdf_module()
    calls = []

    monkeypatch.setattr(
        pdf_module.img2pdf,
        "convert",
        lambda files: calls.append(files) or b"%PDF",
    )

    summary = pdf_module.generate_pdfs(slides_root)

    assert summary.generated_count == 2
    assert summary.page_count == 2
    assert (slides_root / "课程一" / "章节A.pdf").exists()
    assert (slides_root / "课程二" / "章节B.pdf").exists()


def test_generate_pdfs_skips_item_without_manifest_images(tmp_path, monkeypatch):
    pdf_module = _pdf_module()
    item_dir = tmp_path / "课程一" / "空章节"
    item_dir.mkdir(parents=True)
    (item_dir / "manifest.json").write_text(
        json.dumps({"title": "空章节", "image_count": 0, "images": []}, ensure_ascii=False),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        pdf_module.img2pdf,
        "convert",
        lambda files: b"%PDF",
    )

    summary = pdf_module.generate_pdfs(item_dir)

    assert summary.generated_count == 0
    assert summary.page_count == 0
    assert summary.skipped_count == 1
    assert summary.results[0].status == "skipped"
    assert summary.results[0].reason == "NO_IMAGES"
