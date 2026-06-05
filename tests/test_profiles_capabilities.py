from __future__ import annotations

import json
import sqlite3
import zipfile
from pathlib import Path
from typing import Any

import pytest

from all2text import run
from all2text.capabilities import capability_report, resolve_external_tool
from all2text.cli import main
from all2text.config import config_from_dict, default_config, options_with_profile
from all2text.models import RunOptions
from all2text.providers import provider_statuses
from tests.conftest import PNG_1X1, entry, make_options


class _FakeCompleted:
    def __init__(self, stdout: str, returncode: int = 0, stderr: str = "") -> None:
        self.stdout = stdout
        self.returncode = returncode
        self.stderr = stderr


class _FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


def test_default_auto_detects_tools_and_probes_models_without_file_post(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    (source / "notes.txt").write_text("plain text\n", encoding="utf-8")
    (source / "chart.png").write_bytes(PNG_1X1)
    (source / "clip.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42")
    paths = {
        "file": "/usr/local/bin/file",
        "getfacl": "/usr/local/bin/getfacl",
        "ffprobe": "/usr/local/bin/ffprobe",
        "ffmpeg": "/usr/local/bin/ffmpeg",
    }
    subprocess_calls: list[list[str]] = []
    urlopen_calls: list[tuple[str, str, bool]] = []
    ffprobe_calls: list[tuple[Path, str | None, int]] = []

    def fake_which(name: str) -> str | None:
        return paths.get(name)

    def fake_run(cmd: list[str], **kwargs: object) -> _FakeCompleted:
        subprocess_calls.append([str(item) for item in cmd])
        if cmd[0] == paths["file"] and "--mime-type" in cmd:
            return _FakeCompleted("text/plain\n")
        if cmd[0] == paths["file"]:
            return _FakeCompleted("fake file description\n")
        if cmd[0] == paths["getfacl"]:
            return _FakeCompleted("user::rw-\ngroup::r--\nother::r--\n")
        raise AssertionError(f"unexpected subprocess call: {cmd}")

    def fake_ffprobe(
        path: Path,
        *,
        executable: str | None = None,
        timeout_seconds: int = 15,
    ) -> tuple[dict[str, object], list[str]]:
        ffprobe_calls.append((path, executable, timeout_seconds))
        return ({"format": {"duration": "1.5"}, "streams": [{"codec_type": "video"}]}, [])

    def fake_urlopen(request: object, timeout: float = 0) -> _FakeResponse:
        method = request.get_method()  # type: ignore[attr-defined]
        url = request.full_url  # type: ignore[attr-defined]
        urlopen_calls.append((str(url), str(method), bool(getattr(request, "data", None))))
        assert method == "GET"
        assert not getattr(request, "data", None)
        return _FakeResponse({"data": [{"id": "unit-test-model"}]})

    monkeypatch.setattr("all2text.capabilities.shutil.which", fake_which)
    monkeypatch.setattr("all2text.metadata.subprocess.run", fake_run)
    monkeypatch.setattr("all2text.backends.media.ffprobe", fake_ffprobe)
    monkeypatch.setattr("all2text.providers.urllib.request.urlopen", fake_urlopen)

    manifest = run(source, target, options=RunOptions(copy_source_stat=False))

    assert manifest["summary"]["profile"] == "auto"
    assert manifest["summary"]["auto_detect_tools"] is True
    assert manifest["summary"]["allow_external_tools"] is True
    assert manifest["summary"]["allow_local_models"] is True
    assert "file" in manifest["summary"]["capability_summary"]["available_external_tools"]
    assert "ffprobe" in manifest["summary"]["capability_summary"]["available_external_tools"]
    assert ffprobe_calls == [(source / "clip.mp4", paths["ffprobe"], 15)]
    assert any(call[0] == paths["file"] for call in subprocess_calls)
    assert any(call[0] == paths["getfacl"] for call in subprocess_calls)
    assert any(url.endswith("/models") for url, _, _ in urlopen_calls)
    assert entry(manifest, "clip.mp4")["converter_metadata"]["ffprobe"]["format"]["duration"] == "1.5"
    assert entry(manifest, "chart.png")["vlm_used"] is False
    statuses = {status["name"]: status for status in manifest["provider_statuses"]}
    assert statuses["vlm"]["available"] is True
    assert statuses["vlm"]["error"] == "openai-compatible VLM reachable but auto_invoke=false; not invoked"


def test_missing_tools_and_models_are_reported_not_fatal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    (source / "notes.txt").write_text("hello\n", encoding="utf-8")
    (source / "clip.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42")

    monkeypatch.setattr("all2text.capabilities.shutil.which", lambda name: None)

    def unreachable(*args: object, **kwargs: object) -> object:
        raise OSError("connection refused")

    monkeypatch.setattr("all2text.providers.urllib.request.urlopen", unreachable)

    manifest = run(source, target, options=RunOptions(copy_source_stat=False))

    assert manifest["summary"]["converted_text_file_count"] == 2
    missing_tools = manifest["summary"]["capability_summary"]["missing_external_tools"]
    assert "file" in missing_tools
    assert "ffprobe" in missing_tools
    assert any("ffprobe executable not found" in item for item in entry(manifest, "clip.mp4")["warnings"])
    statuses = {status["name"]: status for status in manifest["provider_statuses"]}
    assert statuses["vlm"]["enabled"] is True
    assert statuses["vlm"]["available"] is False
    assert statuses["llm_text"]["available"] is False


def test_capability_report_is_json_safe_and_records_auto_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("all2text.capabilities.shutil.which", lambda name: None)
    report = capability_report(default_config())

    encoded = json.dumps(report, sort_keys=True)

    assert '"profile": "auto"' in encoded
    assert report["profile"]["auto_detect_python"] is True
    assert report["profile"]["auto_detect_tools"] is True
    assert report["profile"]["allow_external_tools"] is True
    assert "ffprobe" in report["summary"]["missing_external_tools"]
    assert isinstance(report["optional_python_libraries"], list)


def test_tool_config_overrides_path_and_disabled_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    custom_ffprobe = tmp_path / "ffprobe-custom"
    custom_ffprobe.write_text("#!/bin/sh\n", encoding="utf-8")
    monkeypatch.setattr("all2text.capabilities.shutil.which", lambda name: None)
    config = config_from_dict(
        {
            "tools": {
                "ffprobe": {"path": str(custom_ffprobe), "timeout_seconds": 7},
                "file": {"enabled": False},
            }
        }
    )

    ffprobe = resolve_external_tool(config, "ffprobe")
    file_tool = resolve_external_tool(config, "file")

    assert ffprobe["available"] is True
    assert ffprobe["source"] == str(custom_ffprobe)
    assert ffprobe["auto_detected"] is False
    assert ffprobe["timeout_seconds"] == 7
    assert file_tool["enabled"] is False
    assert file_tool["error"] == "disabled_by_tools.file.enabled=false"


def test_openai_compatible_endpoint_probe_uses_configured_base_url_safely(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, str, bool, float]] = []
    config = config_from_dict(
        {
            "providers": {
                "vlm": {
                    "name": "openai_compatible",
                    "enabled": True,
                    "base_url": "http://127.0.0.1:9999/v1",
                    "model": "vision-model",
                    "auto_invoke": False,
                }
            }
        }
    )

    def fake_urlopen(request: object, timeout: float = 0) -> _FakeResponse:
        calls.append(
            (
                str(request.full_url),  # type: ignore[attr-defined]
                str(request.get_method()),  # type: ignore[attr-defined]
                bool(getattr(request, "data", None)),
                timeout,
            )
        )
        return _FakeResponse({"data": [{"id": "vision-model"}]})

    monkeypatch.setattr("all2text.providers.urllib.request.urlopen", fake_urlopen)

    statuses = {status.name: status for status in provider_statuses(config, family="image")}

    assert calls[0] == ("http://127.0.0.1:9999/v1/models", "GET", False, 0.5)
    assert statuses["vlm"].available is True
    assert statuses["vlm"].source == "http://127.0.0.1:9999/v1"
    assert statuses["vlm"].details["endpoint_probe"]["model_list_contains_configured_model"] is True


