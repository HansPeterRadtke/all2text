from __future__ import annotations

import json
import subprocess
import sys
from typing import Any, Callable, Dict, List

from all2text.version import __version__

PROTOCOL_VERSION = "2026-07-28"
SERVER_INFO = {"name": "all2text", "version": __version__}

TOOLS = (
    {
        "name": "all2text_capabilities",
        "description": "Inspect all2text's currently configured and available conversion capabilities without converting files.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "all2text_convert",
        "description": "Convert a caller-selected source folder tree into auditable text outputs under a caller-selected target folder.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source_folder": {"type": "string"},
                "target_folder": {"type": "string"},
                "profile": {"type": "string", "enum": ["auto", "core", "pip", "tools", "local-models", "full"], "default": "auto"},
                "config": {"type": "string"},
            },
            "required": ["source_folder", "target_folder"],
            "additionalProperties": False,
        },
    },
)


def _error(request_id: Any, code: int, message: str) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def _result(request_id: Any, payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": {
            "resultType": "complete",
            **payload,
            "_meta": {"io.modelcontextprotocol/serverInfo": dict(SERVER_INFO)},
        },
    }


def _validate_request(request: Dict[str, Any]) -> str | None:
    if request.get("jsonrpc") != "2.0":
        return "jsonrpc must be '2.0'"
    if not isinstance(request.get("method"), str) or not request["method"]:
        return "method must be a non-empty string"
    params = request.get("params", {})
    if not isinstance(params, dict):
        return "params must be an object"
    meta = params.get("_meta")
    if not isinstance(meta, dict):
        return "Every MCP request requires params._meta"
    if meta.get("io.modelcontextprotocol/protocolVersion") != PROTOCOL_VERSION:
        return "Unsupported MCP protocol version"
    if not isinstance(meta.get("io.modelcontextprotocol/clientCapabilities"), dict):
        return "params._meta.io.modelcontextprotocol/clientCapabilities must be an object"
    return None


def _run_json_command(command: List[str]) -> Dict[str, Any]:
    completed = subprocess.run(command, text=True, capture_output=True, check=False)
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or f"exit {completed.returncode}"
        raise RuntimeError(detail)
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"all2text returned non-JSON output: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("all2text returned a non-object JSON result")
    return payload


def _call_tool(name: str, arguments: Dict[str, Any], runner: Callable[[List[str]], Dict[str, Any]]) -> Dict[str, Any]:
    if name == "all2text_capabilities":
        if arguments:
            raise ValueError("all2text_capabilities accepts no arguments")
        return runner([sys.executable, "-m", "all2text.cli", "--capabilities"])
    if name == "all2text_convert":
        source = arguments.get("source_folder")
        target = arguments.get("target_folder")
        if not isinstance(source, str) or not source.strip():
            raise ValueError("source_folder must be a non-empty string")
        if not isinstance(target, str) or not target.strip():
            raise ValueError("target_folder must be a non-empty string")
        profile = str(arguments.get("profile", "auto"))
        if profile not in {"auto", "core", "pip", "tools", "local-models", "full"}:
            raise ValueError("profile is invalid")
        command = [sys.executable, "-m", "all2text.cli", source.strip(), target.strip(), "--profile", profile]
        config = arguments.get("config")
        if config is not None:
            if not isinstance(config, str) or not config.strip():
                raise ValueError("config must be a non-empty string when supplied")
            command.extend(["--config", config.strip()])
        return runner(command)
    raise KeyError(name)


def handle_request(request: Dict[str, Any], runner: Callable[[List[str]], Dict[str, Any]] = _run_json_command) -> Dict[str, Any] | None:
    validation_error = _validate_request(request)
    request_id = request.get("id")
    if validation_error:
        return _error(request_id, -32602, validation_error)
    if "id" not in request:
        return None
    method = request["method"]
    params = request.get("params", {})
    if method == "ping":
        return _result(request_id, {})
    if method == "server/discover":
        return _result(request_id, {"supportedVersions": [PROTOCOL_VERSION], "capabilities": {"tools": {}}, "ttlMs": 0, "cacheScope": "private"})
    if method == "tools/list":
        return _result(request_id, {"tools": list(TOOLS), "ttlMs": 0, "cacheScope": "private"})
    if method != "tools/call":
        return _error(request_id, -32601, f"Method not found: {method}")
    name = params.get("name")
    arguments = params.get("arguments", {})
    if not isinstance(name, str) or not name:
        return _error(request_id, -32602, "tools/call name must be a non-empty string")
    if not isinstance(arguments, dict):
        return _error(request_id, -32602, "tools/call arguments must be an object")
    try:
        payload = _call_tool(name, arguments, runner)
    except KeyError:
        return _error(request_id, -32602, f"Unknown tool: {name}")
    except (TypeError, ValueError) as exc:
        return _error(request_id, -32602, str(exc))
    except Exception as exc:
        failure = {"error": f"{type(exc).__name__}: {exc}"}
        return _result(request_id, {"content": [{"type": "text", "text": failure["error"]}], "structuredContent": failure, "isError": True})
    return _result(request_id, {"content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False, sort_keys=True)}], "structuredContent": payload, "isError": False})


def main() -> int:
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            request = json.loads(line)
            if not isinstance(request, dict):
                response = _error(None, -32600, "request must be a JSON object")
            else:
                response = handle_request(request)
        except Exception as exc:
            response = _error(None, -32700, f"Parse error: {exc}")
        if response is not None:
            sys.stdout.write(json.dumps(response, ensure_ascii=False, separators=(",", ":")) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
