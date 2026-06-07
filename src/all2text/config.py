from __future__ import annotations

import math
import os
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any

from all2text.models import RunOptions


@dataclass
class ModuleConfig:
    backend: str
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class ProviderConfig:
    name: str = "none"
    enabled: bool = False
    params: dict[str, Any] = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        return self.params.get(key, default)


@dataclass
class ToolConfig:
    name: str
    enabled: bool | None = None
    path: str = ""
    executable: str = ""
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class All2TextConfig:
    options: RunOptions = field(default_factory=RunOptions)
    modules: dict[str, ModuleConfig] = field(default_factory=dict)
    providers: dict[str, ProviderConfig] = field(default_factory=dict)
    tools: dict[str, ToolConfig] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)
    source_path: str | None = None

    def module_backend(self, family: str, default: str | None = None) -> str | None:
        module = self.modules.get(family)
        return module.backend if module else default

    def module_config(self, family: str) -> ModuleConfig:
        return self.modules.get(family, ModuleConfig(backend=""))

    def module_params(self, *families: str) -> dict[str, Any]:
        params: dict[str, Any] = {}
        for family in families:
            module = self.modules.get(family)
            if module:
                params.update(module.params)
        return params

    def provider(self, task: str) -> ProviderConfig:
        return self.providers.get(task, ProviderConfig())

    def tool(self, name: str) -> ToolConfig:
        return self.tools.get(name, ToolConfig(name=name))

    def with_options(self, options: RunOptions) -> "All2TextConfig":
        return replace(self, options=options)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_path": self.source_path,
            "options": asdict(self.options),
            "modules": {key: asdict(value) for key, value in sorted(self.modules.items())},
            "providers": {key: asdict(value) for key, value in sorted(self.providers.items())},
            "tools": {key: asdict(value) for key, value in sorted(self.tools.items())},
        }


DEFAULT_MODULES: dict[str, str] = {
    "filesystem": "filesystem_metadata_backend",
    "text": "text_exact_backend",
    "structured_text": "text_exact_backend",
    "source_code": "text_exact_backend",
    "notebook": "text_exact_backend",
    "email": "email_metadata_backend",
    "archive": "archive_listing_backend",
    "compressed": "archive_listing_backend",
    "ebook": "ebook_placeholder_backend",
    "database": "database_metadata_backend",
    "document": "document_native_backend",
    "spreadsheet": "document_native_backend",
    "presentation": "document_native_backend",
    "image": "image_analysis_backend",
    "audio": "media_analysis_backend",
    "video": "media_analysis_backend",
    "scientific_data": "scientific_placeholder_backend",
    "geospatial": "geospatial_placeholder_backend",
    "cad_or_technical": "cad_placeholder_backend",
    "font": "font_placeholder_backend",
    "executable_or_binary": "executable_placeholder_backend",
    "disk_image_or_container": "container_placeholder_backend",
    "unknown": "binary_fallback",
}

DEFAULT_MODULE_PARAMS: dict[str, dict[str, Any]] = {
    "document": {
        "max_pdf_pages": 100,
        "max_text_blocks": 5000,
    },
    "spreadsheet": {
        "include_hidden_sheets": True,
        "max_cells_per_sheet": 20000,
    },
    "audio": {
        "max_ffprobe_json_chars": 20000,
    },
    "video": {
        "max_ffprobe_json_chars": 20000,
    },
}

