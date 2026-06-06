from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from all2text.capabilities import resolve_external_tool
from all2text.config import config_for_context, effective_provider
from all2text.models import Classification, ConversionContext, ConversionResult
from all2text.providers import provider_statuses


class MediaAnalysisBackend:
    name = "media_analysis_backend"

    def can_handle(self, classification: Classification, entry_type: str) -> bool:
        return entry_type == "file" and classification.rough_category in {"audio", "video"}

    def convert(
        self,
        path: Path,
        rel_path: Path,
        classification: Classification,
        metadata: dict[str, object],
        ctx: ConversionContext,
    ) -> ConversionResult:
        cfg = config_for_context(ctx.config)
        ffprobe_tool = resolve_external_tool(cfg, "ffprobe")
        if ffprobe_tool["enabled"] and ffprobe_tool["available"]:
            ffprobe_metadata, warnings = ffprobe(
                path,
                executable=str(ffprobe_tool["source"]),
                timeout_seconds=int(ffprobe_tool.get("timeout_seconds") or 15),
            )
        else:
            ffprobe_metadata = None
            warnings = [str(ffprobe_tool["error"] or "ffprobe_unavailable")]
        python_metadata, python_warnings = python_media_metadata(
            path,
            allow_optional_python=ctx.options.allow_optional_python and ctx.options.auto_detect_python,
            profile=ctx.options.profile,
            disabled_reason=(
                f"disabled_by_profile:{ctx.options.profile}"
                if not ctx.options.allow_optional_python
                else "disabled_by_run.auto_detect_python=false"
            ),
        )
        warnings.extend(python_warnings)
        family = classification.rough_category
        params = cfg.module_params(family, classification.concrete_format.casefold())
        max_ffprobe_json_chars = positive_int_or_zero(params.get("max_ffprobe_json_chars"))
        statuses = provider_statuses(cfg, family=family)
        profile = media_profile(classification, ffprobe_metadata, python_metadata)
        stages = media_stages(classification, profile, statuses, cfg)
        ffprobe_output_metadata, ffprobe_truncated = limit_ffprobe_metadata(
            ffprobe_metadata,
            max_chars=max_ffprobe_json_chars,
        )
        limitations: list[str] = []
        if ffprobe_truncated:
            warnings.append(f"ffprobe_metadata_truncated:max_chars={max_ffprobe_json_chars}")
            limitations.append("ffprobe JSON metadata was truncated by media.max_ffprobe_json_chars.")
        limitation = (
            "Media conversion is layered metadata/provider reporting in the core package. "
            "Speech transcription, translation, frame OCR, scene analysis, and VLM understanding "
            "require configured providers."
        )
        limitations.insert(0, limitation)
        text = render_media_text(
            classification,
            limitation,
            ffprobe_output_metadata,
            python_metadata,
            profile,
            stages,
            [status.to_dict() for status in statuses],
        )
        methods = ["media_layered_metadata"]
        if python_metadata:
            methods.append("python_mutagen_metadata")
        if ffprobe_metadata:
            methods.append("ffprobe_metadata")
        return ConversionResult(
            text=text,
            converter_used=self.name,
            extraction_methods_used=methods,
            warnings=warnings,
            metadata={
                "ffprobe": ffprobe_output_metadata or None,
                "ffprobe_truncated": ffprobe_truncated,
                "max_ffprobe_json_chars": max_ffprobe_json_chars,
                "python_media_metadata": python_metadata,
                "profile": profile,
                "stages": stages,
                "provider_statuses": [status.to_dict() for status in statuses],
            },
            limitations=limitations,
        )


MediaPlaceholderBackend = MediaAnalysisBackend


