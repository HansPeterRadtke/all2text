from __future__ import annotations

from pathlib import Path

from all2text.backends.binary import binary_summary_text
from all2text.models import Classification, ConversionContext, ConversionResult


class CadPlaceholderBackend:
    name = "cad_placeholder_backend"

    def can_handle(self, classification: Classification, entry_type: str) -> bool:
        return entry_type == "file" and classification.rough_category == "cad_or_technical"

    def convert(
        self,
        path: Path,
        rel_path: Path,
        classification: Classification,
        metadata: dict[str, object],
        ctx: ConversionContext,
    ) -> ConversionResult:
        limitation = (
            "CAD/technical model conversion is safe-summary only unless the file is plain text. "
            "Geometry, layers, units, and drawings require a specialist CAD backend."
        )
        return ConversionResult(
            text=binary_summary_text(
                path,
                classification,
                ctx,
                heading="CAD/technical safe summary",
                extra_lines=[f"- limitation: {limitation}"],
            ),
            converter_used=self.name,
            extraction_methods_used=["cad_placeholder_summary"],
            limitations=[limitation],
        )

