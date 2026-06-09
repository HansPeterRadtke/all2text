from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Iterable


COVERAGE_SCHEMA = "all2text.coverage_matrix.v1"
PLATFORM_MANIFEST_SCHEMA = "all2text.platform_manifest.v1"


@dataclass
class CoverageFamily:
    id: str
    title: str
    status: str
    required: bool = True
    selected_provider: str = ""
    fallback_provider: str = ""
    install_action_ids: list[str] = field(default_factory=list)
    optional_action_ids: list[str] = field(default_factory=list)
    blocker: str = ""
    notes: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def platform_manifest(environment: dict[str, Any] | None = None) -> dict[str, Any]:
    env = environment or {}
    system = str(env.get("normalized_system") or "").lower()
    arch = str(env.get("architecture") or "unknown").lower()
    jetson = bool(env.get("is_jetson"))
    managers = set(str(item) for item in env.get("package_managers") or [])
    has_docker = bool(env.get("docker")) or "docker" in managers
    native_packages: list[str]
    python_env = "uv_or_venv"
    service_route = "openai_compatible_or_llama_cpp"
    warnings: list[str] = []

    if system.startswith("windows"):
        native_packages = ["winget", "choco"]
        python_env = "windows_venv_or_uv"
        service_route = "llama_cpp_or_wsl_service"
        if arch in {"aarch64", "arm64"}:
            warnings.append("Windows ARM64 has partial package coverage; prefer x64 emulation or service routes for heavy providers.")
    elif system.startswith("darwin"):
        native_packages = ["brew"]
        python_env = "venv_uv_or_brew_python"
        service_route = "brew_llama_cpp_or_external_service"
    else:
        native_packages = [manager for manager in ("apt-get", "dnf", "yum", "pacman", "zypper") if manager in managers]
        if not native_packages:
            native_packages = ["system_package_manager"]
        if arch in {"aarch64", "arm64"}:
            service_route = "llama_cpp_edge_or_container_service"
            if jetson:
                python_env = "isolated_python311_cpu_headless_on_jetson"
                warnings.append("Do not use unrestricted PyPI CUDA/Torch stacks on Jetson; use CPU/headless isolated envs or containers.")
            warnings.append("PaddlePaddle local ARM64 runtime is not a default route; use Docling/RapidOCR/Tesseract or service/container fallback.")
        else:
            service_route = "docker_vllm_sglang_or_llama_cpp"

    return {
        "schema": PLATFORM_MANIFEST_SCHEMA,
        "system": system or "unknown",
        "architecture": arch,
        "is_jetson": jetson,
        "native_package_routes": native_packages,
        "python_env_route": python_env,
        "service_route": service_route,
        "container_route": "docker_or_nvidia_container_toolkit" if has_docker or not system.startswith("windows") else "wsl_or_external_service",
        "model_route": "external_model_root_with_cache_and_explicit_large_model_approval",
        "warnings": warnings,
    }


def build_coverage_matrix(
    actions: Iterable[dict[str, Any]],
    environment: dict[str, Any] | None = None,
    *,
    profile: str = "full",
    mode: str = "full",
) -> dict[str, Any]:
    action_map = {str(action.get("id")): action for action in actions if isinstance(action, dict)}
    manifest = platform_manifest(environment)
    families = [family.to_dict() for family in _coverage_families(action_map, manifest, profile=profile, mode=mode)]
    summary = coverage_summary(families)
    return {
        "schema": COVERAGE_SCHEMA,
        "profile": profile,
        "mode": mode,
        "platform_manifest": manifest,
        "families": families,
        "summary": summary,
    }


def coverage_summary(families: Iterable[dict[str, Any]]) -> dict[str, Any]:
    items = list(families)
    counts: dict[str, int] = {}
    for item in items:
        status = str(item.get("status") or "unknown")
        counts[status] = counts.get(status, 0) + 1
    missing_required = [
        str(item.get("id"))
        for item in items
        if item.get("required", True) and item.get("status") == "missing"
    ]
    degraded_required = [
        str(item.get("id"))
        for item in items
        if item.get("required", True) and item.get("status") == "degraded"
    ]
    optional = [str(item.get("id")) for item in items if item.get("status") == "optional"]
    return {
        "counts": counts,
        "missing_required": missing_required,
        "degraded_required": degraded_required,
        "optional": optional,
        "prompt_recommended": bool(missing_required),
        "required_covered": not missing_required,
    }


