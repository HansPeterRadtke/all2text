from __future__ import annotations

from pathlib import Path

from all2text.backends.binary import binary_summary_text
from all2text.models import Classification, ConversionContext, ConversionResult


class ScientificPlaceholderBackend:
    name = "scientific_placeholder_backend"

    def can_handle(self, classification: Classification, entry_type: str) -> bool:
        return entry_type == "file" and classification.rough_category == "scientific_data"

    def convert(
        self,
        path: Path,
        rel_path: Path,
        classification: Classification,
        metadata: dict[str, object],
        ctx: ConversionContext,
    ) -> ConversionResult:
        limitation = (
            "Scientific data conversion is safe-summary only in the core package. Install a specialist "
            "backend for HDF5, NetCDF, FITS, Parquet, MATLAB, NumPy, or domain-specific arrays."
        )
        return ConversionResult(
            text=binary_summary_text(
                path,
                classification,
                ctx,
                heading="Scientific data safe summary",
                extra_lines=[f"- limitation: {limitation}"],
            ),
            converter_used=self.name,
            extraction_methods_used=["scientific_placeholder_summary"],
            limitations=[limitation],
        )

