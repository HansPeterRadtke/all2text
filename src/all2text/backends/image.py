from __future__ import annotations

import re
import struct
from pathlib import Path
from typing import Any

from all2text.backends.binary import binary_summary_text
from all2text.backends.text import decode_text_bytes
from all2text.models import Classification, ConversionContext, ConversionResult
from all2text.utils import read_header


class ImagePlaceholderBackend:
    name = "image_placeholder_backend"

    def can_handle(self, classification: Classification, entry_type: str) -> bool:
        return entry_type == "file" and classification.rough_category == "image"

    def convert(
        self,
        path: Path,
        rel_path: Path,
        classification: Classification,
        metadata: dict[str, object],
        ctx: ConversionContext,
    ) -> ConversionResult:
        limitation = (
            "Core all2text records image metadata only. OCR, VLM captioning, layout analysis, "
            "and chart understanding require optional backends."
        )
        image_metadata = image_metadata_light(path, classification, ctx)
        extra = [f"- limitation: {limitation}"]
        extra.extend(
            [
                "- ocr_status: not_yet_run_no_ocr_backend_configured",
                "- vlm_status: not_yet_run_no_vision_language_backend_configured",
                "- chart_analysis_status: not_yet_run_no_chart_backend_configured",
                "- document_image_analysis_status: not_yet_run_no_document_intelligence_backend_configured",
            ]
        )
        if image_metadata:
            extra.append("- image_metadata: " + repr(image_metadata))
        text = binary_summary_text(path, classification, ctx, heading="Image safe summary", extra_lines=extra)
        methods = ["image_magic_metadata", "image_placeholder_summary"]
        if classification.concrete_format.upper() == "SVG" and bool(metadata.get("looks_text")):
            raw = path.read_bytes()
            svg_text, decode_meta, warnings = decode_text_bytes(raw)
            text += "\nSVG textual markup preserved below:\n" + svg_text
            return ConversionResult(
                text=text if text.endswith("\n") else text + "\n",
                converter_used=self.name,
                extraction_methods_used=methods + ["svg_text_preservation"],
                warnings=warnings,
                metadata={
                    "image": image_metadata,
                    "svg_decode": decode_meta,
                    "analysis_hooks": placeholder_analysis_hooks(),
                },
                limitations=[limitation],
            )
        return ConversionResult(
            text=text,
            converter_used=self.name,
            extraction_methods_used=methods,
            metadata={"image": image_metadata, "analysis_hooks": placeholder_analysis_hooks()},
            limitations=[limitation],
        )


def image_metadata_light(path: Path, classification: Classification, ctx: ConversionContext) -> dict[str, Any]:
    header = read_header(path, max(ctx.options.max_header_bytes, 128))
    fmt = classification.concrete_format.upper()
    try:
        if fmt == "PNG" and len(header) >= 24:
            width, height = struct.unpack(">II", header[16:24])
            return {"format": "PNG", "width": width, "height": height}
        if fmt == "GIF" and len(header) >= 10:
            width, height = struct.unpack("<HH", header[6:10])
            return {"format": "GIF", "width": width, "height": height}
        if fmt == "BMP" and len(header) >= 26:
            width, height = struct.unpack("<II", header[18:26])
            return {"format": "BMP", "width": width, "height": height}
        if fmt == "JPEG":
            dims = jpeg_dimensions(path)
            return {"format": "JPEG", **dims} if dims else {"format": "JPEG"}
        if fmt == "SVG":
            text = header.decode("utf-8", errors="replace")
            return svg_dimensions(text)
    except Exception as exc:
        return {"metadata_error": str(exc)}
    return {}


def placeholder_analysis_hooks() -> dict[str, Any]:
    return {
        "ocr": {"configured": False, "attempted": False},
        "vlm": {"configured": False, "attempted": False},
        "chart_analysis": {"configured": False, "attempted": False},
        "document_intelligence": {"configured": False, "attempted": False},
    }


def jpeg_dimensions(path: Path) -> dict[str, int] | None:
    try:
        data = path.read_bytes()[:1024 * 1024]
    except Exception:
        return None
    index = 2
    while index + 9 < len(data):
        if data[index] != 0xFF:
            index += 1
            continue
        marker = data[index + 1]
        index += 2
        if marker in {0xD8, 0xD9, 0x01} or 0xD0 <= marker <= 0xD7:
            continue
        if index + 2 > len(data):
            return None
        length = int.from_bytes(data[index : index + 2], "big")
        if marker in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}:
            if index + 7 > len(data):
                return None
            height = int.from_bytes(data[index + 3 : index + 5], "big")
            width = int.from_bytes(data[index + 5 : index + 7], "big")
            return {"width": width, "height": height}
        index += length
    return None


def svg_dimensions(text: str) -> dict[str, Any]:
    result: dict[str, Any] = {"format": "SVG"}
    for attr in ("width", "height", "viewBox"):
        match = re.search(rf"\b{attr}\s*=\s*['\"]([^'\"]+)['\"]", text[:4096], flags=re.IGNORECASE)
        if match:
            result[attr] = match.group(1)
    return result
