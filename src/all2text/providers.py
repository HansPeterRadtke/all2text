from __future__ import annotations

import base64
import importlib.util
import json
import os
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from typing import Any

from all2text.capabilities import resolve_external_tool
from all2text.config import ProviderConfig, config_for_context, effective_provider

TEXT_MODEL_ENDPOINTS = [
    "http://127.0.0.1:14829/v1",
    "http://127.0.0.1:8080/v1",
    "http://127.0.0.1:8000/v1",
    "http://127.0.0.1:1234/v1",
    "http://127.0.0.1:11434/v1",
]

VISION_MODEL_ENDPOINTS = [
    "http://127.0.0.1:14830/v1",
    "http://127.0.0.1:8080/v1",
    "http://127.0.0.1:8000/v1",
    "http://127.0.0.1:1234/v1",
    "http://127.0.0.1:11434/v1",
]


@dataclass(frozen=True)
class ProviderStatus:
    name: str
    kind: str
    enabled: bool
    available: bool
    source: str | None = None
    error: str | None = None
    details: dict[str, Any] | None = None
    lifecycle: dict[str, bool] | None = None
    evidence: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RoutePlan:
    family: str
    primary_route: str
    provider_sequence: list[str]
    fallback_reasons: list[str]
    evidence: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ProviderCandidate:
    name: str
    family: str
    kind: str
    python_modules: tuple[str, ...] = ()
    executables: tuple[str, ...] = ()
    model_hints: tuple[str, ...] = ()
    endpoint_task: str | None = None
    execution_status: str = "contract_only"
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


PROVIDER_CANDIDATES: tuple[ProviderCandidate, ...] = (
    ProviderCandidate("docling", "document_ocr_layout", "document_parser", ("docling",), notes="High-level PDF/document conversion provider."),
    ProviderCandidate("paddleocr_vl", "document_ocr_layout", "document_ocr_vlm", ("paddleocr", "paddle"), ("paddleocr",), ("PaddleOCR", "paddleocr"), notes="Document OCR/layout VLM; model files are external."),
    ProviderCandidate("glm_ocr", "document_ocr_layout", "document_ocr_vlm", ("transformers",), model_hints=("GLM-OCR", "glm-ocr"), notes="External multimodal OCR model contract."),
    ProviderCandidate("olmocr", "document_ocr_layout", "pdf_ocr", ("olmocr",), model_hints=("olmOCR", "olmocr"), notes="Heavy PDF OCR/linearization provider contract."),
    ProviderCandidate("tesseract", "ocr", "ocr_engine", ("pytesseract",), ("tesseract",), execution_status="implemented"),
    ProviderCandidate("paddleocr", "ocr", "ocr_engine", ("paddleocr", "paddle"), ("paddleocr",)),
    ProviderCandidate("surya", "ocr", "ocr_layout", ("surya",)),
    ProviderCandidate("deterministic_image_profile", "image_routing", "deterministic_classifier", execution_status="implemented", notes="Header/Pillow/geometry route classifier."),
    ProviderCandidate("clip", "image_routing", "image_classifier", ("transformers",), model_hints=("clip", "CLIP")),
    ProviderCandidate("open_clip", "image_routing", "image_classifier", ("open_clip",), model_hints=("open_clip", "CLIP")),
    ProviderCandidate("siglip2", "image_routing", "image_classifier", ("transformers",), model_hints=("siglip", "SigLIP")),
    ProviderCandidate("siglip", "image_routing", "image_classifier", ("transformers",), model_hints=("siglip", "SigLIP")),
    ProviderCandidate("openai_compatible_vlm", "image_vlm", "vision_language_model", endpoint_task="vlm", execution_status="implemented"),
    ProviderCandidate("deterministic_chart_geometry", "chart", "chart_heuristic", ("PIL", "numpy"), execution_status="implemented"),
    ProviderCandidate("deplot", "chart", "chart_to_table", ("transformers", "torch"), model_hints=("deplot", "google_deplot", "Pix2Struct")),
    ProviderCandidate("unichart", "chart", "chart_vlm", ("transformers", "torch"), model_hints=("unichart", "UniChart")),
    ProviderCandidate("chartgemma", "chart", "chart_vlm", ("transformers", "torch"), model_hints=("chartgemma", "ChartGemma")),
    ProviderCandidate("chartcoder", "chart", "chart_structure", ("transformers", "torch"), model_hints=("chartcoder", "ChartCoder")),
    ProviderCandidate("chartocr", "chart", "chart_ocr", model_hints=("ChartOCR", "chartocr")),
    ProviderCandidate("ffprobe", "audio", "media_metadata", executables=("ffprobe",), execution_status="implemented"),
    ProviderCandidate("yamnet", "audio", "audio_classifier", ("tensorflow",), model_hints=("yamnet", "YAMNet")),
    ProviderCandidate("panns", "audio", "audio_classifier", ("panns_inference",), model_hints=("PANN", "panns")),
    ProviderCandidate("openbeats", "audio", "audio_classifier", ("transformers",), model_hints=("OpenBEATs", "openbeats")),
    ProviderCandidate("clap", "audio", "audio_classifier", ("laion_clap",), model_hints=("CLAP", "clap")),
    ProviderCandidate("whisper_cpp", "audio", "asr", executables=("whisper-cli", "whisper.cpp"), model_hints=("whisper", "Whisper")),
    ProviderCandidate(
        "faster_whisper",
        "audio",
        "asr",
        ("faster_whisper",),
        model_hints=("faster-whisper", "faster_whisper"),
        execution_status="implemented_when_dependency_found",
    ),
    ProviderCandidate("whisper", "audio", "asr", ("whisper",), model_hints=("whisper", "Whisper")),
    ProviderCandidate("parakeet", "audio", "asr", ("nemo",), model_hints=("parakeet", "Parakeet")),
    ProviderCandidate("canary", "audio", "asr", ("nemo",), model_hints=("canary", "Canary")),
    ProviderCandidate("pyannote", "audio", "diarization", ("pyannote.audio",), model_hints=("pyannote", "diarization")),
    ProviderCandidate("diarizen", "audio", "diarization", ("diarizen",), model_hints=("diarizen", "Diarization")),
    ProviderCandidate("nemo", "audio", "diarization", ("nemo",), model_hints=("nemo", "diarization")),
    ProviderCandidate("ffmpeg", "video", "frame_extractor", executables=("ffmpeg",), execution_status="implemented"),
    ProviderCandidate("opencv", "video", "frame_analyzer", ("cv2",), execution_status="implemented_for_detection"),
    ProviderCandidate("pyscenedetect", "video", "scene_detection", ("scenedetect",)),
    ProviderCandidate("ezdxf", "cad_bim", "dxf_schema", ("ezdxf",), execution_status="implemented_when_dependency_found"),
    ProviderCandidate("ifcopenshell", "cad_bim", "ifc_bim_schema", ("ifcopenshell",)),
    ProviderCandidate("h5py", "scientific_geospatial", "hdf5_schema", ("h5py",), execution_status="implemented_when_dependency_found"),
    ProviderCandidate("h5netcdf", "scientific_geospatial", "netcdf_schema", ("h5netcdf",)),
    ProviderCandidate("netcdf4", "scientific_geospatial", "netcdf_schema", ("netCDF4",), execution_status="implemented_when_dependency_found"),
    ProviderCandidate("astropy", "scientific_geospatial", "fits_schema", ("astropy",), execution_status="implemented_when_dependency_found"),
    ProviderCandidate("pyarrow", "scientific_geospatial", "parquet_schema", ("pyarrow",), execution_status="implemented_when_dependency_found"),
    ProviderCandidate("scipy", "scientific_geospatial", "matlab_schema", ("scipy",), execution_status="implemented_when_dependency_found"),
    ProviderCandidate("numpy", "scientific_geospatial", "npy_schema", ("numpy",), execution_status="implemented"),
    ProviderCandidate("pyshp", "scientific_geospatial", "shapefile_schema", ("shapefile",), execution_status="implemented_when_dependency_found"),
    ProviderCandidate("pyproj", "scientific_geospatial", "crs_transform_metadata", ("pyproj",), execution_status="implemented_when_dependency_found"),
    ProviderCandidate("shapely", "scientific_geospatial", "geometry_metadata", ("shapely",), execution_status="implemented_when_dependency_found"),
    ProviderCandidate("pefile", "binary_metadata", "pe_metadata", ("pefile",), execution_status="implemented_when_dependency_found"),
    ProviderCandidate("macholib", "binary_metadata", "macho_metadata", ("macholib",)),
    ProviderCandidate("lief", "binary_metadata", "cross_binary_metadata", ("lief",), execution_status="implemented_when_dependency_found"),
    ProviderCandidate("capa", "binary_metadata", "binary_capability_metadata", executables=("capa",)),
    ProviderCandidate("radare2", "binary_metadata", "binary_metadata_tool", executables=("radare2", "r2")),
    ProviderCandidate("file", "binary_metadata", "file_type_metadata", executables=("file",), execution_status="implemented"),
)