PROFILE_DEFAULTS: dict[str, dict[str, Any]] = {
    "auto": {
        "auto_detect_python": True,
        "auto_detect_tools": True,
        "auto_detect_local_models": True,
        "allow_optional_python": True,
        "allow_external_tools": True,
        "allow_local_models": True,
        "use_file_command": True,
    },
    "core": {
        "auto_detect_python": False,
        "auto_detect_tools": False,
        "auto_detect_local_models": False,
        "allow_optional_python": False,
        "allow_external_tools": False,
        "allow_local_models": False,
        "use_file_command": False,
    },
    "pip": {
        "auto_detect_python": True,
        "auto_detect_tools": False,
        "auto_detect_local_models": False,
        "allow_optional_python": True,
        "allow_external_tools": False,
        "allow_local_models": False,
        "use_file_command": False,
    },
    "tools": {
        "auto_detect_python": True,
        "auto_detect_tools": True,
        "auto_detect_local_models": False,
        "allow_optional_python": True,
        "allow_external_tools": True,
        "allow_local_models": False,
        "use_file_command": True,
    },
    "local-models": {
        "auto_detect_python": True,
        "auto_detect_tools": False,
        "auto_detect_local_models": True,
        "allow_optional_python": True,
        "allow_external_tools": False,
        "allow_local_models": True,
        "use_file_command": False,
    },
    "full": {
        "auto_detect_python": True,
        "auto_detect_tools": True,
        "auto_detect_local_models": True,
        "allow_optional_python": True,
        "allow_external_tools": True,
        "allow_local_models": True,
        "use_file_command": True,
    },
}

PROFILE_ALIASES = {
    "base": "auto",
    "default": "auto",
    "automatic": "auto",
    "lowest": "auto",
    "lowest-detail": "auto",
    "python": "pip",
    "python-only": "pip",
    "local_models": "local-models",
    "models": "local-models",
    "all": "full",
}

PROVIDER_PROFILE_REQUIREMENTS: dict[str, str] = {
    "audio_classifier": "local_models",
    "diarization": "local_models",
    "ocr": "external_tools",
    "vlm": "local_models",
    "llm_text": "local_models",
    "chart": "local_models",
    "document_intelligence": "local_models",
    "speech": "local_models",
    "video_frames": "external_tools",
}

KNOWN_BACKEND_NAMES = {
    "archive_listing_backend",
    "binary_fallback",
    "cad_placeholder_backend",
    "container_placeholder_backend",
    "database_metadata_backend",
    "document_native_backend",
    "ebook_placeholder_backend",
    "email_metadata_backend",
    "executable_placeholder_backend",
    "filesystem_metadata_backend",
    "font_placeholder_backend",
    "geospatial_placeholder_backend",
    "image_analysis_backend",
    "media_analysis_backend",
    "scientific_placeholder_backend",
    "text_exact_backend",
}

ALLOWED_PROVIDER_NAMES: dict[str, set[str]] = {
    "audio_classifier": {"none", "yamnet", "panns", "openbeats", "clap"},
    "binary_metadata": {"none", "pefile", "macholib", "lief", "capa", "radare2", "file"},
    "cad": {"none", "ezdxf", "ifcopenshell"},
    "diarization": {"none", "pyannote", "diarizen", "nemo"},
    "geospatial": {"none", "pyshp", "pyproj", "shapely"},
    "image_classifier": {"none", "clip", "open_clip", "siglip", "siglip2"},
    "ocr": {"none", "tesseract", "paddleocr", "surya"},
    "vlm": {"none", "openai_compatible"},
    "llm_text": {"none", "openai_compatible"},
    "chart": {"none", "deplot", "chartgemma", "unichart", "chartcoder", "chartocr"},
    "document_intelligence": {"none", "docling", "paddleocr_vl", "glm_ocr", "olmocr"},
    "scientific": {"none", "h5py", "h5netcdf", "netcdf4", "astropy", "pyarrow", "scipy", "numpy"},
    "speech": {"none", "whisper", "whisper_cpp", "faster_whisper", "vosk", "parakeet", "canary"},
    "video_frames": {"none", "ffmpeg"},
}

RUN_OPTION_POSITIVE_INT_FIELDS = {
    "max_header_bytes",
    "max_hash_bytes",
    "max_binary_sample_bytes",
    "max_archive_members",
}

