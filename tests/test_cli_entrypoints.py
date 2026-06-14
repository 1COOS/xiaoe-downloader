import subprocess
import sys
from importlib.util import find_spec


def test_package_module_entrypoint_shows_help():
    result = subprocess.run(
        [sys.executable, "-m", "xiaoe_downloader", "--help"],
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == 0, result.stderr
    assert "xiaoe-downloader v" in result.stdout
    assert "{extract,download,all,slides,slides-pdf}" in result.stdout


def test_old_src_module_entrypoint_is_not_supported():
    result = subprocess.run(
        [sys.executable, "-m", "src", "--help"],
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode != 0


def test_console_script_shows_help():
    result = subprocess.run(
        ["xiaoe-downloader", "--help"],
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == 0, result.stderr
    assert "xiaoe-downloader v" in result.stdout
    assert "{extract,download,all,slides,slides-pdf}" in result.stdout


def test_slides_command_shows_help():
    result = subprocess.run(
        ["xiaoe-downloader", "slides", "--help"],
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == 0, result.stderr
    assert "COURSE_URL" in result.stdout
    assert "--profile" in result.stdout
    assert "--headed" in result.stdout
    assert "--skip-title" in result.stdout
    assert "--no-clear" in result.stdout
    assert "--pdf" in result.stdout
    assert "--no-pdf" in result.stdout


def test_slides_pdf_command_shows_help():
    result = subprocess.run(
        ["xiaoe-downloader", "slides-pdf", "--help"],
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == 0, result.stderr
    assert "SLIDES_ROOT" in result.stdout


def test_old_intro_command_is_not_supported():
    result = subprocess.run(
        ["xiaoe-downloader", "intro" + "-images", "--help"],
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode != 0


def test_new_package_import_paths_are_available():
    assert find_spec("xiaoe_downloader.video.extractor") is not None
    assert find_spec("xiaoe_downloader.video.downloader") is not None
    assert find_spec("xiaoe_downloader.slides.scraper") is not None


def test_old_flat_package_import_paths_are_not_available():
    assert find_spec("xiaoe_downloader.extractor") is None
    assert find_spec("xiaoe_downloader.downloader") is None
    assert find_spec("xiaoe_downloader." + "intro" + "_" + "images") is None