def provider_statuses(config: object | None, *, family: str | None = None) -> list[ProviderStatus]:
    cfg = config_for_context(config)
    statuses: list[ProviderStatus] = []
    if family in {None, "image", "document", "chart", "video"}:
        statuses.extend(
            [
                ocr_status(
                    effective_provider(cfg, "ocr"),
                    configured=cfg.provider("ocr"),
                    profile=cfg.options.profile,
                    tool=resolve_external_tool(cfg, "tesseract"),
                ),
                vlm_status(
                    effective_provider(cfg, "vlm"),
                    configured=cfg.provider("vlm"),
                    profile=cfg.options.profile,
                    auto_detect=cfg.options.auto_detect_local_models,
                ),
                configured_candidate_status(
                    "image_classifier",
                    effective_provider(cfg, "image_classifier"),
                    configured=cfg.provider("image_classifier"),
                    profile=cfg.options.profile,
                ),
            ]
        )
    if family in {None, "image", "document", "chart"}:
        statuses.extend(
            [
                chart_status(
                    effective_provider(cfg, "chart"),
                    configured=cfg.provider("chart"),
                    profile=cfg.options.profile,
                ),
                document_intelligence_status(
                    effective_provider(cfg, "document_intelligence"),
                    configured=cfg.provider("document_intelligence"),
                    profile=cfg.options.profile,
                ),
            ]
        )
    if family in {None, "audio", "video"}:
        statuses.extend(
            [
                configured_candidate_status(
                    "audio_classifier",
                    effective_provider(cfg, "audio_classifier"),
                    configured=cfg.provider("audio_classifier"),
                    profile=cfg.options.profile,
                ),
                speech_status(
                    effective_provider(cfg, "speech"),
                    configured=cfg.provider("speech"),
                    profile=cfg.options.profile,
                ),
                configured_candidate_status(
                    "diarization",
                    effective_provider(cfg, "diarization"),
                    configured=cfg.provider("diarization"),
                    profile=cfg.options.profile,
                ),
            ]
        )
    if family in {None, "video"}:
        statuses.append(
            video_frame_status(
                effective_provider(cfg, "video_frames"),
                configured=cfg.provider("video_frames"),
                profile=cfg.options.profile,
                tool=resolve_external_tool(cfg, "ffmpeg"),
            )
        )
    if family in {None, "text"}:
        statuses.append(
            llm_text_status(
                effective_provider(cfg, "llm_text"),
                configured=cfg.provider("llm_text"),
                profile=cfg.options.profile,
                auto_detect=cfg.options.auto_detect_local_models,
            )
        )
    if family in {None, "cad_bim"}:
        statuses.append(
            configured_candidate_status(
                "cad",
                effective_provider(cfg, "cad"),
                configured=cfg.provider("cad"),
                profile=cfg.options.profile,
            )
        )
    if family in {None, "scientific_geospatial"}:
        for task in ("scientific", "geospatial"):
            statuses.append(
                configured_candidate_status(
                    task,
                    effective_provider(cfg, task),
                    configured=cfg.provider(task),
                    profile=cfg.options.profile,
                )
            )
    if family in {None, "binary_metadata"}:
        statuses.append(
            configured_candidate_status(
                "binary_metadata",
                effective_provider(cfg, "binary_metadata"),
                configured=cfg.provider("binary_metadata"),
                profile=cfg.options.profile,
            )
        )
    return statuses