RUN_OPTION_BOOL_FIELDS = {
    "auto_detect_local_models",
    "auto_detect_python",
    "auto_detect_tools",
    "allow_external_tools",
    "allow_local_models",
    "allow_optional_python",
    "use_file_command",
    "copy_source_stat",
    "interactive_setup_prompt",
    "reject_target_inside_source",
}

RUN_OPTION_STRING_FIELDS = {
    "setup_models_dir",
    "setup_report_path",
    "setup_tools_dir",
}

KNOWN_TOOL_NAMES = {
    "capa",
    "ffmpeg",
    "ffprobe",
    "file",
    "getfacl",
    "libreoffice",
    "radare2",
    "tesseract",
    "whisper_cpp",
}

TOOL_BOOL_PARAMS = {"enabled"}

TOOL_POSITIVE_INT_PARAMS = {"timeout_seconds"}

MODULE_NON_NEGATIVE_INT_PARAMS = {
    "max_ffprobe_json_chars",
    "max_pdf_pages",
    "max_text_blocks",
    "max_cells_per_sheet",
}

MODULE_BOOL_PARAMS = {
    "include_hidden_sheets",
}

PROVIDER_POSITIVE_INT_PARAMS: dict[str, set[str]] = {
    "audio_classifier": {"timeout_seconds"},
    "binary_metadata": {"timeout_seconds", "max_strings"},
    "cad": {"timeout_seconds"},
    "chart": {"timeout_seconds"},
    "diarization": {"timeout_seconds"},
    "geospatial": {"timeout_seconds"},
    "image_classifier": {"timeout_seconds"},
    "ocr": {"timeout_seconds", "min_characters"},
    "vlm": {"timeout_seconds", "max_tokens"},
    "llm_text": {"timeout_seconds", "max_tokens"},
    "document_intelligence": {"timeout_seconds"},
    "scientific": {"timeout_seconds"},
    "speech": {"timeout_seconds"},
    "video_frames": {"timeout_seconds", "max_frames"},
}

PROVIDER_POSITIVE_FLOAT_PARAMS: dict[str, set[str]] = {
    "vlm": {"discovery_timeout_seconds"},
    "llm_text": {"discovery_timeout_seconds"},
    "video_frames": {"interval_seconds"},
}

PROVIDER_RATIO_PARAMS: dict[str, set[str]] = {
    "ocr": {"min_alnum_ratio"},
    "chart": {"confidence_threshold"},
}

PROVIDER_PERCENT_PARAMS: dict[str, set[str]] = {
    "ocr": {"min_confidence"},
}

PROVIDER_BOOL_PARAMS: dict[str, set[str]] = {
    "audio_classifier": {"auto_invoke"},
    "binary_metadata": {"auto_invoke"},
    "cad": {"auto_invoke"},
    "diarization": {"auto_invoke"},
    "geospatial": {"auto_invoke"},
    "image_classifier": {"auto_invoke"},
    "ocr": {"auto_invoke"},
    "vlm": {"auto_detect", "auto_invoke"},
    "llm_text": {"auto_detect", "auto_invoke"},
    "chart": {"embedded_images_enabled", "auto_invoke"},
    "document_intelligence": {"auto_invoke"},
    "scientific": {"auto_invoke"},
    "speech": {"transcribe", "translate", "language_detection", "auto_invoke"},
    "video_frames": {"sample_frames", "auto_invoke", "ocr", "vlm", "preserve_frames"},
}


