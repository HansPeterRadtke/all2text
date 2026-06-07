from __future__ import annotations

import io
import json
import os
import subprocess
import sys
from types import SimpleNamespace
from pathlib import Path

from all2text.backends.documents import convert_with_docling_subprocess, docling_external_python
from all2text.cli import main
from all2text.config import config_from_dict, default_config
from all2text.external_setup import (
    SetupAction,
    SetupOptions,
    action_command_timeout,
    build_setup_plan,
    capa_action,
    execute_setup,
    faster_whisper_action,
    package_tool_action,
    render_setup_prompt,
    run_command,
    setup_options_from_environment,
    summarize_last_setup_report,
)
from all2text.install_hook import run_install_hook
from all2text.providers import provider_statuses


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
    assert windows["actions"][0]["user_commands"] == [
        "winget install Gyan.FFmpeg",
        "choco install ffmpeg",
    ]
    assert mac["actions"][0]["user_commands"] == ["brew install ffmpeg"]
    assert linux["environment"]["architecture"]


def test_setup_options_from_environment_supports_assume_yes_and_modes() -> None:
    options = setup_options_from_environment(
        {
            "ALL2TEXT_SETUP_MODE": "full",
            "ALL2TEXT_SETUP_ASSUME_YES": "1",
            "ALL2TEXT_SETUP_SKIP_HEAVY": "0",
            "ALL2TEXT_SETUP_TOOLS": "whisper_cpp,capa",
            "ALL2TEXT_SETUP_MODELS": "faster_whisper_tiny",
            "ALL2TEXT_SETUP_NONINTERACTIVE": "1",
        }
    )

    assert options.mode == "full"
    assert options.profile == "full"
    assert options.yes is True
    assert options.skip_heavy is False
    assert options.noninteractive is True
    assert options.selected_tools == ("whisper_cpp", "capa")
    assert options.selected_models == ("faster_whisper_tiny",)


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


def test_capa_uses_detected_newer_python(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("all2text.external_setup.shutil.which", lambda name: None)
    monkeypatch.setattr(
        "all2text.external_setup.environment_metadata",
        lambda system, machine: {
            "normalized_system": "linux",
            "python_candidates": [{"executable": "/usr/bin/python3.11", "version": "3.11.8"}],
        },
    )

    action = capa_action("linux", "aarch64", tmp_path / "tools")

    assert action.status == "installable"
    assert action.safe_to_run is True
    assert action.commands[0][:3] == ["/usr/bin/python3.11", "-m", "venv"]


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
            report_path=str(tmp_path / "report.json"),
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
            report_path=str(tmp_path / "report.json"),
        ),
        input_stream=TtyBuffer("no\n"),
        output_stream=TtyBuffer(),
    )

    assert report["status"] == "cancelled"
    assert report["results"] == []
    assert json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))["status"] == "cancelled"


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
            report_path=str(tmp_path / "report.json"),
        ),
        input_stream=io.StringIO(""),
        output_stream=io.StringIO(),
    )

    assert report["status"] == "not_run_noninteractive"
    assert "ALL2TEXT_SETUP_ASSUME_YES" in report["note"]


def test_last_setup_report_summary_does_not_embed_full_plan() -> None:
    summary = summarize_last_setup_report(
        {
            "schema": "all2text.setup_report.v1",
            "status": "completed",
            "plan": {"large": "payload"},
            "plan_summary": {"counts": {"satisfied": 1}},
            "paths": {"report_path": "/tmp/report.json"},
            "results": [{"id": "capa", "status": "installed", "stdout": "long"}],
        }
    )

    assert summary == {
        "schema": "all2text.setup_report.v1",
        "status": "completed",
        "note": None,
        "plan_summary": {"counts": {"satisfied": 1}},
        "paths": {"report_path": "/tmp/report.json"},
        "results": [{"id": "capa", "status": "installed"}],
    }


def test_setup_prompt_lists_size_time_and_yes_no(monkeypatch, tmp_path: Path) -> None:
    def fake_which(name: str) -> str | None:
        return f"/usr/bin/{name}" if name in {"git", "cmake", "make", "g++"} else None

    monkeypatch.setattr("all2text.external_setup.shutil.which", fake_which)
    monkeypatch.setattr("all2text.external_setup.probe_endpoints", lambda endpoints, timeout: [])
    plan = build_setup_plan(
        default_config(),
        options=SetupOptions(
            include_models=False,
            selected_tools=("whisper_cpp",),
            tools_dir=str(tmp_path / "tools"),
        ),
    )
    action = plan["actions"][0]
    prompt = render_setup_prompt(plan, [SetupAction(**action)])

    assert "may take a few minutes" in prompt
    assert "Download/build these missing all2text external tools/models now? [y/N]" in prompt


