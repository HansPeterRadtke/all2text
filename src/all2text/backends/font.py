from __future__ import annotations

from pathlib import Path

from all2text.backends.binary import binary_summary_text
from all2text.models import Classification, ConversionContext, ConversionResult


class FontPlaceholderBackend:
    name = "font_placeholder_backend"

    def can_handle(self, classification: Classification, entry_type: str) -> bool:
        return entry_type == "file" and classification.rough_category == "font"

    def convert(
        self,
        path: Path,
        rel_path: Path,
        classification: Classification,
        metadata: dict[str, object],
        ctx: ConversionContext,
    ) -> ConversionResult:
        limitation = "Font conversion is metadata-only in the core package; glyph tables are not extracted."
        return ConversionResult(
            text=binary_summary_text(
                path,
                classification,
                ctx,
                heading="Font safe summary",
                extra_lines=[f"- limitation: {limitation}"],
            ),
            converter_used=self.name,
            extraction_methods_used=["font_placeholder_summary"],
            limitations=[limitation],
        )

