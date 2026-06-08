from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

from all2text.config import All2TextConfig, config_for_context


SETUP_REPORT_SCHEMA = "all2text.setup_report.v1"
DEFAULT_ENDPOINTS = (
    "http://127.0.0.1:14829/v1",
    "http://127.0.0.1:14830/v1",
    "http://127.0.0.1:8080/v1",
    "http://127.0.0.1:8000/v1",
    "http://127.0.0.1:1234/v1",
    "http://127.0.0.1:11434/v1",
)
TRUE_VALUES = {"1", "true", "yes", "on"}
FALSE_VALUES = {"0", "false", "no", "off"}
SETUP_MODES = {"minimal", "full", "tools", "models", "plan", "skip"}
PIP_SETUP_DEFAULT_MODE = "minimal"


@dataclass(frozen=True)
class SetupOptions:
    profile: str = "full"
    mode: str = "full"
    include_tools: bool = True
    include_models: bool = True
    selected_tools: tuple[str, ...] = ()
    selected_models: tuple[str, ...] = ()
    dry_run: bool = False
    json_output: bool = False
    yes: bool = False
    noninteractive: bool = False
    skip_root: bool = False
    skip_heavy: bool = False
    skip_models: bool = False
    strict: bool = False
    source: str = "cli"
    target: str = ""
    tools_dir: str = ""
    models_dir: str = ""
    report_path: str = ""
    system: str | None = None


@dataclass
class SetupAction:
    id: str
    category: str
    name: str
    status: str
    reason: str = ""
    detected_path: str | None = None
    commands: list[list[str]] = field(default_factory=list)
    user_commands: list[str] = field(default_factory=list)
    target_path: str | None = None
    installer: str = ""
    heavy: bool = False
    selected: bool = True
    safe_to_run: bool = False
    blockers: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    approx_size: str = ""
    time_note: str = ""
    confirmation: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def default_tools_dir() -> Path:
    if os.environ.get("ALL2TEXT_TOOLS_DIR"):
        return Path(os.environ["ALL2TEXT_TOOLS_DIR"]).expanduser()
    if Path("/data").exists():
        return Path("/data/opt/all2text-tools")
    return Path.home() / ".local" / "share" / "all2text" / "tools"


def default_models_dir() -> Path:
    if os.environ.get("ALL2TEXT_MODELS_DIR"):
        return Path(os.environ["ALL2TEXT_MODELS_DIR"]).expanduser()
    if Path("/data").exists():
        return Path("/data/models/all2text")
    return Path.home() / ".local" / "share" / "all2text" / "models"


def default_report_path() -> Path:
    if os.environ.get("ALL2TEXT_SETUP_REPORT"):
        return Path(os.environ["ALL2TEXT_SETUP_REPORT"]).expanduser()
    state_root = Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local" / "state"))).expanduser()
    return state_root / "all2text" / "setup-report.json"


def setup_options_from_environment(
    env: dict[str, str] | None = None,
    *,
    source: str = "pip_install",
    default_mode: str = PIP_SETUP_DEFAULT_MODE,
) -> SetupOptions:
    """Build setup options from environment variables accepted by pip and CI."""

    values = env if env is not None else os.environ
    mode = normalize_setup_mode(values.get("ALL2TEXT_SETUP_MODE"), default=default_mode)
    profile = values.get("ALL2TEXT_SETUP_PROFILE") or ("full" if mode == "full" else "minimal")
    if profile == "all":
        profile = "full"
    tools_only = env_bool(values, "ALL2TEXT_SETUP_TOOLS_ONLY", False) or mode == "tools"
    models_only = env_bool(values, "ALL2TEXT_SETUP_MODELS_ONLY", False) or mode == "models"
    include_tools = not models_only
    include_models = not tools_only
    if env_bool(values, "ALL2TEXT_SETUP_SKIP_MODELS", False):
        include_models = False
    selected_tools = split_env_selectors(values.get("ALL2TEXT_SETUP_TOOLS"))
    selected_models = split_env_selectors(values.get("ALL2TEXT_SETUP_MODELS"))
    if mode == "minimal" and include_models and not selected_models:
        selected_models = ("minimal",)
    dry_run = env_bool(values, "ALL2TEXT_SETUP_DRY_RUN", False) or mode == "plan"
    yes = (
        env_bool(values, "ALL2TEXT_SETUP_ASSUME_YES", False)
        or env_bool(values, "ALL2TEXT_SETUP_YES", False)
    )
    default_skip_heavy = mode != "full"
    return SetupOptions(
        profile=profile,
        mode=mode,
        include_tools=include_tools,
        include_models=include_models,
        selected_tools=selected_tools,
        selected_models=selected_models,
        dry_run=dry_run,
        yes=yes,
        noninteractive=(
            env_bool(values, "ALL2TEXT_SETUP_NONINTERACTIVE", False)
            or env_bool(values, "ALL2TEXT_SETUP_NO_PROMPT", False)
        ),
        skip_root=env_bool(values, "ALL2TEXT_SETUP_SKIP_ROOT", False),
        skip_heavy=env_bool(values, "ALL2TEXT_SETUP_SKIP_HEAVY", default_skip_heavy),
        skip_models=not include_models,
        strict=env_bool(values, "ALL2TEXT_SETUP_STRICT", False),
        source=source,
        target=values.get("ALL2TEXT_SETUP_TARGET", ""),
        tools_dir=values.get("ALL2TEXT_TOOLS_DIR", "") or values.get("ALL2TEXT_SETUP_TOOLS_DIR", ""),
        models_dir=values.get("ALL2TEXT_MODELS_DIR", "") or values.get("ALL2TEXT_SETUP_MODELS_DIR", ""),
        report_path=values.get("ALL2TEXT_SETUP_REPORT", ""),
    )


def normalize_setup_mode(value: str | None, *, default: str) -> str:
    normalized = str(value or default).strip().lower().replace("_", "-")
    aliases = {
        "": default,
        "0": "skip",
        "off": "skip",
        "none": "skip",
        "no": "skip",
        "false": "skip",
        "1": "minimal",
        "yes": "minimal",
        "all": "full",
        "dry-run": "plan",
        "dryrun": "plan",
    }
    normalized = aliases.get(normalized, normalized).replace("-", "_")
    return normalized if normalized in SETUP_MODES else default


def env_bool(env: dict[str, str], key: str, default: bool) -> bool:
    value = env.get(key)
    if value is None:
        return default
    normalized = str(value).strip().lower()
    if normalized in TRUE_VALUES:
        return True
    if normalized in FALSE_VALUES:
        return False
    return default


