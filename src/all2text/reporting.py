from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from all2text.models import TreeEntry


def build_summary(
    records: list[dict[str, Any]],
    entries: list[TreeEntry],
    directory_collisions: list[dict[str, Any]],
    planning_warnings: list[dict[str, Any]],
    started: float,
) -> dict[str, Any]:
    text_records = [record for record in records if record.get("entry_type") != "directory"]
    category_counts: dict[str, int] = {}
    format_counts: dict[str, int] = {}
    converter_counts: dict[str, int] = {}
    limitation_counts: dict[str, int] = {}
    for record in text_records:
        classification = record.get("classification") or {}
        category = str(classification.get("rough_category") or "none")
        fmt = str(classification.get("concrete_format") or "none")
        category_counts[category] = category_counts.get(category, 0) + 1
        format_counts[fmt] = format_counts.get(fmt, 0) + 1
        converter = str(record.get("converter_used") or "none")
        converter_counts[converter] = converter_counts.get(converter, 0) + 1
        for limitation in record.get("limitations") or []:
            key = str(limitation)
            limitation_counts[key] = limitation_counts.get(key, 0) + 1
    return {
        "scan_first": True,
        "source_entry_count": len(entries),
        "directory_count": sum(1 for entry in entries if entry.entry_type == "directory"),
        "converted_text_file_count": len(text_records),
        "files_with_errors": [record["relative_path"] for record in text_records if record.get("errors")],
        "files_with_warnings": [
            record["relative_path"]
            for record in text_records
            if record.get("warnings") or record.get("metadata_copy_warnings")
        ],
        "category_counts": category_counts,
        "format_counts": format_counts,
        "converter_counts": converter_counts,
        "limitation_counts": limitation_counts,
        "directory_collision_count": len(directory_collisions),
        "output_collision_count": len(planning_warnings),
        "runtime_seconds": round(time.monotonic() - started, 3),
    }


def build_module_statuses(
    modules: dict[str, Any],
    records: list[dict[str, Any]],
    registered_backends: list[str],
) -> dict[str, Any]:
    registered = set(registered_backends)
    statuses: dict[str, Any] = {}
    for key, module in sorted(modules.items()):
        backend = getattr(module, "backend", "")
        matched = [record for record in records if _record_matches_module_key(record, key)]
        selected_count = sum(1 for record in matched if record.get("converter_used") == backend)
        if backend not in registered:
            status = "configured_backend_not_registered"
        elif selected_count:
            status = "used"
        elif matched:
            status = "configured_backend_not_selected_for_matching_entries"
        else:
            status = "configured_not_run_no_matching_entries"
        statuses[key] = {
            "backend": backend,
            "registered": backend in registered,
            "matching_entry_count": len(matched),
            "selected_count": selected_count,
            "status": status,
            "params": dict(getattr(module, "params", {}) or {}),
        }
    return statuses


def _record_matches_module_key(record: dict[str, Any], key: str) -> bool:
    classification = record.get("classification") or {}
    rough = str(classification.get("rough_category") or "")
    fmt = str(classification.get("concrete_format") or "").casefold()
    entry_type = str(record.get("entry_type") or "")
    lowered = key.casefold()
    return lowered in {rough.casefold(), fmt, entry_type.casefold()}


def render_report(manifest: dict[str, Any]) -> str:
    summary = manifest["summary"]
    lines = [
        "all2text Conversion Report",
        "",
        f"Source folder: {manifest['source_folder']}",
        f"Target folder: {manifest['target_folder']}",
        f"Created UTC: {manifest['created_utc']}",
        "",
        "Summary:",
        f"- scan_first: {summary['scan_first']}",
        f"- source_entry_count: {summary['source_entry_count']}",
        f"- directory_count: {summary['directory_count']}",
        f"- converted_text_file_count: {summary['converted_text_file_count']}",
        f"- runtime_seconds: {summary['runtime_seconds']}",
        f"- directory_collision_count: {summary['directory_collision_count']}",
        f"- output_collision_count: {summary['output_collision_count']}",
        "",
        "Category counts:",
    ]
    lines.extend(f"- {key}: {value}" for key, value in sorted(summary["category_counts"].items()))
    lines.append("")
    lines.append("Format counts:")
    lines.extend(f"- {key}: {value}" for key, value in sorted(summary["format_counts"].items()))
    lines.append("")
    lines.append("Converter counts:")
    lines.extend(f"- {key}: {value}" for key, value in sorted(summary["converter_counts"].items()))
    if manifest.get("module_statuses"):
        lines.extend(["", "Module statuses:"])
        for key, status in sorted(manifest["module_statuses"].items()):
            lines.append(
                f"- {key}: {status.get('status')} "
                f"(backend={status.get('backend')}, matches={status.get('matching_entry_count')}, "
                f"selected={status.get('selected_count')})"
            )
    if summary["files_with_errors"]:
        lines.extend(["", "Files with errors:", *[f"- {item}" for item in summary["files_with_errors"]]])
    if summary["files_with_warnings"]:
        lines.extend(["", "Files with warnings:", *[f"- {item}" for item in summary["files_with_warnings"]]])
    if manifest.get("planning_warnings"):
        lines.extend(["", "Output planning warnings:"])
        for item in manifest["planning_warnings"]:
            lines.append(f"- {item}")
    return "\n".join(lines).rstrip() + "\n"


def manifest_paths(target_root: Path) -> tuple[Path, Path]:
    return target_root / "_conversion_manifest.json", target_root / "_conversion_report.txt"
