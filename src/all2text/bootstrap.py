from __future__ import annotations

import os
import platform
import shlex
import subprocess
import sys
from dataclasses import asdict, dataclass
from typing import Any


BOOTSTRAP_SCHEMA = "all2text.bootstrap_plan.v1"


@dataclass(frozen=True)
class BootstrapOptions:
    package: str = "all2text"
    profile: str = "full"
    mode: str = "full"
    yes: bool = False
    noninteractive: bool = False
    skip_heavy: bool = False
    skip_models: bool = False
    python: str = ""
    system: str | None = None


def build_bootstrap_plan(options: BootstrapOptions | None = None) -> dict[str, Any]:
    opts = options or BootstrapOptions()
    system = (opts.system or platform.system()).lower()
    python_cmd = opts.python or sys.executable or "python"
    env = {
        "ALL2TEXT_SETUP_MODE": opts.mode or opts.profile,
        "ALL2TEXT_SETUP_PROFILE": opts.profile,
    }
    if opts.yes:
        env["ALL2TEXT_SETUP_ASSUME_YES"] = "1"
    if opts.noninteractive:
        env["ALL2TEXT_SETUP_NONINTERACTIVE"] = "1"
    if opts.skip_heavy:
        env["ALL2TEXT_SETUP_SKIP_HEAVY"] = "1"
    if opts.skip_models:
        env["ALL2TEXT_SETUP_SKIP_MODELS"] = "1"
    pip_step = [python_cmd, "-m", "pip", "install", opts.package]
    setup_step = [python_cmd, "-m", "all2text", "setup", "--profile", opts.profile]
    if opts.yes:
        setup_step.append("--yes")
    if opts.noninteractive:
        setup_step.append("--noninteractive")
    if opts.skip_heavy:
        setup_step.append("--skip-heavy")
    if opts.skip_models:
        setup_step.append("--skip-models")
    shell = linux_shell_command(env, pip_step, setup_step)
    powershell = windows_powershell_command(env, pip_step, setup_step)
    return {
        "schema": BOOTSTRAP_SCHEMA,
        "platform": {"system": system, "python": python_cmd},
        "options": asdict(opts),
        "environment": env,
        "steps": [pip_step, setup_step],
        "commands": {
            "posix_shell": shell,
            "windows_powershell": powershell,
            "recommended": powershell if system.startswith("windows") else shell,
        },
        "notes": [
            "Source installs can run the setup hook when pip invokes the setuptools backend.",
            "Wheel installs cannot run arbitrary postinstall machine provisioning, so the bootstrap command runs pip install and all2text setup in one flow.",
            "Noninteractive mode never prompts; yes-to-all is controlled by ALL2TEXT_SETUP_ASSUME_YES=1 or --yes.",
        ],
    }


def linux_shell_command(env: dict[str, str], pip_step: list[str], setup_step: list[str]) -> str:
    prefix = " ".join(f"{key}={shlex.quote(value)}" for key, value in env.items())
    return f"{prefix} {quote_command(pip_step)} && {prefix} {quote_command(setup_step)}"


def windows_powershell_command(env: dict[str, str], pip_step: list[str], setup_step: list[str]) -> str:
    assignments = "; ".join(f"$env:{key}='{value.replace(chr(39), chr(39)+chr(39))}'" for key, value in env.items())
    return f"{assignments}; {quote_powershell(pip_step)}; if ($LASTEXITCODE -eq 0) {{ {quote_powershell(setup_step)} }}"


def quote_command(command: list[str]) -> str:
    return " ".join(shlex.quote(str(part)) for part in command)


def quote_powershell(command: list[str]) -> str:
    return " ".join(powershell_quote(str(part)) for part in command)


def powershell_quote(value: str) -> str:
    if not value or any(ch.isspace() or ch in "'\";&|()" for ch in value):
        return "'" + value.replace("'", "''") + "'"
    return value


def render_bootstrap_text(plan: dict[str, Any]) -> str:
    commands = plan.get("commands") or {}
    lines = [
        "all2text bootstrap plan",
        f"Package: {(plan.get('options') or {}).get('package')}",
        f"Profile: {(plan.get('options') or {}).get('profile')}",
        "",
        "Recommended one-command install:",
        str(commands.get("recommended") or ""),
        "",
        "Windows PowerShell:",
        str(commands.get("windows_powershell") or ""),
    ]
    return "\n".join(lines).rstrip() + "\n"


def execute_bootstrap(plan: dict[str, Any]) -> dict[str, Any]:
    env = dict(os.environ)
    env.update({str(k): str(v) for k, v in (plan.get("environment") or {}).items()})
    results = []
    for step in plan.get("steps") or []:
        completed = subprocess.run(
            [str(part) for part in step],
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        results.append(
            {
                "command": [str(part) for part in step],
                "returncode": completed.returncode,
                "stdout": completed.stdout[-4000:],
                "stderr": completed.stderr[-4000:],
            }
        )
        if completed.returncode != 0:
            break
    return {
        "schema": "all2text.bootstrap_report.v1",
        "status": "completed" if results and all(result["returncode"] == 0 for result in results) else "failed",
        "plan": plan,
        "results": results,
    }
