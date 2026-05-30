from __future__ import annotations

from pathlib import Path

from all2text.models import Classification, ConversionContext, ConversionResult
from all2text.utils import file_size, printable_strings_sample, read_header, safe_ascii


def binary_summary_text(
    path: Path,
    classification: Classification,
    ctx: ConversionContext,
    *,
    heading: str = "Binary summary",
    extra_lines: list[str] | None = None,
) -> str:
    header = read_header(path, ctx.options.max_header_bytes)
    lines = [
        f"Format: {classification.concrete_format}",
        f"Category: {classification.rough_category}",
        "Conversion: safe metadata, byte signature, and printable string samples only.",
        "",
        f"{heading}:",
        f"- size_bytes: {file_size(path)}",
        f"- header_hex: {header[:64].hex()}",
        f"- header_ascii: {safe_ascii(header[:64])}",
    ]
    if extra_lines:
        lines.extend(extra_lines)
    strings = printable_strings_sample(path, ctx.options.max_binary_sample_bytes)
    lines.extend(["", "Printable strings sample:"])
    lines.extend([f"- {item}" for item in strings] if strings else ["- none"])
    return "\n".join(lines).rstrip() + "\n"


class BinaryFallbackBackend:
    name = "binary_fallback"

    def can_handle(self, classification: Classification, entry_type: str) -> bool:
        return entry_type == "file"

    def convert(
        self,
        path: Path,
        rel_path: Path,
        classification: Classification,
        metadata: dict[str, object],
        ctx: ConversionContext,
    ) -> ConversionResult:
        limitation = "No specialized backend is registered for this file type; no deep extraction was attempted."
        return ConversionResult(
            text=binary_summary_text(path, classification, ctx, extra_lines=[f"- limitation: {limitation}"]),
            converter_used=self.name,
            extraction_methods_used=["binary_magic_and_strings_summary"],
            limitations=[limitation],
        )

