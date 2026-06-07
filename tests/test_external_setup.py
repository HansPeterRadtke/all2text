from __future__ import annotations

import io
import json
import os
import subprocess
import sys
from pathlib import Path

from all2text.cli import main
from all2text.config import config_from_dict, default_config
from all2text.external_setup import (
    SetupOptions,
    build_setup_plan,
    execute_setup,
    faster_whisper_action,
    package_tool_action,
)


class TtyBuffer(io.StringIO):
    def isatty(self) -> bool:
        return True


def test_setup_plan_generates_platform_package_commands(monkeypatch) -> None:
    monkeypatch.setattr("all2text.external_setup.shutil.which", lambda name: None)
    monkeypatch.setattr("all2text.external_setup.probe_endpoints", lambda endpoints, timeout: [])
    monkeypatch.setattr("all2text.external_setup.find_paths", lambda roots, patterns: [])

    linux = build_setup_plan(
        default_config(),
        options=SetupOptions(
            include_models=False,
            selected_tools=("ffmpeg",),
            system="Linux",
        ),
    )
    windows = build_setup_plan(
        default_config(),
        options=SetupOptions(
            include_models=False,
            selected_tools=("ffmpeg",),
            system="Windows",
        ),
    )
    mac = build_setup_plan(
        default_config(),
        options=SetupOptions(
            include_models=False,
            selected_tools=("ffmpeg",),
            system="Darwin",
        ),
    )

    assert linux["actions"][0]["user_commands"] == ["sudo apt-get update && sudo apt-get install -y ffmpeg"]
    assert windows["actions"][0]["user_commands"] == ["winget install Gyan.FFmpeg"]
    assert mac["actions"][0]["user_commands"] == ["brew install ffmpeg"]


def test_tool_already_present_detection(monkeypatch) -> None:
    monkeypatch.setattr("all2text.external_setup.shutil.which", lambda name: f"/tools/{name}")

    action = package_tool_action("ffmpeg", "ffmpeg", "linux", "ffmpeg", tools=("ffmpeg", "ffprobe"))

    assert action.status == "satisfied"
    assert action.detected_path == "/tools/ffmpeg"


def test_missing_tool_blocker_reporting(monkeypatch) -> None:
    monkeypatch.setattr("all2text.external_setup.shutil.which", lambda name: None)

    action = package_tool_action("radare2", "radare2", "linux", "radare2", tools=("radare2",))

    assert action.status == "blocked"
    assert "sudo apt-get install -y radare2" in action.user_commands[0]
    assert action.blockers


def test_interactive_setup_prompt_yes_runs_safe_action(monkeypatch, tmp_path: Path) -> None:
    def fake_which(name: str) -> str | None:
        return f"/usr/bin/{name}" if name in {"git", "cmake", "make", "g++"} else None

    monkeypatch.setattr("all2text.external_setup.shutil.which", fake_which)
    monkeypatch.setattr("all2text.external_setup.probe_endpoints", lambda endpoints, timeout: [])
    monkeypatch.setattr(
        "all2text.external_setup.run_action",
        lambda action, options: {"id": action.id, "status": "installed"},
    )

    report = execute_setup(
        default_config(),
        options=SetupOptions(
            include_models=False,
            selected_tools=("whisper_cpp",),
            tools_dir=str(tmp_path / "tools"),
        ),
        input_stream=TtyBuffer("yes\n"),
        output_stream=TtyBuffer(),
    )

    assert report["status"] == "completed"
    assert report["results"] == [{"id": "whisper_cpp", "status": "installed"}]


def test_interactive_setup_prompt_no_cancels(monkeypatch, tmp_path: Path) -> None:
    def fake_which(name: str) -> str | None:
        return f"/usr/bin/{name}" if name in {"git", "cmake", "make", "g++"} else None

    monkeypatch.setattr("all2text.external_setup.shutil.which", fake_which)
    monkeypatch.setattr("all2text.external_setup.probe_endpoints", lambda endpoints, timeout: [])

    report = execute_setup(
        default_config(),
        options=SetupOptions(
            include_models=False,
            selected_tools=("whisper_cpp",),
            tools_dir=str(tmp_path / "tools"),
        ),
        input_stream=TtyBuffer("no\n"),
        output_stream=TtyBuffer(),
    )

    assert report["status"] == "cancelled"
    assert report["results"] == []


