import pytest

from xiaoe_downloader.config import load_app_config
from xiaoe_downloader.video.downloader import VideoDownloader
from xiaoe_downloader.video.extractor import build_extracted_item


def test_video_url_templates_are_empty_by_default(tmp_path):
    config = load_app_config(tmp_path)

    assert config.extract.video_url_template == ""
    assert config.download.fallback_video_url_template == ""


def test_extracted_item_prefers_real_page_url_over_template():
    item = build_extracted_item(
        {
            "id": "v_1",
            "name": "第一课",
            "jump_url": "/p/course/video/v_1",
        },
        index=1,
        course_url="https://app.example.com/p/course/ecourse/course_1",
        video_url_template="https://legacy.example.com/video/{resource_id}",
    )

    assert item["video_url"] == "https://app.example.com/p/course/video/v_1"


def test_extracted_item_omits_video_url_when_no_real_url_or_template():
    item = build_extracted_item(
        {"id": "v_1", "name": "第一课"},
        index=1,
        course_url="https://app.example.com/p/course/ecourse/course_1",
        video_url_template="",
    )

    assert item == {"id": "v_1", "name": "第一课"}


def test_extracted_item_allows_explicit_legacy_template_override():
    item = build_extracted_item(
        {"id": "v_1", "name": "第一课"},
        index=1,
        course_url="https://app.example.com/p/course/ecourse/course_1",
        video_url_template="https://legacy.example.com/video/{resource_id}?n={index}",
    )

    assert item["video_url"] == "https://legacy.example.com/video/v_1?n=1"


def test_downloader_requires_video_url_when_no_fallback_template():
    downloader = VideoDownloader(
        [{"id": "v_1", "name": "第一课"}],
        fallback_video_url_template="",
    )

    with pytest.raises(ValueError, match="Missing video_url.*fallback_video_url_template"):
        downloader._resolve_video_url({"id": "v_1", "name": "第一课"})


def test_downloader_allows_explicit_fallback_template_override():
    downloader = VideoDownloader(
        [{"id": "v_1", "name": "第一课"}],
        fallback_video_url_template="https://legacy.example.com/video/{resource_id}",
    )

    assert downloader._resolve_video_url({"id": "v_1", "name": "第一课"}) == (
        "https://legacy.example.com/video/v_1"
    )