def test_install_hook_noninteractive_writes_report(monkeypatch, tmp_path: Path) -> None:
    def fake_which(name: str) -> str | None:
        return f"/usr/bin/{name}" if name in {"git", "cmake", "make", "g++"} else None

    report_path = tmp_path / "setup-report.json"
    monkeypatch.setattr("all2text.external_setup.shutil.which", fake_which)
    monkeypatch.setattr("all2text.external_setup.probe_endpoints", lambda endpoints, timeout: [])

    report = run_install_hook(
        env={
            "ALL2TEXT_SETUP_MODE": "tools",
            "ALL2TEXT_SETUP_TOOLS": "whisper_cpp",
            "ALL2TEXT_SETUP_TOOLS_DIR": str(tmp_path / "tools"),
            "ALL2TEXT_SETUP_REPORT": str(report_path),
            "ALL2TEXT_SETUP_NONINTERACTIVE": "1",
        },
        input_stream=io.StringIO(""),
        output_stream=io.StringIO(),
    )

    assert report["status"] == "not_run_noninteractive"
    assert json.loads(report_path.read_text(encoding="utf-8"))["status"] == "not_run_noninteractive"


def test_install_hook_assume_yes_runs_safe_action(monkeypatch, tmp_path: Path) -> None:
    def fake_which(name: str) -> str | None:
        return f"/usr/bin/{name}" if name in {"git", "cmake", "make", "g++"} else None

    monkeypatch.setattr("all2text.external_setup.shutil.which", fake_which)
    monkeypatch.setattr("all2text.external_setup.probe_endpoints", lambda endpoints, timeout: [])
    monkeypatch.setattr(
        "all2text.external_setup.run_action",
        lambda action, options: {"id": action.id, "status": "installed"},
    )

    report = run_install_hook(
        env={
            "ALL2TEXT_SETUP_MODE": "tools",
            "ALL2TEXT_SETUP_TOOLS": "whisper_cpp",
            "ALL2TEXT_SETUP_TOOLS_DIR": str(tmp_path / "tools"),
            "ALL2TEXT_SETUP_ASSUME_YES": "1",
            "ALL2TEXT_SETUP_REPORT": str(tmp_path / "setup-report.json"),
        },
        input_stream=io.StringIO(""),
        output_stream=io.StringIO(),
    )

    assert report["status"] == "completed"
    assert report["results"] == [{"id": "whisper_cpp", "status": "installed"}]


def test_setup_result_failure_marks_report_failed(monkeypatch, tmp_path: Path) -> None:
    def fake_which(name: str) -> str | None:
        return f"/usr/bin/{name}" if name in {"git", "cmake", "make", "g++"} else None

    monkeypatch.setattr("all2text.external_setup.shutil.which", fake_which)
    monkeypatch.setattr("all2text.external_setup.probe_endpoints", lambda endpoints, timeout: [])
    monkeypatch.setattr(
        "all2text.external_setup.run_action",
        lambda action, options: {"id": action.id, "status": "failed", "error": "boom"},
    )

    report = execute_setup(
        default_config(),
        options=SetupOptions(
            include_models=False,
            selected_tools=("whisper_cpp",),
            tools_dir=str(tmp_path / "tools"),
            report_path=str(tmp_path / "report.json"),
            yes=True,
        ),
    )

    assert report["status"] == "failed"
    assert json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))["status"] == "failed"


def test_setup_cli_dry_run_json(monkeypatch, tmp_path: Path, capsys) -> None:
    monkeypatch.setattr("all2text.external_setup.probe_endpoints", lambda endpoints, timeout: [])

    assert main(
        [
            "setup",
            "--dry-run",
            "--json",
            "--tools",
            "ffmpeg",
            "--skip-root",
            "--report",
            str(tmp_path / "report.json"),
        ]
    ) == 0
    report = json.loads(capsys.readouterr().out)

    assert report["schema"] == "all2text.setup_report.v1"
    assert report["status"] == "dry_run"
    assert [action["id"] for action in report["plan"]["actions"]] == ["ffmpeg"]


def test_setup_cli_accepts_minimal_profile(monkeypatch, tmp_path: Path, capsys) -> None:
    monkeypatch.setattr("all2text.external_setup.probe_endpoints", lambda endpoints, timeout: [])

    assert main(
        [
            "setup",
            "--profile",
            "minimal",
            "--dry-run",
            "--json",
            "--report",
            str(tmp_path / "report.json"),
        ]
    ) == 0
    report = json.loads(capsys.readouterr().out)

    assert report["plan"]["profile"] == "minimal"
    assert report["plan"]["mode"] == "minimal"
    assert "faster_whisper_base" not in [action["id"] for action in report["plan"]["actions"]]


