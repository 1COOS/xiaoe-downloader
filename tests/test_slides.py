import json

from xiaoe_downloader.slides.collector import (
    build_detail_url,
    is_slide_resource_candidate,
    sort_slide_resources,
)
from xiaoe_downloader.slides.downloads import DownloadResult
from xiaoe_downloader.slides.manifest import build_success_manifest
from xiaoe_downloader.slides.naming import make_unique_name, sanitize_name
from xiaoe_downloader.slides.catalog import (
    CatalogItem,
    catalog_item_from_raw,
    filter_catalog_items,
    parse_chapter_children,
)
from xiaoe_downloader.slides.models import SlideScrapeOptions


def test_default_slide_options_match_cli_defaults():
    options = SlideScrapeOptions(course_url="https://example.com/p/course/ecourse/course_123")

    assert options.output_dir == "./slides"
    assert options.profile == "/tmp/xiaoe-playwright-profile"
    assert options.skip_title == "测试题"
    assert options.clear is True
    assert options.resource_concurrency == 6


def test_catalog_item_from_raw_prefers_resource_and_chapter_titles():
    resource_item = catalog_item_from_raw(
        {
            "resource_title": "资源标题",
            "chapter_title": "章节标题",
            "resource_id": "v_1",
            "jump_url": "/p/course/video/v_1",
            "section_num": 0,
        },
        index=3,
    )
    chapter_item = catalog_item_from_raw(
        {
            "chapter_title": "章节标题",
            "chapter_id": "chap_1",
            "section_num": 2,
        },
        index=4,
    )

    assert resource_item.title == "资源标题"
    assert resource_item.resource_id == "v_1"
    assert resource_item.index == 3
    assert chapter_item.title == "章节标题"
    assert chapter_item.resource_id == "chap_1"
    assert chapter_item.section_count == 2


def test_filter_catalog_items_skips_test_titles():
    items = [
        CatalogItem(index=1, title="正课", resource_id="v_1", jump_url="/p/course/video/v_1"),
        CatalogItem(index=2, title="正课测试题", resource_id="ex_1", jump_url="/exam"),
    ]

    selected, skipped = filter_catalog_items(items, skip_title="测试题")

    assert [item.title for item in selected] == ["正课"]
    assert [item.title for item in skipped] == ["正课测试题"]


def test_parse_chapter_children_uses_parent_id_and_sort_order():
    payload = {
        "data": {
            "list": [
                {
                    "p_id": "chap_1",
                    "resource_title": "第二节",
                    "resource_id": "v_2",
                    "jump_url": "/p/course/video/v_2",
                    "sort_value": 2,
                },
                {
                    "p_id": "other",
                    "resource_title": "其他章节",
                    "resource_id": "v_x",
                    "jump_url": "/p/course/video/v_x",
                    "sort_value": 1,
                },
                {
                    "p_id": "chap_1",
                    "resource_title": "第一节",
                    "resource_id": "v_1",
                    "jump_url": "/p/course/video/v_1",
                    "sort_value": 1,
                },
            ]
        }
    }

    children = parse_chapter_children(payload, parent_resource_id="chap_1")

    assert [child.title for child in children] == ["第一节", "第二节"]
    assert [child.resource_id for child in children] == ["v_1", "v_2"]


def test_build_detail_url_adds_course_query_parameters():
    item = CatalogItem(
        index=1,
        title="课程",
        resource_id="v_1",
        jump_url="/p/course/video/v_1",
    )

    url = build_detail_url(
        item,
        origin="https://app.example.com",
        course_id="course_abc",
    )

    assert url == (
        "https://app.example.com/p/course/video/v_1"
        "?product_id=course_abc&course_id=course_abc&sub_course_id="
    )


def test_sort_slide_resources_prefers_slide_numbers_when_present():
    entries = [
        {"src": "3.jpg", "alt": "幻灯片3.jpg", "first_seen_step": 0, "top": 0},
        {"src": "1.jpg", "alt": "幻灯片1.jpg", "first_seen_step": 1, "top": 100},
        {"src": "2.jpg", "alt": "幻灯片2.jpg", "first_seen_step": 2, "top": 200},
    ]

    assert [entry["src"] for entry in sort_slide_resources(entries)] == [
        "1.jpg",
        "2.jpg",
        "3.jpg",
    ]


def test_sanitize_name_replaces_illegal_path_characters():
    assert sanitize_name('A/B:C*D?E"F<G>H|') == "A-B-C-D-E-F-G-H-"
    assert sanitize_name("  多   个   空格  . ") == "多 个 空格"


def test_make_unique_name_appends_suffix_for_duplicate_titles():
    used = {}

    assert make_unique_name("同名课程", used) == "同名课程"
    assert make_unique_name("同名课程", used) == "同名课程-2"
    assert make_unique_name("同名课程", used) == "同名课程-3"


def test_is_slide_resource_candidate_keeps_slides_and_large_course_images():
    assert is_slide_resource_candidate(
        {
            "src": "https://cdn.example.com/a.jpg",
            "alt": "幻灯片12.jpg",
            "natural_width": 320,
            "natural_height": 180,
        }
    )
    assert is_slide_resource_candidate(
        {
            "src": "https://wechatapppro-cos.cdn.xiaoe-materials.com/app/image/a.jpg",
            "alt": "",
            "natural_width": 1600,
            "natural_height": 900,
        }
    )


def test_is_slide_resource_candidate_filters_ui_images():
    assert not is_slide_resource_candidate(
        {
            "src": "data:image/png;base64,abc",
            "alt": "幻灯片1.jpg",
            "natural_width": 1600,
            "natural_height": 900,
        }
    )
    assert not is_slide_resource_candidate(
        {
            "src": "https://commonresource-1252524126.cdn.xiaoeknow.com/icon.png",
            "alt": "幻灯片1.jpg",
            "natural_width": 1600,
            "natural_height": 900,
        }
    )
    assert not is_slide_resource_candidate(
        {
            "src": "https://wechatapppro-cos.cdn.xiaoe-materials.com/avatar.jpg",
            "alt": "",
            "natural_width": 120,
            "natural_height": 120,
        }
    )


def test_build_success_manifest_numbers_images_sequentially(tmp_path):
    entries = [
        {
            "src": "https://example.com/one.jpg",
            "alt": "幻灯片1.jpg",
            "natural_width": 1600,
            "natural_height": 900,
        },
        {
            "src": "https://example.com/two.jpg",
            "alt": "幻灯片2.jpg",
            "natural_width": 1600,
            "natural_height": 900,
        },
    ]
    results = [
        DownloadResult(ok=True, bytes=10),
        DownloadResult(ok=True, bytes=20),
    ]

    manifest = build_success_manifest(
        title="课程标题",
        resource_id="v_1",
        detail_url="https://example.com/video/v_1",
        clicked_intro=True,
        entries=entries,
        results=results,
        output_dir=tmp_path,
    )

    assert manifest["image_count"] == 2
    assert [image["file"] for image in manifest["images"]] == ["001.jpg", "002.jpg"]
    assert [image["bytes"] for image in manifest["images"]] == [10, 20]
    assert manifest["failed_download_count"] == 0

    saved = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert saved["title"] == "课程标题"
    assert [image["index"] for image in saved["images"]] == [1, 2]
