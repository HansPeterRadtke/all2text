from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from all2text.jsonsafe import json_dumps, to_jsonable
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
        "llm_used": result.llm_used,
        "ocr_used": result.ocr_used,
        "vlm_used": result.vlm_used,
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
        + json_dumps(metadata, indent=2)
        + "\n\n=== Classification ===\n"
        + json_dumps(classification.to_dict(), indent=2)
        + "\n\n=== Conversion ===\n"
        + json_dumps(conversion, indent=2)
        + "\n\n=== Extracted Content ===\n"
        + result.text
    )


def planned_output_dict(planned: PlannedOutput) -> dict[str, Any]:
    data = asdict(planned)
    data["output_path"] = str(planned.output_path)
    return to_jsonable(data)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", errors="surrogateescape", newline="") as handle:
        handle.write(text)