def provider_family_statuses(config: object | None, *, family: str | None = None) -> list[ProviderStatus]:
    cfg = config_for_context(config)
    return [
        candidate_status(candidate, cfg)
        for candidate in PROVIDER_CANDIDATES
        if family is None or candidate.family == family
    ]


def candidate_status(candidate: ProviderCandidate, config: Any) -> ProviderStatus:
    if candidate.endpoint_task:
        endpoint = next(
            (
                status
                for status in provider_statuses(config, family=_family_for_endpoint_task(candidate.endpoint_task))
                if status.name == candidate.endpoint_task
            ),
            None,
        )
        if endpoint is not None:
            details = dict(endpoint.details or {})
            details.update({"candidate": candidate.to_dict()})
            return ProviderStatus(
                name=candidate.name,
                kind=candidate.kind,
                enabled=endpoint.enabled,
                available=endpoint.available,
                source=endpoint.source,
                error=endpoint.error,
                details=details,
                lifecycle=dict(endpoint.lifecycle or {}),
                evidence=list(endpoint.evidence or []),
            )

    dependency_results = {module: python_module_available(module) for module in candidate.python_modules}
    executable_results = {
        executable: _which_executable(executable) for executable in candidate.executables
    }
    model_matches = discover_model_hints(candidate.model_hints)

    dependency_found = all(dependency_results.values()) if dependency_results else None
    executable_found = any(executable_results.values()) if executable_results else None
    if candidate.name.startswith("deterministic_"):
        available = True
        error = None
    elif dependency_results and not all(dependency_results.values()):
        available = False
        missing = ", ".join(name for name, found in dependency_results.items() if not found)
        error = f"Python dependency missing: {missing}"
    elif candidate.executables and not executable_found:
        available = False
        error = f"Executable not found: {' or '.join(candidate.executables)}"
    elif candidate.model_hints and not model_matches:
        available = False
        error = "External model files not found under configured/runtime model roots"
    elif candidate.execution_status.startswith("implemented"):
        available = True
        error = None
    else:
        available = False
        error = f"{candidate.name} provider execution adapter is {candidate.execution_status}"

    source = None
    if model_matches:
        source = model_matches[0]
    elif executable_results:
        source = next((path for path in executable_results.values() if path), None)

    evidence = []
    if dependency_results:
        evidence.extend(f"python:{name}={found}" for name, found in sorted(dependency_results.items()))
    if executable_results:
        evidence.extend(f"tool:{name}={bool(path)}" for name, path in sorted(executable_results.items()))
    if model_matches:
        evidence.append(f"model_hint_matches:{len(model_matches)}")
    if candidate.notes:
        evidence.append(candidate.notes)

    return ProviderStatus(
        name=candidate.name,
        kind=candidate.kind,
        enabled=True,
        available=available,
        source=source,
        error=error,
        details={
            "candidate": candidate.to_dict(),
            "python_dependencies": dependency_results,
            "executables": executable_results,
            "model_matches": model_matches[:10],
            "model_roots": [str(path) for path in model_roots()],
            "execution_status": candidate.execution_status,
        },
        lifecycle=provider_lifecycle(
            configured=True,
            enabled=True,
            available=available,
            error=error,
            dependency_found=dependency_found,
            executable_found=executable_found,
            auto_detected=bool(source),
            endpoint_reachable=None,
        ),
        evidence=evidence,
    )