DEFAULT_PROVIDERS: dict[str, ProviderConfig] = {
    "image_classifier": ProviderConfig(
        name="none",
        enabled=False,
        params={
            "model_path": "",
            "labels": "default",
            "timeout_seconds": 120,
            "auto_invoke": False,
        },
    ),
    "ocr": ProviderConfig(
        name="tesseract",
        enabled=True,
        params={
            "language": "eng",
            "timeout_seconds": 30,
            "preprocess": "none",
            "min_characters": 4,
            "min_alnum_ratio": 0.35,
            "min_confidence": 35,
            "auto_invoke": True,
        },
    ),
    "vlm": ProviderConfig(
        name="openai_compatible",
        enabled=True,
        params={
            "base_url": "http://127.0.0.1:14830/v1",
            "model": "Qwen2.5-VL-3B-Instruct-Q4_K_M.gguf",
            "timeout_seconds": 120,
            "discovery_timeout_seconds": 0.5,
            "max_tokens": 300,
            "temperature": 0,
            "prompt": "Describe visible evidence only.",
            "auto_detect": True,
            "auto_invoke": False,
        },
    ),
    "llm_text": ProviderConfig(
        name="openai_compatible",
        enabled=True,
        params={
            "base_url": "http://127.0.0.1:14829/v1",
            "model": "Qwen2.5-14B-Instruct-Q4_K_M.gguf",
            "timeout_seconds": 120,
            "discovery_timeout_seconds": 0.5,
            "max_tokens": 512,
            "temperature": 0,
            "prompt": "Summarize extracted text using only supplied evidence.",
            "auto_detect": True,
            "auto_invoke": False,
        },
    ),
    "chart": ProviderConfig(
        name="none",
        enabled=False,
        params={
            "specialist": "none",
            "model_path": "",
            "embedded_images_enabled": False,
            "confidence_threshold": 0.6,
            "timeout_seconds": 120,
            "auto_invoke": False,
        },
    ),
    "document_intelligence": ProviderConfig(
        name="none",
        enabled=False,
        params={
            "endpoint": "",
            "api_key_env": "",
            "timeout_seconds": 120,
            "auto_invoke": False,
        },
    ),
    "audio_classifier": ProviderConfig(
        name="none",
        enabled=False,
        params={
            "model_path": "",
            "labels": "speech,music,noise,mixed,unknown",
            "timeout_seconds": 120,
            "auto_invoke": False,
        },
    ),
    "speech": ProviderConfig(
        name="none",
        enabled=False,
        params={
            "transcribe": False,
            "translate": False,
            "language_detection": False,
            "model_path": "",
            "device": "auto",
            "timeout_seconds": 300,
            "auto_invoke": False,
        },
    ),
    "diarization": ProviderConfig(
        name="none",
        enabled=False,
        params={
            "model_path": "",
            "device": "auto",
            "timeout_seconds": 300,
            "auto_invoke": False,
        },
    ),
    "video_frames": ProviderConfig(
        name="none",
        enabled=False,
        params={
            "sample_frames": False,
            "max_frames": 5,
            "interval_seconds": 10,
            "output_format": "png",
            "timeout_seconds": 120,
            "auto_invoke": False,
            "ocr": False,
            "vlm": False,
            "preserve_frames": False,
        },
    ),
    "cad": ProviderConfig(
        name="none",
        enabled=False,
        params={"timeout_seconds": 120, "auto_invoke": False},
    ),
    "scientific": ProviderConfig(
        name="none",
        enabled=False,
        params={"timeout_seconds": 120, "auto_invoke": False},
    ),
    "geospatial": ProviderConfig(
        name="none",
        enabled=False,
        params={"timeout_seconds": 120, "auto_invoke": False},
    ),
    "binary_metadata": ProviderConfig(
        name="none",
        enabled=False,
        params={"timeout_seconds": 120, "max_strings": 100, "auto_invoke": False},
    ),
}

DEFAULT_TOOLS: dict[str, ToolConfig] = {
    name: ToolConfig(name=name, executable=name)
    for name in sorted(KNOWN_TOOL_NAMES)
}


def default_config() -> All2TextConfig:
    return All2TextConfig(
        modules={
            key: ModuleConfig(backend=value, params=dict(DEFAULT_MODULE_PARAMS.get(key, {})))
            for key, value in DEFAULT_MODULES.items()
        },
        providers={
            key: ProviderConfig(value.name, value.enabled, dict(value.params))
            for key, value in DEFAULT_PROVIDERS.items()
        },
        tools={
            key: ToolConfig(value.name, value.enabled, value.path, value.executable, dict(value.params))
            for key, value in DEFAULT_TOOLS.items()
        },
    )


