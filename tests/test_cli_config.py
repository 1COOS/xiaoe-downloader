import json
import subprocess
import sys

from xiaoe_downloader import cli


def test_all_command_reads_url_and_outputs_from_default_config(tmp_path, monkeypatch):
    (tmp_path / "config.toml").write_text(
        """
        [browser]
        cdp_url = "http://127.0.0.1:9333"

        [extract]
        course_url = "https://config.example/course"
        password = "config-password"

        [download]
        output_dir = "./configured-videos"
        """,
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    calls = {}

    class FakeExtractor:
        def __init__(self, course_url, *, password, cdp_url, **kwargs):
            calls["extractor"] = {
                "course_url": course_url,
                "password": password,
                "cdp_url": cdp_url,
                "kwargs": kwargs,
            }

        async def extract(self):
            return [{"id": "v_1", "name": "课程一"}]

    class FakeDownloader:
        def __init__(self, items, output_dir, *, cdp_url, **kwargs):
            calls["downloader"] = {
                "items": items,
                "output_dir": output_dir,
                "cdp_url": cdp_url,
                "kwargs": kwargs,
            }

        async def download_all(self):
            return {"success": 1, "failed": 0, "skipped": 0}

    monkeypatch.setattr(cli, "CourseExtractor", FakeExtractor)
    monkeypatch.setattr(cli, "VideoDownloader", FakeDownloader)

    cli.main(["all"])

    assert calls["extractor"]["course_url"] == "https://config.example/course"
    assert calls["extractor"]["password"] == "config-password"
    assert calls["extractor"]["cdp_url"] == "http://127.0.0.1:9333"
    assert calls["downloader"]["output_dir"] == "./configured-videos"
    assert calls["downloader"]["cdp_url"] == "http://127.0.0.1:9333"


def test_all_command_cli_arguments_override_default_config(tmp_path, monkeypatch):
    (tmp_path / "config.toml").write_text(
        """
        [browser]
        cdp_url = "http://config-cdp"

        [extract]
        course_url = "https://config.example/course"
        password = "config-password"

        [download]
        output_dir = "./configured-videos"
        """,
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    calls = {}

    class FakeExtractor:
        def __init__(self, course_url, *, password, cdp_url, **kwargs):
            calls["extractor"] = {
                "course_url": course_url,
                "password": password,
                "cdp_url": cdp_url,
            }

        async def extract(self):
            return []

    class FakeDownloader:
        def __init__(self, items, output_dir, *, cdp_url, **kwargs):
            calls["downloader"] = {"output_dir": output_dir, "cdp_url": cdp_url}

        async def download_all(self):
            return {}

    monkeypatch.setattr(cli, "CourseExtractor", FakeExtractor)
    monkeypatch.setattr(cli, "VideoDownloader", FakeDownloader)

    cli.main(
        [
            "all",
            "https://cli.example/course",
            "--password",
            "cli-password",
            "--cdp",
            "http://cli-cdp",
            "--out",
            "./cli-videos",
        ]
    )

    assert calls["extractor"] == {
        "course_url": "https://cli.example/course",
        "password": "cli-password",
        "cdp_url": "http://cli-cdp",
    }
    assert calls["downloader"] == {
        "output_dir": "./cli-videos",
        "cdp_url": "http://cli-cdp",
    }


def test_download_command_uses_configured_items_json_when_argument_is_missing(
    tmp_path,
    monkeypatch,
):
    (tmp_path / "items-from-config.json").write_text(
        json.dumps([{"id": "v_1", "name": "课程一"}], ensure_ascii=False),
        encoding="utf-8",
    )
    (tmp_path / "config.toml").write_text(
        """
        [browser]
        cdp_url = "http://127.0.0.1:9333"

        [download]
        items_json = "items-from-config.json"
        output_dir = "./configured-videos"
        """,
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    calls = {}

    class FakeDownloader:
        def __init__(self, items, output_dir, *, cdp_url, **kwargs):
            calls["items"] = items
            calls["output_dir"] = output_dir
            calls["cdp_url"] = cdp_url

        async def download_all(self):
            return {}

    monkeypatch.setattr(cli, "VideoDownloader", FakeDownloader)

    cli.main(["download"])

    assert calls["items"] == [{"id": "v_1", "name": "课程一"}]
    assert calls["output_dir"] == "./configured-videos"
    assert calls["cdp_url"] == "http://127.0.0.1:9333"


def test_all_command_without_url_in_cli_or_config_exits_with_clear_error(tmp_path):
    result = subprocess.run(
        [sys.executable, "-m", "xiaoe_downloader", "all"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == 2
    assert "course URL is required" in result.stderr
    assert "config.toml" in result.stderr
