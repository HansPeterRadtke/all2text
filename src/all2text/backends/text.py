from __future__ import annotations

import csv
import json
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

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
    if fmt in {"YAML", "YML"}:
        return yaml_metadata(text)
    if fmt == "XML":
        return xml_metadata(text)
    if fmt == "HTML":
        return html_metadata(text)
    if fmt == "RTF":
        return rtf_metadata(text)
    if fmt == "IPYNB":
        try:
            data = json.loads(text)
            cells = data.get("cells", []) if isinstance(data, dict) else []
        except Exception as exc:
            return {"parse_status": "notebook_parse_failed", "error": str(exc)}
        return {"parse_status": "ok", "cell_count": len(cells), "nbformat": data.get("nbformat")}
    return {}


def yaml_metadata(text: str) -> dict[str, Any]:
    keys: list[str] = []
    sequence_items = 0
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("- "):
            sequence_items += 1
            continue
        match = re.match(r"^([A-Za-z0-9_.-]+)\s*:", stripped)
        if match and len(keys) < 50:
            keys.append(match.group(1))
    return {
        "parse_status": "lightweight",
        "top_level_key_candidates": keys,
        "sequence_item_line_count": sequence_items,
    }


def xml_metadata(text: str) -> dict[str, Any]:
    try:
        root = ElementTree.fromstring(text)
    except Exception as exc:
        return {"parse_status": "xml_parse_failed", "error": str(exc)}
    return {
        "parse_status": "ok",
        "root_tag": root.tag,
        "root_attribute_count": len(root.attrib),
        "direct_child_count": len(list(root)),
    }


class _HTMLMetadataParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tag_counts: dict[str, int] = {}
        self._in_title = False
        self._title_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tag_counts[tag] = self.tag_counts.get(tag, 0) + 1
        if tag.casefold() == "title":
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self._title_parts.append(data)

    @property
    def title(self) -> str | None:
        title = "".join(self._title_parts).strip()
        return title or None


def html_metadata(text: str) -> dict[str, Any]:
    parser = _HTMLMetadataParser()
    try:
        parser.feed(text)
    except Exception as exc:
        return {"parse_status": "html_parse_failed", "error": str(exc)}
    return {
        "parse_status": "lightweight",
        "title": parser.title,
        "tag_counts": dict(sorted(parser.tag_counts.items())[:50]),
    }


def rtf_metadata(text: str) -> dict[str, Any]:
    control_words = re.findall(r"\\([A-Za-z]+)-?\d* ?", text)
    destinations = [word for word in control_words if word in {"fonttbl", "colortbl", "stylesheet", "info"}]
    return {
        "parse_status": "lightweight",
        "control_word_count": len(control_words),
        "unique_control_words": sorted(set(control_words))[:50],
        "known_destination_controls": sorted(set(destinations)),
        "group_open_count": text.count("{"),
        "group_close_count": text.count("}"),
    }
