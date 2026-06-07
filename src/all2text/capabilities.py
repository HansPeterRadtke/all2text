from __future__ import annotations

import importlib.util
import shutil
from typing import Any

from all2text.config import All2TextConfig, config_for_context


OPTIONAL_PYTHON_LIBRARIES: list[dict[str, Any]] = [
    {"name": "astropy", "module": "astropy", "extra": "scientific", "implemented_in_core": True},
    {"name": "beautifulsoup4", "module": "bs4", "extra": "documents", "implemented_in_core": False},
    {"name": "docling", "module": "docling", "extra": "document-ocr", "implemented_in_core": False},
    {"name": "ebooklib", "module": "ebooklib", "extra": "documents", "implemented_in_core": False},
    {"name": "faster-whisper", "module": "faster_whisper", "extra": "audio", "implemented_in_core": True},
    {"name": "fonttools", "module": "fontTools", "extra": "fonts", "implemented_in_core": False},
    {"name": "h5netcdf", "module": "h5netcdf", "extra": "scientific", "implemented_in_core": False},
    {"name": "h5py", "module": "h5py", "extra": "scientific", "implemented_in_core": True},
    {"name": "IfcOpenShell", "module": "ifcopenshell", "extra": "cad", "implemented_in_core": True},
    {"name": "LIEF", "module": "lief", "extra": "executables", "implemented_in_core": True},
    {"name": "markitdown", "module": "markitdown", "extra": "markitdown", "implemented_in_core": False},
    {"name": "macholib", "module": "macholib", "extra": "executables", "implemented_in_core": True},
    {"name": "mutagen", "module": "mutagen", "extra": "media", "implemented_in_core": True},
    {"name": "netCDF4", "module": "netCDF4", "extra": "scientific", "implemented_in_core": True},
    {"name": "numpy", "module": "numpy", "extra": "scientific", "implemented_in_core": True},
    {"name": "odfpy", "module": "odf", "extra": "documents", "implemented_in_core": False},
    {"name": "openpyxl", "module": "openpyxl", "extra": "documents", "implemented_in_core": True},
    {"name": "opencv-python", "module": "cv2", "extra": "video", "implemented_in_core": True},
    {"name": "PaddleOCR", "module": "paddleocr", "extra": "document-ocr", "implemented_in_core": False},
    {"name": "pefile", "module": "pefile", "extra": "executables", "implemented_in_core": True},
    {"name": "piexif", "module": "piexif", "extra": "images", "implemented_in_core": False},
    {"name": "Pillow", "module": "PIL", "extra": "images", "implemented_in_core": True},
    {"name": "py7zr", "module": "py7zr", "extra": "archives", "implemented_in_core": False},
    {"name": "pyannote.audio", "module": "pyannote.audio", "extra": "audio", "implemented_in_core": False},
    {"name": "pyarrow", "module": "pyarrow", "extra": "scientific", "implemented_in_core": True},
    {"name": "pypdf", "module": "pypdf", "extra": "documents", "implemented_in_core": True},
    {"name": "pyproj", "module": "pyproj", "extra": "geospatial", "implemented_in_core": True},
    {"name": "pyshp", "module": "shapefile", "extra": "geospatial", "implemented_in_core": True},
    {"name": "pytesseract", "module": "pytesseract", "extra": "ocr", "implemented_in_core": True},
    {"name": "python-docx", "module": "docx", "extra": "documents", "implemented_in_core": True},
    {"name": "python-pptx", "module": "pptx", "extra": "documents", "implemented_in_core": True},
    {"name": "rarfile", "module": "rarfile", "extra": "archives", "implemented_in_core": False},
    {"name": "scipy", "module": "scipy", "extra": "scientific", "implemented_in_core": True},
    {"name": "shapely", "module": "shapely", "extra": "geospatial", "implemented_in_core": True},
    {"name": "textract", "module": "textract", "extra": "legacy-textract", "implemented_in_core": False},
    {"name": "xlrd", "module": "xlrd", "extra": "documents", "implemented_in_core": True},
    {"name": "torch", "module": "torch", "extra": "models", "implemented_in_core": False},
    {"name": "transformers", "module": "transformers", "extra": "models", "implemented_in_core": False},
    {"name": "whisper", "module": "whisper", "extra": "audio", "implemented_in_core": False},
    {"name": "ezdxf", "module": "ezdxf", "extra": "cad", "implemented_in_core": True},
]

