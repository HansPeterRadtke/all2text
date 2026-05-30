from __future__ import annotations

import json
import mimetypes
import re
import tarfile
import zipfile
from pathlib import Path
from typing import Any

from all2text.models import Classification, LayerEvidence, RunOptions
from all2text.taxonomy import EXTENSION_HINTS, MIME_HINTS, SOURCE_CODE_EXTENSIONS, TEXTUAL_CATEGORIES
from all2text.utils import looks_like_text, read_header, stable_unique


def classify_path(
    path: Path,
    *,
    metadata: dict[str, Any] | None = None,
    entry_type: str = "file",
    options: RunOptions | None = None,
) -> Classification:
    options = options or RunOptions()
    metadata = metadata or {}
    extension_hint = extension_hint_for(path)
    mime_hint = mime_hint_for(path, metadata)
    content_signature = content_signature_for(path, entry_type=entry_type, options=options)

    layers = [extension_hint, mime_hint, content_signature]
    evidence: list[str] = []
    warnings: list[str] = []
    for layer in layers:
        evidence.extend(layer.evidence)
        warnings.extend(layer.warnings)

    chosen = _choose_layer(extension_hint, mime_hint, content_signature, metadata)
    rough = chosen.rough_category or ("text" if metadata.get("looks_text") else "unknown")
    fmt = chosen.concrete_format or ("TXT" if rough == "text" else "unknown")
    if chosen is content_signature and chosen.rough_category:
        evidence.append("layer2_content_signature_override")
    elif chosen is mime_hint and chosen.rough_category:
        evidence.append("layer2_mime_override")
    elif chosen is extension_hint and chosen.rough_category:
        evidence.append("layer1_extension_hint")
    else:
        evidence.append("generic_text_content" if rough == "text" else "no_known_signature_or_extension")

    content_profile = _content_profile(rough, fmt, metadata)
    is_textual = _is_textual(rough, fmt, content_signature, metadata)
    confidence = chosen.confidence if chosen.rough_category else ("low" if rough == "text" else "none")
    return Classification(
        extension_hint=extension_hint,
        mime_hint=mime_hint,
        content_signature=content_signature,
        rough_category=rough,
        concrete_format=fmt,
        content_profile=content_profile,
        confidence=confidence,
        evidence=stable_unique(evidence),
        warnings=stable_unique(warnings),
        is_textual=is_textual,
    )


def extension_hint_for(path: Path) -> LayerEvidence:
    suffixes = [suffix.casefold() for suffix in path.suffixes]
    compound = "".join(suffixes[-2:]) if len(suffixes) >= 2 else ""
    if compound in {".tar.gz", ".tar.bz2", ".tar.xz"}:
        return LayerEvidence(
            source="extension",
            rough_category="archive",
            concrete_format="TAR" + compound[4:].upper(),
            confidence="medium",
            details={"extension": compound},
            evidence=[f"compound_extension:{compound}"],
        )
    suffix = suffixes[-1] if suffixes else ""
    if suffix in SOURCE_CODE_EXTENSIONS:
        return LayerEvidence(
            source="extension",
            rough_category="source_code",
            concrete_format=suffix[1:].upper(),
            confidence="medium",
            details={"extension": suffix},
            evidence=[f"source_code_extension:{suffix}"],
        )
    if suffix not in EXTENSION_HINTS:
        return LayerEvidence(
            source="extension",
            confidence="none",
            details={"extension": suffix},
            evidence=[f"extension_unmapped:{suffix or '<none>'}"],
        )
    category, fmt = EXTENSION_HINTS[suffix]
    return LayerEvidence(
        source="extension",
        rough_category=category,
        concrete_format=fmt,
        confidence="medium",
        details={"extension": suffix},
        evidence=[f"extension_hint:{suffix}->{fmt}"],
    )


def mime_hint_for(path: Path, metadata: dict[str, Any]) -> LayerEvidence:
    candidates = [
        ("file", metadata.get("file_mime_type")),
        ("python", metadata.get("python_mimetype")),
    ]
    guessed, _ = mimetypes.guess_type(str(path))
    candidates.append(("python_guess", guessed))

    for source, value in candidates:
        mime = str(value or "").strip()
        if not mime:
            continue
        if mime.startswith("text/"):
            return LayerEvidence(
                source=source,
                rough_category="text",
                concrete_format="TXT",
                confidence="low" if mime == "text/plain" else "medium",
                details={"mime_type": mime},
                evidence=[f"{source}_mime:{mime}"],
            )
        for prefix, category in (("image/", "image"), ("audio/", "audio"), ("video/", "video")):
            if mime.startswith(prefix) and mime not in MIME_HINTS:
                return LayerEvidence(
                    source=source,
                    rough_category=category,
                    concrete_format=mime.split("/", 1)[1].upper(),
                    confidence="medium",
                    details={"mime_type": mime},
                    evidence=[f"{source}_mime:{mime}"],
                )
        if mime in MIME_HINTS:
            category, fmt = MIME_HINTS[mime]
            return LayerEvidence(
                source=source,
                rough_category=category,
                concrete_format=fmt,
                confidence="low" if mime == "application/octet-stream" else "medium",
                details={"mime_type": mime},
                evidence=[f"{source}_mime:{mime}->{fmt}"],
            )
    return LayerEvidence(source="mime", confidence="none", details={"mime_type": None})


