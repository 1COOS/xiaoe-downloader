"""Filesystem-safe naming helpers."""
from __future__ import annotations

import re

BAD_NAME_CHARS = re.compile(r'[\\/:*?"<>|]+')


def sanitize_name(name: str) -> str:
    """Return a filesystem-safe name while preserving readable titles."""
    cleaned = BAD_NAME_CHARS.sub("-", name).strip()
    cleaned = re.sub(r"\s+", " ", cleaned).rstrip(". ")
    return cleaned[:180] or "untitled"


def make_unique_name(title: str, used: dict[str, int]) -> str:
    """Return a sanitized title, appending ``-2`` etc. for duplicates."""
    base = sanitize_name(title)
    used[base] = used.get(base, 0) + 1
    return base if used[base] == 1 else f"{base}-{used[base]}"