EXTERNAL_TOOLS: list[dict[str, Any]] = [
    {"name": "file", "executable": "file", "used_by_core": True},
    {"name": "ffprobe", "executable": "ffprobe", "used_by_core": True},
    {"name": "ffmpeg", "executable": "ffmpeg", "used_by_core": True},
    {"name": "tesseract", "executable": "tesseract", "used_by_core": True},
    {"name": "getfacl", "executable": "getfacl", "used_by_core": True},
    {"name": "libreoffice", "executable": "libreoffice", "used_by_core": False},
    {"name": "whisper_cpp", "executable": "whisper-cli", "used_by_core": False},
    {"name": "radare2", "executable": "radare2", "used_by_core": False},
    {"name": "capa", "executable": "capa", "used_by_core": False},
]


def capability_report(config: object | None) -> dict[str, Any]:
    cfg = config_for_context(config)
    python = optional_python_statuses(cfg)
    tools = external_tool_statuses(cfg)
    summary = capability_summary(cfg, python, tools)
    return {
        "profile": {
            "name": cfg.options.profile,
            "auto_detect_python": cfg.options.auto_detect_python,
            "auto_detect_tools": cfg.options.auto_detect_tools,
            "auto_detect_local_models": cfg.options.auto_detect_local_models,
            "allow_optional_python": cfg.options.allow_optional_python,
            "allow_external_tools": cfg.options.allow_external_tools,
            "allow_local_models": cfg.options.allow_local_models,
            "use_file_command": cfg.options.use_file_command,
        },
        "optional_python_libraries": python,
        "external_tools": tools,
        "summary": summary,
    }


def optional_python_statuses(config: All2TextConfig) -> list[dict[str, Any]]:
    statuses: list[dict[str, Any]] = []
    for item in OPTIONAL_PYTHON_LIBRARIES:
        available = python_module_available(str(item["module"]))
        enabled = bool(config.options.allow_optional_python and config.options.auto_detect_python)
        error = None
        if not config.options.allow_optional_python:
            error = f"disabled_by_profile:{config.options.profile}"
        elif not config.options.auto_detect_python:
            error = "disabled_by_run.auto_detect_python=false"
        elif not available:
            error = "python_package_not_installed"
        elif not item["implemented_in_core"]:
            error = "library_available_but_no_core_extractor_uses_it_yet"
        statuses.append(
            {
                "name": item["name"],
                "module": item["module"],
                "extra": item["extra"],
                "enabled_by_profile": enabled,
                "available": available,
                "implemented_in_core": bool(item["implemented_in_core"]),
                "error": error,
            }
        )
    return statuses


def python_module_available(module: str) -> bool:
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


def external_tool_statuses(config: All2TextConfig) -> list[dict[str, Any]]:
    statuses: list[dict[str, Any]] = []
    for item in EXTERNAL_TOOLS:
        resolved = resolve_external_tool(config, str(item["name"]))
        error = resolved["error"]
        if resolved["enabled"] and resolved["available"] and not item["used_by_core"]:
            error = "external_tool_available_but_no_core_adapter_runs_it"
        statuses.append(
            {
                "name": resolved["name"],
                "executable": resolved["executable"],
                "enabled": resolved["enabled"],
                "available": resolved["available"],
                "source": resolved["source"],
                "configured_path": resolved["configured_path"],
                "auto_detected": resolved["auto_detected"],
                "used_by_core": bool(item["used_by_core"]),
                "error": error,
            }
        )
    return statuses


