from __future__ import annotations

import fnmatch
import os
from pathlib import Path

from all2text.models import TreeEntry


DEFAULT_EXCLUDED_DIR_NAMES = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".tox",
        ".nox",
        ".venv",
        "venv",
        "env",
        "node_modules",
        "build",
        "dist",
        ".eggs",
    }
)

DEFAULT_EXCLUDED_FILE_GLOBS = (
    "*.pyc",
    "*.pyo",
    "*.class",
    ".DS_Store",
    "Thumbs.db",
)


def is_default_excluded(path: Path, *, is_dir: bool) -> bool:
    name = path.name
    if is_dir and name in DEFAULT_EXCLUDED_DIR_NAMES:
        return True
    return any(fnmatch.fnmatchcase(name, pattern) for pattern in DEFAULT_EXCLUDED_FILE_GLOBS)


def scan_source_tree(source_root: Path) -> list[TreeEntry]:
    entries = [TreeEntry(source_root, Path("."), "directory")]
    visited: set[tuple[int, int]] = set()

    def remember_directory(folder: Path) -> None:
        try:
            st = os.stat(folder, follow_symlinks=False)
            visited.add((int(st.st_dev), int(st.st_ino)))
        except Exception:
            return

    def already_seen_directory(folder: Path) -> bool:
        try:
            st = os.stat(folder, follow_symlinks=False)
            return (int(st.st_dev), int(st.st_ino)) in visited
        except Exception:
            return False

    def walk(folder: Path, rel: Path) -> None:
        remember_directory(folder)
        try:
            children = sorted(os.scandir(folder), key=lambda item: item.name.casefold())
        except Exception as exc:
            entries.append(TreeEntry(folder, rel, "directory", scan_errors=[f"scandir_failed:{exc}"]))
            return

        for child in children:
            path = Path(child.path)
            child_rel = rel / child.name if rel != Path(".") else Path(child.name)
            errors: list[str] = []
            warnings: list[str] = []
            try:
                if child.is_symlink():
                    try:
                        target = os.readlink(path)
                    except Exception as exc:
                        target = None
                        errors.append(f"readlink_failed:{exc}")
                    entries.append(
                        TreeEntry(
                            path,
                            child_rel,
                            "symlink",
                            link_target=target,
                            scan_errors=errors,
                            scan_warnings=["symlink_not_followed"],
                        )
                    )
                    continue
                if child.is_dir(follow_symlinks=False):
                    if is_default_excluded(path, is_dir=True):
                        continue
                    entry = TreeEntry(path, child_rel, "directory")
                    entries.append(entry)
                    if already_seen_directory(path):
                        entry.scan_warnings.append("directory_already_visited")
                        continue
                    walk(path, child_rel)
                    continue
                if child.is_file(follow_symlinks=False):
                    if is_default_excluded(path, is_dir=False):
                        continue
                    entries.append(TreeEntry(path, child_rel, "file"))
                    continue
                entries.append(TreeEntry(path, child_rel, "other"))
            except OSError as exc:
                entries.append(
                    TreeEntry(path, child_rel, "other", scan_errors=[f"type_check_failed:{exc}"], scan_warnings=warnings)
                )

    walk(source_root, Path("."))
    return entries
