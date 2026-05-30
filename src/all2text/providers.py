from __future__ import annotations

import base64
import json
import shutil
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from io import BytesIO
from pathlib import Path
from typing import Any

from all2text.config import ProviderConfig, config_for_context


@dataclass(frozen=True)
class ProviderStatus:
    name: str
    kind: str
    enabled: bool
    available: bool
    source: str | None = None
    error: str | None = None
    details: dict[str, Any] | None = None

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


def provider_statuses(config: object | None, *, family: str | None = None) -> list[ProviderStatus]:
    cfg = config_for_context(config)
    statuses: list[ProviderStatus] = []
    if family in {None, "image", "document", "chart"}:
        statuses.extend(
            [
                ocr_status(cfg.provider("ocr")),
                vlm_status(cfg.provider("vlm")),
                chart_status(cfg.provider("chart")),
                document_intelligence_status(cfg.provider("document_intelligence")),
            ]
        )
    if family in {None, "audio", "video"}:
        statuses.append(speech_status(cfg.provider("speech")))
    if family in {None, "video"}:
        statuses.append(video_frame_status(cfg.provider("video_frames")))
    if family in {None, "text"}:
        statuses.append(llm_text_status(cfg.provider("llm_text")))
    return statuses


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
    profile = str(image_profile.get("profile") or "").lower()
    if chart_candidate or "chart" in profile or "plot" in profile:
        return "chart"
    if "document" in profile or "scan" in profile:
        return "document"
    if "screenshot" in profile or "interface" in profile:
        return "screenshot"
    if "diagram" in profile or "technical" in profile:
        return "diagram"
    return "scene_or_photo"


def ocr_status(provider: ProviderConfig) -> ProviderStatus:
    executable = shutil.which("tesseract") if provider.name == "tesseract" else None
    enabled = provider.enabled and provider.name != "none"
    error = None
    available = False
    if not enabled:
        error = "OCR disabled by config"
    elif provider.name == "tesseract":
        available = bool(executable)
        error = None if executable else "tesseract executable not found"
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
            "language": provider.get("language", "eng"),
            "auto_invoke": bool(provider.get("auto_invoke", False)),
        },
    )


def vlm_status(provider: ProviderConfig) -> ProviderStatus:
    enabled = provider.enabled and provider.name != "none"
    base_url = str(provider.get("base_url", "") or "").rstrip("/")
    model = str(provider.get("model", "") or "")
    error = None
    available = False
    if not enabled:
        error = "VLM disabled by config"
    elif provider.name != "openai_compatible":
        error = f"VLM provider is not implemented in all2text core: {provider.name}"
    elif not base_url or not model:
        error = "openai-compatible VLM requires base_url and model"
    else:
        available = True
    return ProviderStatus(
        name="vlm",
        kind="vision_language_model",
        enabled=enabled,
        available=available,
        source=base_url or None,
        error=error,
        details={
            "provider": provider.name,
            "model": model or None,
            "auto_invoke": bool(provider.get("auto_invoke", False)),
        },
    )


def llm_text_status(provider: ProviderConfig) -> ProviderStatus:
    enabled = provider.enabled and provider.name != "none"
    base_url = str(provider.get("base_url", "") or "").rstrip("/")
    model = str(provider.get("model", "") or "")
    if not enabled:
        error = "text LLM disabled by config"
        available = False
    elif provider.name != "openai_compatible":
        error = f"text LLM provider is not implemented in all2text core: {provider.name}"
        available = False
    elif not base_url or not model:
        error = "openai-compatible text LLM requires base_url and model"
        available = False
    else:
        error = None
        available = True
    return ProviderStatus(
        name="llm_text",
        kind="text_language_model",
        enabled=enabled,
        available=available,
        source=base_url or None,
        error=error,
        details={"provider": provider.name, "model": model or None},
    )


def chart_status(provider: ProviderConfig) -> ProviderStatus:
    enabled = provider.enabled and provider.name != "none"
    model_path = str(provider.get("model_path", "") or "")
    error = None
    available = False
    if not enabled:
        error = "chart specialist disabled by config"
    elif provider.name in {"deplot", "chartgemma", "unichart"}:
        path = Path(model_path)
        available = path.exists() and any((path / filename).exists() for filename in ("config.json", "model.safetensors"))
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
        details={"provider": provider.name, "embedded_images_enabled": bool(provider.get("embedded_images_enabled", False))},
    )


def document_intelligence_status(provider: ProviderConfig) -> ProviderStatus:
    enabled = provider.enabled and provider.name != "none"
    return ProviderStatus(
        name="document_intelligence",
        kind="document_intelligence",
        enabled=enabled,
        available=False,
        source=str(provider.get("endpoint", "") or "") or None,
        error="document intelligence provider disabled by config"
        if not enabled
        else f"document intelligence provider is not implemented in all2text core: {provider.name}",
        details={"provider": provider.name},
    )


def speech_status(provider: ProviderConfig) -> ProviderStatus:
    enabled = provider.enabled and provider.name != "none"
    available = False
    error = None
    if not enabled:
        error = "speech provider disabled by config"
    elif provider.name in {"whisper", "faster_whisper", "vosk"}:
        module_name = "faster_whisper" if provider.name == "faster_whisper" else provider.name
        try:
            __import__(module_name)
            available = True
        except Exception:
            error = f"Python package not installed for speech provider: {module_name}"
    else:
        error = f"speech provider is not implemented in all2text core: {provider.name}"
    return ProviderStatus(
        name="speech",
        kind="speech",
        enabled=enabled,
        available=available,
        source=str(provider.get("model_path", "") or "") or None,
        error=error,
        details={
            "provider": provider.name,
            "transcribe": bool(provider.get("transcribe", False)),
            "translate": bool(provider.get("translate", False)),
            "language_detection": bool(provider.get("language_detection", False)),
        },
    )


def video_frame_status(provider: ProviderConfig) -> ProviderStatus:
    enabled = provider.enabled and provider.name != "none"
    ffmpeg = shutil.which("ffmpeg")
    error = None
    available = False
    if not enabled:
        error = "video frame provider disabled by config"
    elif provider.name == "ffmpeg":
        available = bool(ffmpeg)
        error = None if ffmpeg else "ffmpeg executable not found"
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
            "sample_frames": bool(provider.get("sample_frames", False)),
            "ocr": bool(provider.get("ocr", False)),
            "vlm": bool(provider.get("vlm", False)),
        },
    )


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
        return None, ["vlm_call_skipped_provider_disabled"], {}
    if not bool(provider.get("auto_invoke", False)):
        return None, ["vlm_call_skipped_auto_invoke_false"], {"base_url": base_url, "model": model}
    if not base_url or not model:
        return None, ["vlm_call_skipped_missing_base_url_or_model"], {"base_url": base_url, "model": model}
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
        return None, warnings, {"base_url": base_url, "model": model}
    content = str((((data.get("choices") or [{}])[0].get("message") or {}).get("content")) or "").strip()
    return content or None, warnings, {"base_url": base_url, "model": model}


def image_to_png_bytes(image: Any) -> bytes | None:
    try:
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()
    except Exception:
        return None


def _available(statuses: list[ProviderStatus], name: str) -> bool:
    return any(status.name == name and status.available for status in statuses)


def _status_error(statuses: list[ProviderStatus], name: str) -> str | None:
    status = next((item for item in statuses if item.name == name), None)
    return status.error if status else None