def ffprobe(
    path: Path,
    *,
    executable: str | None = None,
    timeout_seconds: int = 15,
) -> tuple[dict[str, object] | None, list[str]]:
    ffprobe_bin = executable or shutil.which("ffprobe")
    if not ffprobe_bin:
        return None, ["ffprobe_unavailable"]
    try:
        completed = subprocess.run(
            [
                ffprobe_bin,
                "-v",
                "error",
                "-print_format",
                "json",
                "-show_format",
                "-show_streams",
                "-show_chapters",
                str(path),
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except Exception as exc:
        return None, [f"ffprobe_error:{exc}"]
    if completed.returncode != 0:
        return None, [f"ffprobe_exit_code:{completed.returncode}", f"ffprobe_stderr:{completed.stderr.strip()}"]
    try:
        return json.loads(completed.stdout or "{}"), []
    except Exception:
        return {"raw_stdout": completed.stdout[:4000]}, ["ffprobe_json_parse_failed"]


def python_media_metadata(
    path: Path,
    *,
    allow_optional_python: bool,
    profile: str,
    disabled_reason: str = "",
) -> tuple[dict[str, object] | None, list[str]]:
    if not allow_optional_python:
        reason = disabled_reason or f"disabled_by_profile:{profile}"
        return None, [f"mutagen_metadata_disabled:{reason}"]
    try:
        import mutagen
    except Exception as exc:
        return None, [f"mutagen_unavailable:{exc}"]
    try:
        media = mutagen.File(path)
    except Exception as exc:
        return None, [f"mutagen_open_failed:{exc}"]
    if media is None:
        return None, ["mutagen_unrecognized_media"]
    info = getattr(media, "info", None)
    tags = getattr(media, "tags", None)
    metadata: dict[str, object] = {
        "library": "mutagen",
        "type": type(media).__name__,
        "mime": list(getattr(media, "mime", []) or []),
        "duration_seconds": round(float(getattr(info, "length")), 3)
        if getattr(info, "length", None) is not None
        else None,
        "bitrate": getattr(info, "bitrate", None),
        "sample_rate": getattr(info, "sample_rate", None),
        "channels": getattr(info, "channels", None),
        "pprint": str(media.pprint())[:4000],
    }
    tag_dict: dict[str, object] = {}
    if tags is not None:
        for key in list(tags.keys())[:100]:
            value = tags.get(key)
            tag_dict[str(key)] = str(value)[:500]
    if tag_dict:
        metadata["tags"] = tag_dict
    streams: list[dict[str, object]] = []
    if metadata.get("sample_rate") is not None or metadata.get("channels") is not None:
        streams.append({"type": "audio", "source": "mutagen"})
    if any(str(item).startswith("video/") for item in metadata.get("mime", []) or []):
        streams.append({"type": "video", "source": "mutagen"})
    metadata["streams"] = streams
    return metadata, []


def media_profile(
    classification: Classification,
    ffprobe_metadata: dict[str, object] | None,
    python_metadata: dict[str, object] | None = None,
) -> dict[str, Any]:
    streams = ffprobe_metadata.get("streams", []) if isinstance(ffprobe_metadata, dict) else []
    if not isinstance(streams, list):
        streams = []
    audio_streams = [stream for stream in streams if isinstance(stream, dict) and stream.get("codec_type") == "audio"]
    video_streams = [stream for stream in streams if isinstance(stream, dict) and stream.get("codec_type") == "video"]
    subtitles = [stream for stream in streams if isinstance(stream, dict) and stream.get("codec_type") == "subtitle"]
    tags = (ffprobe_metadata.get("format", {}) or {}).get("tags", {}) if isinstance(ffprobe_metadata, dict) else {}
    python_streams = python_metadata.get("streams", []) if isinstance(python_metadata, dict) else []
    if not isinstance(python_streams, list):
        python_streams = []
    language_tags = sorted(
        {
            str(stream.get("tags", {}).get("language"))
            for stream in streams
            if isinstance(stream, dict) and stream.get("tags", {}).get("language")
        }
    )
    coarse = "unknown"
    if classification.rough_category == "audio":
        coarse = "unknown_audio_content"
    elif classification.rough_category == "video":
        if audio_streams and video_streams:
            coarse = "mixed_audio_video"
        elif video_streams:
            coarse = "visual_only_video"
        elif audio_streams:
            coarse = "audio_only_container"
    return {
        "family": classification.rough_category,
        "format": classification.concrete_format,
        "coarse_classification": coarse,
        "audio_stream_count": len(audio_streams) or _python_stream_count(python_streams, "audio"),
        "video_stream_count": len(video_streams) or _python_stream_count(python_streams, "video"),
        "subtitle_stream_count": len(subtitles),
        "duration_seconds": _duration(ffprobe_metadata) or _python_duration(python_metadata),
        "language_tags": language_tags,
        "format_tags_present": bool(tags) or bool((python_metadata or {}).get("tags")),
        "metadata_sources": {
            "ffprobe": bool(ffprobe_metadata),
            "python_mutagen": bool(python_metadata),
        },
        "classification_note": (
            "Content class such as speech/music/song/noise/screen recording/lecture is not "
            "inferred without a configured analyzer."
        ),
    }


def media_stages(
    classification: Classification,
    profile: dict[str, Any],
    statuses: list[Any],
    config: Any | None = None,
) -> dict[str, Any]:
    cfg = config_for_context(config)
    speech_status = next((status for status in statuses if status.name == "speech"), None)
    audio_classifier_status = next((status for status in statuses if status.name == "audio_classifier"), None)
    diarization_status = next((status for status in statuses if status.name == "diarization"), None)
    frame_status = next((status for status in statuses if status.name == "video_frames"), None)
    ocr_status = next((status for status in statuses if status.name == "ocr"), None)
    vlm_status = next((status for status in statuses if status.name == "vlm"), None)
    speech_provider = effective_provider(cfg, "speech")
    audio_classifier_provider = effective_provider(cfg, "audio_classifier")
    diarization_provider = effective_provider(cfg, "diarization")
    frame_provider = effective_provider(cfg, "video_frames")
    speech_likely = profile.get("coarse_classification") in {
        "unknown_audio_content",
        "mixed_audio_video",
        "audio_only_container",
    }
    speech_auto = bool(speech_provider.get("auto_invoke", False))
    stages: dict[str, Any] = {
        "metadata": {
            "attempted": True,
            "used": True,
            "provider": "ffprobe" if profile.get("duration_seconds") is not None else "header_or_ffprobe",
        },
        "coarse_classification": {
            "attempted": True,
            "label": profile.get("coarse_classification"),
            "confidence": "low",
            "limitation": profile.get("classification_note"),
        },
        "audio_kind_classification": audio_classifier_stage_plan(
            audio_classifier_provider,
            audio_classifier_status,
            audio_possible=speech_likely,
        ),
        "language_detection": speech_stage_plan(
            speech_provider,
            speech_status,
            enabled_key="language_detection",
            speech_possible=speech_likely,
            auto_invoke=speech_auto,
        ),
        "transcription": speech_stage_plan(
            speech_provider,
            speech_status,
            enabled_key="transcribe",
            speech_possible=speech_likely,
            auto_invoke=speech_auto,
        ),
        "translation": speech_stage_plan(
            speech_provider,
            speech_status,
            enabled_key="translate",
            speech_possible=speech_likely,
            auto_invoke=speech_auto,
        ),
        "diarization": diarization_stage_plan(
            diarization_provider,
            diarization_status,
            speech_possible=speech_likely,
        ),
    }
    if classification.rough_category == "video":
        stages.update(
            {
                "subtitle_extraction": {
                    "attempted": profile.get("subtitle_stream_count", 0) > 0,
                    "subtitle_stream_count": profile.get("subtitle_stream_count", 0),
                    "limitation": "Subtitle streams are counted; subtitle text extraction is a future provider stage.",
                },
                "frame_sampling": frame_sampling_plan(frame_provider, frame_status, profile),
                "frame_ocr": {
                    "attempted": False,
                    "planned": bool(frame_provider.get("ocr", False)),
                    "reason": frame_dependent_reason(frame_provider, frame_status, ocr_status, "ocr"),
                    "provider_status": ocr_status.to_dict() if ocr_status else None,
                },
                "frame_vlm": {
                    "attempted": False,
                    "planned": bool(frame_provider.get("vlm", False)),
                    "reason": frame_dependent_reason(frame_provider, frame_status, vlm_status, "vlm"),
                    "provider_status": vlm_status.to_dict() if vlm_status else None,
                },
            }
        )
    return stages


def audio_classifier_stage_plan(provider: Any, status: Any | None, *, audio_possible: bool) -> dict[str, Any]:
    auto_invoke = bool(provider.get("auto_invoke", False))
    requested = bool(provider.enabled and provider.name != "none")
    plan = {
        "attempted": False,
        "planned": requested,
        "audio_possible": audio_possible,
        "provider": getattr(provider, "name", "none"),
        "labels": str(provider.get("labels", "speech,music,noise,mixed,unknown") or ""),
        "auto_invoke": auto_invoke,
        "provider_status": status.to_dict() if status else None,
        "output_schema": {
            "kind": "speech|music|noise|mixed|unknown",
            "confidence": "0.0-1.0",
            "evidence": "provider scores or deterministic metadata only",
        },
    }
    if not requested:
        plan["reason"] = "audio classifier disabled by config"
    elif not audio_possible:
        plan["reason"] = "no audio stream/profile evidence"
    elif status is None or not status.available:
        plan["reason"] = getattr(status, "error", None) or "audio classifier unavailable"
    elif not auto_invoke:
        plan["reason"] = "audio classifier configured but auto_invoke=false"
    else:
        plan["reason"] = "audio classifier execution hook configured"
    return plan


def diarization_stage_plan(provider: Any, status: Any | None, *, speech_possible: bool) -> dict[str, Any]:
    auto_invoke = bool(provider.get("auto_invoke", False))
    requested = bool(provider.enabled and provider.name != "none")
    plan = {
        "attempted": False,
        "planned": requested,
        "speech_possible": speech_possible,
        "provider": getattr(provider, "name", "none"),
        "auto_invoke": auto_invoke,
        "provider_status": status.to_dict() if status else None,
        "output_schema": {
            "speaker_turns": [],
            "speaker_labels": "provider-assigned labels only",
            "timestamps": "seconds",
        },
    }
    if not requested:
        plan["reason"] = "diarization disabled by config"
    elif not speech_possible:
        plan["reason"] = "no audio stream/profile evidence that speech is possible"
    elif status is None or not status.available:
        plan["reason"] = getattr(status, "error", None) or "diarization provider unavailable"
    elif not auto_invoke:
        plan["reason"] = "diarization provider configured but auto_invoke=false"
    else:
        plan["reason"] = "diarization execution hook configured"
    return plan


def speech_stage_plan(
    provider: Any,
    status: Any | None,
    *,
    enabled_key: str,
    speech_possible: bool,
    auto_invoke: bool,
) -> dict[str, Any]:
    requested = bool(provider.get(enabled_key, False))
    plan = {
        "attempted": False,
        "planned": requested,
        "speech_possible": speech_possible,
        "auto_invoke": auto_invoke,
        "provider": getattr(provider, "name", "none"),
        "provider_status": status.to_dict() if status else None,
    }
    if not requested:
        plan["reason"] = f"{enabled_key} disabled by speech provider config"
    elif not speech_possible:
        plan["reason"] = "no audio stream/profile evidence that speech is possible"
    elif status is None or not status.available:
        plan["reason"] = getattr(status, "error", None) or "speech provider unavailable"
    elif not auto_invoke:
        plan["reason"] = "speech provider configured but auto_invoke=false"
    else:
        plan["reason"] = "speech execution hook is configured; core package does not run model downloads in tests"
    return plan


def frame_sampling_plan(provider: Any, status: Any | None, profile: dict[str, Any]) -> dict[str, Any]:
    requested = bool(provider.get("sample_frames", False))
    auto_invoke = bool(provider.get("auto_invoke", False))
    max_frames = positive_int(provider.get("max_frames")) or 5
    interval_seconds = positive_float(provider.get("interval_seconds")) or 10.0
    plan = {
        "attempted": False,
        "planned": requested,
        "auto_invoke": auto_invoke,
        "provider": getattr(provider, "name", "none"),
        "max_frames": max_frames,
        "interval_seconds": interval_seconds,
        "output_format": str(provider.get("output_format", "png") or "png"),
        "duration_seconds": profile.get("duration_seconds"),
        "sample_timestamps_seconds": sample_timestamps(profile.get("duration_seconds"), max_frames, interval_seconds),
        "provider_status": status.to_dict() if status else None,
    }
    if not requested:
        plan["reason"] = "frame sampling disabled by video_frames provider config"
    elif status is None or not status.available:
        plan["reason"] = getattr(status, "error", None) or "video frame provider unavailable"
    elif not auto_invoke:
        plan["reason"] = "video frame provider configured but auto_invoke=false"
    else:
        plan["reason"] = (
            "frame sampling execution hook is configured; extraction must run inside bounded "
            "output workspace"
        )
    return plan


def frame_dependent_reason(
    frame_provider: Any,
    frame_status: Any | None,
    provider_status: Any | None,
    provider_name: str,
) -> str:
    if not bool(frame_provider.get(provider_name, False)):
        return f"frame {provider_name} disabled by video_frames provider config"
    if not bool(frame_provider.get("sample_frames", False)):
        return "frame sampling must be enabled before frame analysis"
    if frame_status is None or not frame_status.available:
        return getattr(frame_status, "error", None) or "video frame provider unavailable"
    if provider_status is None or not provider_status.available:
        return getattr(provider_status, "error", None) or f"{provider_name} provider unavailable"
    if not bool(frame_provider.get("auto_invoke", False)):
        return "frame sampling/analysis configured but auto_invoke=false"
    return f"frame {provider_name} execution hook configured"


def sample_timestamps(duration: Any, max_frames: int, interval_seconds: float) -> list[float]:
    try:
        duration_value = float(duration)
    except (TypeError, ValueError):
        duration_value = 0.0
    if duration_value <= 0:
        return [round(index * interval_seconds, 3) for index in range(max_frames)]
    timestamps: list[float] = []
    current = 0.0
    while current <= duration_value and len(timestamps) < max_frames:
        timestamps.append(round(current, 3))
        current += interval_seconds
    return timestamps or [0.0]


def positive_int(value: Any) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def positive_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def positive_int_or_zero(value: Any) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def limit_ffprobe_metadata(
    metadata: dict[str, object] | None,
    *,
    max_chars: int | None,
) -> tuple[dict[str, object] | None, bool]:
    if metadata is None:
        return None, False
    if max_chars is None or max_chars == 0:
        return metadata, False
    encoded = json.dumps(metadata, ensure_ascii=False, sort_keys=True)
    if len(encoded) <= max_chars:
        return metadata, False
    return (
        {
            "truncated": True,
            "max_chars": max_chars,
            "json_preview": encoded[:max_chars],
            "original_json_chars": len(encoded),
        },
        True,
    )


def render_media_text(
    classification: Classification,
    limitation: str,
    ffprobe_metadata: dict[str, object] | None,
    python_metadata: dict[str, object] | None,
    profile: dict[str, Any],
    stages: dict[str, Any],
    statuses: list[dict[str, Any]],
) -> str:
    lines = [
        f"Format: {classification.concrete_format}",
        "Conversion: layered media metadata and provider-routing report.",
        f"Limitation: {limitation}",
        "",
        "Media profile:",
        json.dumps(profile, indent=2, ensure_ascii=False),
        "",
        "Provider statuses:",
        json.dumps(statuses, indent=2, ensure_ascii=False),
        "",
        "Layered stages:",
        json.dumps(stages, indent=2, ensure_ascii=False),
    ]
    if ffprobe_metadata:
        lines.extend(["", "ffprobe metadata:", json.dumps(ffprobe_metadata, indent=2, ensure_ascii=False)])
    else:
        lines.extend(["", "ffprobe metadata: <unavailable>"])
    if python_metadata:
        lines.extend(["", "Python media metadata:", json.dumps(python_metadata, indent=2, ensure_ascii=False)])
    else:
        lines.extend(["", "Python media metadata: <unavailable>"])
    return "\n".join(lines).rstrip() + "\n"


def _duration(ffprobe_metadata: dict[str, object] | None) -> float | None:
    if not isinstance(ffprobe_metadata, dict):
        return None
    fmt = ffprobe_metadata.get("format")
    if not isinstance(fmt, dict):
        return None
    value = fmt.get("duration")
    try:
        return round(float(value), 3)
    except Exception:
        return None


def _python_duration(python_metadata: dict[str, object] | None) -> float | None:
    if not isinstance(python_metadata, dict):
        return None
    try:
        value = python_metadata.get("duration_seconds")
        return round(float(value), 3) if value is not None else None
    except Exception:
        return None


def _python_stream_count(streams: list[object], stream_type: str) -> int:
    return sum(1 for item in streams if isinstance(item, dict) and item.get("type") == stream_type)