def resolve_external_tool(config: object | None, name: str) -> dict[str, Any]:
    cfg = config_for_context(config)
    configured = cfg.tool(name)
    default_executable = next(
        (str(item["executable"]) for item in EXTERNAL_TOOLS if item["name"] == name),
        name,
    )
    executable = configured.executable or default_executable
    configured_path = configured.path or ""
    enabled = tool_enabled(cfg, name)
    source = None
    auto_detected = False
    error = None
    if not cfg.options.allow_external_tools:
        error = f"disabled_by_profile:{cfg.options.profile}"
    elif configured.enabled is False:
        error = f"disabled_by_tools.{name}.enabled=false"
    elif not cfg.options.auto_detect_tools and not configured_path and configured.enabled is not True:
        error = "disabled_by_run.auto_detect_tools=false"
    elif not enabled:
        error = tool_disabled_reason(cfg, name)
    else:
        if configured_path:
            source = configured_path if shutil.which(configured_path) or _path_exists(configured_path) else None
        elif cfg.options.auto_detect_tools or configured.enabled is True:
            source = shutil.which(executable)
            auto_detected = bool(source)
            if not source:
                source = setup_managed_tool_path(cfg, name, executable)
                auto_detected = bool(source)
        if not source:
            error = f"{configured_path or executable} executable not found"
    return {
        "name": name,
        "executable": executable,
        "enabled": enabled,
        "available": bool(source),
        "source": source,
        "configured_path": configured_path or None,
        "auto_detected": auto_detected,
        "error": error,
        "timeout_seconds": configured.params.get("timeout_seconds"),
    }


def _path_exists(path: str) -> bool:
    try:
        from pathlib import Path

        return Path(path).exists()
    except Exception:
        return False


def setup_managed_tool_path(config: All2TextConfig, name: str, executable: str) -> str | None:
    try:
        from pathlib import Path

        from all2text.external_setup import default_tools_dir

        configured_root = str(getattr(config.options, "setup_tools_dir", "") or "")
        root = Path(configured_root).expanduser() if configured_root else default_tools_dir()
        candidates = {
            "whisper_cpp": [
                root / "whisper.cpp" / "build" / "bin" / "whisper-cli",
                root / "whisper.cpp" / "main",
            ],
            "capa": [root / "capa-venv" / "bin" / "capa"],
            "radare2": [root / "radare2" / "bin" / "radare2", root / "radare2" / "bin" / "rabin2"],
        }.get(name, [])
        candidates.append(root / name / "bin" / executable)
        for candidate in candidates:
            if candidate.exists():
                return str(candidate)
    except Exception:
        return None
    return None


def tool_enabled(config: All2TextConfig, name: str) -> bool:
    if not config.options.allow_external_tools:
        return False
    tool = config.tool(name)
    if tool.enabled is False:
        return False
    if not config.options.auto_detect_tools and not tool.path and tool.enabled is not True:
        return False
    if name == "file":
        return bool(config.options.use_file_command)
    if name == "tesseract":
        provider = config.provider("ocr")
        return bool(provider.enabled and provider.name == "tesseract")
    if name == "libreoffice":
        return False
    return True


def tool_disabled_reason(config: All2TextConfig, name: str) -> str:
    if name == "file":
        return "disabled_by_run.use_file_command=false"
    if name == "tesseract":
        return "disabled_by_ocr_provider_config"
    if name == "libreoffice":
        return "libreoffice_adapter_not_implemented_in_core"
    return "disabled_by_config"


