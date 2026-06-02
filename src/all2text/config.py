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
class All2TextConfig:
    options: RunOptions = field(default_factory=RunOptions)
    modules: dict[str, ModuleConfig] = field(default_factory=dict)
    providers: dict[str, ProviderConfig] = field(default_factory=dict)
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

    def with_options(self, options: RunOptions) -> "All2TextConfig":
        return replace(self, options=options)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_path": self.source_path,
            "options": asdict(self.options),
            "modules": {key: asdict(value) for key, value in sorted(self.modules.items())},
            "providers": {key: asdict(value) for key, value in sorted(self.providers.items())},
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
    "geospatial": "text_exact_backend",
    "cad_or_technical": "text_exact_backend",
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
    "ocr": {"none", "tesseract"},
    "vlm": {"none", "openai_compatible"},
    "llm_text": {"none", "openai_compatible"},
    "chart": {"none", "deplot", "chartgemma", "unichart"},
    "document_intelligence": {"none"},
    "speech": {"none", "whisper", "faster_whisper", "vosk"},
    "video_frames": {"none", "ffmpeg"},
}

RUN_OPTION_POSITIVE_INT_FIELDS = {
    "max_header_bytes",
    "max_hash_bytes",
    "max_binary_sample_bytes",
    "max_archive_members",
}

MODULE_NON_NEGATIVE_INT_PARAMS = {
    "max_ffprobe_json_chars",
    "max_pdf_pages",
    "max_text_blocks",
    "max_cells_per_sheet",
}

PROVIDER_POSITIVE_INT_PARAMS: dict[str, set[str]] = {
    "ocr": {"timeout_seconds", "min_characters"},
    "vlm": {"timeout_seconds", "max_tokens"},
    "llm_text": {"timeout_seconds", "max_tokens"},
    "document_intelligence": {"timeout_seconds"},
    "speech": {"timeout_seconds"},
    "video_frames": {"timeout_seconds", "max_frames"},
}

PROVIDER_POSITIVE_FLOAT_PARAMS: dict[str, set[str]] = {
    "video_frames": {"interval_seconds"},
}

PROVIDER_RATIO_PARAMS: dict[str, set[str]] = {
    "ocr": {"min_alnum_ratio"},
    "chart": {"confidence_threshold"},
}

PROVIDER_PERCENT_PARAMS: dict[str, set[str]] = {
    "ocr": {"min_confidence"},
}


DEFAULT_PROVIDERS: dict[str, ProviderConfig] = {
    "ocr": ProviderConfig(
        name="none",
        enabled=False,
        params={
            "language": "eng",
            "timeout_seconds": 30,
            "preprocess": "none",
            "min_characters": 4,
            "min_alnum_ratio": 0.35,
            "min_confidence": 35,
            "auto_invoke": False,
        },
    ),
    "vlm": ProviderConfig(
        name="openai_compatible",
        enabled=False,
        params={
            "base_url": "http://127.0.0.1:14830/v1",
            "model": "Qwen2.5-VL-3B-Instruct-Q4_K_M.gguf",
            "timeout_seconds": 120,
            "max_tokens": 300,
            "temperature": 0,
            "prompt": "Describe visible evidence only.",
            "auto_invoke": False,
        },
    ),
    "llm_text": ProviderConfig(
        name="openai_compatible",
        enabled=False,
        params={
            "base_url": "http://127.0.0.1:14829/v1",
            "model": "Qwen2.5-14B-Instruct-Q4_K_M.gguf",
            "timeout_seconds": 120,
            "max_tokens": 512,
            "temperature": 0,
            "prompt": "Summarize extracted text using only supplied evidence.",
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
        },
    ),
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
    run_options = _run_options_from_dict(run_data if run_data is not None else {}, base.options)
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
        enabled = _bool_value(value.get("enabled", current.enabled))
        params = dict(current.params)
        params.update({str(k): v for k, v in value.items() if k not in {"name", "enabled"}})
        providers[str(key)] = ProviderConfig(name=name, enabled=enabled, params=params)
    config = All2TextConfig(
        options=run_options,
        modules=modules,
        providers=providers,
        raw=data,
        source_path=source_path,
    )
    validate_config(config)
    return config


def _run_options_from_dict(data: dict[str, Any], defaults: RunOptions) -> RunOptions:
    if not isinstance(data, dict):
        raise ValueError("run must be a table")
    values = asdict(defaults)
    for key in values:
        if key in data:
            values[key] = data[key]
    return RunOptions(**values)


def validate_config(config: All2TextConfig) -> None:
    for field_name in RUN_OPTION_POSITIVE_INT_FIELDS:
        _require_int(
            getattr(config.options, field_name),
            f"run.{field_name}",
            source_path=config.source_path,
            minimum=1,
        )
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
                _require_int(
                    module.params[key],
                    f"modules.{family}.{key}",
                    source_path=config.source_path,
                    minimum=0,
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
                _require_int(
                    provider.params[key],
                    f"providers.{task}.{key}",
                    source_path=config.source_path,
                    minimum=1,
                )
        for key in PROVIDER_POSITIVE_FLOAT_PARAMS.get(task, set()):
            if key in provider.params:
                _require_float(
                    provider.params[key],
                    f"providers.{task}.{key}",
                    source_path=config.source_path,
                    minimum=0.0,
                    include_minimum=False,
                )
        for key in PROVIDER_RATIO_PARAMS.get(task, set()):
            if key in provider.params:
                _require_float(
                    provider.params[key],
                    f"providers.{task}.{key}",
                    source_path=config.source_path,
                    minimum=0.0,
                    maximum=1.0,
                )
        for key in PROVIDER_PERCENT_PARAMS.get(task, set()):
            if key in provider.params:
                _require_float(
                    provider.params[key],
                    f"providers.{task}.{key}",
                    source_path=config.source_path,
                    minimum=0.0,
                    maximum=100.0,
                )


def _require_int(value: Any, field: str, *, source_path: str | None, minimum: int) -> None:
    if isinstance(value, bool):
        raise ValueError(
            _config_error(f"{field} must be an integer >= {minimum}, got boolean", source_path)
        )
    if isinstance(value, float) and not value.is_integer():
        raise ValueError(
            _config_error(f"{field} must be an integer >= {minimum}, got {value!r}", source_path)
        )
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ValueError(
            _config_error(f"{field} must be an integer >= {minimum}, got {value!r}", source_path)
        ) from None
    if number < minimum:
        raise ValueError(_config_error(f"{field} must be >= {minimum}, got {value!r}", source_path))


def _require_float(
    value: Any,
    field: str,
    *,
    source_path: str | None,
    minimum: float,
    maximum: float | None = None,
    include_minimum: bool = True,
) -> None:
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


def _bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on", "enabled"}
    return bool(value)


def config_for_context(config: object | None) -> All2TextConfig:
    return config if isinstance(config, All2TextConfig) else default_config()
