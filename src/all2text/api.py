from __future__ import annotations

from pathlib import Path
from typing import Any

from all2text.config import All2TextConfig
from all2text.core import run as _run
from all2text.models import RunOptions
from all2text.registry import ConversionRegistry


def run(
    source_folder: str | Path,
    target_folder: str | Path,
    *,
    options: RunOptions | None = None,
    registry: ConversionRegistry | None = None,
    config: All2TextConfig | None = None,
) -> dict[str, Any]:
    """Convert a source folder tree into mirrored plain-text outputs."""

    return _run(source_folder, target_folder, options=options, registry=registry, config=config)
