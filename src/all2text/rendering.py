from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from all2text.models import Classification, ConversionResult, PlannedOutput, TreeEntry


def render_text_output(
    metadata: dict[str, Any],
    classification: Classification,
    result: ConversionResult,
    planned: PlannedOutput,
    entry: TreeEntry,
) -> str:
    conversion = {
        "converter_used": result.converter_used,
        "extraction_methods_used": result.extraction_methods_used,
        "converter_metadata": result.metadata,
        "planned_output": planned_output_dict(planned),
        "scan_warnings": entry.scan_warnings,
        "scan_errors": entry.scan_errors,
        "converter_warnings": result.warnings,
        "converter_errors": result.errors,
        "limitations": result.limitations,
    }
    return (
        "=== Metadata ===\n"
        + json.dumps(metadata, indent=2, ensure_ascii=False, default=str)
        + "\n\n=== Classification ===\n"
        + json.dumps(classification.to_dict(), indent=2, ensure_ascii=False, default=str)
        + "\n\n=== Conversion ===\n"
        + json.dumps(conversion, indent=2, ensure_ascii=False, default=str)
        + "\n\n=== Extracted Content ===\n"
        + result.text
    )


def planned_output_dict(planned: PlannedOutput) -> dict[str, Any]:
    data = asdict(planned)
    data["output_path"] = str(planned.output_path)
    return data


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", errors="surrogateescape", newline="") as handle:
        handle.write(text)