def load_config(path: str | Path | None = None) -> All2TextConfig:
    configured_path = path or os.environ.get("ALL2TEXT_CONFIG")
    config_path = Path(configured_path).expanduser() if configured_path else None
    if config_path is None:
        return default_config()
    data = _load_toml(config_path)
    return config_from_dict(data, source_path=str(config_path))


def config_from_dict(data: dict[str, Any], *, source_path: str | None = None) -> All2TextConfig:
    if not isinstance(data, dict):
        raise ValueError(_config_error("config root must be a table", source_path))
    base = default_config()
    run_data = data.get("run", {})
    run_options = _run_options_from_dict(
        run_data if run_data is not None else {},
        base.options,
        source_path=source_path,
    )
    modules = dict(base.modules)
    module_data = data.get("modules", {})
    if module_data is None:
        module_data = {}
    if not isinstance(module_data, dict):
        raise ValueError(_config_error("modules must be a table", source_path))
    for key, value in module_data.items():
        if isinstance(value, str):
            modules[str(key)] = ModuleConfig(backend=value)
        elif isinstance(value, dict):
            backend = str(value.get("backend") or modules.get(str(key), ModuleConfig("")).backend)
            params = {str(k): v for k, v in value.items() if k != "backend"}
            inherited = dict(modules.get(str(key), ModuleConfig(backend="")).params)
            inherited.update(params)
            modules[str(key)] = ModuleConfig(backend=backend, params=inherited)
        else:
            raise ValueError(
                _config_error(f"modules.{key} must be a backend string or table", source_path)
            )
    providers = dict(base.providers)
    provider_data = data.get("providers", {})
    if provider_data is None:
        provider_data = {}
    if not isinstance(provider_data, dict):
        raise ValueError(_config_error("providers must be a table", source_path))
    for key, value in provider_data.items():
        if not isinstance(value, dict):
            raise ValueError(_config_error(f"providers.{key} must be a table", source_path))
        current = providers.get(str(key), ProviderConfig())
        name = str(value.get("name", current.name))
        enabled = _coerce_bool(
            value.get("enabled", current.enabled),
            f"providers.{key}.enabled",
            source_path=source_path,
        )
        params = dict(current.params)
        params.update({str(k): v for k, v in value.items() if k not in {"name", "enabled"}})
        providers[str(key)] = ProviderConfig(name=name, enabled=enabled, params=params)
    tools = dict(base.tools)
    tool_data = data.get("tools", {})
    if tool_data is None:
        tool_data = {}
    if not isinstance(tool_data, dict):
        raise ValueError(_config_error("tools must be a table", source_path))
    for key, value in tool_data.items():
        name = str(key)
        current = tools.get(name, ToolConfig(name=name, executable=name))
        if isinstance(value, str):
            tools[name] = ToolConfig(name=name, path=value, executable=current.executable)
        elif isinstance(value, dict):
            enabled = (
                _coerce_bool(value["enabled"], f"tools.{name}.enabled", source_path=source_path)
                if "enabled" in value
                else current.enabled
            )
            path = str(value.get("path", current.path) or "")
            executable = str(value.get("executable", current.executable or name) or name)
            params = dict(current.params)
            params.update({str(k): v for k, v in value.items() if k not in {"enabled", "path", "executable"}})
            tools[name] = ToolConfig(
                name=name,
                enabled=enabled,
                path=path,
                executable=executable,
                params=params,
            )
        else:
            raise ValueError(_config_error(f"tools.{name} must be a path string or table", source_path))
    config = All2TextConfig(
        options=run_options,
        modules=modules,
        providers=providers,
        tools=tools,
        raw=data,
        source_path=source_path,
    )
    validate_config(config)
    return config