def test_config_profile_normalization_and_validation() -> None:
    core = config_from_dict({"run": {"profile": "core"}})
    tools = config_from_dict({"run": {"profile": "tools", "use_file_command": False}})
    alias = config_from_dict({"run": {"profile": "base"}})

    assert core.options.allow_optional_python is False
    assert core.options.allow_external_tools is False
    assert tools.options.allow_external_tools is True
    assert tools.options.use_file_command is False
    assert alias.options.profile == "auto"
    with pytest.raises(ValueError, match="run.profile must be one of"):
        config_from_dict({"run": {"profile": "dangerous"}})


def test_cli_capabilities_and_advanced_profile_override(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc = main(["--capabilities", "--profile", "core"])

    assert rc == 0
    capabilities = json.loads(capsys.readouterr().out)
    assert capabilities["profile"]["name"] == "core"
    assert "provider_statuses" in capabilities

    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    (source / "notes.json").write_text('{"answer": 42}\n', encoding="utf-8")

    rc = main(["--profile", "core", "--no-copy-source-stat", str(source), str(target)])

    assert rc == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["profile"] == "core"
    assert printed["allow_optional_python"] is False
    assert "capability_summary" in printed
    manifest = json.loads((target / "_conversion_manifest.json").read_text(encoding="utf-8"))
    assert manifest["capabilities"]["profile"]["name"] == "core"


def test_pip_profile_remains_python_only_safety_override(tmp_path: Path) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    (source / "notes.txt").write_text("hello\n", encoding="utf-8")
    (source / "payload.json").write_text('{"items": [1, 2]}\n', encoding="utf-8")

    manifest = run(source, target, options=options_with_profile(make_options(), "pip"))

    assert manifest["summary"]["profile"] == "pip"
    assert manifest["summary"]["allow_external_tools"] is False
    assert manifest["summary"]["allow_local_models"] is False
    assert manifest["summary"]["converted_text_file_count"] == 2


def test_auto_default_end_to_end_diverse_folder_without_tools_or_models(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    (source / "notes.txt").write_text("hello\n", encoding="utf-8")
    (source / "payload.json").write_text('{"items": [1, 2]}\n', encoding="utf-8")
    (source / "image.png").write_bytes(PNG_1X1)
    with zipfile.ZipFile(source / "archive.zip", "w") as zf:
        zf.writestr("inside.txt", "zip text")
    con = sqlite3.connect(source / "data.sqlite")
    con.execute("create table item(id integer primary key, name text)")
    con.commit()
    con.close()
    monkeypatch.setattr("all2text.capabilities.shutil.which", lambda name: None)
    monkeypatch.setattr(
        "all2text.providers.urllib.request.urlopen",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("connection refused")),
    )

    manifest = run(source, target, options=RunOptions(copy_source_stat=False))

    assert manifest["summary"]["profile"] == "auto"
    assert manifest["summary"]["converted_text_file_count"] == 5
    assert (target / "notes.txt.txt").exists()
    assert entry(manifest, "archive.zip")["converter_used"] == "archive_listing_backend"
    assert entry(manifest, "data.sqlite")["converter_used"] == "database_metadata_backend"