def configured_candidate_status(
    name: str,
    provider: ProviderConfig,
    *,
    configured: ProviderConfig,
    profile: str,
) -> ProviderStatus:
    enabled = provider.enabled and provider.name != "none"
    if provider.get("disabled_by_profile"):
        error = f"{name} provider disabled by profile:{profile}"
        available = False
    elif not enabled:
        error = f"{name} provider disabled by config"
        available = False
    else:
        candidate = next((item for item in PROVIDER_CANDIDATES if item.name == provider.name), None)
        if candidate is None:
            error = f"{name} provider is not implemented in all2text core: {provider.name}"
            available = False
        else:
            status = candidate_status(candidate, config_for_context(None))
            available = status.available and candidate.execution_status.startswith("implemented")
            error = None if available else (status.error or f"{provider.name} execution adapter is not implemented")
    return ProviderStatus(
        name=name,
        kind=name,
        enabled=enabled,
        available=available,
        source=str(provider.get("model_path", "") or provider.get("path", "") or "") or None,
        error=error,
        details={
            "provider": provider.name,
            "configured_enabled": configured.enabled,
            "effective_enabled": enabled,
            "profile": profile,
            "auto_invoke": bool(provider.get("auto_invoke", False)),
            "params": dict(provider.params),
        },
        lifecycle=provider_lifecycle(
            configured=configured.enabled or configured.name != "none",
            enabled=enabled,
            available=available,
            error=error,
            skipped=enabled and not bool(provider.get("auto_invoke", False)),
        ),
        evidence=[f"configured_provider:{provider.name}"],
    )


def plan_image_route(
    image_profile: dict[str, Any],
    statuses: list[ProviderStatus],
    *,
    ocr_attempted: bool,
    chart_candidate: bool,
) -> RoutePlan:
    family = image_family(image_profile, chart_candidate=chart_candidate)
    providers = ["image_header_metadata", "deterministic_image_profile"]
    fallback_reasons: list[str] = []

    if ocr_attempted:
        providers.append("ocr")
    elif family in {"document", "chart", "diagram", "screenshot"}:
        fallback_reasons.append("OCR not attempted because no enabled OCR provider accepted the image")

    if family == "chart":
        if _available(statuses, "chart"):
            providers.append("chart")
            primary_route = "chart_specialist_then_vlm_or_metadata"
        else:
            primary_route = "chart_metadata_ocr_vlm_fallback"
            fallback_reasons.append(_status_error(statuses, "chart") or "chart specialist unavailable")
    elif family == "document":
        primary_route = "document_image_ocr_vlm_or_metadata"
        if _available(statuses, "document_intelligence"):
            providers.append("document_intelligence")
    elif family in {"diagram", "screenshot"}:
        primary_route = "technical_image_ocr_vlm_or_metadata"
    else:
        primary_route = "image_metadata_vlm_optional"

    if _available(statuses, "vlm"):
        providers.append("vlm")
    else:
        fallback_reasons.append(_status_error(statuses, "vlm") or "VLM provider unavailable or disabled")

    return RoutePlan(
        family=family,
        primary_route=primary_route,
        provider_sequence=list(dict.fromkeys(providers)),
        fallback_reasons=list(dict.fromkeys(reason for reason in fallback_reasons if reason)),
        evidence={
            "profile": image_profile.get("profile"),
            "chart_candidate": chart_candidate,
            "ocr_attempted": ocr_attempted,
            "dimensions": image_profile.get("dimensions"),
        },
    )


def image_family(image_profile: dict[str, Any], *, chart_candidate: bool) -> str:
    taxonomy = str(image_profile.get("taxonomy") or "").lower()
    if taxonomy == "chart_plot" or chart_candidate:
        return "chart"
    if taxonomy in {"document_page", "table_screenshot"}:
        return "document"
    if taxonomy == "screenshot_ui":
        return "screenshot"
    if taxonomy in {
        "diagram_flowchart_uml_network",
        "circuit_schematic",
        "mechanical_technical_drawing",
        "architectural_floor_plan",
        "map_plan_heatmap",
        "scientific_medical_image",
    }:
        return "diagram"
    profile = str(image_profile.get("profile") or "").lower()
    if "chart" in profile or "plot" in profile:
        return "chart"
    if "document" in profile or "scan" in profile:
        return "document"
    if "screenshot" in profile or "interface" in profile:
        return "screenshot"
    if "diagram" in profile or "technical" in profile:
        return "diagram"
    return "scene_or_photo"


def ocr_status(
    provider: ProviderConfig,
    *,
    configured: ProviderConfig,
    profile: str,
    tool: dict[str, Any],
) -> ProviderStatus:
    executable = str(tool["source"]) if provider.name == "tesseract" and tool.get("source") else None
    enabled = provider.enabled and provider.name != "none"
    error = None
    available = False
    if provider.get("disabled_by_profile"):
        error = f"OCR disabled by profile:{profile}"
    elif not enabled:
        error = "OCR disabled by config"
    elif provider.name == "tesseract":
        pytesseract_available = importlib.util.find_spec("pytesseract") is not None
        available = bool(executable and pytesseract_available)
        if not executable:
            error = str(tool.get("error") or "tesseract executable not found")
        elif not pytesseract_available:
            error = "Python package not installed for OCR provider: pytesseract"
    else:
        error = f"OCR provider is not implemented in all2text core: {provider.name}"
    return ProviderStatus(
        name="ocr",
        kind="ocr",
        enabled=enabled,
        available=available,
        source=executable,
        error=error,
        details={
            "provider": provider.name,
            "configured_enabled": configured.enabled,
            "effective_enabled": enabled,
            "profile": profile,
            "language": provider.get("language", "eng"),
            "auto_invoke": bool(provider.get("auto_invoke", False)),
            "python_package": "pytesseract",
            "python_package_available": (
                importlib.util.find_spec("pytesseract") is not None if provider.name == "tesseract" else None
            ),
            "tool": tool,
        },
        lifecycle=provider_lifecycle(
            configured=configured.enabled or configured.name != "none",
            enabled=enabled,
            available=available,
            error=error,
            auto_detected=bool(tool.get("auto_detected")),
            dependency_found=(
                importlib.util.find_spec("pytesseract") is not None if provider.name == "tesseract" else None
            ),
            executable_found=bool(executable) if provider.name == "tesseract" else None,
        ),
        evidence=[
            f"provider:{provider.name}",
            f"profile:{profile}",
            f"tool_source:{executable or '<none>'}",
        ],
    )


