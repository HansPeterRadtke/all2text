from __future__ import annotations

import json
from pathlib import Path

from all2text.bootstrap import BootstrapOptions, build_bootstrap_plan
from all2text.cli import main
from all2text.config import default_config
from all2text.coverage import build_coverage_matrix, coverage_summary, platform_manifest
from all2text.external_setup import SetupOptions, build_setup_plan


def _action(action_id: str, status: str = "satisfied") -> dict[str, object]:
    return {"id": action_id, "status": status, "selected": True}


def test_jetson_installed_stack_has_no_missing_required_coverage() -> None:
    actions = [
        _action("ffmpeg"),
        _action("ffprobe"),
        _action("tesseract"),
        _action("file"),
        _action("libreoffice"),
        _action("docling"),
        _action("whisper_cpp"),
        _action("whisper_cpp_tiny"),
        _action("radare2"),
        _action("capa"),
        _action("deplot"),
        _action("unichart"),
        _action("llama_cpp"),
        _action("qwen_vl_gguf"),
    ]
    matrix = build_coverage_matrix(
        actions,
        {"normalized_system": "linux", "architecture": "aarch64", "is_jetson": True},
        profile="minimal",
        mode="minimal",
    )

    assert matrix["summary"]["missing_required"] == []
    assert matrix["summary"]["required_covered"] is True
    families = {family["id"]: family for family in matrix["families"]}
    assert families["office_pdf"]["selected_provider"] == "docling"
    assert families["audio"]["selected_provider"] == "whisper_cpp"
    assert families["binary_static"]["selected_provider"] == "radare2+capa"


def test_platform_manifest_marks_arm64_paddle_as_service_route() -> None:
    manifest = platform_manifest({"normalized_system": "linux", "architecture": "aarch64", "is_jetson": True})

    assert manifest["python_env_route"] == "isolated_python311_cpu_headless_on_jetson"
    assert any("PaddlePaddle" in note for note in manifest["warnings"])


