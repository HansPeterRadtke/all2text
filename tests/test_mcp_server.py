from all2text.mcp_server import PROTOCOL_VERSION, handle_request


def _request(method, params=None, request_id=1):
    payload = dict(params or {})
    payload["_meta"] = {
        "io.modelcontextprotocol/protocolVersion": PROTOCOL_VERSION,
        "io.modelcontextprotocol/clientCapabilities": {},
        "io.modelcontextprotocol/clientInfo": {"name": "test", "version": "1"},
    }
    return {"jsonrpc": "2.0", "id": request_id, "method": method, "params": payload}


def test_mcp_lists_all2text_tools():
    response = handle_request(_request("tools/list"))
    assert [tool["name"] for tool in response["result"]["tools"]] == ["all2text_capabilities", "all2text_convert"]


def test_mcp_capabilities_delegates_to_existing_cli():
    calls = []
    def runner(command):
        calls.append(command)
        return {"profile": {"name": "auto"}, "providers": []}
    response = handle_request(_request("tools/call", {"name": "all2text_capabilities", "arguments": {}}), runner=runner)
    assert response["result"]["isError"] is False
    assert response["result"]["structuredContent"]["profile"]["name"] == "auto"
    assert calls[0][-1] == "--capabilities"


def test_mcp_convert_delegates_paths_and_profile():
    calls = []
    def runner(command):
        calls.append(command)
        return {"converted": 1}
    response = handle_request(_request("tools/call", {"name": "all2text_convert", "arguments": {"source_folder": "/tmp/source", "target_folder": "/tmp/out", "profile": "core"}}), runner=runner)
    assert response["result"]["structuredContent"] == {"converted": 1}
    assert "/tmp/source" in calls[0]
    assert "/tmp/out" in calls[0]
    assert calls[0][-2:] == ["--profile", "core"]


def test_mcp_conversion_failure_is_tool_error():
    def runner(_command):
        raise RuntimeError("converter unavailable")
    response = handle_request(_request("tools/call", {"name": "all2text_convert", "arguments": {"source_folder": "/tmp/source", "target_folder": "/tmp/out"}}), runner=runner)
    assert "error" not in response
    assert response["result"]["isError"] is True
    assert "converter unavailable" in response["result"]["structuredContent"]["error"]