def vlm_status(
    provider: ProviderConfig,
    *,
    configured: ProviderConfig,
    profile: str,
    auto_detect: bool,
) -> ProviderStatus:
    enabled = provider.enabled and provider.name != "none"
    base_url = str(provider.get("base_url", "") or "").rstrip("/")
    model = str(provider.get("model", "") or "")
    error = None
    available = False
    endpoint_probe: dict[str, Any] | None = None
    if provider.get("disabled_by_profile"):
        error = f"VLM disabled by profile:{profile}"
    elif not enabled:
        error = "VLM disabled by config"
    elif provider.name != "openai_compatible":
        error = f"VLM provider is not implemented in all2text core: {provider.name}"
    elif not base_url or not model:
        error = "openai-compatible VLM requires base_url and model"
    else:
        endpoint_probe = discover_openai_compatible_endpoint(
            provider,
            model=model,
            configured_base_url=base_url,
            defaults=VISION_MODEL_ENDPOINTS,
            auto_detect=auto_detect and bool(provider.get("auto_detect", True)),
        )
        available = bool(endpoint_probe.get("reachable"))
        if available and not bool(provider.get("auto_invoke", False)):
            error = "openai-compatible VLM reachable but auto_invoke=false; not invoked"
        elif not available:
            error = str(endpoint_probe.get("error") or "openai-compatible VLM endpoint unreachable")
    return ProviderStatus(
        name="vlm",
        kind="vision_language_model",
        enabled=enabled,
        available=available,
        source=str((endpoint_probe or {}).get("base_url") or base_url or "") or None,
        error=error,
        details={
            "provider": provider.name,
            "configured_enabled": configured.enabled,
            "effective_enabled": enabled,
            "profile": profile,
            "model": model or None,
            "auto_invoke": bool(provider.get("auto_invoke", False)),
            "endpoint_probe": endpoint_probe,
        },
        lifecycle=provider_lifecycle(
            configured=configured.enabled or configured.name != "none",
            enabled=enabled,
            available=available,
            error=error,
            auto_detected=bool((endpoint_probe or {}).get("base_url")),
            endpoint_reachable=bool((endpoint_probe or {}).get("reachable")) if endpoint_probe else None,
            skipped=available and not bool(provider.get("auto_invoke", False)),
        ),
        evidence=[
            f"provider:{provider.name}",
            f"model:{model or '<none>'}",
            f"base_url:{(endpoint_probe or {}).get('base_url') or base_url or '<none>'}",
        ],
    )


def llm_text_status(
    provider: ProviderConfig,
    *,
    configured: ProviderConfig,
    profile: str,
    auto_detect: bool,
) -> ProviderStatus:
    enabled = provider.enabled and provider.name != "none"
    base_url = str(provider.get("base_url", "") or "").rstrip("/")
    model = str(provider.get("model", "") or "")
    endpoint_probe: dict[str, Any] | None = None
    if provider.get("disabled_by_profile"):
        error = f"text LLM disabled by profile:{profile}"
        available = False
    elif not enabled:
        error = "text LLM disabled by config"
        available = False
    elif provider.name != "openai_compatible":
        error = f"text LLM provider is not implemented in all2text core: {provider.name}"
        available = False
    elif not base_url or not model:
        error = "openai-compatible text LLM requires base_url and model"
        available = False
    else:
        endpoint_probe = discover_openai_compatible_endpoint(
            provider,
            model=model,
            configured_base_url=base_url,
            defaults=TEXT_MODEL_ENDPOINTS,
            auto_detect=auto_detect and bool(provider.get("auto_detect", True)),
        )
        available = bool(endpoint_probe.get("reachable"))
        if available and not bool(provider.get("auto_invoke", False)):
            error = "openai-compatible text LLM reachable but auto_invoke=false; not invoked"
        elif not available:
            error = str(endpoint_probe.get("error") or "openai-compatible text LLM endpoint unreachable")
    return ProviderStatus(
        name="llm_text",
        kind="text_language_model",
        enabled=enabled,
        available=available,
        source=str((endpoint_probe or {}).get("base_url") or base_url or "") or None,
        error=error,
        details={
            "provider": provider.name,
            "configured_enabled": configured.enabled,
            "effective_enabled": enabled,
            "profile": profile,
            "model": model or None,
            "auto_invoke": bool(provider.get("auto_invoke", False)),
            "endpoint_probe": endpoint_probe,
        },
        lifecycle=provider_lifecycle(
            configured=configured.enabled or configured.name != "none",
            enabled=enabled,
            available=available,
            error=error,
            auto_detected=bool((endpoint_probe or {}).get("base_url")),
            endpoint_reachable=bool((endpoint_probe or {}).get("reachable")) if endpoint_probe else None,
            skipped=available and not bool(provider.get("auto_invoke", False)),
        ),
        evidence=[
            f"provider:{provider.name}",
            f"model:{model or '<none>'}",
            f"base_url:{(endpoint_probe or {}).get('base_url') or base_url or '<none>'}",
        ],
    )


