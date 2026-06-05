from __future__ import annotations

import base64
import mimetypes
import os
import platform
import shutil
import stat as stat_module
import subprocess
from pathlib import Path
from typing import Any

from all2text.capabilities import resolve_external_tool
from all2text.models import RunOptions
from all2text.utils import (
    file_size,
    looks_like_text,
    os_info,
    read_header,
    safe_ascii,
    sha256_file,
    timestamp,
    utc_now,
)


def collect_metadata(
    path: Path,
    *,
    entry_type: str,
    link_target: str | None,
    options: RunOptions,
    config: object | None = None,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "path": str(path),
        "name": path.name,
        "extension": path.suffix,
        "suffixes": list(path.suffixes),
        "entry_type": entry_type,
        "link_target": link_target,
        "collected_utc": utc_now(),
        "os": os_info(),
    }
    errors: list[str] = []
    warnings: list[str] = []

    try:
        st = os.stat(path, follow_symlinks=False)
        metadata["stat"] = stat_metadata(st)
        metadata["size_bytes"] = int(st.st_size)
    except Exception as exc:
        errors.append(f"stat_failed:{exc}")

    if entry_type == "file":
        metadata.update(content_metadata(path, options))
    elif entry_type == "symlink":
        metadata["symlink"] = symlink_metadata(path, link_target)

    python_mime, python_encoding = mimetypes.guess_type(str(path))
    metadata["python_mimetype"] = python_mime
    metadata["python_encoding"] = python_encoding

    file_mime, file_description, file_warnings = file_command_metadata(path, options, config)
    metadata["file_mime_type"] = file_mime
    metadata["file_description"] = file_description
    warnings.extend(file_warnings)

    xattrs, xattr_warnings = xattrs_metadata(path)
    metadata["xattrs"] = xattrs
    warnings.extend(xattr_warnings)

    acl, acl_warnings = acl_summary(path, options, config)
    metadata["acl_summary"] = acl
    warnings.extend(acl_warnings)

    metadata["metadata_errors"] = errors
    metadata["metadata_warnings"] = warnings
    return metadata


def content_metadata(path: Path, options: RunOptions) -> dict[str, Any]:
    header = read_header(path, options.max_header_bytes)
    metadata: dict[str, Any] = {
        "magic_header": {
            "bytes_read": len(header),
            "hex": header[:256].hex(),
            "ascii_preview": safe_ascii(header[:256]),
        },
        "looks_text": looks_like_text(header),
    }
    size = file_size(path)
    if size is not None and size <= options.max_hash_bytes:
        try:
            metadata["hashes"] = {"sha256": sha256_file(path)}
        except Exception as exc:
            metadata["hashes"] = {"error": str(exc)}
    elif size is not None:
        metadata["hashes"] = {
            "skipped": f"file_larger_than_{options.max_hash_bytes}_bytes",
            "size_bytes": size,
        }
    return metadata


def stat_metadata(st: os.stat_result) -> dict[str, Any]:
    mode = int(st.st_mode)
    uid = getattr(st, "st_uid", None)
    gid = getattr(st, "st_gid", None)
    return {
        "mode": mode,
        "mode_octal": oct(mode),
        "permissions_octal": oct(stat_module.S_IMODE(mode)),
        "file_type": stat_file_type(mode),
        "size": int(st.st_size),
        "mtime": timestamp(st.st_mtime),
        "ctime": timestamp(st.st_ctime),
        "atime": timestamp(st.st_atime),
        "mtime_ns": getattr(st, "st_mtime_ns", None),
        "ctime_ns": getattr(st, "st_ctime_ns", None),
        "atime_ns": getattr(st, "st_atime_ns", None),
        "uid": uid,
        "gid": gid,
        "owner_name": owner_name(uid),
        "group_name": group_name(gid),
        "inode": getattr(st, "st_ino", None),
        "device": getattr(st, "st_dev", None),
        "nlink": getattr(st, "st_nlink", None),
        "windows_file_attributes": getattr(st, "st_file_attributes", None),
        "windows_reparse_tag": getattr(st, "st_reparse_tag", None),
    }


def stat_file_type(mode: int) -> str:
    checks = [
        (stat_module.S_ISREG, "regular_file"),
        (stat_module.S_ISDIR, "directory"),
        (stat_module.S_ISLNK, "symlink"),
        (stat_module.S_ISFIFO, "fifo"),
        (stat_module.S_ISSOCK, "socket"),
        (stat_module.S_ISCHR, "character_device"),
        (stat_module.S_ISBLK, "block_device"),
    ]
    for check, name in checks:
        if check(mode):
            return name
    return "unknown"


def symlink_metadata(path: Path, link_target: str | None) -> dict[str, Any]:
    result: dict[str, Any] = {"target": link_target, "target_exists": None, "target_kind": None}
    if link_target is None:
        return result
    try:
        target_path = Path(link_target) if os.path.isabs(link_target) else path.parent / link_target
        result["target_exists"] = target_path.exists()
        if target_path.exists():
            result["target_kind"] = (
                "directory" if target_path.is_dir() else "file" if target_path.is_file() else "other"
            )
    except Exception as exc:
        result["target_error"] = str(exc)
    return result