def content_signature_for(path: Path, *, entry_type: str, options: RunOptions) -> LayerEvidence:
    if entry_type == "symlink":
        return _signature("filesystem", "unknown", "symlink", "strong", "filesystem_entry_is_symlink")
    if entry_type != "file":
        return _signature("filesystem", "unknown", entry_type, "strong", f"filesystem_entry_type:{entry_type}")
    header = read_header(path, options.max_header_bytes)
    if not header:
        return _signature("content", "text", "empty file", "strong", "empty_file")
    binary = _binary_signature(path, header, options)
    if binary is not None:
        return binary
    text = decode_for_classification(header)
    if text is not None:
        textual = _textual_signature(path, text)
        if textual is not None:
            return textual
        if looks_like_text(header):
            return _signature("content", "text", "TXT", "medium", "printable_text_signature")
    return LayerEvidence(source="content", confidence="none")


def decode_for_classification(raw: bytes) -> str | None:
    for encoding in ("utf-8", "utf-8-sig", "utf-16"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace") if looks_like_text(raw) else None


def _choose_layer(
    extension_hint: LayerEvidence,
    mime_hint: LayerEvidence,
    content_signature: LayerEvidence,
    metadata: dict[str, Any],
) -> LayerEvidence:
    if content_signature.rough_category and content_signature.confidence == "strong":
        return content_signature
    if mime_hint.rough_category and mime_hint.confidence in {"strong", "medium"}:
        return mime_hint
    if content_signature.rough_category:
        return content_signature
    if extension_hint.rough_category:
        return extension_hint
    if metadata.get("looks_text"):
        return LayerEvidence(
            source="generic",
            rough_category="text",
            concrete_format="TXT",
            confidence="low",
            evidence=["metadata_looks_text"],
        )
    return LayerEvidence(source="generic", rough_category="unknown", concrete_format="unknown")


def _is_textual(
    rough_category: str,
    concrete_format: str,
    content_signature: LayerEvidence,
    metadata: dict[str, Any],
) -> bool:
    if rough_category in TEXTUAL_CATEGORIES:
        return True
    if rough_category == "cad_or_technical" and metadata.get("looks_text"):
        return concrete_format.upper() in {"DXF", "STEP", "STP", "STL", "OBJ", "IGES"}
    if rough_category == "email" and concrete_format.upper() in {"EML", "MBOX"} and metadata.get("looks_text"):
        return False
    return bool(content_signature.rough_category == "text" and metadata.get("looks_text"))


def _content_profile(rough_category: str, concrete_format: str, metadata: dict[str, Any]) -> str:
    if rough_category in {"audio", "video"}:
        return "metadata_only"
    if rough_category in {"image", "document", "spreadsheet", "presentation"}:
        return "placeholder_or_optional_backend"
    if rough_category in {"archive", "compressed", "ebook", "disk_image_or_container"}:
        return "container_listing_or_placeholder"
    if metadata.get("looks_text"):
        return "text_decodable"
    return "binary_or_unknown"


def _binary_signature(path: Path, header: bytes, options: RunOptions) -> LayerEvidence | None:
    if header.startswith(b"%PDF-"):
        return _signature("content", "document", "PDF", "strong", "magic:%PDF")
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return _signature("content", "image", "PNG", "strong", "magic:PNG")
    if header.startswith(b"\xff\xd8\xff"):
        return _signature("content", "image", "JPEG", "strong", "magic:JPEG")
    if header.startswith((b"GIF87a", b"GIF89a")):
        return _signature("content", "image", "GIF", "strong", "magic:GIF")
    if header.startswith((b"II*\x00", b"MM\x00*")):
        return _signature("content", "image", "TIFF", "strong", "magic:TIFF")
    if header.startswith(b"BM"):
        return _signature("content", "image", "BMP", "strong", "magic:BMP")
    if header.startswith(b"RIFF") and header[8:12] == b"WEBP":
        return _signature("content", "image", "WebP", "strong", "magic:RIFF_WEBP")
    if header.startswith(b"RIFF") and header[8:12] == b"WAVE":
        return _signature("content", "audio", "WAV", "strong", "magic:RIFF_WAVE")
    if header.startswith(b"RIFF") and header[8:12] == b"AVI ":
        return _signature("content", "video", "AVI", "strong", "magic:RIFF_AVI")
    if header.startswith(b"fLaC"):
        return _signature("content", "audio", "FLAC", "strong", "magic:FLAC")
    if header.startswith(b"OggS"):
        return _signature("content", "audio", "OGG", "strong", "magic:OGG")
    if header.startswith(b"ID3") or (
        len(header) >= 2 and header[0] == 0xFF and (header[1] & 0xE0) == 0xE0
    ):
        return _signature("content", "audio", "MP3", "strong", "magic:MP3")
    if header.startswith(b"MThd"):
        return _signature("content", "audio", "MIDI", "strong", "magic:MIDI")
    if len(header) >= 12 and header[4:8] == b"ftyp":
        brand = header[8:12].decode("ascii", errors="replace").strip()
        fmt = "MOV" if brand == "qt" else "MP4"
        return _signature("content", "video", fmt, "strong", f"magic:ISO_BMFF:{brand}")
    if header.startswith(b"\x1a\x45\xdf\xa3"):
        return _signature("content", "video", "MKV/WebM", "strong", "magic:EBML")
    if header.startswith((b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")):
        return _zip_signature(path, options) or _signature("content", "archive", "ZIP", "strong", "magic:ZIP")
    if header.startswith(b"\x1f\x8b"):
        return _signature("content", "compressed", "GZIP", "strong", "magic:GZIP")
    if header.startswith(b"BZh"):
        return _signature("content", "compressed", "BZIP2", "strong", "magic:BZIP2")
    if header.startswith(b"\xfd7zXZ\x00"):
        return _signature("content", "compressed", "XZ", "strong", "magic:XZ")
    if header.startswith(b"7z\xbc\xaf\x27\x1c"):
        return _signature("content", "archive", "7Z", "strong", "magic:7Z")
    if header.startswith((b"Rar!\x1a\x07\x00", b"Rar!\x1a\x07\x01\x00")):
        return _signature("content", "archive", "RAR", "strong", "magic:RAR")
    if header.startswith(b"SQLite format 3\x00"):
        return _signature("content", "database", "SQLite", "strong", "magic:SQLite")
    if header.startswith(b"\x89HDF\r\n\x1a\n"):
        return _signature("content", "scientific_data", "HDF5", "strong", "magic:HDF5")
    if header.startswith((b"CDF\x01", b"CDF\x02")):
        return _signature("content", "scientific_data", "NetCDF", "strong", "magic:NetCDF")
    if header.startswith(b"PAR1"):
        return _signature("content", "scientific_data", "Parquet", "strong", "magic:Parquet")
    if header[:6] == b"SIMPLE":
        return _signature("content", "scientific_data", "FITS", "strong", "magic:FITS")
    if header.startswith(b"\x7fELF"):
        return _signature("content", "executable_or_binary", "ELF executable/shared object", "strong", "magic:ELF")
    if header.startswith(b"MZ"):
        return _signature("content", "executable_or_binary", "Windows executable", "strong", "magic:MZ")
    if header.startswith((b"\xfe\xed\xfa\xce", b"\xfe\xed\xfa\xcf", b"\xce\xfa\xed\xfe", b"\xcf\xfa\xed\xfe")):
        return _signature("content", "executable_or_binary", "Mach-O binary", "strong", "magic:MachO")
    try:
        if tarfile.is_tarfile(path):
            return _signature("content", "archive", "TAR", "strong", "tarfile_module_detected_tar")
    except Exception:
        pass
    return None


def _zip_signature(path: Path, options: RunOptions) -> LayerEvidence | None:
    try:
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()[: options.max_archive_members]
            lowered = {name.casefold() for name in names}
            if "word/document.xml" in lowered:
                return _signature("content", "document", "DOCX", "strong", "zip_contains:word/document.xml")
            if "xl/workbook.xml" in lowered:
                return _signature("content", "spreadsheet", "XLSX", "strong", "zip_contains:xl/workbook.xml")
            if "ppt/presentation.xml" in lowered:
                return _signature("content", "presentation", "PPTX", "strong", "zip_contains:ppt/presentation.xml")
            if "mimetype" in lowered:
                actual = next((name for name in names if name.casefold() == "mimetype"), "mimetype")
                data = archive.read(actual)[:128].decode("ascii", errors="replace").strip()
                if data == "application/epub+zip":
                    return _signature("content", "ebook", "EPUB", "strong", "zip_mimetype:epub")
                if data == "application/vnd.oasis.opendocument.text":
                    return _signature("content", "document", "ODT", "strong", "zip_mimetype:odt")
                if data == "application/vnd.oasis.opendocument.spreadsheet":
                    return _signature("content", "spreadsheet", "ODS", "strong", "zip_mimetype:ods")
                if data == "application/vnd.oasis.opendocument.presentation":
                    return _signature("content", "presentation", "ODP", "strong", "zip_mimetype:odp")
    except Exception as exc:
        return LayerEvidence(
            source="content",
            rough_category="archive",
            concrete_format="ZIP",
            confidence="strong",
            evidence=["magic:ZIP"],
            warnings=[f"zip_inspection_failed:{exc}"],
        )
    return None


def _textual_signature(path: Path, text: str) -> LayerEvidence | None:
    stripped = text.lstrip("\ufeff \t\r\n")
    lowered = stripped[:1024].casefold()
    if stripped.startswith("{") or stripped.startswith("["):
        parsed = _try_json_parse(path)
        if isinstance(parsed, dict) and "cells" in parsed and "nbformat" in parsed:
            return _signature("content", "notebook", "IPYNB", "strong", "json_keys:cells,nbformat")
        if parsed is not None:
            if path.suffix.casefold() == ".geojson" or _looks_geojson(parsed):
                return _signature("content", "geospatial", "GeoJSON", "strong", "json_geojson_signature")
            return _signature("content", "structured_text", "JSON", "strong", "json_parse_success")
    if lowered.startswith("<!doctype html") or lowered.startswith("<html") or "<html" in lowered[:256]:
        return _signature("content", "structured_text", "HTML", "strong", "html_signature")
    if lowered.startswith("<svg") or "<svg" in lowered[:512]:
        return _signature("content", "image", "SVG", "strong", "svg_xml_signature")
    if lowered.startswith("<?xml") or (stripped.startswith("<") and re.match(r"<[A-Za-z_][\w:.-]*(\s|>|/)", stripped)):
        if "<kml" in lowered[:512]:
            return _signature("content", "geospatial", "KML", "strong", "kml_xml_signature")
        return _signature("content", "structured_text", "XML", "medium", "xml_like_signature")
    if _looks_like_email(text):
        return _signature("content", "email", "EML", "medium", "rfc822_header_signature")
    if _looks_like_delimited(text, "\t"):
        return _signature("content", "structured_text", "TSV", "medium", "tabular_text_signature:tab")
    if _looks_like_delimited(text, ","):
        return _signature("content", "structured_text", "CSV", "medium", "tabular_text_signature:comma")
    if lowered.startswith("---\n") and ":" in stripped[:1024]:
        return _signature("content", "structured_text", "YAML", "medium", "yaml_document_marker")
    if stripped.startswith("#!") or path.suffix.casefold() in SOURCE_CODE_EXTENSIONS:
        fmt = path.suffix.casefold()[1:].upper() or "script"
        return _signature("content", "source_code", fmt, "medium", "source_text_signature")
    if path.suffix.casefold() in {".dxf", ".step", ".stp", ".stl", ".obj", ".iges", ".igs"}:
        category, fmt = EXTENSION_HINTS[path.suffix.casefold()]
        return _signature("content", category, fmt, "medium", "technical_text_extension_with_printable_content")
    return None


def _signature(source: str, category: str, fmt: str, confidence: str, evidence: str) -> LayerEvidence:
    return LayerEvidence(
        source=source,
        rough_category=category,
        concrete_format=fmt,
        confidence=confidence,
        evidence=[evidence],
    )


def _try_json_parse(path: Path) -> Any:
    try:
        if (path.stat().st_size or 0) > 128 * 1024 * 1024:
            return None
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return None


def _looks_geojson(parsed: Any) -> bool:
    return isinstance(parsed, dict) and parsed.get("type") in {
        "Feature",
        "FeatureCollection",
        "GeometryCollection",
        "Point",
        "LineString",
        "Polygon",
        "MultiPoint",
        "MultiLineString",
        "MultiPolygon",
    }


def _looks_like_email(text: str) -> bool:
    prefixes = ("From:", "To:", "Subject:", "Date:", "Message-ID:", "MIME-Version:")
    return sum(1 for prefix in prefixes if re.search(rf"(?im)^{re.escape(prefix)}", text[:2048])) >= 2


def _looks_like_delimited(text: str, delimiter: str) -> bool:
    lines = [line for line in text.splitlines()[:20] if line.strip()]
    if len(lines) < 2:
        return False
    counts = [line.count(delimiter) for line in lines]
    return max(counts, default=0) > 0 and len(set(counts[: min(5, len(counts))])) == 1