def _run_options_from_dict(
    data: dict[str, Any],
    defaults: RunOptions,
    *,
    source_path: str | None = None,
) -> RunOptions:
    if not isinstance(data, dict):
        raise ValueError(_config_error("run must be a table", source_path))
    values = asdict(defaults)
    profile = normalize_profile(data.get("profile", values.get("profile", "auto")), source_path=source_path)
    values.update(PROFILE_DEFAULTS[profile])
    values["profile"] = profile
    for key in values:
        if key == "profile":
            continue
        if key in data:
            field = f"run.{key}"
            if key in RUN_OPTION_POSITIVE_INT_FIELDS:
                values[key] = _coerce_int(
                    data[key],
                    field,
                    source_path=source_path,
                    minimum=1,
                )
            elif key in RUN_OPTION_BOOL_FIELDS:
                values[key] = _coerce_bool(data[key], field, source_path=source_path)
            elif key in RUN_OPTION_STRING_FIELDS:
                values[key] = str(data[key] or "")
            else:
                values[key] = data[key]
    return RunOptions(**values)


def normalize_profile(value: Any, *, source_path: str | None = None) -> str:
    profile = str(value or "auto").strip().casefold().replace("_", "-")
    profile = PROFILE_ALIASES.get(profile, profile)
    if profile not in PROFILE_DEFAULTS:
        allowed = ", ".join(sorted(PROFILE_DEFAULTS))
        raise ValueError(_config_error(f"run.profile must be one of: {allowed}; got {value!r}", source_path))
    return profile


def options_with_profile(options: RunOptions, profile: str) -> RunOptions:
    normalized = normalize_profile(profile, source_path=None)
    values = asdict(options)
    values.update(PROFILE_DEFAULTS[normalized])
    values["profile"] = normalized
    return RunOptions(**values)


