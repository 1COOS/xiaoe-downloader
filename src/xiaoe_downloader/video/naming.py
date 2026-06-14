"""Filesystem-safe naming helpers for downloaded videos."""
from __future__ import annotations

import re


def sanitize_filename(name: str) -> str:
    name = re.sub(r'[\\/:*?"<>|]', "-", name)
    return re.sub(r"\s+", " ", name).strip()
