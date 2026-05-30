from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

from all2text.models import RunOptions

PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
)


def make_options() -> RunOptions:
    return RunOptions(use_file_command=False, copy_source_stat=False)


def entry(manifest: dict[str, Any], relative_path: str) -> dict[str, Any]:
    for item in manifest["entries"]:
        if item.get("relative_path") == relative_path:
            return item
    raise AssertionError(f"missing manifest entry {relative_path}")


def extracted_text(path: Path) -> str:
    return path.read_text(encoding="utf-8").split("=== Extracted Content ===\n", 1)[1]
