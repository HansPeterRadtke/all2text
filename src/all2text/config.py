from __future__ import annotations

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


DEFAULT_PROVIDERS: dict[str, ProviderConfig] = {
    "ocr": ProviderConfig(
        name="none",
        enabled=False,
        params={
            "language": "eng",
            "timeout_seconds": 30,
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
        },
    ),
    "document_intelligence": ProviderConfig(name="none", enabled=False, params={}),
    "speech": ProviderConfig(
        name="none",
        enabled=False,
        params={"transcribe": False, "translate": False, "language_detection": False},
    ),
    "video_frames": ProviderConfig(
        name="none",
        enabled=False,
        params={"sample_frames": False, "ocr": False, "vlm": False},
    ),
}


def default_config() -> All2TextConfig:
    return All2TextConfig(
        modules={key: ModuleConfig(backend=value) for key, value in DEFAULT_MODULES.items()},
        providers={key: ProviderConfig(value.name, value.enabled, dict(value.params)) for key, value in DEFAULT_PROVIDERS.items()},
    )


def load_config(path: str | Path | None = None) -> All2TextConfig:
    config_path = Path(path or os.environ.get("ALL2TEXT_CONFIG", "")).expanduser() if path or os.environ.get("ALL2TEXT_CONFIG") else None
    if config_path is None:
        return default_config()
    data = _load_toml(config_path)
    return config_from_dict(data, source_path=str(config_path))


def config_from_dict(data: dict[str, Any], *, source_path: str | None = None) -> All2TextConfig:
    base = default_config()
    run_options = _run_options_from_dict(data.get("run") or {}, base.options)
    modules = dict(base.modules)
    for key, value in (data.get("modules") or {}).items():
        if isinstance(value, str):
            modules[str(key)] = ModuleConfig(backend=value)
        elif isinstance(value, dict):
            backend = str(value.get("backend") or modules.get(str(key), ModuleConfig("")).backend)
            params = {str(k): v for k, v in value.items() if k != "backend"}
            modules[str(key)] = ModuleConfig(backend=backend, params=params)
    providers = dict(base.providers)
    for key, value in (data.get("providers") or {}).items():
        if not isinstance(value, dict):
            continue
        current = providers.get(str(key), ProviderConfig())
        name = str(value.get("name", current.name))
        enabled = _bool_value(value.get("enabled", current.enabled))
        params = dict(current.params)
        params.update({str(k): v for k, v in value.items() if k not in {"name", "enabled"}})
        providers[str(key)] = ProviderConfig(name=name, enabled=enabled, params=params)
    return All2TextConfig(
        options=run_options,
        modules=modules,
        providers=providers,
        raw=data,
        source_path=source_path,
    )


def _run_options_from_dict(data: dict[str, Any], defaults: RunOptions) -> RunOptions:
    values = asdict(defaults)
    for key in values:
        if key in data:
            values[key] = data[key]
    return RunOptions(**values)


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