def _coverage_families(
    actions: dict[str, dict[str, Any]],
    manifest: dict[str, Any],
    *,
    profile: str,
    mode: str,
) -> list[CoverageFamily]:
    def ok(*ids: str) -> bool:
        return any(str(actions.get(action_id, {}).get("status")) == "satisfied" for action_id in ids)

    def evidence(*ids: str) -> list[str]:
        values: list[str] = []
        for action_id in ids:
            action = actions.get(action_id) or {}
            if action.get("status") == "satisfied":
                values.append(action_id)
        return values

    def missing(title: str, family_id: str, actions_needed: list[str], blocker: str) -> CoverageFamily:
        return CoverageFamily(
            id=family_id,
            title=title,
            status="missing",
            selected_provider="",
            install_action_ids=actions_needed,
            blocker=blocker,
        )

    families: list[CoverageFamily] = [
        CoverageFamily("plain_text", "Plain text and source text", "covered", selected_provider="builtin_text", evidence=["builtin"]),
        CoverageFamily("archives_compressed", "Archives and compression", "covered", selected_provider="builtin_archive", evidence=["builtin"]),
        CoverageFamily("email_rtf", "Email and RTF", "covered", selected_provider="builtin_email_rtf", evidence=["builtin"]),
        CoverageFamily("geospatial", "Geospatial text formats", "covered", selected_provider="builtin_geojson_kml", evidence=["builtin"]),
    ]

    if ok("docling"):
        families.append(CoverageFamily("office_pdf", "Office, ODF, and PDF", "covered", selected_provider="docling", fallback_provider="libreoffice/native", install_action_ids=["docling", "libreoffice"], evidence=evidence("docling", "libreoffice")))
        families.append(CoverageFamily("tables", "Tables in documents", "covered", selected_provider="docling", fallback_provider="native_spreadsheet", install_action_ids=["docling"], evidence=evidence("docling")))
    elif ok("libreoffice"):
        families.append(CoverageFamily("office_pdf", "Office, ODF, and PDF", "degraded", selected_provider="libreoffice/native", fallback_provider="docling", install_action_ids=["libreoffice", "docling"], blocker="Docling is missing, so rich layout/table semantics are degraded.", evidence=evidence("libreoffice")))
        families.append(CoverageFamily("tables", "Tables in documents", "degraded", selected_provider="native_spreadsheet", fallback_provider="docling", install_action_ids=["docling"], blocker="Rich PDF/table intelligence is missing without Docling."))
    else:
        families.append(missing("Office, ODF, and PDF", "office_pdf", ["libreoffice", "docling"], "Install LibreOffice and/or Docling."))
        families.append(missing("Tables in documents", "tables", ["docling"], "Install Docling or another table provider."))

    if ok("tesseract") or ok("docling"):
        families.append(CoverageFamily("ocr", "OCR", "covered", selected_provider="docling/tesseract", fallback_provider="rapidocr", install_action_ids=["tesseract", "docling"], evidence=evidence("tesseract", "docling")))
    else:
        families.append(missing("OCR", "ocr", ["tesseract", "docling"], "Install Tesseract, Docling/RapidOCR, or an OCR service."))

    if ok("deplot", "unichart", "chartgemma"):
        families.append(CoverageFamily("charts", "Charts and plots", "covered", selected_provider="deplot/unichart/chartgemma", fallback_provider="vlm", install_action_ids=["deplot", "unichart", "chartgemma"], optional_action_ids=["chartgemma"], evidence=evidence("deplot", "unichart", "chartgemma")))
    elif ok("docling") or ok("qwen_vl_gguf"):
        families.append(CoverageFamily("charts", "Charts and plots", "degraded", selected_provider="docling_or_vlm_baseline", fallback_provider="chartgemma", install_action_ids=["chartgemma", "deplot", "unichart"], optional_action_ids=["chartgemma"], blocker="Chart-specialized model is optional but not installed."))
    else:
        families.append(missing("Charts and plots", "charts", ["deplot", "unichart", "chartgemma", "qwen_vl_gguf"], "Install a chart model or VLM route."))

    if ok("qwen_vl_gguf") and ok("llama_cpp"):
        families.append(CoverageFamily("images_vlm", "Images and VLM", "covered", selected_provider="llama_cpp_qwen_vl", fallback_provider="tesseract_image_ocr", install_action_ids=["llama_cpp", "qwen_vl_gguf"], evidence=evidence("llama_cpp", "qwen_vl_gguf")))
    elif ok("tesseract"):
        families.append(CoverageFamily("images_vlm", "Images and VLM", "degraded", selected_provider="image_metadata_tesseract", fallback_provider="llama_cpp_qwen_vl", install_action_ids=["llama_cpp", "qwen_vl_gguf"], blocker="VLM route is missing; image OCR/metadata route is available.", evidence=evidence("tesseract")))
    else:
        families.append(missing("Images and VLM", "images_vlm", ["tesseract", "llama_cpp", "qwen_vl_gguf"], "Install Tesseract for OCR or a VLM service/model."))

    whisper_model = ok("whisper_cpp_tiny", "whisper_cpp_base", "faster_whisper_tiny", "faster_whisper_base", "faster_whisper_small")
    if ok("whisper_cpp") and whisper_model:
        families.append(CoverageFamily("audio", "Audio ASR and classification", "covered", selected_provider="whisper_cpp", fallback_provider="faster_whisper", install_action_ids=["whisper_cpp", "whisper_cpp_tiny", "whisper_cpp_base"], evidence=evidence("whisper_cpp", "whisper_cpp_tiny", "whisper_cpp_base", "faster_whisper_tiny", "faster_whisper_base", "faster_whisper_small")))
    elif ok("ffmpeg", "ffprobe"):
        families.append(CoverageFamily("audio", "Audio ASR and classification", "degraded", selected_provider="ffprobe_audio_metadata", fallback_provider="whisper_cpp", install_action_ids=["whisper_cpp", "whisper_cpp_tiny"], blocker="ASR model route is missing; metadata/classification route is available.", evidence=evidence("ffmpeg", "ffprobe")))
    else:
        families.append(missing("Audio ASR and classification", "audio", ["ffmpeg", "ffprobe", "whisper_cpp", "whisper_cpp_tiny"], "Install FFmpeg and an ASR route."))

    if ok("ffmpeg", "ffprobe"):
        families.append(CoverageFamily("video", "Video metadata, keyframes, OCR, VLM", "covered" if ok("tesseract", "qwen_vl_gguf") else "degraded", selected_provider="ffmpeg_keyframes", fallback_provider="tesseract_or_vlm", install_action_ids=["ffmpeg", "ffprobe", "tesseract", "qwen_vl_gguf"], evidence=evidence("ffmpeg", "ffprobe", "tesseract", "qwen_vl_gguf")))
    else:
        families.append(missing("Video metadata, keyframes, OCR, VLM", "video", ["ffmpeg", "ffprobe"], "Install FFmpeg/ffprobe."))

    if ok("radare2") and ok("capa"):
        families.append(CoverageFamily("binary_static", "Binary/static analysis", "covered", selected_provider="radare2+capa", fallback_provider="file_magic", install_action_ids=["radare2", "capa", "file"], evidence=evidence("radare2", "capa", "file")))
    elif ok("file", "radare2"):
        families.append(CoverageFamily("binary_static", "Binary/static analysis", "degraded", selected_provider="file_or_radare2", fallback_provider="capa", install_action_ids=["capa", "radare2"], blocker="Capa or radare2 is missing; binary metadata is degraded.", evidence=evidence("file", "radare2")))
    else:
        families.append(missing("Binary/static analysis", "binary_static", ["file", "radare2", "capa"], "Install file/libmagic, radare2, and Capa."))

    families.append(CoverageFamily("cad_bim", "CAD and BIM", "degraded", selected_provider="schema_probe", fallback_provider="ezdxf_ifcopenshell_external_env", install_action_ids=["ezdxf", "ifcopenshell"], blocker="CAD/BIM rich extraction needs optional external envs; schema probes are available.", evidence=["builtin_schema_probe"]))
    families.append(CoverageFamily("scientific_arrays", "Scientific arrays", "degraded", selected_provider="safe_schema_probe", fallback_provider="h5py_netcdf4_astropy_pixi", install_action_ids=["h5py", "netcdf4", "astropy", "pyarrow"], blocker="Scientific rich extraction depends on optional native stacks; safe schema probes are available.", evidence=["builtin_schema_probe"]))

    _apply_platform_notes(families, manifest)
    return families


def _apply_platform_notes(families: list[CoverageFamily], manifest: dict[str, Any]) -> None:
    arch = str(manifest.get("architecture") or "")
    system = str(manifest.get("system") or "")
    for family in families:
        if family.id in {"ocr", "office_pdf", "tables"} and arch in {"aarch64", "arm64"}:
            family.notes.append("ARM64 route prefers Docling/RapidOCR/Tesseract or service/container providers; PaddleOCR-VL local runtime is not a default requirement.")
        if family.id == "images_vlm" and system.startswith("windows"):
            family.notes.append("Windows VLM route prefers llama.cpp/Ollama/WSL or external OpenAI-compatible services; native vLLM is not assumed.")


def coverage_prompt_recommended(coverage: dict[str, Any] | None) -> bool:
    if not coverage:
        return False
    summary = coverage.get("summary") or {}
    return bool(summary.get("missing_required"))
