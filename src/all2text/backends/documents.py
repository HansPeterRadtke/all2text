from __future__ import annotations

import re
from pathlib import Path

from all2text.backends.binary import binary_summary_text
from all2text.models import Classification, ConversionContext, ConversionResult


class DocumentPlaceholderBackend:
    name = "document_placeholder_backend"

    CATEGORIES = {"document", "spreadsheet", "presentation"}

    def can_handle(self, classification: Classification, entry_type: str) -> bool:
        return entry_type == "file" and classification.rough_category in self.CATEGORIES

    def convert(
        self,
        path: Path,
        rel_path: Path,
        classification: Classification,
        metadata: dict[str, object],
        ctx: ConversionContext,
    ) -> ConversionResult:
        limitation = (
            "Core all2text does not claim deep semantic extraction for office/PDF formats. "
            "Install and register optional MarkItDown, pypdf, python-docx, openpyxl, python-pptx, "
            "OCR, or document-intelligence backends for native extraction."
        )
        doc_meta = document_light_metadata(path, classification)
        extra = [f"- limitation: {limitation}"]
        if doc_meta:
            extra.append("- document_metadata: " + repr(doc_meta))
        return ConversionResult(
            text=binary_summary_text(path, classification, ctx, heading="Document safe summary", extra_lines=extra),
            converter_used=self.name,
            extraction_methods_used=["document_placeholder_summary"],
            metadata={"document": doc_meta},
            limitations=[limitation],
        )


def document_light_metadata(path: Path, classification: Classification) -> dict[str, object]:
    fmt = classification.concrete_format.upper()
    result: dict[str, object] = {"format": classification.concrete_format}
    if fmt == "PDF":
        try:
            raw = path.read_bytes()
            result["pdf_header"] = raw[:16].decode("ascii", errors="replace")
            result["rough_page_marker_count"] = len(re.findall(rb"/Type\s*/Page\b", raw))
            result["eof_marker_count"] = raw.count(b"%%EOF")
        except Exception as exc:
            result["metadata_error"] = str(exc)
    return result

