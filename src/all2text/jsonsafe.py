from __future__ import annotations

import base64
import json
from dataclasses import asdict, is_dataclass
from datetime import date, datetime, time
from pathlib import Path
from typing import Any


def to_jsonable(value: Any, *, _seen: set[int] | None = None) -> Any:
    """Convert common Python/OS objects into JSON-safe structures."""

    if _seen is None:
        _seen = set()
    if value is None or isinstance(value, (str, int, float, bool)):
        return value

    value_id = id(value)
    if value_id in _seen:
        return {"type": type(value).__name__, "repr": "<recursive>"}

    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, (bytes, bytearray, memoryview)):
        raw = bytes(value)
        preview = raw[:4096]
        return {
            "type": "bytes",
            "size": len(raw),
            "base64": base64.b64encode(preview).decode("ascii"),
            "truncated": len(raw) > len(preview),
        }
    if isinstance(value, BaseException):
        return {
            "type": value.__class__.__name__,
            "message": str(value),
            "args": to_jsonable(list(value.args), _seen=_seen),
        }
    if is_dataclass(value) and not isinstance(value, type):
        _seen.add(value_id)
        try:
            return to_jsonable(asdict(value), _seen=_seen)
        finally:
            _seen.discard(value_id)
    if isinstance(value, dict):
        _seen.add(value_id)
        try:
            return {str(to_jsonable(key, _seen=_seen)): to_jsonable(item, _seen=_seen) for key, item in value.items()}
        finally:
            _seen.discard(value_id)
    if isinstance(value, (list, tuple)):
        _seen.add(value_id)
        try:
            return [to_jsonable(item, _seen=_seen) for item in value]
        finally:
            _seen.discard(value_id)
    if isinstance(value, (set, frozenset)):
        _seen.add(value_id)
        try:
            return [to_jsonable(item, _seen=_seen) for item in sorted(value, key=repr)]
        finally:
            _seen.discard(value_id)
    if hasattr(value, "_asdict"):
        try:
            return to_jsonable(value._asdict(), _seen=_seen)
        except Exception:
            pass
    if hasattr(value, "__fspath__"):
        try:
            return str(value)
        except Exception:
            pass
    return {"type": type(value).__name__, "repr": repr(value)}


def json_dumps(value: Any, **kwargs: Any) -> str:
    kwargs.setdefault("ensure_ascii", False)
    return json.dumps(to_jsonable(value), **kwargs)
