import pytest

from xiaoe_downloader.config import ConfigError, load_app_config


def test_load_app_config_uses_builtin_defaults_when_file_is_missing(tmp_path):
    config = load_app_config(tmp_path)

    assert config.browser.cdp_url == "http://localhost:9222"
    assert config.extract.output_json == "items.json"
    assert config.download.output_dir == "./videos"
    assert config.slides.output_dir == "./out/slides"
    assert config.slides.input_type == "auto"
    assert config.slides.resource_concurrency == 6
    assert config.slides.pdf.enabled is False


def test_load_app_config_overrides_nested_toml_values(tmp_path):
    (tmp_path / "config.toml").write_text(
        """
        [browser]
        cdp_url = "http://127.0.0.1:9333"
        default_timeout_ms = 25000
        viewport_width = 430
        viewport_height = 932

        [extract]
        course_url = "https://example.com/course"
        password = "secret"
        max_scrolls = 42

        [slides]
        output_dir = "./slides"
        input_type = "video"
        resource_concurrency = 3

        [slides.resource_filter]
        min_width = 1200
        exclude_url_tokens = ["avatar", "icon"]

        [slides.pdf]
        enabled = true
        """,
        encoding="utf-8",
    )

    config = load_app_config(tmp_path)

    assert config.browser.cdp_url == "http://127.0.0.1:9333"
    assert config.browser.default_timeout_ms == 25000
    assert config.browser.viewport_width == 430
    assert config.browser.viewport_height == 932
    assert config.extract.course_url == "https://example.com/course"
    assert config.extract.password == "secret"
    assert config.extract.max_scrolls == 42
    assert config.slides.output_dir == "./slides"
    assert config.slides.input_type == "video"
    assert config.slides.resource_concurrency == 3
    assert config.slides.resource_filter.min_width == 1200
    assert config.slides.resource_filter.exclude_url_tokens == ("avatar", "icon")
    assert config.slides.pdf.enabled is True


def test_load_app_config_ignores_old_xiaoe_downloader_toml(tmp_path):
    old_config_name = "xiaoe" + "-downloader.toml"
    (tmp_path / old_config_name).write_text(
        """
        [download]
        output_dir = "./legacy-videos"
        """,
        encoding="utf-8",
    )

    config = load_app_config(tmp_path)

    assert config.download.output_dir == "./videos"


def test_load_app_config_rejects_unknown_keys_with_path(tmp_path):
    (tmp_path / "config.toml").write_text(
        """
        [browser]
        cdp_url = "http://127.0.0.1:9333"
        surprise = true
        """,
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="browser.surprise"):
        load_app_config(tmp_path)


def test_load_app_config_rejects_unknown_sections_with_path(tmp_path):
    (tmp_path / "config.toml").write_text(
        """
        [unknown]
        enabled = true
        """,
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="unknown"):
        load_app_config(tmp_path)


def test_load_app_config_accepts_int_for_float_values(tmp_path):
    (tmp_path / "config.toml").write_text(
        """
        [slides.download]
        retry_backoff_seconds = 1
        """,
        encoding="utf-8",
    )

    config = load_app_config(tmp_path)

    assert config.slides.download.retry_backoff_seconds == 1.0