def chart_status(provider: ProviderConfig, *, configured: ProviderConfig, profile: str) -> ProviderStatus:
    enabled = provider.enabled and provider.name != "none"
    model_path = str(provider.get("model_path", "") or "")
    error = None
    available = False
    if provider.get("disabled_by_profile"):
        error = f"chart specialist disabled by profile:{profile}"
    elif not enabled:
        error = "chart specialist disabled by config"
    elif provider.name in {"deplot", "chartgemma", "unichart", "chartcoder", "chartocr"}:
        path = Path(model_path)
        available = path.exists() and any((path / filename).exists() for filename in ("config.json", "model.safetensors", "pytorch_model.bin"))
        error = None if available else f"chart model files not found at {path}"
        if available:
            error = f"{provider.name} execution adapter is not implemented in all2text core yet"
            available = False
    else:
        error = f"chart provider is not implemented in all2text core: {provider.name}"
    return ProviderStatus(
        name="chart",
        kind="chart",
        enabled=enabled,
        available=available,
        source=model_path or None,
        error=error,
        details={
            "provider": provider.name,
            "configured_enabled": configured.enabled,
            "effective_enabled": enabled,
            "profile": profile,
            "embedded_images_enabled": bool(provider.get("embedded_images_enabled", False)),
        },
        lifecycle=provider_lifecycle(
            configured=configured.enabled or configured.name != "none",
            enabled=enabled,
            available=available,
            error=error,
            dependency_found=provider.name in {"deplot", "chartgemma", "unichart", "chartcoder", "chartocr"}
            and importlib.util.find_spec("transformers") is not None,
            auto_detected=bool(model_path),
        ),
        evidence=[f"provider:{provider.name}", f"model_path:{model_path or '<none>'}"],
    )


def document_intelligence_status(provider: ProviderConfig, *, configured: ProviderConfig, profile: str) -> ProviderStatus:
    enabled = provider.enabled and provider.name != "none"
    available = False
    source = str(provider.get("endpoint", "") or provider.get("model_path", "") or "") or None
    if provider.get("disabled_by_profile"):
        error = f"document intelligence provider disabled by profile:{profile}"
    elif not enabled:
        error = "document intelligence provider disabled by config"
    elif provider.name == "docling":
        if not python_module_available("docling"):
            error = "Python package not installed for document intelligence provider: docling"
        else:
            available = True
            error = None
            if not bool(provider.get("auto_invoke", False)):
                error = "Docling is installed but auto_invoke=false; not invoked"
    elif provider.name in {"paddleocr_vl", "glm_ocr", "olmocr"}:
        dependency_found = _provider_dependency_found(provider.name)
        if not dependency_found:
            error = f"Python package/model dependency missing for document intelligence provider: {provider.name}"
        else:
            error = f"{provider.name} document intelligence adapter is contract-only; configure an implemented provider"
    else:
        error = f"document intelligence provider is not implemented in all2text core: {provider.name}"
    return ProviderStatus(
        name="document_intelligence",
        kind="document_intelligence",
        enabled=enabled,
        available=available,
        source=source,
        error=error,
        details={
            "provider": provider.name,
            "configured_enabled": configured.enabled,
            "effective_enabled": enabled,
            "profile": profile,
            "auto_invoke": bool(provider.get("auto_invoke", False)),
            "model_path": str(provider.get("model_path", "") or "") or None,
            "endpoint": str(provider.get("endpoint", "") or "") or None,
        },
        lifecycle=provider_lifecycle(
            configured=configured.enabled or configured.name != "none",
            enabled=enabled,
            available=available,
            error=error,
            dependency_found=_provider_dependency_found(provider.name),
            auto_detected=bool(provider.get("endpoint", "") or provider.get("model_path", "")),
            skipped=available and not bool(provider.get("auto_invoke", False)),
        ),
        evidence=[f"provider:{provider.name}"],
    )


def speech_status(provider: ProviderConfig, *, configured: ProviderConfig, profile: str) -> ProviderStatus:
    enabled = provider.enabled and provider.name != "none"
    available = False
    error = None
    model_ref = str(provider.get("model_path", "") or provider.get("model", "") or "")
    executable_ref = None
    if provider.get("disabled_by_profile"):
        error = f"speech provider disabled by profile:{profile}"
    elif not enabled:
        error = "speech provider disabled by config"
    elif provider.name in {"whisper", "faster_whisper", "vosk", "parakeet", "canary"}:
        module_names = {
            "whisper": ("whisper",),
            "faster_whisper": ("faster_whisper",),
            "vosk": ("vosk",),
            "parakeet": ("nemo",),
            "canary": ("nemo",),
        }[provider.name]
        dependency_found = all(python_module_available(module_name) for module_name in module_names)
        if not dependency_found:
            module_name = ", ".join(module_names)
            error = f"Python package not installed for speech provider: {module_name}"
        elif not model_ref:
            error = "speech provider package found but model_path/model is not configured; no model download performed"
        elif not Path(model_ref).expanduser().exists() and not bool(provider.get("allow_download", False)):
            error = (
                "speech provider model_path/model is not a local path; "
                "no model download performed"
            )
        else:
            available = True
    elif provider.name == "whisper_cpp":
        executable_ref = str(
            provider.get("executable", "")
            or _which_executable("whisper-cli")
            or _which_executable("whisper.cpp")
            or _which_executable("main")
            or ""
        )
        if not executable_ref:
            error = "whisper.cpp executable not found: whisper-cli or whisper.cpp"
        elif not model_ref:
            error = "whisper.cpp executable found but model_path/model is not configured"
        elif not Path(model_ref).expanduser().exists():
            error = "whisper.cpp model_path/model is not a local path"
        else:
            available = True
    else:
        error = f"speech provider is not implemented in all2text core: {provider.name}"
    return ProviderStatus(
        name="speech",
        kind="speech",
        enabled=enabled,
        available=available,
        source=model_ref or executable_ref or None,
        error=error,
        details={
            "provider": provider.name,
            "configured_enabled": configured.enabled,
            "effective_enabled": enabled,
            "profile": profile,
            "model_ref": model_ref or None,
            "executable": executable_ref or None,
            "transcribe": bool(provider.get("transcribe", False)),
            "translate": bool(provider.get("translate", False)),
            "language_detection": bool(provider.get("language_detection", False)),
        },
        lifecycle=provider_lifecycle(
            configured=configured.enabled or configured.name != "none",
            enabled=enabled,
            available=available,
            error=error,
            dependency_found=_provider_dependency_found(provider.name),
            executable_found=bool(executable_ref) if provider.name == "whisper_cpp" else None,
            auto_detected=bool(model_ref),
            skipped=available and not bool(provider.get("auto_invoke", False)),
        ),
        evidence=[
            f"provider:{provider.name}",
            f"model_ref:{model_ref or '<none>'}",
            f"executable:{executable_ref or '<none>'}",
        ],
    )


