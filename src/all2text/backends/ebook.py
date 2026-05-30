from __future__ import annotations

import json
import zipfile
from pathlib import Path

from all2text.backends.archive import zip_listing
from all2text.backends.binary import binary_summary_text
from all2text.models import Classification, ConversionContext, ConversionResult


class EbookPlaceholderBackend:
    name = "ebook_placeholder_backend"

    def can_handle(self, classification: Classification, entry_type: str) -> bool:
        return entry_type == "file" and classification.rough_category == "ebook"

    def convert(
        self,
        path: Path,
        rel_path: Path,
        classification: Classification,
        metadata: dict[str, object],
        ctx: ConversionContext,
    ) -> ConversionResult:
        limitation = (
            "E-book conversion is package/metadata-only in the core package. Chapter text extraction "
            "requires an EPUB/MOBI/AZW backend."
        )
        if classification.concrete_format.upper() == "EPUB":
            listing, listing_meta = zip_listing(path, ctx)
            epub_meta = epub_metadata(path)
            lines = [
                f"Format: {classification.concrete_format}",
                "Conversion: EPUB package listing and metadata only.",
                f"Limitation: {limitation}",
                "",
                "EPUB metadata:",
                json.dumps(epub_meta, indent=2, ensure_ascii=False),
                "",
                *listing,
            ]
            return ConversionResult(
                text="\n".join(lines).rstrip() + "\n",
                converter_used=self.name,
                extraction_methods_used=["epub_zip_listing", "epub_container_probe"],
                metadata={"ebook": epub_meta, "archive": listing_meta},
                limitations=[limitation],
            )
        return ConversionResult(
            text=binary_summary_text(
                path,
                classification,
                ctx,
                heading="E-book safe summary",
                extra_lines=[f"- limitation: {limitation}"],
            ),
            converter_used=self.name,
            extraction_methods_used=["ebook_placeholder_summary"],
            limitations=[limitation],
        )


def epub_metadata(path: Path) -> dict[str, object]:
    result: dict[str, object] = {}
    try:
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            result["member_count"] = len(names)
            result["has_mimetype"] = "mimetype" in names
            container_name = "META-INF/container.xml"
            result["has_container_xml"] = container_name in names
            if container_name in names:
                result["container_xml_preview"] = archive.read(container_name)[:2000].decode("utf-8", errors="replace")
    except Exception as exc:
        result["metadata_error"] = str(exc)
    return result

