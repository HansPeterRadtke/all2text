from __future__ import annotations

import importlib.util
import shutil
from typing import Any

from all2text.config import All2TextConfig, config_for_context


OPTIONAL_PYTHON_LIBRARIES: list[dict[str, Any]] = [
    {"name": "beautifulsoup4", "module": "bs4", "extra": "documents", "implemented_in_core": False},
    {"name": "ebooklib", "module": "ebooklib", "extra": "documents", "implemented_in_core": False},
    {"name": "fonttools", "module": "fontTools", "extra": "fonts", "implemented_in_core": False},
    {"name": "h5py", "module": "h5py", "extra": "scientific", "implemented_in_core": False},
    {"name": "markitdown", "module": "markitdown", "extra": "markitdown", "implemented_in_core": False},
    {"name": "mutagen", "module": "mutagen", "extra": "media", "implemented_in_core": True},
    {"name": "netCDF4", "module": "netCDF4", "extra": "scientific", "implemented_in_core": False},
    {"name": "numpy", "module": "numpy", "extra": "scientific", "implemented_in_core": False},
    {"name": "odfpy", "module": "odf", "extra": "documents", "implemented_in_core": False},
    {"name": "openpyxl", "module": "openpyxl", "extra": "documents", "implemented_in_core": True},
    {"name": "pefile", "module": "pefile", "extra": "executables", "implemented_in_core": False},
    {"name": "piexif", "module": "piexif", "extra": "images", "implemented_in_core": False},
    {"name": "Pillow", "module": "PIL", "extra": "images", "implemented_in_core": True},
    {"name": "py7zr", "module": "py7zr", "extra": "archives", "implemented_in_core": False},
    {"name": "pyarrow", "module": "pyarrow", "extra": "scientific", "implemented_in_core": False},
    {"name": "pypdf", "module": "pypdf", "extra": "documents", "implemented_in_core": True},
    {"name": "pyproj", "module": "pyproj", "extra": "geospatial", "implemented_in_core": False},
    {"name": "pyshp", "module": "shapefile", "extra": "geospatial", "implemented_in_core": False},
    {"name": "pytesseract", "module": "pytesseract", "extra": "ocr", "implemented_in_core": True},
    {"name": "python-docx", "module": "docx", "extra": "documents", "implemented_in_core": True},
    {"name": "python-pptx", "module": "pptx", "extra": "documents", "implemented_in_core": True},
    {"name": "rarfile", "module": "rarfile", "extra": "archives", "implemented_in_core": False},
    {"name": "scipy", "module": "scipy", "extra": "scientific", "implemented_in_core": False},
    {"name": "shapely", "module": "shapely", "extra": "geospatial", "implemented_in_core": False},
    {"name": "textract", "module": "textract", "extra": "legacy-textract", "implemented_in_core": False},
    {"name": "xlrd", "module": "xlrd", "extra": "documents", "implemented_in_core": True},
    {"name": "ezdxf", "module": "ezdxf", "extra": "cad", "implemented_in_core": False},
]

EXTERNAL_TOOLS: list[dict[str, Any]] = [
    {"name": "file", "executable": "file", "used_by_core": True},
    {"name": "ffprobe", "executable": "ffprobe", "used_by_core": True},
    {"name": "ffmpeg", "executable": "ffmpeg", "used_by_core": False},
    {"name": "tesseract", "executable": "tesseract", "used_by_core": True},
    {"name": "getfacl", "executable": "getfacl", "used_by_core": True},
    {"name": "libreoffice", "executable": "libreoffice", "used_by_core": False},
]


def capability_report(config: object | None) -> dict[str, Any]:
    cfg = config_for_context(config)
    python = optional_python_statuses(cfg)
    tools = external_tool_statuses(cfg)
    summary = capability_summary(cfg, python, tools)
    return {
        "profile": {
            "name": cfg.options.profile,
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
        available = importlib.util.find_spec(str(item["module"])) is not None
        enabled = bool(config.options.allow_optional_python)
        error = None
        if not enabled:
            error = f"disabled_by_profile:{config.options.profile}"
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


def external_tool_statuses(config: All2TextConfig) -> list[dict[str, Any]]:
    statuses: list[dict[str, Any]] = []
    for item in EXTERNAL_TOOLS:
        name = str(item["name"])
        executable = str(item["executable"])
        source = shutil.which(executable)
        available = bool(source)
        enabled = tool_enabled(config, name)
        error = None
        if not config.options.allow_external_tools:
            error = f"disabled_by_profile:{config.options.profile}"
        elif not enabled:
            error = tool_disabled_reason(config, name)
        elif not available:
            error = f"{executable} executable not found"
        elif not item["used_by_core"]:
            error = "external_tool_available_but_no_core_adapter_runs_it"
        statuses.append(
            {
                "name": name,
                "executable": executable,
                "enabled": enabled,
                "available": available,
                "source": source,
                "used_by_core": bool(item["used_by_core"]),
                "error": error,
            }
        )
    return statuses


def tool_enabled(config: All2TextConfig, name: str) -> bool:
    if not config.options.allow_external_tools:
        return False
    if name == "file":
        return bool(config.options.use_file_command)
    if name == "tesseract":
        provider = config.provider("ocr")
        return bool(provider.enabled and provider.name == "tesseract")
    if name == "ffmpeg":
        provider = config.provider("video_frames")
        return bool(provider.enabled and provider.name == "ffmpeg")
    if name == "libreoffice":
        return False
    return True


def tool_disabled_reason(config: All2TextConfig, name: str) -> str:
    if name == "file":
        return "disabled_by_run.use_file_command=false"
    if name == "tesseract":
        return "disabled_by_ocr_provider_config"
    if name == "ffmpeg":
        return "disabled_by_video_frames_provider_config"
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
        "available_optional_python_libraries": sorted(
            item["name"] for item in enabled_python if item["available"]
        ),
        "missing_optional_python_libraries": sorted(missing_python),
        "available_external_tools": sorted(item["name"] for item in enabled_tools if item["available"]),
        "missing_external_tools": sorted(missing_tools),
        "disabled_by_profile": sorted(set(disabled_by_profile)),
    }