def video_frame_status(
    provider: ProviderConfig,
    *,
    configured: ProviderConfig,
    profile: str,
    tool: dict[str, Any],
) -> ProviderStatus:
    enabled = provider.enabled and provider.name != "none"
    ffmpeg = str(tool["source"]) if tool.get("source") else None
    error = None
    available = False
    if provider.get("disabled_by_profile"):
        error = f"video frame provider disabled by profile:{profile}"
    elif not enabled:
        error = "video frame provider disabled by config"
    elif provider.name == "ffmpeg":
        available = bool(ffmpeg)
        error = None if ffmpeg else str(tool.get("error") or "ffmpeg executable not found")
    else:
        error = f"video frame provider is not implemented in all2text core: {provider.name}"
    return ProviderStatus(
        name="video_frames",
        kind="video_frames",
        enabled=enabled,
        available=available,
        source=ffmpeg,
        error=error,
        details={
            "provider": provider.name,
            "configured_enabled": configured.enabled,
            "effective_enabled": enabled,
            "profile": profile,
            "sample_frames": bool(provider.get("sample_frames", False)),
            "ocr": bool(provider.get("ocr", False)),
            "vlm": bool(provider.get("vlm", False)),
            "tool": tool,
        },
        lifecycle=provider_lifecycle(
            configured=configured.enabled or configured.name != "none",
            enabled=enabled,
            available=available,
            error=error,
            auto_detected=bool(tool.get("auto_detected")),
            executable_found=bool(ffmpeg) if provider.name == "ffmpeg" else None,
            skipped=available and not bool(provider.get("auto_invoke", False)),
        ),
        evidence=[f"provider:{provider.name}", f"tool_source:{ffmpeg or '<none>'}"],
    )


def discover_openai_compatible_endpoint(
    provider: ProviderConfig,
    *,
    model: str,
    configured_base_url: str,
    defaults: list[str],
    auto_detect: bool,
) -> dict[str, Any]:
    timeout = float(provider.get("discovery_timeout_seconds", provider.get("timeout_seconds", 1.0)) or 1.0)
    candidates: list[str] = []
    if configured_base_url:
        candidates.append(configured_base_url)
    if auto_detect:
        candidates.extend(defaults)
    unique_candidates = list(dict.fromkeys(url.rstrip("/") for url in candidates if url))
    attempts: list[dict[str, Any]] = []
    for base_url in unique_candidates:
        attempt = probe_openai_compatible_endpoint(base_url, model, timeout_seconds=timeout)
        attempts.append(attempt)
        if attempt.get("reachable"):
            return {**attempt, "base_url": base_url, "attempts": attempts}
    error = attempts[-1].get("error") if attempts else "no OpenAI-compatible endpoint configured"
    return {
        "reachable": False,
        "base_url": configured_base_url or None,
        "model": model,
        "attempts": attempts,
        "error": error,
    }


def probe_openai_compatible_endpoint(
    base_url: str,
    model: str,
    *,
    timeout_seconds: float = 1.0,
) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}/models"
    request = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        return {"reachable": False, "url": url, "model": model, "error": str(exc)}
    models = data.get("data") or data.get("models") or []
    model_names: list[str] = []
    if isinstance(models, list):
        for item in models:
            if isinstance(item, dict):
                value = item.get("id") or item.get("model") or item.get("name")
                if value:
                    model_names.append(str(value))
    return {
        "reachable": True,
        "base_url": base_url.rstrip("/"),
        "url": url,
        "model": model,
        "model_list_contains_configured_model": model in model_names if model_names else None,
        "model_names": model_names[:20],
    }