def test_noninteractive_setup_never_hangs(monkeypatch, tmp_path: Path) -> None:
    def fake_which(name: str) -> str | None:
        return f"/usr/bin/{name}" if name in {"git", "cmake", "make", "g++"} else None

    monkeypatch.setattr("all2text.external_setup.shutil.which", fake_which)
    monkeypatch.setattr("all2text.external_setup.probe_endpoints", lambda endpoints, timeout: [])

    report = execute_setup(
        default_config(),
        options=SetupOptions(
            include_models=False,
            selected_tools=("whisper_cpp",),
            tools_dir=str(tmp_path / "tools"),
        ),
        input_stream=io.StringIO(""),
        output_stream=io.StringIO(),
    )

    assert report["status"] == "not_run_noninteractive"
    assert "without --yes" in report["note"]


def test_setup_cli_dry_run_json(monkeypatch, capsys) -> None:
    monkeypatch.setattr("all2text.external_setup.probe_endpoints", lambda endpoints, timeout: [])

    assert main(["setup", "--dry-run", "--json", "--tools", "ffmpeg", "--skip-root"]) == 0
    report = json.loads(capsys.readouterr().out)

    assert report["schema"] == "all2text.setup_report.v1"
    assert report["status"] == "dry_run"
    assert [action["id"] for action in report["plan"]["actions"]] == ["ffmpeg"]


def test_model_detection_from_local_root(tmp_path: Path) -> None:
    snapshot = tmp_path / "models--Systran--faster-whisper-tiny"
    snapshot.mkdir()

    action = faster_whisper_action(
        "faster_whisper_tiny",
        "Systran/faster-whisper-tiny",
        tmp_path,
        heavy=False,
    )

    assert action.status == "satisfied"
    assert action.detected_path == str(snapshot)


def test_doctor_includes_setup_plan(monkeypatch, capsys) -> None:
    fake_setup = {
        "schema": "all2text.setup_plan.v1",
        "summary": {"safe_installable": ["whisper_cpp"]},
        "actions": [],
    }
    monkeypatch.setattr("all2text.cli.build_setup_plan", lambda config, options: fake_setup)

    assert main(["doctor", "--profile", "core"]) == 0
    report = json.loads(capsys.readouterr().out)

    assert report["setup"] == fake_setup


def test_python_module_setup_invocation_can_print_dry_run() -> None:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(Path.cwd() / "src")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "all2text",
            "setup",
            "--dry-run",
            "--json",
            "--tools",
            "ffmpeg",
            "--skip-root",
        ],
        cwd=str(Path.cwd()),
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["status"] == "dry_run"


def test_conversion_reports_setup_command_in_noninteractive_mode(monkeypatch, tmp_path: Path, capsys) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    (source / "note.txt").write_text("hello\n", encoding="utf-8")
    monkeypatch.setattr(
        "all2text.cli.setup_recommendation",
        lambda config: {
            "needed": True,
            "command": "python -m all2text setup --dry-run --profile full",
            "unavailable_enabled_providers": [{"name": "ocr"}],
        },
    )

    assert main(["--profile", "core", str(source), str(target)]) == 0
    captured = capsys.readouterr()

    assert "python -m all2text setup --dry-run --profile full" in captured.err


def test_config_accepts_setup_options() -> None:
    config = config_from_dict(
        {
            "run": {
                "interactive_setup_prompt": False,
                "setup_tools_dir": "/tmp/tools",
                "setup_models_dir": "/tmp/models",
                "setup_report_path": "/tmp/setup.json",
            }
        }
    )

    assert config.options.interactive_setup_prompt is False
    assert config.options.setup_tools_dir == "/tmp/tools"
    assert config.options.setup_models_dir == "/tmp/models"
    assert config.options.setup_report_path == "/tmp/setup.json"