def test_paddleocr_vl_arm64_is_container_or_service_not_local_install(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("all2text.external_setup.find_paths", lambda roots, patterns: [])
    monkeypatch.setattr("all2text.external_setup.python_module_available", lambda module: False)
    monkeypatch.setattr("all2text.external_setup.external_python_module_available", lambda path, module: False)
    monkeypatch.setattr(
        "all2text.external_setup.environment_metadata",
        lambda system, machine: {
            "normalized_system": "linux",
            "architecture": "aarch64",
            "is_jetson": True,
            "python_candidates": [{"executable": "/usr/bin/python3.11", "version": "3.11.8"}],
            "package_managers": ["apt-get"],
            "build_tools": {},
        },
    )

    plan = build_setup_plan(
        default_config(),
        options=SetupOptions(
            include_tools=False,
            selected_models=("paddleocr_vl",),
            tools_dir=str(tmp_path / "tools"),
            models_dir=str(tmp_path / "models"),
            system="Linux",
        ),
    )
    action = plan["actions"][0]

    assert action["id"] == "paddleocr_vl"
    assert action["installer"] == "container_or_service"
    assert action["metadata"]["local_install_supported"] is False
    assert action["safe_to_run"] is False


def test_bootstrap_plan_generates_posix_and_powershell_commands() -> None:
    plan = build_bootstrap_plan(
        BootstrapOptions(
            package=".",
            profile="full",
            mode="full",
            yes=True,
            noninteractive=True,
            python="python",
            system="Linux",
        )
    )

    assert "python -m pip install ." in plan["commands"]["posix_shell"]
    assert "ALL2TEXT_SETUP_ASSUME_YES=1" in plan["commands"]["posix_shell"]
    assert "$env:ALL2TEXT_SETUP_ASSUME_YES='1'" in plan["commands"]["windows_powershell"]
    assert plan["steps"][1][:4] == ["python", "-m", "all2text", "setup"]


def test_cli_bootstrap_json(capsys) -> None:
    assert main(["bootstrap", "--package", ".", "--yes", "--json", "--python", "python"]) == 0
    plan = json.loads(capsys.readouterr().out)

    assert plan["schema"] == "all2text.bootstrap_plan.v1"
    assert plan["options"]["package"] == "."
    assert plan["environment"]["ALL2TEXT_SETUP_ASSUME_YES"] == "1"


def test_setup_plan_includes_coverage_and_summary_prompt_uses_coverage(monkeypatch, tmp_path: Path) -> None:
    def fake_find_paths(roots, patterns):
        text = " ".join(patterns).lower()
        if "deplot" in text or "unichart" in text or "ggml-tiny" in text:
            return [str(tmp_path / "models" / "found")]
        return []

    docling_py = tmp_path / "tools" / "docling-env" / "bin" / "python"
    docling_py.parent.mkdir(parents=True)
    docling_py.write_text("#!/bin/sh\n", encoding="utf-8")
    monkeypatch.setattr("all2text.external_setup.find_paths", fake_find_paths)
    monkeypatch.setattr("all2text.external_setup.python_module_available", lambda module: False)
    monkeypatch.setattr("all2text.external_setup.external_python_module_available", lambda path, module: True)
    monkeypatch.setattr("all2text.external_setup.shutil.which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(
        "all2text.external_setup.probe_endpoints",
        lambda endpoints, timeout: [{"base_url": "http://127.0.0.1:14829/v1", "models": ["qwen"]}],
    )
    monkeypatch.setattr(
        "all2text.external_setup.environment_metadata",
        lambda system, machine: {
            "normalized_system": "linux",
            "architecture": "aarch64",
            "is_jetson": True,
            "python_candidates": [{"executable": "/usr/bin/python3.11", "version": "3.11.8"}],
            "package_managers": ["apt-get"],
            "build_tools": {},
        },
    )

    plan = build_setup_plan(
        default_config(),
        options=SetupOptions(
            tools_dir=str(tmp_path / "tools"),
            models_dir=str(tmp_path / "models"),
            selected_models=("minimal",),
            profile="minimal",
            mode="minimal",
            system="Linux",
        ),
    )

    assert plan["coverage"]["summary"]["missing_required"] == []
    assert plan["summary"]["required_coverage_missing"] == []
    assert plan["summary"]["coverage_required_covered"] is True


def test_capa_action_requires_rules_when_executable_exists(monkeypatch, tmp_path: Path) -> None:
    from all2text.external_setup import capa_action

    exe = tmp_path / "tools" / "capa-venv" / "bin" / "capa"
    exe.parent.mkdir(parents=True)
    exe.write_text("#!/bin/sh\n", encoding="utf-8")
    monkeypatch.setattr("all2text.external_setup.find_executable", lambda *args: str(exe))
    monkeypatch.setattr("all2text.external_setup.find_capa_rules", lambda tools_dir: None)
    monkeypatch.setattr("all2text.external_setup.shutil.which", lambda name: "/usr/bin/git" if name == "git" else None)
    monkeypatch.setattr(
        "all2text.external_setup.environment_metadata",
        lambda system, machine: {"python_candidates": [{"executable": "/usr/bin/python3.11", "version": "3.11.8"}]},
    )

    action = capa_action("linux", "aarch64", tmp_path / "tools")

    assert action.status == "installable"
    assert action.reason == "capa rules not found"
    assert action.commands[-1][:3] == ["git", "clone", "--depth"]


def test_capa_action_satisfied_when_rules_exist(monkeypatch, tmp_path: Path) -> None:
    from all2text.external_setup import capa_action

    exe = tmp_path / "tools" / "capa-venv" / "bin" / "capa"
    exe.parent.mkdir(parents=True)
    exe.write_text("#!/bin/sh\n", encoding="utf-8")
    rules = tmp_path / "tools" / "capa-rules"
    rules.mkdir(parents=True)
    (rules / "example.yml").write_text("rule:\n", encoding="utf-8")
    monkeypatch.setattr("all2text.external_setup.find_executable", lambda *args: str(exe))

    action = capa_action("linux", "aarch64", tmp_path / "tools")

    assert action.status == "satisfied"
    assert action.metadata["rules_path"] == str(rules)
