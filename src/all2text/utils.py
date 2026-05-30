from __future__ import annotations

import hashlib
import os
import platform
import string
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def timestamp(value: float) -> str:
    return datetime.fromtimestamp(value, tz=timezone.utc).isoformat()


def os_info() -> dict[str, Any]:
    return {
        "platform_system": platform.system(),
        "platform_release": platform.release(),
        "platform_version": platform.version(),
        "python_version": platform.python_version(),
        "os_name": os.name,
        "case_sensitive_collision_policy": "casefold_planning_with_deterministic_collision_names",
        "symlink_policy": "record_symlinks_without_following",
    }


def rel_text(path: Path) -> str:
    return "." if path == Path(".") else path.as_posix()


def parent_or_root(path: Path) -> Path:
    parent = path.parent
    return Path(".") if str(parent) in {"", "."} else parent


def casefold_key(value: str) -> str:
    return os.path.normcase(value).casefold()


def collision_name(name: str, rel_path: Path, attempt: int = 0) -> str:
    seed = rel_text(rel_path)
    if attempt:
        seed = f"{seed}:{attempt}"
    digest = hashlib.sha1(seed.encode("utf-8", errors="surrogateescape")).hexdigest()[:12]
    if name.endswith(".txt"):
        return f"{name[:-4]}.collision-{digest}.txt"
    return f"{name}.collision-{digest}"


def stable_unique(items: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(str(item) for item in items if str(item)))


def is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.expanduser().resolve(strict=False).relative_to(root.expanduser().resolve(strict=False))
        return True
    except ValueError:
        return False


def read_header(path: Path, max_bytes: int) -> bytes:
    try:
        with path.open("rb") as handle:
            return handle.read(max_bytes)
    except Exception:
        return b""


def file_size(path: Path) -> int | None:
    try:
        return int(path.stat().st_size)
    except Exception:
        return None


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_ascii(raw: bytes) -> str:
    return "".join(chr(byte) if 32 <= byte < 127 else "." for byte in raw)


def looks_like_text(raw: bytes) -> bool:
    if not raw:
        return True
    if b"\x00" in raw:
        return raw.startswith((b"\xff\xfe", b"\xfe\xff"))
    sample = raw[:4096]
    printable = set(bytes(string.printable, "ascii"))
    acceptable = sum(1 for byte in sample if byte in printable or byte >= 0x80)
    return acceptable / max(1, len(sample)) >= 0.85


def printable_strings_sample(path: Path, max_bytes: int) -> list[str]:
    try:
        data = path.read_bytes()[:max_bytes]
    except Exception:
        return []
    found: list[str] = []
    current: list[int] = []
    allowed = set(bytes(string.printable, "ascii")) - {0x09, 0x0A, 0x0B, 0x0C, 0x0D}
    for byte in data:
        if byte in allowed:
            current.append(byte)
            continue
        if len(current) >= 4:
            found.append(bytes(current).decode("ascii", errors="replace"))
            if len(found) >= 50:
                break
        current = []
    if len(current) >= 4 and len(found) < 50:
        found.append(bytes(current).decode("ascii", errors="replace"))
    return found

