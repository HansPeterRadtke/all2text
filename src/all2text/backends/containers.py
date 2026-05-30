from __future__ import annotations

from pathlib import Path

from all2text.backends.binary import binary_summary_text
from all2text.models import Classification, ConversionContext, ConversionResult


class ContainerPlaceholderBackend:
    name = "container_placeholder_backend"

    def can_handle(self, classification: Classification, entry_type: str) -> bool:
        return entry_type == "file" and classification.rough_category == "disk_image_or_container"

    def convert(
        self,
        path: Path,
        rel_path: Path,
        classification: Classification,
        metadata: dict[str, object],
        ctx: ConversionContext,
    ) -> ConversionResult:
        limitation = (
            "Disk image/container conversion is safe-summary only. The core package does not mount, "
            "decompress, or traverse container filesystems."
        )
        return ConversionResult(
            text=binary_summary_text(
                path,
                classification,
                ctx,
                heading="Container safe summary",
                extra_lines=[f"- limitation: {limitation}"],
            ),
            converter_used=self.name,
            extraction_methods_used=["container_placeholder_summary"],
            limitations=[limitation],
        )