def capability_summary(
    config: All2TextConfig,
    python: list[dict[str, Any]],
    tools: list[dict[str, Any]],
) -> dict[str, Any]:
    enabled_python = [item for item in python if item["enabled_by_profile"]]
    enabled_tools = [item for item in tools if item["enabled"]]
    missing_python = [item["name"] for item in enabled_python if not item["available"]]
    missing_tools = [item["name"] for item in enabled_tools if not item["available"]]
    disabled_by_profile = [
        item["name"] for item in python if str(item.get("error") or "").startswith("disabled_by_profile:")
    ] + [
        item["name"] for item in tools if str(item.get("error") or "").startswith("disabled_by_profile:")
    ]
    return {
        "profile": config.options.profile,
        "auto_detect_python": config.options.auto_detect_python,
        "auto_detect_tools": config.options.auto_detect_tools,
        "auto_detect_local_models": config.options.auto_detect_local_models,
        "available_optional_python_libraries": sorted(
            item["name"] for item in enabled_python if item["available"]
        ),
        "missing_optional_python_libraries": sorted(missing_python),
        "available_external_tools": sorted(item["name"] for item in enabled_tools if item["available"]),
        "missing_external_tools": sorted(missing_tools),
        "disabled_by_profile": sorted(set(disabled_by_profile)),
    }


def provider_execution_summary(
    capabilities: dict[str, Any],
    provider_statuses: list[dict[str, Any]],
    provider_family_statuses: list[dict[str, Any]],
) -> dict[str, Any]:
    optional_python = capabilities.get("optional_python_libraries", [])
    external_tools = capabilities.get("external_tools", [])
    installed_python = [
        str(item.get("name"))
        for item in optional_python
        if item.get("available") and item.get("implemented_in_core")
    ]
    installed_contract_only = [
        str(item.get("name"))
        for item in optional_python
        if item.get("available") and not item.get("implemented_in_core")
    ]
    available_tools = [
        {
            "name": item.get("name"),
            "source": item.get("source"),
            "used_by_core": item.get("used_by_core"),
        }
        for item in external_tools
        if item.get("available")
    ]
    blocked_tools = [
        {"name": item.get("name"), "error": item.get("error")}
        for item in external_tools
        if not item.get("available") or item.get("error")
    ]
    reachable_endpoints = []
    for status in provider_statuses:
        lifecycle = status.get("lifecycle") or {}
        if lifecycle.get("endpoint_reachable"):
            reachable_endpoints.append(
                {
                    "name": status.get("name"),
                    "provider": (status.get("details") or {}).get("provider"),
                    "source": status.get("source"),
                    "model": (status.get("details") or {}).get("model"),
                    "auto_invoke": (status.get("details") or {}).get("auto_invoke"),
                }
            )
    model_matches = []
    for status in provider_family_statuses:
        details = status.get("details") or {}
        for match in details.get("model_matches") or []:
            model_matches.append(str(match))
    implemented = [
        {
            "name": status.get("name"),
            "family": ((status.get("details") or {}).get("candidate") or {}).get("family"),
            "kind": status.get("kind"),
            "source": status.get("source"),
        }
        for status in provider_family_statuses
        if status.get("available")
    ]
    contract_only = [
        {
            "name": status.get("name"),
            "family": ((status.get("details") or {}).get("candidate") or {}).get("family"),
            "kind": status.get("kind"),
            "error": status.get("error"),
        }
        for status in provider_family_statuses
        if ((status.get("details") or {}).get("execution_status") == "contract_only")
    ]
    blockers = [
        {
            "name": status.get("name"),
            "kind": status.get("kind"),
            "enabled": status.get("enabled"),
            "error": status.get("error"),
        }
        for status in [*provider_statuses, *provider_family_statuses]
        if status.get("error") and not status.get("available")
    ]
    return {
        "installed_python_providers": sorted(installed_python),
        "installed_python_contract_only": sorted(installed_contract_only),
        "external_tools_available": available_tools,
        "external_tools_blocked": blocked_tools,
        "reachable_endpoints": reachable_endpoints,
        "locally_discovered_model_files": sorted(set(model_matches))[:100],
        "implemented_and_executable_providers": implemented,
        "contract_only_providers": contract_only,
        "blockers": blockers[:200],
    }