def validate_config(config: All2TextConfig) -> None:
    config.options.profile = normalize_profile(config.options.profile, source_path=config.source_path)
    for field_name in RUN_OPTION_POSITIVE_INT_FIELDS:
        setattr(
            config.options,
            field_name,
            _coerce_int(
                getattr(config.options, field_name),
                f"run.{field_name}",
                source_path=config.source_path,
                minimum=1,
            ),
        )
    for field_name in RUN_OPTION_BOOL_FIELDS:
        setattr(
            config.options,
            field_name,
            _coerce_bool(
                getattr(config.options, field_name),
                f"run.{field_name}",
                source_path=config.source_path,
            ),
        )
    for field_name in RUN_OPTION_STRING_FIELDS:
        setattr(config.options, field_name, str(getattr(config.options, field_name) or ""))
    for family, module in config.modules.items():
        if module.backend not in KNOWN_BACKEND_NAMES:
            allowed = ", ".join(sorted(KNOWN_BACKEND_NAMES))
            raise ValueError(
                _config_error(
                    f"unknown backend for modules.{family}: {module.backend!r}; "
                    f"expected one of: {allowed}",
                    config.source_path,
                )
            )
        for key in MODULE_NON_NEGATIVE_INT_PARAMS:
            if key in module.params:
                module.params[key] = _coerce_int(
                    module.params[key],
                    f"modules.{family}.{key}",
                    source_path=config.source_path,
                    minimum=0,
                )
        for key in MODULE_BOOL_PARAMS:
            if key in module.params:
                module.params[key] = _coerce_bool(
                    module.params[key],
                    f"modules.{family}.{key}",
                    source_path=config.source_path,
                )
    for name, tool in config.tools.items():
        if name not in KNOWN_TOOL_NAMES:
            allowed = ", ".join(sorted(KNOWN_TOOL_NAMES))
            raise ValueError(
                _config_error(f"unknown tool tools.{name}; expected one of: {allowed}", config.source_path)
            )
        if tool.enabled is not None:
            tool.enabled = _coerce_bool(
                tool.enabled,
                f"tools.{name}.enabled",
                source_path=config.source_path,
            )
        for key in TOOL_POSITIVE_INT_PARAMS:
            if key in tool.params:
                tool.params[key] = _coerce_int(
                    tool.params[key],
                    f"tools.{name}.{key}",
                    source_path=config.source_path,
                    minimum=1,
                )
    for task, provider in config.providers.items():
        allowed_names = ALLOWED_PROVIDER_NAMES.get(task)
        if allowed_names is None:
            allowed_tasks = ", ".join(sorted(ALLOWED_PROVIDER_NAMES))
            raise ValueError(
                _config_error(
                    f"unknown provider task providers.{task}; expected one of: {allowed_tasks}",
                    config.source_path,
                )
            )
        if provider.name not in allowed_names:
            allowed = ", ".join(sorted(allowed_names))
            raise ValueError(
                _config_error(
                    f"unknown provider name for providers.{task}: {provider.name!r}; "
                    f"expected one of: {allowed}",
                    config.source_path,
                )
            )
        for key in PROVIDER_POSITIVE_INT_PARAMS.get(task, set()):
            if key in provider.params:
                provider.params[key] = _coerce_int(
                    provider.params[key],
                    f"providers.{task}.{key}",
                    source_path=config.source_path,
                    minimum=1,
                )
        for key in PROVIDER_POSITIVE_FLOAT_PARAMS.get(task, set()):
            if key in provider.params:
                provider.params[key] = _coerce_float(
                    provider.params[key],
                    f"providers.{task}.{key}",
                    source_path=config.source_path,
                    minimum=0.0,
                    include_minimum=False,
                )
        for key in PROVIDER_RATIO_PARAMS.get(task, set()):
            if key in provider.params:
                provider.params[key] = _coerce_float(
                    provider.params[key],
                    f"providers.{task}.{key}",
                    source_path=config.source_path,
                    minimum=0.0,
                    maximum=1.0,
                )
        for key in PROVIDER_PERCENT_PARAMS.get(task, set()):
            if key in provider.params:
                provider.params[key] = _coerce_float(
                    provider.params[key],
                    f"providers.{task}.{key}",
                    source_path=config.source_path,
                    minimum=0.0,
                    maximum=100.0,
                )
        for key in PROVIDER_BOOL_PARAMS.get(task, set()):
            if key in provider.params:
                provider.params[key] = _coerce_bool(
                    provider.params[key],
                    f"providers.{task}.{key}",
                    source_path=config.source_path,
                )


def effective_provider(config: All2TextConfig, task: str) -> ProviderConfig:
    provider = config.provider(task)
    if provider_allowed_by_profile(config.options, task):
        return provider
    params = dict(provider.params)
    params["disabled_by_profile"] = config.options.profile
    params["configured_enabled"] = provider.enabled
    return ProviderConfig(name=provider.name, enabled=False, params=params)


def provider_allowed_by_profile(options: RunOptions, task: str) -> bool:
    requirement = PROVIDER_PROFILE_REQUIREMENTS.get(task)
    if requirement == "external_tools":
        return bool(options.allow_external_tools)
    if requirement == "local_models":
        return bool(options.allow_local_models)
    return True


def _coerce_int(value: Any, field: str, *, source_path: str | None, minimum: int) -> int:
    if isinstance(value, bool):
        raise ValueError(
            _config_error(f"{field} must be an integer >= {minimum}, got boolean", source_path)
        )
    try:
        if isinstance(value, float):
            if not math.isfinite(value) or not value.is_integer():
                raise ValueError
            number = int(value)
        elif isinstance(value, str):
            stripped = value.strip()
            try:
                number = int(stripped)
            except ValueError:
                as_float = float(stripped)
                if not math.isfinite(as_float) or not as_float.is_integer():
                    raise ValueError
                number = int(as_float)
        else:
            number = int(value)
    except (TypeError, ValueError):
        raise ValueError(
            _config_error(f"{field} must be an integer >= {minimum}, got {value!r}", source_path)
        ) from None
    if number < minimum:
        raise ValueError(_config_error(f"{field} must be >= {minimum}, got {value!r}", source_path))
    return number


