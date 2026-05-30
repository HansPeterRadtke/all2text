from __future__ import annotations

from pathlib import Path
from typing import Any

from all2text.models import PlannedOutput, TreeEntry
from all2text.utils import casefold_key, collision_name, parent_or_root, rel_text


def create_target_directories(
    target_root: Path, directories: list[TreeEntry]
) -> tuple[dict[Path, Path], list[dict[str, Any]]]:
    dir_map: dict[Path, Path] = {Path("."): Path(".")}
    collisions: list[dict[str, Any]] = []
    occupied_by_parent: dict[str, dict[str, str]] = {".": {}}

    sorted_dirs = sorted(
        [entry for entry in directories if entry.relative_path != Path(".")],
        key=lambda entry: (len(entry.relative_path.parts), entry.relative_path.as_posix().casefold()),
    )
    for entry in sorted_dirs:
        parent = parent_or_root(entry.relative_path)
        target_parent_rel = dir_map.get(parent, parent)
        occupied = occupied_by_parent.setdefault(rel_text(target_parent_rel), {})
        desired = entry.relative_path.name
        actual = desired
        reason = None
        attempt = 0
        while casefold_key(actual) in occupied:
            reason = "case_insensitive_directory_collision"
            actual = collision_name(desired, entry.relative_path, attempt)
            attempt += 1
        if reason:
            collisions.append(
                {
                    "source_relative_path": rel_text(entry.relative_path),
                    "desired_target_name": desired,
                    "actual_target_name": actual,
                    "reason": reason,
                }
            )
        occupied[casefold_key(actual)] = rel_text(entry.relative_path)
        target_rel = target_parent_rel / actual
        dir_map[entry.relative_path] = target_rel
        (target_root / target_rel).mkdir(parents=True, exist_ok=True)
    return dir_map, collisions


def reserve_output_files(
    target_root: Path, entries: list[TreeEntry], dir_map: dict[Path, Path]
) -> tuple[dict[Path, PlannedOutput], list[dict[str, Any]]]:
    planned: dict[Path, PlannedOutput] = {}
    warnings: list[dict[str, Any]] = []
    occupied_by_parent: dict[str, dict[str, str]] = {}

    for source_rel, target_rel in dir_map.items():
        if source_rel == Path(".") or target_rel == Path("."):
            continue
        parent = parent_or_root(target_rel)
        occupied = occupied_by_parent.setdefault(rel_text(parent), {})
        occupied[casefold_key(target_rel.name)] = f"directory:{rel_text(source_rel)}"

    for entry in sorted(entries, key=lambda item: item.relative_path.as_posix().casefold()):
        parent = parent_or_root(entry.relative_path)
        target_parent_rel = dir_map.get(parent, parent)
        (target_root / target_parent_rel).mkdir(parents=True, exist_ok=True)
        occupied = occupied_by_parent.setdefault(rel_text(target_parent_rel), {})
        desired = f"{entry.relative_path.name}.txt"
        actual = desired
        reason = None
        attempt = 0
        while casefold_key(actual) in occupied or (target_root / target_parent_rel / actual).is_dir():
            reason = "case_insensitive_output_name_collision"
            actual = collision_name(desired, entry.relative_path, attempt)
            attempt += 1
        if reason:
            warnings.append(
                {
                    "source_relative_path": rel_text(entry.relative_path),
                    "desired_output_name": desired,
                    "actual_output_name": actual,
                    "reason": reason,
                }
            )
        occupied[casefold_key(actual)] = rel_text(entry.relative_path)
        output_rel = target_parent_rel / actual
        planned[entry.relative_path] = PlannedOutput(
            source_relative_path=rel_text(entry.relative_path),
            target_relative_path=rel_text(output_rel),
            output_path=target_root / output_rel,
            collision=reason is not None,
            collision_reason=reason,
        )
    return planned, warnings