def call_openai_compatible_vision(
    image_bytes: bytes,
    provider: ProviderConfig,
    *,
    prompt: str,
    mime_type: str = "image/png",
) -> tuple[str | None, list[str], dict[str, Any]]:
    warnings: list[str] = []
    base_url = str(provider.get("base_url", "") or "").rstrip("/")
    model = str(provider.get("model", "") or "")
    if not provider.enabled or provider.name != "openai_compatible":
        return None, ["vlm_call_skipped_provider_disabled"], {
            "base_url": base_url,
            "model": model,
            "disabled_by_profile": provider.get("disabled_by_profile"),
        }
    if not bool(provider.get("auto_invoke", False)):
        return None, ["vlm_call_skipped_auto_invoke_false"], {"base_url": base_url, "model": model}
    if not base_url or not model:
        return None, ["vlm_call_skipped_missing_base_url_or_model"], {"base_url": base_url, "model": model}
    endpoint_probe = discover_openai_compatible_endpoint(
        provider,
        model=model,
        configured_base_url=base_url,
        defaults=VISION_MODEL_ENDPOINTS,
        auto_detect=bool(provider.get("auto_detect", True)),
    )
    if not endpoint_probe.get("reachable"):
        return None, ["vlm_call_skipped_endpoint_unreachable"], {
            "base_url": base_url,
            "model": model,
            "endpoint_probe": endpoint_probe,
        }
    base_url = str(endpoint_probe.get("base_url") or base_url).rstrip("/")
    data_url = f"data:{mime_type};base64," + base64.b64encode(image_bytes).decode("ascii")
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }
        ],
        "temperature": 0,
        "max_tokens": int(provider.get("max_tokens", 300)),
    }
    request = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=float(provider.get("timeout_seconds", 120))) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        warnings.append(f"vlm_call_failed:{exc}")
        return None, warnings, {"base_url": base_url, "model": model, "endpoint_probe": endpoint_probe}
    content = str((((data.get("choices") or [{}])[0].get("message") or {}).get("content")) or "").strip()
    return content or None, warnings, {"base_url": base_url, "model": model, "endpoint_probe": endpoint_probe}


def image_to_png_bytes(image: Any) -> bytes | None:
    try:
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()
    except Exception:
        return None


def provider_lifecycle(
    *,
    configured: bool,
    enabled: bool,
    available: bool,
    error: str | None,
    auto_detected: bool = False,
    dependency_found: bool | None = None,
    executable_found: bool | None = None,
    endpoint_reachable: bool | None = None,
    attempted: bool = False,
    used: bool = False,
    skipped: bool = False,
) -> dict[str, bool]:
    failed = bool(error) and attempted
    missing = bool(enabled and not available and error)
    result: dict[str, bool] = {
        "configured": configured,
        "auto_detected": auto_detected,
        "attempted": attempted,
        "used": used,
        "skipped": skipped or bool(enabled and not attempted and not used),
        "failed": failed,
        "disabled": not enabled,
        "missing": missing,
        "error": bool(error),
    }
    if dependency_found is not None:
        result["dependency_found"] = dependency_found
    if executable_found is not None:
        result["executable_found"] = executable_found
    if endpoint_reachable is not None:
        result["endpoint_reachable"] = endpoint_reachable
    return result


def model_roots() -> list[Path]:
    roots: list[Path] = []
    for value in (
        os.environ.get("ALL2TEXT_MODEL_ROOT"),
        "/data/models",
    ):
        if not value:
            continue
        path = Path(value).expanduser()
        if path.exists() and path not in roots:
            roots.append(path)
    return roots


@lru_cache(maxsize=64)
def discover_model_hints(hints: tuple[str, ...]) -> list[str]:
    if not hints:
        return []
    lowered = [hint.casefold() for hint in hints if hint]
    matches: list[str] = []
    for root in model_roots():
        try:
            for path in _bounded_model_files(root, max_depth=5, max_files=20000):
                if len(matches) >= 25:
                    return matches
                name = path.name.casefold()
                parent = path.parent.as_posix().casefold()
                if path.name not in {"config.json", "model.safetensors", "pytorch_model.bin"} and path.suffix.casefold() != ".gguf":
                    continue
                if any(hint in name or hint in parent for hint in lowered):
                    matches.append(str(path.parent if path.name == "config.json" else path))
        except (OSError, PermissionError):
            continue
    return list(dict.fromkeys(matches))


def _bounded_model_files(root: Path, *, max_depth: int, max_files: int) -> list[Path]:
    files: list[Path] = []
    root_depth = len(root.parts)
    for current, dirs, names in os.walk(root):
        current_path = Path(current)
        depth = len(current_path.parts) - root_depth
        if depth >= max_depth:
            dirs[:] = []
        dirs[:] = [name for name in dirs if name not in {".git", "__pycache__", "blobs"}]
        for name in names:
            path = current_path / name
            if name in {"config.json", "model.safetensors", "pytorch_model.bin"} or path.suffix.casefold() == ".gguf":
                files.append(path)
                if len(files) >= max_files:
                    return files
    return files


def _which_executable(name: str) -> str | None:
    import shutil

    return shutil.which(name)


def _family_for_endpoint_task(task: str) -> str | None:
    if task == "vlm":
        return "image"
    if task == "llm_text":
        return "text"
    return None


def _provider_dependency_found(provider_name: str) -> bool | None:
    module_map = {
        "docling": ("docling",),
        "paddleocr_vl": ("paddleocr", "paddle"),
        "glm_ocr": ("transformers",),
        "olmocr": ("olmocr",),
        "whisper": ("whisper",),
        "faster_whisper": ("faster_whisper",),
        "vosk": ("vosk",),
        "parakeet": ("nemo",),
        "canary": ("nemo",),
        "pyannote": ("pyannote.audio",),
        "diarizen": ("diarizen",),
        "nemo": ("nemo",),
    }
    modules = module_map.get(provider_name)
    if modules is None:
        return None
    return all(python_module_available(module) for module in modules)


def python_module_available(module: str) -> bool:
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


def _available(statuses: list[ProviderStatus], name: str) -> bool:
    return any(status.name == name and status.available for status in statuses)


def _status_error(statuses: list[ProviderStatus], name: str) -> str | None:
    status = next((item for item in statuses if item.name == name), None)
    return status.error if status else None