def _coerce_float(
    value: Any,
    field: str,
    *,
    source_path: str | None,
    minimum: float,
    maximum: float | None = None,
    include_minimum: bool = True,
) -> float:
    if isinstance(value, bool):
        raise ValueError(_config_error(f"{field} must be numeric, got boolean", source_path))
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(_config_error(f"{field} must be numeric, got {value!r}", source_path)) from None
    if not math.isfinite(number):
        raise ValueError(_config_error(f"{field} must be finite, got {value!r}", source_path))
    if include_minimum:
        too_low = number < minimum
        comparator = f">= {minimum:g}"
    else:
        too_low = number <= minimum
        comparator = f"> {minimum:g}"
    if too_low:
        raise ValueError(_config_error(f"{field} must be {comparator}, got {value!r}", source_path))
    if maximum is not None and number > maximum:
        raise ValueError(
            _config_error(f"{field} must be <= {maximum:g}, got {value!r}", source_path)
        )
    return number


def _coerce_bool(value: Any, field: str, *, source_path: str | None) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in {0, 1}:
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().casefold()
        if lowered in {"1", "true", "yes", "on", "enabled"}:
            return True
        if lowered in {"0", "false", "no", "off", "disabled"}:
            return False
    raise ValueError(_config_error(f"{field} must be a boolean, got {value!r}", source_path))


def _config_error(message: str, source_path: str | None) -> str:
    return f"{source_path}: {message}" if source_path else message


def _load_toml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"all2text config file does not exist: {path}")
    try:
        import tomllib  # type: ignore[attr-defined]
    except ModuleNotFoundError:
        try:
            import tomli as tomllib  # type: ignore[no-redef]
        except ModuleNotFoundError:
            return _load_basic_toml(path)
    with path.open("rb") as handle:
        data = tomllib.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"all2text config root must be a TOML table: {path}")
    return data


def _load_basic_toml(path: Path) -> dict[str, Any]:
    """Parse the simple TOML subset used by all2text.default.toml.

    This fallback keeps config files usable on Python 3.8 installs that have no
    tomli. It intentionally supports only tables and scalar string/bool/int/float
    values; full TOML remains delegated to tomllib/tomli when available.
    """

    root: dict[str, Any] = {}
    current = root
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = _strip_toml_comment(raw_line).strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            names = [part.strip() for part in line[1:-1].split(".") if part.strip()]
            if not names:
                raise ValueError(f"empty TOML table at {path}:{line_number}")
            current = root
            for name in names:
                value = current.setdefault(name, {})
                if not isinstance(value, dict):
                    raise ValueError(f"TOML table conflicts with scalar at {path}:{line_number}: {name}")
                current = value
            continue
        if "=" not in line:
            raise ValueError(f"unsupported TOML line at {path}:{line_number}: {raw_line}")
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            raise ValueError(f"empty TOML key at {path}:{line_number}")
        current[key] = _parse_basic_toml_value(value.strip())
    return root


def _strip_toml_comment(line: str) -> str:
    in_string = False
    escaped = False
    result: list[str] = []
    for char in line:
        if escaped:
            result.append(char)
            escaped = False
            continue
        if char == "\\" and in_string:
            result.append(char)
            escaped = True
            continue
        if char == '"':
            in_string = not in_string
            result.append(char)
            continue
        if char == "#" and not in_string:
            break
        result.append(char)
    return "".join(result)


def _parse_basic_toml_value(value: str) -> Any:
    if value.startswith('"') and value.endswith('"'):
        return bytes(value[1:-1], "utf-8").decode("unicode_escape")
    lowered = value.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    try:
        if any(char in value for char in (".", "e", "E")):
            return float(value)
        return int(value)
    except ValueError:
        return value


def config_for_context(config: object | None) -> All2TextConfig:
    return config if isinstance(config, All2TextConfig) else default_config()