def file_command_metadata(
    path: Path,
    options: RunOptions,
    config: object | None = None,
) -> tuple[str | None, str | None, list[str]]:
    if not options.use_file_command:
        return None, None, ["file_command_disabled"]
    tool = resolve_external_tool(config, "file")
    file_cmd = tool["source"]
    if not tool["enabled"]:
        return None, None, [str(tool["error"] or "file_command_disabled")]
    if not file_cmd:
        return None, None, [str(tool["error"] or "file_command_unavailable")]
    timeout = int(tool.get("timeout_seconds") or 5)
    warnings: list[str] = []
    values: list[str | None] = []
    for args in (["--brief", "--mime-type", "--"], ["--brief", "--"]):
        try:
            completed = subprocess.run(
                [file_cmd, *args, str(path)],
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            if completed.returncode == 0:
                values.append(completed.stdout.strip() or None)
            else:
                values.append(None)
                warnings.append(f"file_command_failed:{completed.stderr.strip() or completed.returncode}")
        except Exception as exc:
            values.append(None)
            warnings.append(f"file_command_failed:{exc}")
    return values[0], values[1], warnings


def xattrs_metadata(path: Path) -> tuple[dict[str, Any], list[str]]:
    if not hasattr(os, "listxattr"):
        return {"available": False, "items": []}, ["xattr_unavailable_on_platform"]
    warnings: list[str] = []
    items: list[dict[str, Any]] = []
    try:
        try:
            names = os.listxattr(path, follow_symlinks=False)
        except TypeError:
            names = os.listxattr(path)
    except Exception as exc:
        return {"available": True, "items": []}, [f"xattr_list_failed:{exc}"]
    for name in names:
        try:
            try:
                value = os.getxattr(path, name, follow_symlinks=False)
            except TypeError:
                value = os.getxattr(path, name)
            items.append(
                {
                    "name": str(name),
                    "size": len(value),
                    "base64": base64.b64encode(value[:4096]).decode("ascii"),
                    "truncated": len(value) > 4096,
                }
            )
        except Exception as exc:
            warnings.append(f"xattr_read_failed:{name}:{exc}")
    return {"available": True, "items": items}, warnings


def acl_summary(path: Path, options: RunOptions, config: object | None = None) -> tuple[dict[str, Any], list[str]]:
    tool = resolve_external_tool(config, "getfacl")
    getfacl = tool["source"]
    if not tool["enabled"]:
        return {"available": False, "enabled": False, "summary": None}, [
            str(tool["error"] or f"acl_summary_disabled_by_profile:{options.profile}")
        ]
    if platform.system() != "Linux" or not getfacl:
        return {"available": False, "enabled": True, "summary": None}, [
            str(tool["error"] or "acl_summary_unavailable")
        ]
    timeout = int(tool.get("timeout_seconds") or 5)
    try:
        completed = subprocess.run(
            [getfacl, "-cp", "--", str(path)],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except Exception as exc:
        return {"available": True, "enabled": True, "summary": None}, [f"acl_summary_failed:{exc}"]
    if completed.returncode != 0:
        return {
            "available": True,
            "enabled": True,
            "summary": None,
        }, [f"acl_summary_failed:{completed.stderr.strip() or completed.returncode}"]
    text = completed.stdout.strip()
    return {"available": True, "enabled": True, "summary": text[:4000], "truncated": len(text) > 4000}, []


def copy_supported_metadata(source: Path, target: Path, *, entry_type: str, options: RunOptions) -> list[str]:
    if not options.copy_source_stat:
        return ["filesystem_metadata_copy_disabled"]
    if entry_type != "file":
        return [f"filesystem_metadata_copy_skipped_for_entry_type:{entry_type}"]
    warnings: list[str] = []
    try:
        shutil.copystat(source, target, follow_symlinks=False)
    except Exception as exc:
        warnings.append(f"copystat_failed:{exc}")
    warnings.extend(copy_xattrs(source, target))
    return warnings


def copy_xattrs(source: Path, target: Path) -> list[str]:
    if not all(hasattr(os, name) for name in ("listxattr", "getxattr", "setxattr")):
        return ["xattr_copy_unavailable_on_platform"]
    warnings: list[str] = []
    try:
        try:
            names = os.listxattr(source, follow_symlinks=False)
        except TypeError:
            names = os.listxattr(source)
    except Exception as exc:
        return [f"xattr_copy_list_failed:{exc}"]
    for name in names:
        try:
            try:
                value = os.getxattr(source, name, follow_symlinks=False)
            except TypeError:
                value = os.getxattr(source, name)
            try:
                os.setxattr(target, name, value, follow_symlinks=False)
            except TypeError:
                os.setxattr(target, name, value)
        except Exception as exc:
            warnings.append(f"xattr_copy_failed:{name}:{exc}")
    return warnings


def owner_name(uid: Any) -> str | None:
    if uid is None:
        return None
    try:
        import pwd

        return pwd.getpwuid(int(uid)).pw_name
    except Exception:
        return None


def group_name(gid: Any) -> str | None:
    if gid is None:
        return None
    try:
        import grp

        return grp.getgrgid(int(gid)).gr_name
    except Exception:
        return None
