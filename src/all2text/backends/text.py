from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from all2text.models import Classification, ConversionContext, ConversionResult


class TextBackend:
    name = "text_exact_backend"

    def can_handle(self, classification: Classification, entry_type: str) -> bool:
        return entry_type == "file" and classification.is_textual

    def convert(
        self,
        path: Path,
        rel_path: Path,
        classification: Classification,
        metadata: dict[str, object],
        ctx: ConversionContext,
    ) -> ConversionResult:
        raw = path.read_bytes()
        text, decode_metadata, warnings = decode_text_bytes(raw)
        parsed_metadata = parsed_text_metadata(text, classification)
        result_metadata: dict[str, Any] = {
            **decode_metadata,
            "characters": len(text),
            "lines": len(text.splitlines()),
        }
        if parsed_metadata:
            result_metadata["parsed_structure"] = parsed_metadata
        return ConversionResult(
            text=text,
            converter_used=self.name,
            extraction_methods_used=["exact_text_decode_preserve_content"],
            warnings=warnings,
            metadata=result_metadata,
        )


def decode_text_bytes(raw: bytes) -> tuple[str, dict[str, Any], list[str]]:
    warnings: list[str] = []
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        try:
            return raw.decode("utf-16"), {"encoding": "utf-16", "byte_length": len(raw)}, warnings
        except UnicodeDecodeError as exc:
            warnings.append(f"utf16_decode_failed:{exc}")
    try:
        return raw.decode("utf-8"), {"encoding": "utf-8", "byte_length": len(raw)}, warnings
    except UnicodeDecodeError as exc:
        warnings.append(f"utf8_decode_failed_surrogateescape:{exc}")
        return (
            raw.decode("utf-8", errors="surrogateescape"),
            {"encoding": "utf-8", "errors": "surrogateescape", "byte_length": len(raw)},
            warnings,
        )


def parsed_text_metadata(text: str, classification: Classification) -> dict[str, Any]:
    fmt = classification.concrete_format.upper()
    if fmt == "JSON":
        try:
            data = json.loads(text)
        except Exception as exc:
            return {"parse_status": "json_parse_failed", "error": str(exc)}
        if isinstance(data, dict):
            return {
                "parse_status": "ok",
                "top_level_type": "object",
                "top_level_keys": list(data.keys())[:50],
            }
        if isinstance(data, list):
            return {"parse_status": "ok", "top_level_type": "array", "top_level_length": len(data)}
        return {"parse_status": "ok", "top_level_type": type(data).__name__}
    if fmt == "JSON LINES":
        lines = [line for line in text.splitlines() if line.strip()]
        parsed = 0
        for line in lines:
            try:
                json.loads(line)
                parsed += 1
            except Exception:
                break
        return {"parse_status": "ok" if parsed == len(lines) else "partial", "line_count": len(lines), "parsed_lines": parsed}
    if fmt in {"CSV", "TSV"}:
        delimiter = "\t" if fmt == "TSV" else ","
        try:
            rows = list(csv.reader(text.splitlines(), delimiter=delimiter))
        except Exception as exc:
            return {"parse_status": "delimited_parse_failed", "error": str(exc)}
        return {
            "parse_status": "ok",
            "row_count": len(rows),
            "max_column_count": max((len(row) for row in rows), default=0),
        }
    if fmt == "MARKDOWN":
        headings = [line for line in text.splitlines() if line.lstrip().startswith("#")]
        return {"parse_status": "lightweight", "heading_count": len(headings)}
    if fmt == "IPYNB":
        try:
            data = json.loads(text)
            cells = data.get("cells", []) if isinstance(data, dict) else []
        except Exception as exc:
            return {"parse_status": "notebook_parse_failed", "error": str(exc)}
        return {"parse_status": "ok", "cell_count": len(cells), "nbformat": data.get("nbformat")}
    return {}

