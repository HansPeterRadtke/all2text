from __future__ import annotations

import bz2
import gzip
import json
import lzma
import tarfile
import zipfile
from pathlib import Path
from typing import Any

from all2text.models import Classification, ConversionContext, ConversionResult
from all2text.utils import file_size


class ArchiveBackend:
    name = "archive_listing_backend"

    def can_handle(self, classification: Classification, entry_type: str) -> bool:
        return entry_type == "file" and classification.rough_category in {"archive", "compressed"}

    def convert(
        self,
        path: Path,
        rel_path: Path,
        classification: Classification,
        metadata: dict[str, object],
        ctx: ConversionContext,
    ) -> ConversionResult:
        limitation = "Archive members are listed safely; nested extraction is not enabled by default."
        lines = [
            f"Format: {classification.concrete_format}",
            "Conversion: archive/container metadata and safe listing only.",
            f"Limitation: {limitation}",
            "",
        ]
        methods = ["safe_archive_listing"]
        fmt = classification.concrete_format.casefold()
        suffix = path.suffix.casefold()
        if fmt in {"zip", "kmz"} or suffix in {".zip", ".kmz"}:
            listing, listing_meta = zip_listing(path, ctx)
            lines.extend(listing)
        elif fmt.startswith("tar") or _is_tar(path):
            listing, listing_meta = tar_listing(path, ctx)
            lines.extend(listing)
        elif fmt == "gzip" or suffix == ".gz":
            listing_meta = gzip_summary(path)
            lines.extend(["GZIP stream:", *[f"- {key}: {value}" for key, value in listing_meta.items()]])
            methods.append("gzip_header_summary")
        elif fmt == "bzip2" or suffix == ".bz2":
            listing_meta = compressed_stream_summary(path, opener=bz2.open, label="bzip2")
            lines.extend(["BZIP2 stream:", *[f"- {key}: {value}" for key, value in listing_meta.items()]])
            methods.append("bzip2_stream_summary")
        elif fmt == "xz" or suffix == ".xz":
            listing_meta = compressed_stream_summary(path, opener=lzma.open, label="xz")
            lines.extend(["XZ stream:", *[f"- {key}: {value}" for key, value in listing_meta.items()]])
            methods.append("xz_stream_summary")
        else:
            listing_meta = {}
            lines.append("Archive listing: unsupported archive listing backend for this format.")
        return ConversionResult(
            text="\n".join(lines).rstrip() + "\n",
            converter_used=self.name,
            extraction_methods_used=methods,
            metadata=listing_meta,
            limitations=[limitation],
        )


def zip_listing(path: Path, ctx: ConversionContext) -> tuple[list[str], dict[str, Any]]:
    lines = ["ZIP members:"]
    metadata: dict[str, Any] = {}
    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            metadata["member_count"] = len(infos)
            lines.append(f"- member_count: {len(infos)}")
            if len(infos) > ctx.options.max_archive_members:
                lines.append(f"- listing_truncated_after: {ctx.options.max_archive_members}")
                metadata["listing_truncated_after"] = ctx.options.max_archive_members
            for info in infos[: ctx.options.max_archive_members]:
                item = {
                    "name": info.filename,
                    "size": info.file_size,
                    "compressed_size": info.compress_size,
                    "is_dir": info.is_dir(),
                    **archive_member_safety(info.filename),
                }
                lines.append("- " + json.dumps(item, ensure_ascii=False))
    except Exception as exc:
        metadata["error"] = str(exc)
        lines.append(f"- zip_listing_error: {exc}")
    return lines, metadata


def tar_listing(path: Path, ctx: ConversionContext) -> tuple[list[str], dict[str, Any]]:
    lines = ["TAR members:"]
    metadata: dict[str, Any] = {}
    try:
        with tarfile.open(path) as archive:
            members = archive.getmembers()
            metadata["member_count"] = len(members)
            lines.append(f"- member_count: {len(members)}")
            if len(members) > ctx.options.max_archive_members:
                lines.append(f"- listing_truncated_after: {ctx.options.max_archive_members}")
                metadata["listing_truncated_after"] = ctx.options.max_archive_members
            for member in members[: ctx.options.max_archive_members]:
                mtype = member.type.decode("ascii", errors="replace") if isinstance(member.type, bytes) else str(member.type)
                item = {
                    "name": member.name,
                    "size": member.size,
                    "type": mtype,
                    **archive_member_safety(member.name),
                }
                lines.append("- " + json.dumps(item, ensure_ascii=False))
    except Exception as exc:
        metadata["error"] = str(exc)
        lines.append(f"- tar_listing_error: {exc}")
    return lines, metadata


def gzip_summary(path: Path) -> dict[str, Any]:
    result: dict[str, Any] = {"compressed_size": file_size(path), "nested_decompression": "not_enabled"}
    try:
        with gzip.open(path, "rb") as handle:
            result["first_uncompressed_bytes_hex"] = handle.read(64).hex()
    except Exception as exc:
        result["peek_error"] = str(exc)
    return result


def compressed_stream_summary(path: Path, *, opener: Any, label: str) -> dict[str, Any]:
    result: dict[str, Any] = {
        "compressed_size": file_size(path),
        "stream_format": label,
        "nested_decompression": "metadata_peek_only",
    }
    try:
        with opener(path, "rb") as handle:
            result["first_uncompressed_bytes_hex"] = handle.read(64).hex()
    except Exception as exc:
        result["peek_error"] = str(exc)
    return result


def archive_member_safety(name: str) -> dict[str, Any]:
    warnings: list[str] = []
    pure = Path(name)
    if pure.is_absolute():
        warnings.append("absolute_path")
    if ".." in pure.parts:
        warnings.append("parent_directory_reference")
    return {"safe_to_extract": not warnings, "safety_warnings": warnings}


def _is_tar(path: Path) -> bool:
    try:
        return tarfile.is_tarfile(path)
    except Exception:
        return False
