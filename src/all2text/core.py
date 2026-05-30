from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from all2text.backends.binary import BinaryFallbackBackend
from all2text.detection import classify_path
from all2text.metadata import collect_metadata, copy_supported_metadata
from all2text.models import Classification, ConversionContext, ConversionResult, RunOptions, TreeEntry
from all2text.planning import create_target_directories, reserve_output_files
from all2text.registry import ConversionRegistry, build_default_registry
from all2text.rendering import planned_output_dict, render_text_output, write_text
from all2text.reporting import build_summary, manifest_paths, render_report
from all2text.scanning import scan_source_tree
from all2text.utils import is_relative_to, os_info, rel_text, utc_now
from all2text.version import __version__


def run(
    source_folder: str | Path,
    target_folder: str | Path,
    *,
    options: RunOptions | None = None,
    registry: ConversionRegistry | None = None,
) -> dict[str, Any]:
    started = time.monotonic()
    options = options or RunOptions()
    source_root = Path(source_folder).expanduser()
    target_root = Path(target_folder).expanduser()
    if not source_root.exists():
        raise FileNotFoundError(f"source_folder does not exist: {source_root}")
    if not source_root.is_dir():
        raise NotADirectoryError(f"source_folder is not a directory: {source_root}")
    source_root = source_root.resolve(strict=True)
    target_root = target_root.resolve(strict=False)
    if options.reject_target_inside_source and is_relative_to(target_root, source_root):
        raise ValueError("target_folder must not be inside source_folder")

    entries = scan_source_tree(source_root)
    scan_finished_utc = utc_now()

    target_root.mkdir(parents=True, exist_ok=True)
    dir_entries = [entry for entry in entries if entry.entry_type == "directory"]
    text_entries = [entry for entry in entries if entry.produces_text]
    dir_map, directory_collisions = create_target_directories(target_root, dir_entries)
    planned, planning_warnings = reserve_output_files(target_root, text_entries, dir_map)
    ctx = ConversionContext(source_root=source_root, target_root=target_root, options=options)
    registry = registry or build_default_registry()

    records: list[dict[str, Any]] = []
    for entry in entries:
        if entry.entry_type == "directory":
            records.append(directory_record(entry, options))
            continue
        records.append(convert_entry(entry, planned[entry.relative_path], ctx, registry))

    manifest = {
        "schema": "all2text.conversion_manifest.v1",
        "all2text_version": __version__,
        "source_folder": str(source_root),
        "target_folder": str(target_root),
        "created_utc": utc_now(),
        "scan_finished_utc": scan_finished_utc,
        "scan_first": True,
        "os": os_info(),
        "options": {
            "max_header_bytes": options.max_header_bytes,
            "max_hash_bytes": options.max_hash_bytes,
            "max_binary_sample_bytes": options.max_binary_sample_bytes,
            "max_archive_members": options.max_archive_members,
            "use_file_command": options.use_file_command,
            "copy_source_stat": options.copy_source_stat,
            "reject_target_inside_source": options.reject_target_inside_source,
        },
        "registry": {"backends": registry.names()},
        "directory_collisions": directory_collisions,
        "planning_warnings": planning_warnings,
        "summary": build_summary(records, entries, directory_collisions, planning_warnings, started),
        "entries": records,
    }
    manifest_path, report_path = manifest_paths(target_root)
    write_text(manifest_path, json.dumps(manifest, indent=2, ensure_ascii=False, default=str) + "\n")
    write_text(report_path, render_report(manifest))
    return manifest


def directory_record(entry: TreeEntry, options: RunOptions) -> dict[str, Any]:
    metadata = collect_metadata(
        entry.source_path,
        entry_type="directory",
        link_target=entry.link_target,
        options=options,
    )
    return {
        "relative_path": rel_text(entry.relative_path),
        "source_path": str(entry.source_path),
        "entry_type": "directory",
        "output_path": None,
        "output_relative_path": None,
        "planned_output": None,
        "metadata": metadata,
        "classification": None,
        "converter_used": "directory_mirror",
        "extraction_methods_used": ["directory_metadata"],
        "metadata_copy_warnings": [],
        "errors": entry.scan_errors + list(metadata.get("metadata_errors", [])),
        "warnings": entry.scan_warnings + list(metadata.get("metadata_warnings", [])),
        "runtime_seconds": 0.0,
        "limitations": [],
    }


def convert_entry(
    entry: TreeEntry,
    planned: Any,
    ctx: ConversionContext,
    registry: ConversionRegistry,
) -> dict[str, Any]:
    started = time.monotonic()
    metadata = collect_metadata(
        entry.source_path,
        entry_type=entry.entry_type,
        link_target=entry.link_target,
        options=ctx.options,
    )
    classification = classify_path(
        entry.source_path,
        metadata=metadata,
        entry_type=entry.entry_type,
        options=ctx.options,
    )
    errors = list(entry.scan_errors) + list(metadata.get("metadata_errors", []))
    warnings = list(entry.scan_warnings) + list(metadata.get("metadata_warnings", [])) + list(classification.warnings)

    result = convert_with_backend(entry, classification, metadata, ctx, registry)
    errors.extend(result.errors)
    warnings.extend(result.warnings)
    rendered = render_text_output(metadata, classification, result, planned, entry)
    write_text(planned.output_path, rendered)
    copy_warnings = copy_supported_metadata(
        entry.source_path,
        planned.output_path,
        entry_type=entry.entry_type,
        options=ctx.options,
    )
    return {
        "relative_path": rel_text(entry.relative_path),
        "source_path": str(entry.source_path),
        "entry_type": entry.entry_type,
        "output_path": str(planned.output_path),
        "output_relative_path": planned.target_relative_path,
        "planned_output": planned_output_dict(planned),
        "metadata": metadata,
        "classification": classification.to_dict(),
        "converter_used": result.converter_used,
        "extraction_methods_used": result.extraction_methods_used,
        "metadata_copy_warnings": copy_warnings,
        "errors": errors,
        "warnings": warnings,
        "runtime_seconds": round(time.monotonic() - started, 3),
        "limitations": result.limitations,
    }


def convert_with_backend(
    entry: TreeEntry,
    classification: Classification,
    metadata: dict[str, Any],
    ctx: ConversionContext,
    registry: ConversionRegistry,
) -> ConversionResult:
    try:
        backend = registry.select(classification, entry.entry_type)
        return backend.convert(entry.source_path, entry.relative_path, classification, metadata, ctx)
    except Exception as exc:
        if entry.entry_type == "file":
            fallback = BinaryFallbackBackend().convert(
                entry.source_path, entry.relative_path, classification, metadata, ctx
            )
            fallback.converter_used = "conversion_error_safe_fallback"
            fallback.errors.append(f"converter_failed:{exc}")
            fallback.limitations.append("A converter failed; safe binary fallback output was used.")
            return fallback
        return ConversionResult(
            text=f"Conversion failed for non-regular entry: {exc}\n",
            converter_used="conversion_error_non_file_fallback",
            extraction_methods_used=["conversion_error_notice"],
            errors=[f"converter_failed:{exc}"],
            limitations=["The entry could not be converted beyond recorded metadata."],
        )