def test_docling_external_env_plan_uses_newer_python(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("all2text.external_setup.find_paths", lambda roots, patterns: [])
    monkeypatch.setattr("all2text.external_setup.python_module_available", lambda module: False)
    monkeypatch.setattr(
        "all2text.external_setup.environment_metadata",
        lambda system, machine: {
            "python_candidates": [{"executable": "/usr/bin/python3.11", "version": "3.11.8"}],
            "package_managers": [],
            "build_tools": {},
        },
    )

    plan = build_setup_plan(
        default_config(),
        options=SetupOptions(
            include_tools=False,
            selected_models=("docling",),
            models_dir=str(tmp_path / "models"),
            tools_dir=str(tmp_path / "tools"),
        ),
    )
    action = plan["actions"][0]

    assert action["id"] == "docling"
    assert action["status"] == "installable"
    assert action["safe_to_run"] is True
    assert action["commands"][0][:3] == ["/usr/bin/python3.11", "-m", "venv"]


def test_large_external_env_uses_longer_timeout(monkeypatch) -> None:
    action = SetupAction(
        id="docling",
        category="model",
        name="Docling",
        status="installable",
        installer="external_env_or_service",
        heavy=True,
        time_note="can take a long time or hours",
    )

    assert action_command_timeout(action) == 14_400
    monkeypatch.setenv("ALL2TEXT_SETUP_COMMAND_TIMEOUT_SECONDS", "90")
    assert action_command_timeout(action) == 90


def test_run_command_timeout_returns_structured_failure() -> None:
    result = run_command(
        [sys.executable, "-c", "import time; time.sleep(2)"],
        timeout=1,
    )

    assert result["returncode"] == -1
    assert "timed out after 1 seconds" in result["stderr"]


def test_docling_external_python_uses_setup_tools_dir(tmp_path: Path) -> None:
    python = tmp_path / "tools" / "docling-env" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.write_text("#!/bin/sh\n", encoding="utf-8")
    config = config_from_dict(
        {
            "run": {"setup_tools_dir": str(tmp_path / "tools")},
            "providers": {
                "document_intelligence": {
                    "name": "docling",
                    "enabled": True,
                    "auto_invoke": True,
                }
            },
        }
    )

    assert docling_external_python(config) == python


def test_docling_external_python_accepts_windows_venv_layout(tmp_path: Path) -> None:
    python = tmp_path / "tools" / "docling-env" / "Scripts" / "python.exe"
    python.parent.mkdir(parents=True)
    python.write_text("", encoding="utf-8")
    config = config_from_dict(
        {
            "run": {"setup_tools_dir": str(tmp_path / "tools")},
            "providers": {
                "document_intelligence": {
                    "name": "docling",
                    "enabled": True,
                    "auto_invoke": True,
                }
            },
        }
    )

    assert docling_external_python(config) == python


def test_docling_provider_status_uses_setup_tools_dir(monkeypatch, tmp_path: Path) -> None:
    python = tmp_path / "tools" / "docling-env" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.write_text("#!/bin/sh\n", encoding="utf-8")
    config = config_from_dict(
        {
            "run": {"setup_tools_dir": str(tmp_path / "tools")},
            "providers": {
                "document_intelligence": {
                    "name": "docling",
                    "enabled": True,
                    "auto_invoke": True,
                }
            },
        }
    )
    monkeypatch.setattr("all2text.providers.python_module_available", lambda module: False)
    monkeypatch.setattr("all2text.providers.external_python_module_available", lambda path, module: True)

    status = next(item for item in provider_statuses(config) if item.name == "document_intelligence")

    assert status.available is True
    assert status.source == str(python)
    assert status.details["external_python"] == str(python)


def test_docling_provider_status_accepts_windows_venv_layout(monkeypatch, tmp_path: Path) -> None:
    python = tmp_path / "tools" / "docling-env" / "Scripts" / "python.exe"
    python.parent.mkdir(parents=True)
    python.write_text("", encoding="utf-8")
    config = config_from_dict(
        {
            "run": {"setup_tools_dir": str(tmp_path / "tools")},
            "providers": {
                "document_intelligence": {
                    "name": "docling",
                    "enabled": True,
                    "auto_invoke": True,
                }
            },
        }
    )
    monkeypatch.setattr("all2text.providers.python_module_available", lambda module: False)
    monkeypatch.setattr("all2text.providers.external_python_module_available", lambda path, module: True)

    status = next(item for item in provider_statuses(config) if item.name == "document_intelligence")

    assert status.available is True
    assert status.source == str(python)
    assert status.lifecycle["dependency_found"] is True


def test_docling_subprocess_bridge_parses_json(monkeypatch, tmp_path: Path) -> None:
    def fake_run(*args, **kwargs):
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"text": "hello", "export_method": "export_to_markdown"}),
            stderr="",
        )

    monkeypatch.setattr("all2text.backends.documents.subprocess.run", fake_run)

    result = convert_with_docling_subprocess(
        tmp_path / "docling-env" / "bin" / "python",
        tmp_path / "doc.pdf",
        timeout_seconds=5,
    )

    assert result == {"text": "hello", "export_method": "export_to_markdown"}


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


def test_python_module_setup_invocation_can_print_dry_run(tmp_path: Path) -> None:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(Path.cwd() / "src")
    env["ALL2TEXT_SETUP_REPORT"] = str(tmp_path / "setup-report.json")
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
