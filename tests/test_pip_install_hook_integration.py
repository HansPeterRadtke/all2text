from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def _venv_python(venv: Path) -> Path:
    return venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def test_source_pip_install_invokes_setup_hook_dry_run(tmp_path: Path) -> None:
    venv = tmp_path / "venv"
    subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True, timeout=120)
    python = _venv_python(venv)
    subprocess.run(
        [str(python), "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=180,
    )
    report = tmp_path / "hook-report.json"
    env = dict(os.environ)
    env.update(
        {
            "ALL2TEXT_SETUP_MODE": "plan",
            "ALL2TEXT_SETUP_REPORT": str(report),
            "ALL2TEXT_SETUP_NONINTERACTIVE": "1",
            "PIP_DISABLE_PIP_VERSION_CHECK": "1",
        }
    )
    result = subprocess.run(
        [str(python), "-m", "pip", "install", "--no-deps", "--no-build-isolation", str(Path.cwd())],
        cwd=str(tmp_path),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=240,
        check=False,
    )

    assert result.returncode == 0, result.stdout[-2000:] + result.stderr[-2000:]
    assert report.exists(), result.stdout[-2000:] + result.stderr[-2000:]
    data = json.loads(report.read_text(encoding="utf-8"))
    assert data["status"] == "dry_run"
    assert data["schema"] == "all2text.setup_report.v1"
    assert data["options"]["source"] in {"bdist_wheel", "setuptools_install", "pip_install"}
