from __future__ import annotations

import json
import sqlite3
import zipfile
from pathlib import Path

import pytest

from all2text import run
from all2text.capabilities import capability_report
from all2text.cli import main
from all2text.config import config_from_dict, default_config, options_with_profile
from tests.conftest import PNG_1X1, entry, make_options


def test_default_pip_profile_blocks_shell_tools_and_model_calls(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    (source / "notes.txt").write_text("plain text\n", encoding="utf-8")
    (source / "chart.png").write_bytes(PNG_1X1)
    (source / "clip.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42")
    config = config_from_dict(
        {
            "providers": {
                "ocr": {"name": "tesseract", "enabled": True, "auto_invoke": True},
                "vlm": {
                    "name": "openai_compatible",
                    "enabled": True,
                    "base_url": "http://127.0.0.1:9/v1",
                    "model": "missing-vlm",
                    "auto_invoke": True,
                },
                "video_frames": {
                    "name": "ffmpeg",
                    "enabled": True,
                    "sample_frames": True,
                    "auto_invoke": True,
                },
            }
        }
    )

    def forbidden_subprocess(*args: object, **kwargs: object) -> object:
        raise AssertionError("external subprocess should not run in pip profile")

    def forbidden_ffprobe(path: Path) -> tuple[dict[str, object] | None, list[str]]:
        raise AssertionError("ffprobe should not run in pip profile")

    def forbidden_urlopen(*args: object, **kwargs: object) -> object:
        raise AssertionError("model endpoint should not be called in pip profile")

    monkeypatch.setattr("all2text.metadata.subprocess.run", forbidden_subprocess)
    monkeypatch.setattr("all2text.backends.media.ffprobe", forbidden_ffprobe)
    monkeypatch.setattr("all2text.providers.urllib.request.urlopen", forbidden_urlopen)

    manifest = run(source, target, options=make_options(), config=config)

    assert manifest["summary"]["profile"] == "pip"
    assert manifest["summary"]["allow_external_tools"] is False
    assert manifest["summary"]["allow_local_models"] is False
    statuses = {status["name"]: status for status in manifest["provider_statuses"]}
    assert statuses["ocr"]["enabled"] is False
    assert statuses["ocr"]["error"] == "OCR disabled by profile:pip"
    assert statuses["vlm"]["enabled"] is False
    assert statuses["vlm"]["error"] == "VLM disabled by profile:pip"
    assert statuses["video_frames"]["enabled"] is False
    assert statuses["video_frames"]["error"] == "video frame provider disabled by profile:pip"
    assert any("ffprobe_disabled_by_profile:pip" in warning for warning in entry(manifest, "clip.mp4")["warnings"])
    assert entry(manifest, "chart.png")["vlm_used"] is False


def test_capability_report_is_json_safe_and_records_profile_gates() -> None:
    config = default_config()
    report = capability_report(config)

    encoded = json.dumps(report, sort_keys=True)

    assert '"profile": "pip"' in encoded
    assert report["profile"]["allow_optional_python"] is True
    assert report["profile"]["allow_external_tools"] is False
    assert "ffprobe" in report["summary"]["disabled_by_profile"]
    assert isinstance(report["optional_python_libraries"], list)


def test_config_profile_normalization_and_validation() -> None:
    core = config_from_dict({"run": {"profile": "core"}})
    tools = config_from_dict({"run": {"profile": "tools", "use_file_command": False}})
    alias = config_from_dict({"run": {"profile": "base"}})

    assert core.options.allow_optional_python is False
    assert core.options.allow_external_tools is False
    assert tools.options.allow_external_tools is True
    assert tools.options.use_file_command is False
    assert alias.options.profile == "pip"
    with pytest.raises(ValueError, match="run.profile must be one of"):
        config_from_dict({"run": {"profile": "dangerous"}})


def test_cli_profile_stdout_and_manifest_capabilities(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
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


def test_pip_profile_end_to_end_diverse_folder(tmp_path: Path) -> None:
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

    manifest = run(source, target, options=options_with_profile(make_options(), "pip"))

    assert manifest["summary"]["profile"] == "pip"
    assert manifest["summary"]["converted_text_file_count"] == 5
    assert (target / "notes.txt.txt").exists()
    assert entry(manifest, "archive.zip")["converter_used"] == "archive_listing_backend"
    assert entry(manifest, "data.sqlite")["converter_used"] == "database_metadata_backend"