def split_env_selectors(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(part for part in value.replace(",", " ").split() if part)


def setup_paths(options: SetupOptions, config: All2TextConfig | None = None) -> dict[str, str]:
    cfg = config_for_context(config)
    target = Path(options.target).expanduser() if options.target else None
    configured_tools = str(getattr(cfg.options, "setup_tools_dir", "") or "")
    configured_models = str(getattr(cfg.options, "setup_models_dir", "") or "")
    configured_report = str(getattr(cfg.options, "setup_report_path", "") or "")
    tools_text = options.tools_dir or configured_tools
    models_text = options.models_dir or configured_models
    tools_dir = Path(tools_text).expanduser() if tools_text else None
    models_dir = Path(models_text).expanduser() if models_text else None
    return {
        "tools_dir": str(tools_dir or (target / "tools" if target else default_tools_dir())),
        "models_dir": str(models_dir or (target / "models" if target else default_models_dir())),
        "report_path": str(
            Path(options.report_path or configured_report).expanduser()
            if (options.report_path or configured_report)
            else default_report_path()
        ),
    }


def build_setup_plan(
    config: All2TextConfig | None = None,
    *,
    options: SetupOptions | None = None,
) -> dict[str, Any]:
    cfg = config_for_context(config)
    opts = options or SetupOptions()
    paths = setup_paths(opts, cfg)
    system = (opts.system or platform.system()).lower()
    machine = platform.machine()
    environment = environment_metadata(system, machine)
    tools_dir = Path(paths["tools_dir"])
    models_dir = Path(paths["models_dir"])
    tool_actions = build_tool_actions(cfg, opts, system, machine, tools_dir)
    model_actions = build_model_actions(opts, system, machine, models_dir, tools_dir, environment)
    if opts.skip_models:
        model_actions = []
    actions = []
    if opts.include_tools:
        actions.extend(tool_actions)
    if opts.include_models and not opts.skip_models:
        actions.extend(model_actions)
    selected = [action for action in actions if action.selected]
    return {
        "schema": "all2text.setup_plan.v1",
        "platform": {
            "system": platform.system() if opts.system is None else opts.system,
            "machine": machine,
            "python": sys.version.split()[0],
            "python_executable": sys.executable,
        },
        "environment": environment,
        "profile": opts.profile,
        "mode": opts.mode,
        "paths": paths,
        "actions": [action.to_dict() for action in selected],
        "summary": setup_summary(selected),
        "last_report": summarize_last_setup_report(load_last_setup_report(paths["report_path"])),
        "notes": [
            "Source/legacy pip installs invoke the all2text setup hook when the build backend runs.",
            "Wheel installs cannot run arbitrary postinstall code; all2text setup remains the rerunnable manual path.",
            "Noninteractive installs never prompt. Use ALL2TEXT_SETUP_ASSUME_YES=1 or all2text setup --yes for automation.",
        ],
    }


def environment_metadata(system: str, machine: str) -> dict[str, Any]:
    package_managers = [
        name for name in ("apt-get", "dnf", "yum", "pacman", "zypper", "brew", "winget", "choco", "scoop")
        if shutil.which(name)
    ]
    build_tools = {
        name: bool(shutil.which(name))
        for name in ("git", "cmake", "make", "gcc", "g++", "clang", "cl", "ninja")
    }
    python_candidates = []
    for name in ("python3.12", "python3.11", "python3.10", "python3.9", "python"):
        executable = shutil.which(name)
        if executable:
            python_candidates.append({"executable": executable, "version": python_version(executable)})
    return {
        "normalized_system": system,
        "architecture": normalize_architecture(machine),
        "machine": machine,
        "is_jetson": is_jetson(),
        "nvidia": {
            "nvidia_smi": bool(shutil.which("nvidia-smi")),
            "nvcc": bool(shutil.which("nvcc")),
            "cuda_root": str(Path("/usr/local/cuda")) if Path("/usr/local/cuda").exists() else "",
        },
        "package_managers": package_managers,
        "build_tools": build_tools,
        "python_candidates": python_candidates,
        "external_env_managers": [
            name for name in ("conda", "mamba", "micromamba", "pipx") if shutil.which(name)
        ],
    }


def normalize_architecture(machine: str) -> str:
    value = machine.lower()
    if value in {"x86_64", "amd64"}:
        return "x86_64"
    if value in {"aarch64", "arm64"}:
        return "aarch64"
    if value.startswith("arm"):
        return "arm"
    return value or "unknown"


def is_jetson() -> bool:
    if Path("/etc/nv_tegra_release").exists():
        return True
    for path in (Path("/proc/device-tree/model"), Path("/proc/device-tree/compatible")):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore").lower()
        except Exception:
            continue
        if "jetson" in text or "tegra" in text:
            return True
    return False


def python_version(executable: str) -> str:
    try:
        completed = subprocess.run(
            [executable, "--version"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=2,
            check=False,
        )
    except Exception:
        return "unknown"
    return (completed.stdout or completed.stderr).strip().replace("Python ", "")


def setup_summary(actions: list[SetupAction]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for action in actions:
        counts[action.status] = counts.get(action.status, 0) + 1
    installable = [
        action.id for action in actions if action.status in {"installable", "missing"} and action.safe_to_run
    ]
    blocked = [action.id for action in actions if action.status == "blocked"]
    missing = [
        action.id for action in actions if action.status in {"missing", "blocked", "installable"}
    ]
    return {
        "counts": counts,
        "missing_or_installable": missing,
        "safe_installable": installable,
        "blocked": blocked,
        "prompt_recommended": bool(missing),
    }


def build_tool_actions(
    config: All2TextConfig,
    options: SetupOptions,
    system: str,
    machine: str,
    tools_dir: Path,
) -> list[SetupAction]:
    selectors = normalize_selectors(options.selected_tools)
    actions = [
        package_tool_action("ffmpeg", "ffmpeg", system, "ffmpeg", tools=("ffmpeg", "ffprobe")),
        package_tool_action("ffprobe", "ffprobe", system, "ffmpeg", tools=("ffprobe",)),
        package_tool_action("tesseract", "tesseract", system, "tesseract-ocr", tools=("tesseract",)),
        package_tool_action("file", "file", system, "file", tools=("file",)),
        package_tool_action("getfacl", "getfacl", system, "acl", tools=("getfacl",)),
        package_tool_action("libreoffice", "libreoffice", system, "libreoffice", tools=("libreoffice",)),
        whisper_cpp_action(system, machine, tools_dir),
        llama_cpp_action(system, machine, tools_dir),
        radare2_action(system, machine, tools_dir),
        capa_action(system, machine, tools_dir),
    ]
    for action in actions:
        action.selected = selector_matches(action.id, selectors)
        if options.skip_root and action.installer == "system_package" and action.status != "satisfied":
            action.status = "blocked"
            action.reason = "root/system package installation skipped"
            action.safe_to_run = False
            action.blockers.append("Run with root privileges or install manually using the listed command.")
        if options.skip_heavy and action.heavy and action.status != "satisfied":
            action.status = "blocked"
            action.reason = "heavy build skipped"
            action.safe_to_run = False
            action.blockers.append("Re-run without --skip-heavy and select this tool explicitly.")
    return actions


def package_tool_action(
    action_id: str,
    executable: str,
    system: str,
    package: str,
    *,
    tools: tuple[str, ...],
) -> SetupAction:
    detected = next((shutil.which(tool) for tool in tools if shutil.which(tool)), None)
    if detected:
        return SetupAction(
            id=action_id,
            category="tool",
            name=action_id,
            status="satisfied",
            detected_path=detected,
            reason="found on PATH",
            installer="system_package",
        )
    return SetupAction(
        id=action_id,
        category="tool",
        name=action_id,
        status="blocked",
        reason=f"{executable} not found on PATH",
        installer="system_package",
        safe_to_run=False,
        user_commands=system_install_commands(system, package),
        blockers=["Requires OS package manager/root or user installation outside all2text."],
        approx_size=package_size_note(package),
        time_note="usually a few minutes with the OS package manager",
        confirmation="manual_root",
    )


def system_install_command(system: str, package: str) -> str:
    commands = system_install_commands(system, package)
    return commands[0] if commands else ""


def system_install_commands(system: str, package: str) -> list[str]:
    if system.startswith("linux"):
        return [f"sudo apt-get update && sudo apt-get install -y {package}"]
    if system.startswith("darwin"):
        return [f"brew install {package}"]
    if system.startswith("windows"):
        winget_ids = {
            "ffmpeg": "Gyan.FFmpeg",
            "tesseract-ocr": "UB-Mannheim.TesseractOCR",
            "libreoffice": "TheDocumentFoundation.LibreOffice",
            "radare2": "radareorg.radare2",
        }
        choco_ids = {
            "ffmpeg": "ffmpeg",
            "tesseract-ocr": "tesseract",
            "libreoffice": "libreoffice-fresh",
            "radare2": "radare2",
        }
        return [
            f"winget install {winget_ids.get(package, package)}",
            f"choco install {choco_ids.get(package, package)}",
        ]
    return []


def package_size_note(package: str) -> str:
    if package == "libreoffice":
        return "large desktop suite"
    if package in {"ffmpeg", "tesseract-ocr"}:
        return "tens to hundreds of MB depending on OS packages"
    return "small to moderate OS package"


def whisper_cpp_action(system: str, machine: str, tools_dir: Path) -> SetupAction:
    detected = find_executable(
        "whisper-cli",
        "whisper.cpp",
        "whisper_cpp",
        tools_dir / "whisper.cpp" / "build" / "bin" / "whisper-cli",
        tools_dir / "whisper.cpp" / "main",
    )
    if detected:
        return SetupAction(
            id="whisper_cpp",
            category="tool",
            name="whisper.cpp",
            status="satisfied",
            detected_path=detected,
            reason="whisper.cpp executable found",
            installer="user_source_build",
        )
    blockers = []
    if not system.startswith(("linux", "darwin")):
        blockers.append("User-space source build is implemented for Linux/macOS only.")
    for tool in ("git", "cmake", "make", "g++"):
        if not shutil.which(tool):
            blockers.append(f"missing build tool: {tool}")
    status = "blocked" if blockers else "installable"
    return SetupAction(
        id="whisper_cpp",
        category="tool",
        name="whisper.cpp",
        status=status,
        reason="whisper.cpp executable not found",
        target_path=str(tools_dir / "whisper.cpp"),
        installer="user_source_build",
        safe_to_run=not blockers,
        blockers=blockers,
        approx_size="small source checkout plus build artifacts",
        time_note="may take a few minutes on small ARM machines",
        confirmation="safe_user_space",
        commands=[
            [
                "git",
                "clone",
                "--depth",
                "1",
                "https://github.com/ggml-org/whisper.cpp.git",
                str(tools_dir / "whisper.cpp"),
            ],
            [
                "cmake",
                "-S",
                str(tools_dir / "whisper.cpp"),
                "-B",
                str(tools_dir / "whisper.cpp" / "build"),
                "-DWHISPER_BUILD_TESTS=OFF",
            ],
            ["cmake", "--build", str(tools_dir / "whisper.cpp" / "build"), "--config", "Release", "-j2"],
        ],
        notes=[f"Jetson/aarch64 detected as {machine}; default build is CPU/user-space."],
    )


def llama_cpp_action(system: str, machine: str, tools_dir: Path) -> SetupAction:
    endpoints = probe_endpoints(DEFAULT_ENDPOINTS, timeout=0.3)
    detected = find_executable(
        "llama-server",
        "llama-cli",
        "main",
        tools_dir / "llama.cpp" / "build" / "bin" / "llama-server",
        tools_dir / "llama.cpp" / "build" / "bin" / "llama-cli",
    )
    if detected or endpoints:
        return SetupAction(
            id="llama_cpp",
            category="tool",
            name="llama.cpp",
            status="satisfied",
            detected_path=detected,
            reason="llama.cpp executable or OpenAI-compatible local endpoint found",
            installer="user_source_build",
            metadata={"reachable_endpoints": endpoints},
        )
    blockers = []
    if not system.startswith(("linux", "darwin")):
        blockers.append("User-space source build is implemented for Linux/macOS only.")
    for tool in ("git", "cmake", "make", "g++"):
        if not shutil.which(tool):
            blockers.append(f"missing build tool: {tool}")
    return SetupAction(
        id="llama_cpp",
        category="tool",
        name="llama.cpp",
        status="blocked" if blockers else "installable",
        reason="llama.cpp executable and local endpoints not found",
        target_path=str(tools_dir / "llama.cpp"),
        installer="user_source_build",
        safe_to_run=not blockers,
        heavy=True,
        blockers=blockers,
        approx_size="source checkout plus C++ build artifacts",
        time_note="can take a long time on CPU-only ARM systems",
        confirmation="heavy_user_space",
        commands=[
            ["git", "clone", "--depth", "1", "https://github.com/ggml-org/llama.cpp.git", str(tools_dir / "llama.cpp")],
            [
                "cmake",
                "-S",
                str(tools_dir / "llama.cpp"),
                "-B",
                str(tools_dir / "llama.cpp" / "build"),
                "-DGGML_CUDA=OFF",
                "-DLLAMA_CURL=OFF",
            ],
            ["cmake", "--build", str(tools_dir / "llama.cpp" / "build"), "--config", "Release", "-j2"],
        ],
        notes=[
            f"Jetson/aarch64 detected as {machine}; CUDA/GPU build is intentionally not guessed.",
            "Use an explicit llama.cpp CUDA build outside setup if GPU flags are required.",
        ],
    )


def radare2_action(system: str, machine: str, tools_dir: Path) -> SetupAction:
    detected = find_executable("radare2", "r2", "rabin2")
    if detected:
        return SetupAction(
            id="radare2",
            category="tool",
            name="radare2",
            status="satisfied",
            detected_path=detected,
            reason="radare2/rabin2 found",
            installer="system_package",
        )
    return SetupAction(
        id="radare2",
        category="tool",
        name="radare2",
        status="blocked",
        reason="radare2/rabin2 not found",
        installer="system_package",
        user_commands=system_install_commands(system, "radare2"),
        blockers=[
            "radare2 source builds are not run automatically because they are long and system-sensitive.",
            "Install with the OS package manager or provide tools.radare2.path in config.",
        ],
        approx_size="moderate OS package or long source build",
        time_note="package install is usually minutes; source build can take much longer",
        confirmation="manual_root_or_explicit_source",
        metadata={"machine": machine, "suggested_user_dir": str(tools_dir / "radare2")},
    )


def capa_action(system: str, machine: str, tools_dir: Path) -> SetupAction:
    env_dir = tools_dir / "capa-venv"
    detected = find_executable(
        "capa",
        env_dir / "bin" / "capa",
        env_dir / "Scripts" / "capa.exe",
    )
    if detected:
        return SetupAction(
            id="capa",
            category="tool",
            name="capa",
            status="satisfied",
            detected_path=detected,
            reason="capa found on PATH",
            installer="python_venv",
        )
    blockers = []
    environment = environment_metadata(system, machine)
    python = sys.executable if sys.version_info >= (3, 9) else select_external_python(environment)
    if not python:
        blockers.append("current Python is < 3.9 and no Python 3.10/3.11 interpreter was detected")
    venv_python = external_venv_python(env_dir, system)
    return SetupAction(
        id="capa",
        category="tool",
        name="capa",
        status="blocked" if blockers else "installable",
        reason="capa executable not found",
        target_path=str(env_dir),
        installer="python_venv",
        safe_to_run=not blockers,
        blockers=blockers,
        approx_size="Python virtualenv with flare-capa dependencies",
        time_note="may take a few minutes when compatible wheels are available",
        confirmation="safe_user_space",
        commands=[
            [python or "python3.11", "-m", "venv", str(env_dir)],
            [str(venv_python), "-m", "pip", "install", "--upgrade", "pip"],
            [str(venv_python), "-m", "pip", "install", "flare-capa"],
        ],
        user_commands=[
            " ".join([python or "python3.11", "-m", "venv", str(env_dir)]),
            f"{venv_python} -m pip install --upgrade pip",
            f"{venv_python} -m pip install flare-capa",
        ],
        metadata={"machine": machine, "python": python, "python_candidates": environment.get("python_candidates")},
    )


def build_model_actions(
    options: SetupOptions,
    system: str,
    machine: str,
    models_dir: Path,
    tools_dir: Path,
    environment: dict[str, Any] | None = None,
) -> list[SetupAction]:
    selectors = normalize_model_selectors(options.selected_models, options.profile)
    env = environment or environment_metadata(system, machine)
    actions = [
        faster_whisper_action("faster_whisper_tiny", "Systran/faster-whisper-tiny", models_dir, heavy=False),
        faster_whisper_action("faster_whisper_base", "Systran/faster-whisper-base", models_dir, heavy=True),
        faster_whisper_action("faster_whisper_small", "Systran/faster-whisper-small", models_dir, heavy=True),
        whisper_cpp_model_action("whisper_cpp_tiny", "tiny", models_dir, tools_dir, heavy=False),
        whisper_cpp_model_action("whisper_cpp_base", "base", models_dir, tools_dir, heavy=True),
        detected_model_action(
            "qwen_text_gguf",
            "Qwen text GGUF",
            find_paths(("/data/models/gguf", "/data/models"), ("Qwen2.5*Instruct*.gguf",)),
            "Detected local Qwen text GGUF files; huge model downloads are never automatic.",
        ),
        detected_model_action(
            "qwen_vl_gguf",
            "Qwen2.5-VL GGUF/mmproj",
            find_paths(("/data/models/llama_cpp", "/data/models"), ("*Qwen2.5-VL*.gguf", "mmproj*Qwen2.5*.gguf")),
            "Detected local Qwen2.5-VL model/mmproj files; start a VLM llama-server separately.",
        ),
        detected_model_action(
            "deplot",
            "DePlot chart model",
            find_paths(
                ("/data/models/all2text", "/data/models"),
                ("*deplot*", "*DePlot*"),
            ),
            "Chart model detected; execution adapter remains contract-only until enabled.",
        ),
        detected_model_action(
            "unichart",
            "UniChart chart model",
            find_paths(
                ("/data/models/all2text", "/data/models"),
                ("*unichart*", "*UniChart*"),
            ),
            "Chart model detected; execution adapter remains contract-only until enabled.",
        ),
        heavy_model_blocker("chartgemma", "ChartGemma", models_dir),
        external_env_model_blocker(
            "paddleocr_vl",
            "PaddleOCR-VL",
            "Python 3.10/3.11 environment or container recommended",
            tools_dir,
            models_dir,
            env,
            packages=("paddleocr", "paddlepaddle"),
            huge=True,
        ),
        external_env_model_blocker(
            "glm_ocr",
            "GLM-OCR",
            "External service or Python 3.10/3.11 transformers environment recommended",
            tools_dir,
            models_dir,
            env,
            packages=("transformers", "accelerate", "sentencepiece"),
            huge=True,
        ),
        external_env_model_blocker(
            "olmocr",
            "olmOCR",
            "Separate Python 3.10/3.11 environment or service provider recommended",
            tools_dir,
            models_dir,
            env,
            packages=("olmocr",),
            huge=True,
        ),
        external_env_model_blocker(
            "docling",
            "Docling",
            "Separate Python 3.10/3.11 CPU environment may be required on Jetson",
            tools_dir,
            models_dir,
            env,
            packages=("docling==2.91.0",),
            huge=False,
        ),
    ]
    for action in actions:
        action.selected = selector_matches(action.id, selectors)
        if options.skip_heavy and action.heavy and action.status != "satisfied":
            action.status = "blocked"
            action.reason = "heavy model skipped"
            action.safe_to_run = False
            action.blockers.append("Re-run without --skip-heavy and select this model explicitly.")
        action.metadata.setdefault("system", system)
        action.metadata.setdefault("machine", machine)
    return actions


def faster_whisper_action(action_id: str, repo_id: str, models_dir: Path, *, heavy: bool) -> SetupAction:
    local = find_paths(
        (str(models_dir), "/data/models/all2text", "/data/models/faster_whisper"),
        (f"models--{repo_id.replace('/', '--')}*", repo_id.split("/")[-1]),
    )
    if local:
        return SetupAction(
            id=action_id,
            category="model",
            name=repo_id,
            status="satisfied",
            detected_path=local[0],
            reason="local faster-whisper snapshot found",
            installer="huggingface_hub",
            heavy=heavy,
        )
    target = models_dir / "faster_whisper"
    blockers = []
    if not python_module_available("huggingface_hub"):
        blockers.append("huggingface_hub is not installed")
    return SetupAction(
        id=action_id,
        category="model",
        name=repo_id,
        status="blocked" if blockers else "installable",
        reason="local faster-whisper snapshot not found",
        target_path=str(target),
        installer="huggingface_hub",
        safe_to_run=not blockers and not heavy,
        heavy=heavy,
        blockers=blockers,
        commands=[[sys.executable, "-m", "pip", "install", "huggingface_hub"]],
        notes=["Only tiny is considered a bounded default download; base/small require explicit selection."],
        approx_size=whisper_model_size_note(repo_id),
        time_note="may take a few minutes for tiny; larger variants can take longer",
        confirmation="bounded_default" if not heavy else "explicit_or_full",
        metadata={"repo_id": repo_id},
    )


def whisper_cpp_model_action(
    action_id: str,
    model_name: str,
    models_dir: Path,
    tools_dir: Path,
    *,
    heavy: bool,
) -> SetupAction:
    local = find_paths(
        (str(models_dir), "/data/models/all2text", "/data/models"),
        (f"ggml-{model_name}.bin", f"ggml-{model_name}.en.bin"),
    )
    if local:
        return SetupAction(
            id=action_id,
            category="model",
            name=f"whisper.cpp ggml {model_name}",
            status="satisfied",
            detected_path=local[0],
            reason="local whisper.cpp ggml model found",
            installer="whisper_cpp_download_script",
            heavy=heavy,
        )
    script = tools_dir / "whisper.cpp" / "models" / "download-ggml-model.sh"
    blockers = []
    if not script.exists():
        blockers.append("whisper.cpp download script not found; build/install whisper.cpp first")
    return SetupAction(
        id=action_id,
        category="model",
        name=f"whisper.cpp ggml {model_name}",
        status="blocked" if blockers else "installable",
        reason="local whisper.cpp ggml model not found",
        target_path=str(models_dir / "whisper.cpp"),
        installer="whisper_cpp_download_script",
        safe_to_run=not blockers and not heavy,
        heavy=heavy,
        blockers=blockers,
        commands=[["bash", str(script), model_name, str(models_dir / "whisper.cpp")]],
        notes=["Tiny is the bounded default; base requires explicit selection."],
        approx_size=whisper_cpp_size_note(model_name),
        time_note="may take a few minutes for tiny; base is larger",
        confirmation="bounded_default" if not heavy else "explicit_or_full",
        metadata={"model_name": model_name, "script": str(script)},
    )


def detected_model_action(action_id: str, name: str, matches: list[str], note: str) -> SetupAction:
    if matches:
        return SetupAction(
            id=action_id,
            category="model",
            name=name,
            status="satisfied",
            detected_path=matches[0],
            reason="local model files found",
            installer="external",
            notes=[note],
            approx_size="existing local files only",
            time_note="no download by setup",
            confirmation="detected_only",
            metadata={"matches": matches[:20]},
        )
    return SetupAction(
        id=action_id,
        category="model",
        name=name,
        status="blocked",
        reason="local model files not found",
        installer="external",
        blockers=[
            "Large/gated model downloads are not automatic; place files under /data/models "
            "or configure a provider path."
        ],
        notes=[note],
        approx_size="large or gated model files",
        time_note="can take a long time or hours depending on model size",
        confirmation="explicit_large_model",
    )


def heavy_model_blocker(action_id: str, name: str, models_dir: Path) -> SetupAction:
    return SetupAction(
        id=action_id,
        category="model",
        name=name,
        status="blocked",
        reason="large model not detected and not downloaded by default",
        target_path=str(models_dir / action_id),
        installer="manual_or_huggingface",
        heavy=True,
        blockers=["Explicit model license/size confirmation required."],
        approx_size="large model weights",
        time_note="can take a long time or hours",
        confirmation="explicit_large_model",
    )


def whisper_model_size_note(repo_id: str) -> str:
    lowered = repo_id.lower()
    if "tiny" in lowered:
        return "about 75 MB"
    if "base" in lowered:
        return "about 150 MB"
    if "small" in lowered:
        return "about 500 MB"
    return "model-size dependent"


def whisper_cpp_size_note(model_name: str) -> str:
    if model_name == "tiny":
        return "about 75 MB"
    if model_name == "base":
        return "about 150 MB"
    return "model-size dependent"


def external_env_model_blocker(
    action_id: str,
    name: str,
    reason: str,
    tools_dir: Path,
    models_dir: Path,
    environment: dict[str, Any],
    *,
    packages: tuple[str, ...],
    huge: bool,
) -> SetupAction:
    package_modules = tuple(package_module_name(package) for package in packages)
    current_available = all(python_module_available(module) for module in package_modules)
    model_matches = find_paths(
        (str(models_dir), "/data/models/all2text", "/data/models"),
        (f"*{action_id}*", f"*{name.replace('-', '*')}*"),
    )
    python = select_external_python(environment)
    env_dir = tools_dir / f"{action_id}-env"
    normalized_system = str(environment.get("normalized_system") or platform.system()).lower()
    venv_python = external_venv_python(env_dir, normalized_system)
    external_env_available = venv_python.exists() and all(
        external_python_module_available(venv_python, module) for module in package_modules
    )
    if current_available or external_env_available or (huge and model_matches):
        return SetupAction(
            id=action_id,
            category="model",
            name=name,
            status="satisfied",
            detected_path=str(venv_python if external_env_available else (model_matches[0] if model_matches else sys.executable)),
            reason="provider package/model evidence found",
            installer="external_env_or_service",
            approx_size="existing local package/model evidence",
            time_note="no setup action needed",
            confirmation="detected_only",
            metadata={
                "packages": packages,
                "package_modules": package_modules,
                "model_matches": model_matches[:20],
                "external_python": str(venv_python) if external_env_available else None,
            },
        )
    commands: list[list[str]] = []
    blockers = [
        "Keep this stack isolated from the main all2text runtime to avoid replacing Jetson/NVIDIA packages.",
    ]
    install_command = [str(venv_python), "-m", "pip", "install"]
    post_install_commands: list[list[str]] = []
    if action_id == "docling":
        install_command.extend(["--extra-index-url", "https://download.pytorch.org/whl/cpu"])
        post_install_commands.extend(
            [
                [
                    str(venv_python),
                    "-m",
                    "pip",
                    "uninstall",
                    "-y",
                    "opencv-python",
                    "opencv_python",
                ],
                [
                    str(venv_python),
                    "-m",
                    "pip",
                    "install",
                    "opencv-python-headless==4.13.0.92",
                ],
            ]
        )
    install_command.extend(packages)
    if python:
        commands = [
            [python, "-m", "venv", str(env_dir)],
            [str(venv_python), "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"],
            install_command,
            *post_install_commands,
        ]
        user_commands = [" ".join(command) for command in commands]
        status = "installable"
        safe_to_run = not huge
        if huge:
            blockers.append("Large model/runtime stack requires explicit full/yes setup or service deployment.")
    else:
        user_commands = [
            f"python3.11 -m venv {env_dir}",
            f"{external_venv_python(env_dir, normalized_system)} -m pip install --upgrade pip setuptools wheel",
            " ".join(install_command),
        ]
        status = "blocked"
        safe_to_run = False
        blockers.append("No Python 3.10/3.11 interpreter or external environment manager was detected.")
    large_env = huge or action_id == "docling"
    return SetupAction(
        id=action_id,
        category="model",
        name=name,
        status=status,
        reason=reason,
        installer="external_env_or_service",
        target_path=str(env_dir),
        commands=commands,
        user_commands=user_commands,
        blockers=blockers,
        safe_to_run=safe_to_run,
        heavy=True,
        approx_size="large model/service stack" if large_env else "Python environment plus provider dependencies",
        time_note="can take a long time or hours" if large_env else "may take a few minutes",
        confirmation="explicit_large_model_or_service" if huge else "external_python_env",
        metadata={
            "packages": packages,
            "package_modules": package_modules,
            "python": python,
            "models_dir": str(models_dir),
            "model_matches": model_matches[:20],
        },
    )


def package_module_name(requirement: str) -> str:
    name = requirement.split("==", 1)[0].split(">=", 1)[0].split("<", 1)[0].strip()
    return name.replace("-", "_")


def external_python_module_available(python: Path, module: str) -> bool:
    try:
        completed = subprocess.run(
            [str(python), "-c", f"import {module}"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=8,
            check=False,
        )
    except Exception:
        return False
    return completed.returncode == 0


def select_external_python(environment: dict[str, Any]) -> str:
    for candidate in environment.get("python_candidates") or []:
        executable = str(candidate.get("executable") or "")
        version = str(candidate.get("version") or "")
        if executable and version_tuple(version) >= (3, 10):
            return executable
    return ""


def version_tuple(version: str) -> tuple[int, int]:
    parts = []
    for piece in version.split(".")[:2]:
        try:
            parts.append(int(piece))
        except ValueError:
            parts.append(0)
    while len(parts) < 2:
        parts.append(0)
    return (parts[0], parts[1])


def external_venv_python(env_dir: Path, system: str | None = None) -> Path:
    if (system or platform.system()).lower().startswith("windows"):
        return env_dir / "Scripts" / "python.exe"
    return env_dir / "bin" / "python"


def execute_setup(
    config: All2TextConfig | None = None,
    *,
    options: SetupOptions | None = None,
    input_stream: Any = None,
    output_stream: Any = None,
) -> dict[str, Any]:
    opts = options or SetupOptions()
    input_stream = input_stream or sys.stdin
    output_stream = output_stream or sys.stdout
    plan = build_setup_plan(config, options=opts)
    actions = [SetupAction(**action) for action in plan["actions"]]
    selected_installable = [
        action for action in actions
        if action.selected and action.status == "installable" and action.safe_to_run
    ]
    if opts.dry_run:
        return finalize_setup_report(setup_report(plan, [], "dry_run", opts), plan)
    if selected_installable and not opts.yes:
        if not opts.noninteractive and is_interactive(input_stream, output_stream):
            print(render_setup_prompt(plan, selected_installable), end="", file=output_stream, flush=True)
            answer = input_stream.readline().strip().lower()
            if answer not in TRUE_VALUES:
                return finalize_setup_report(setup_report(plan, [], "cancelled", opts), plan)
        else:
            return finalize_setup_report(
                setup_report(
                    plan,
                    [],
                    "not_run_noninteractive",
                    opts,
                    note=(
                        "Noninteractive setup does not install without --yes or "
                        "ALL2TEXT_SETUP_ASSUME_YES=1."
                    ),
                ),
                plan,
            )
    results = []
    for action in selected_installable:
        results.append(run_action(action, opts))
    status = "failed" if any(result.get("status") == "failed" for result in results) else "completed"
    report = setup_report(plan, results, status, opts)
    return finalize_setup_report(report, plan)


def finalize_setup_report(report: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    write_setup_report(report, plan["paths"]["report_path"])
    return report


def run_action(action: SetupAction, options: SetupOptions) -> dict[str, Any]:
    try:
        if action.id == "whisper_cpp":
            return install_source_tree(action, executable_candidates=("build/bin/whisper-cli", "main"))
        if action.id == "llama_cpp":
            return install_source_tree(action, executable_candidates=("build/bin/llama-server", "build/bin/llama-cli"))
        if action.id.startswith("faster_whisper_"):
            return install_huggingface_snapshot(action)
        if action.id.startswith("whisper_cpp_"):
            return install_whisper_cpp_model(action)
        if action.id == "capa":
            return run_commands(action)
        if action.installer == "external_env_or_service" and action.commands:
            return run_commands(action)
        return {"id": action.id, "status": "skipped", "reason": "no safe installer implemented"}
    except Exception as exc:
        return {"id": action.id, "status": "failed", "error": f"{type(exc).__name__}: {exc}"}


def install_source_tree(action: SetupAction, *, executable_candidates: tuple[str, ...]) -> dict[str, Any]:
    target = Path(action.target_path or "")
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        result = run_command(action.commands[0])
        if result["returncode"] != 0:
            return {"id": action.id, "status": "failed", "step": "clone", **result}
    else:
        result = {"returncode": 0, "stdout": "", "stderr": "source tree already exists"}
    for command in action.commands[1:]:
        step = run_command(command)
        if step["returncode"] != 0:
            return {"id": action.id, "status": "failed", "step": "build", **step}
    executable = next(
        (target / candidate for candidate in executable_candidates if (target / candidate).exists()),
        None,
    )
    return {
        "id": action.id,
        "status": "installed" if executable else "built_without_expected_executable",
        "target_path": str(target),
        "executable": str(executable) if executable else None,
        "clone": result,
    }


def install_huggingface_snapshot(action: SetupAction) -> dict[str, Any]:
    try:
        from huggingface_hub import snapshot_download  # type: ignore
    except Exception as exc:
        return {"id": action.id, "status": "failed", "error": f"huggingface_hub unavailable: {exc}"}
    repo_id = str(action.metadata.get("repo_id") or action.name)
    target = Path(action.target_path or default_models_dir() / "faster_whisper")
    target.mkdir(parents=True, exist_ok=True)
    path = snapshot_download(repo_id=repo_id, cache_dir=str(target))
    return {"id": action.id, "status": "installed", "repo_id": repo_id, "path": path}


def install_whisper_cpp_model(action: SetupAction) -> dict[str, Any]:
    target = Path(action.target_path or default_models_dir() / "whisper.cpp")
    target.mkdir(parents=True, exist_ok=True)
    command = list(action.commands[0])
    result = run_command(command, cwd=target)
    if result["returncode"] == 0:
        return {"id": action.id, "status": "installed", "target_path": str(target), **result}
    fallback = download_whisper_cpp_model(action, target)
    fallback["script_result"] = result
    return fallback


def download_whisper_cpp_model(action: SetupAction, target: Path) -> dict[str, Any]:
    model_name = str(action.metadata.get("model_name") or "").strip()
    if not model_name:
        return {"id": action.id, "status": "failed", "target_path": str(target), "error": "missing model name"}
    destination = target / f"ggml-{model_name}.bin"
    if destination.exists():
        return {
            "id": action.id,
            "status": "installed",
            "target_path": str(target),
            "path": str(destination),
            "reason": "model file already exists",
        }
    source = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main"
    if "tdrz" in model_name:
        source = "https://huggingface.co/akashmjn/tinydiarize-whisper.cpp/resolve/main"
    url = f"{source}/ggml-{model_name}.bin"
    try:
        headers = {}
        if os.environ.get("HF_TOKEN"):
            headers["Authorization"] = f"Bearer {os.environ['HF_TOKEN']}"
        request = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(request, timeout=300) as response, destination.open("wb") as handle:
            shutil.copyfileobj(response, handle)
    except Exception as exc:
        destination.unlink(missing_ok=True)
        return {
            "id": action.id,
            "status": "failed",
            "target_path": str(target),
            "url": url,
            "error": f"{type(exc).__name__}: {exc}",
        }
    return {
        "id": action.id,
        "status": "installed",
        "target_path": str(target),
        "path": str(destination),
        "url": url,
    }


def run_commands(action: SetupAction) -> dict[str, Any]:
    outputs = []
    timeout = action_command_timeout(action)
    for command in action.commands:
        result = run_command(command, timeout=timeout)
        outputs.append({"command": command, **result})
        if result["returncode"] != 0:
            return {"id": action.id, "status": "failed", "outputs": outputs}
    return {"id": action.id, "status": "installed", "outputs": outputs}


def action_command_timeout(action: SetupAction) -> int:
    configured = os.environ.get("ALL2TEXT_SETUP_COMMAND_TIMEOUT_SECONDS", "").strip()
    if configured:
        try:
            return max(60, int(configured))
        except ValueError:
            pass
    if action.installer == "external_env_or_service" and (
        action.heavy or "hours" in action.time_note.lower()
    ):
        return 14_400
    return 1_800


def run_command(command: list[str], *, cwd: Path | None = None, timeout: int = 1800) -> dict[str, Any]:
    command_text = [str(part) for part in command]
    try:
        completed = subprocess.run(
            command_text,
            cwd=str(cwd) if cwd else None,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout.decode("utf-8", errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = exc.stderr.decode("utf-8", errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        return {
            "command": command_text,
            "returncode": -1,
            "stdout": stdout[-4000:],
            "stderr": (stderr + f"\nCommand timed out after {timeout} seconds.").strip()[-4000:],
        }
    return {
        "command": command_text,
        "returncode": completed.returncode,
        "stdout": completed.stdout[-4000:],
        "stderr": completed.stderr[-4000:],
    }


def setup_report(
    plan: dict[str, Any],
    results: list[dict[str, Any]],
    status: str,
    options: SetupOptions,
    *,
    note: str = "",
) -> dict[str, Any]:
    return {
        "schema": SETUP_REPORT_SCHEMA,
        "status": status,
        "note": note or None,
        "plan": plan,
        "plan_summary": plan.get("summary", {}),
        "paths": plan.get("paths", {}),
        "results": results,
        "options": asdict(options),
    }


def write_setup_report(report: dict[str, Any], path: str) -> None:
    report_path = Path(path).expanduser()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_last_setup_report(path: str | Path | None = None) -> dict[str, Any] | None:
    report_path = Path(path).expanduser() if path else default_report_path()
    if not report_path.exists():
        return None
    try:
        data = json.loads(report_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"schema": SETUP_REPORT_SCHEMA, "status": "unreadable", "error": f"{type(exc).__name__}: {exc}"}
    return data if isinstance(data, dict) else None


def summarize_last_setup_report(report: dict[str, Any] | None) -> dict[str, Any] | None:
    if not report:
        return None
    results = []
    for result in report.get("results") or []:
        if not isinstance(result, dict):
            continue
        compact = {
            "id": result.get("id"),
            "status": result.get("status"),
        }
        if result.get("error"):
            compact["error"] = result.get("error")
        if result.get("step"):
            compact["step"] = result.get("step")
        results.append(compact)
    return {
        "schema": report.get("schema"),
        "status": report.get("status"),
        "note": report.get("note"),
        "plan_summary": report.get("plan_summary"),
        "paths": report.get("paths"),
        "results": results,
    }


def render_setup_text(plan_or_report: dict[str, Any]) -> str:
    plan = plan_or_report.get("plan") if "plan" in plan_or_report else plan_or_report
    lines = [
        "all2text external setup plan",
        f"Profile: {plan.get('profile', '')}",
        f"Tools dir: {(plan.get('paths') or {}).get('tools_dir', '')}",
        f"Models dir: {(plan.get('paths') or {}).get('models_dir', '')}",
        "",
    ]
    for action in plan.get("actions", []):
        lines.append(f"- {action['id']}: {action['status']} - {action.get('reason') or ''}")
        if action.get("approx_size") or action.get("time_note"):
            size = action.get("approx_size") or "size unknown"
            time = action.get("time_note") or "time varies"
            lines.append(f"  size/time: {size}; {time}")
        if action.get("detected_path"):
            lines.append(f"  detected: {action['detected_path']}")
        for command in action.get("user_commands") or []:
            lines.append(f"  manual: {command}")
        for blocker in action.get("blockers") or []:
            lines.append(f"  blocker: {blocker}")
    return "\n".join(lines).rstrip() + "\n"


def render_setup_prompt(plan: dict[str, Any], installable: list[SetupAction]) -> str:
    lines = [
        "all2text external setup can download/build missing tools and models now.",
        f"Profile: {plan.get('profile', '')}; mode: {plan.get('mode', '')}",
        f"Tools dir: {(plan.get('paths') or {}).get('tools_dir', '')}",
        f"Models dir: {(plan.get('paths') or {}).get('models_dir', '')}",
        "",
        "Safe installable actions:",
    ]
    for action in installable:
        size = action.approx_size or "size unknown"
        time = action.time_note or "time varies"
        lines.append(f"- {action.id} ({action.category}): {size}; {time}")
    blocked = [
        action for action in plan.get("actions", [])
        if action.get("status") == "blocked" and action.get("selected", True)
    ]
    if blocked:
        lines.extend(
            [
                "",
                "Manual or blocked actions are recorded in the setup report and will not run automatically.",
            ]
        )
    lines.extend(
        [
            "For automated installs set ALL2TEXT_SETUP_ASSUME_YES=1.",
            "Download/build these missing all2text external tools/models now? [y/N] ",
        ]
    )
    return "\n".join(lines)


def setup_command(profile: str = "full", *, yes: bool = False, minimal: bool = False) -> str:
    profile_name = "minimal" if minimal else profile
    command = f"{sys.executable} -m all2text setup --profile {profile_name}"
    if yes:
        command += " --yes"
    else:
        command += " --dry-run"
    return command


def setup_recommendation(config: All2TextConfig | None = None) -> dict[str, Any]:
    cfg = config_for_context(config)
    plan = build_setup_plan(cfg, options=SetupOptions(profile=cfg.options.profile, skip_heavy=True))
    from all2text.providers import provider_statuses

    unavailable_enabled = [
        status.to_dict()
        for status in provider_statuses(cfg)
        if status.enabled
        and not status.available
        and bool((status.details or {}).get("auto_invoke", False))
    ]
    missing = list((plan.get("summary") or {}).get("missing_or_installable") or [])
    return {
        "needed": bool(unavailable_enabled),
        "unavailable_enabled_providers": unavailable_enabled,
        "missing_or_installable": missing,
        "command": setup_command("full"),
        "plan_summary": plan.get("summary", {}),
    }


def find_executable(*candidates: Any) -> str | None:
    for candidate in candidates:
        if isinstance(candidate, Path):
            if candidate.exists():
                return str(candidate)
            continue
        path = shutil.which(str(candidate))
        if path:
            return path
    return None


def find_paths(roots: Iterable[str], patterns: Iterable[str]) -> list[str]:
    matches: list[str] = []
    seen: set[str] = set()
    for root_text in roots:
        root = Path(root_text).expanduser()
        if not root.exists():
            continue
        for pattern in patterns:
            for path in root.rglob(pattern):
                if any(part in {".locks", ".cache"} for part in path.parts):
                    continue
                text = str(path)
                if text in seen:
                    continue
                seen.add(text)
                matches.append(text)
                if len(matches) >= 100:
                    return matches
    return matches


def probe_endpoints(endpoints: Iterable[str], *, timeout: float) -> list[dict[str, Any]]:
    reachable = []
    for base in endpoints:
        url = base.rstrip("/") + "/models"
        try:
            with urllib.request.urlopen(url, timeout=timeout) as response:
                payload = json.loads(response.read().decode("utf-8", errors="replace"))
        except Exception:
            continue
        models = []
        if isinstance(payload, dict):
            for key in ("data", "models"):
                values = payload.get(key)
                if isinstance(values, list):
                    for item in values:
                        if isinstance(item, dict):
                            models.append(item.get("id") or item.get("model") or item.get("name"))
        reachable.append({"base_url": base.rstrip("/"), "models": [str(model) for model in models if model]})
    return reachable


def python_module_available(module: str) -> bool:
    try:
        import importlib.util

        return importlib.util.find_spec(module) is not None
    except Exception:
        return False


def normalize_selectors(values: tuple[str, ...]) -> set[str]:
    if not values:
        return {"all"}
    selectors = set()
    for value in values:
        for part in str(value).replace(",", " ").split():
            selectors.add(part.strip().lower().replace("-", "_"))
    return selectors or {"all"}


def normalize_model_selectors(values: tuple[str, ...], profile: str) -> set[str]:
    selectors = normalize_selectors(values)
    if "minimal" in selectors:
        selectors.update({"faster_whisper_tiny", "qwen_text_gguf", "qwen_vl_gguf", "deplot", "unichart"})
    if profile == "full" and selectors == {"all"}:
        return selectors
    return selectors


def selector_matches(action_id: str, selectors: set[str]) -> bool:
    if "all" in selectors:
        return True
    normalized = action_id.lower().replace("-", "_")
    if normalized in selectors:
        return True
    if "minimal" in selectors and normalized in {
        "ffmpeg",
        "ffprobe",
        "file",
        "getfacl",
        "tesseract",
        "faster_whisper_tiny",
        "qwen_text_gguf",
        "qwen_vl_gguf",
        "deplot",
        "unichart",
    }:
        return True
    return False


def is_interactive(input_stream: Any, output_stream: Any) -> bool:
    return bool(
        getattr(input_stream, "isatty", lambda: False)()
        and getattr(output_stream, "isatty", lambda: False)()
    )
