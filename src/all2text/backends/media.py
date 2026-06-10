from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import wave
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
        profile = media_profile(classification, ffprobe_metadata, python_metadata, path=path)
        stages = media_stages(classification, profile, statuses, cfg)
        frame_sampling = run_frame_sampling_if_configured(path, classification, profile, statuses, cfg)
        if frame_sampling["warnings"]:
            warnings.extend(str(item) for item in frame_sampling["warnings"])
        if classification.rough_category == "video" and "frame_sampling" in stages:
            stages["frame_sampling"].update(frame_sampling)
        speech_execution = run_speech_if_configured(path, classification, profile, statuses, cfg)
        if speech_execution["warnings"]:
            warnings.extend(str(item) for item in speech_execution["warnings"])
        if speech_execution["attempted"]:
            speech_provider = effective_provider(cfg, "speech")
            for key in ("language_detection", "transcription", "translation"):
                if key in stages:
                    stages[key]["attempted"] = True
                    if key == "language_detection":
                        stages[key]["used"] = bool(speech_execution.get("language"))
                    elif key == "translation":
                        stages[key]["used"] = bool(speech_provider.get("translate", False)) and bool(speech_execution.get("used"))
                    else:
                        stages[key]["used"] = not bool(speech_provider.get("translate", False)) and bool(speech_execution.get("used"))
                    stages[key]["execution"] = speech_execution
                    stages[key]["reason"] = speech_execution.get("reason")
        ffprobe_output_metadata, ffprobe_truncated = limit_ffprobe_metadata(
            ffprobe_metadata,
            max_chars=max_ffprobe_json_chars,
        )
        limitations: list[str] = []
        if ffprobe_truncated:
            warnings.append(f"ffprobe_metadata_truncated:max_chars={max_ffprobe_json_chars}")
            limitations.append("ffprobe JSON metadata was truncated by media.max_ffprobe_json_chars.")
        if frame_sampling["attempted"] and not frame_sampling.get("preserve_frames"):
            limitations.append("Sampled video frames were extracted into a temporary directory and cleaned after metadata capture.")
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
        if frame_sampling["attempted"]:
            methods.append("ffmpeg_frame_sampling")
        if speech_execution["attempted"]:
            methods.append(f"{speech_execution.get('provider')}_speech_execution")
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
                "frame_sampling": frame_sampling,
                "speech_execution": speech_execution,
                "provider_statuses": [status.to_dict() for status in statuses],
            },
            limitations=limitations,
            llm_used=False,
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
    *,
    path: Path | None = None,
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
    profile = {
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
    profile["audio_kind"] = deterministic_audio_kind(
        classification,
        profile,
        ffprobe_metadata,
        python_metadata,
        path=path,
    )
    profile["rough_content"] = media_rough_content(classification, profile, ffprobe_metadata, python_metadata)
    profile["classification_note"] = (
        "Coarse deterministic content label is always produced from streams, tags, headers, and simple waveform statistics; "
        "detailed speech, music, scene, and object understanding requires configured providers."
    )
    return profile


def media_rough_content(
    classification: Classification,
    profile: dict[str, Any],
    ffprobe_metadata: dict[str, object] | None,
    python_metadata: dict[str, object] | None,
) -> dict[str, Any]:
    audio_kind = profile.get("audio_kind") if isinstance(profile.get("audio_kind"), dict) else {}
    audio_label = str(audio_kind.get("kind") or "unknown_audio_content")
    audio_confidence = str(audio_kind.get("confidence") or "low")
    evidence = list(audio_kind.get("evidence") or [])
    audio_count = int(profile.get("audio_stream_count") or 0)
    video_count = int(profile.get("video_stream_count") or 0)
    duration = profile.get("duration_seconds")
    tag_kind = audio_kind_from_tags(ffprobe_metadata, python_metadata)
    if tag_kind and "metadata_tags" not in evidence:
        evidence.append("metadata_tags")
    if duration is not None:
        evidence.append(f"duration_seconds:{duration}")
    if classification.rough_category == "audio":
        mapping = {
            "silence": ("audio_silence", "high"),
            "very_short": ("audio_very_short", "medium"),
            "speech_unknown": ("audio_speech_or_voice", audio_confidence),
            "music_unknown": ("audio_music_or_stereo_content", audio_confidence),
            "mixed_unknown": ("audio_mixed_or_complex", audio_confidence),
            "no_audio_stream": ("audio_file_without_audio_stream", "high"),
        }
        kind, confidence = mapping.get(audio_label, ("audio_unknown_content", "low"))
    elif classification.rough_category == "video":
        coarse = str(profile.get("coarse_classification") or "")
        if coarse == "visual_only_video":
            kind, confidence = "video_visual_only_or_silent", "medium"
        elif video_count <= 0 and audio_count > 0:
            kind, confidence = "video_container_with_audio_only", "medium"
        elif video_count > 0 and audio_count <= 0:
            kind, confidence = "video_visual_only_or_silent", "medium"
        elif audio_label == "speech_unknown":
            kind, confidence = "video_with_speech_or_voice", audio_confidence
        elif audio_label == "music_unknown":
            kind, confidence = "video_with_music_or_stereo_audio", audio_confidence
        elif audio_label == "silence":
            kind, confidence = "video_with_silent_or_near_silent_audio", "medium"
        elif audio_count > 0 and video_count > 0:
            kind, confidence = "video_with_audio", "low"
        else:
            kind, confidence = "video_unknown_visual_content", "low"
        evidence.extend([f"audio_stream_count:{audio_count}", f"video_stream_count:{video_count}"])
    else:
        kind, confidence = "media_unknown_content", "low"
    return {
        "kind": kind,
        "confidence": confidence,
        "source": "deterministic_stream_tags_waveform",
        "evidence": sorted(set(str(item) for item in evidence if item)),
        "audio_kind": audio_kind,
        "limits": "Coarse media-content label only; full transcription, music recognition, scene recognition, and object recognition require configured providers.",
    }


def deterministic_audio_kind(
    classification: Classification,
    profile: dict[str, Any],
    ffprobe_metadata: dict[str, object] | None,
    python_metadata: dict[str, object] | None,
    *,
    path: Path | None,
) -> dict[str, Any]:
    if classification.rough_category not in {"audio", "video"}:
        return {"kind": "not_audio_media", "confidence": "none", "evidence": []}
    evidence: list[str] = []
    audio_count = int(profile.get("audio_stream_count") or 0)
    video_count = int(profile.get("video_stream_count") or 0)
    duration = profile.get("duration_seconds")
    try:
        duration_value = float(duration) if duration is not None else None
    except (TypeError, ValueError):
        duration_value = None
    if audio_count <= 0:
        return {"kind": "no_audio_stream", "confidence": "high", "evidence": ["audio_stream_count:0"]}
    wav_stats = wav_audio_stats(path) if path is not None and classification.concrete_format.upper() == "WAV" else None
    if wav_stats:
        evidence.append("wav_stats_available")
        if bool(wav_stats.get("silence")):
            return {
                "kind": "silence",
                "confidence": "high",
                "evidence": [*evidence, f"rms_normalized:{wav_stats.get('rms_normalized')}"],
                "waveform": wav_stats,
            }
    if duration_value is not None and duration_value < 0.5:
        return {
            "kind": "very_short",
            "confidence": "medium",
            "evidence": [*evidence, f"duration_seconds:{duration_value}"],
            **({"waveform": wav_stats} if wav_stats else {}),
        }
    tag_kind = audio_kind_from_tags(ffprobe_metadata, python_metadata)
    if tag_kind is not None:
        return {
            "kind": tag_kind,
            "confidence": "low",
            "evidence": [*evidence, "metadata_tags"],
            **({"waveform": wav_stats} if wav_stats else {}),
        }
    if video_count and audio_count:
        return {
            "kind": "mixed_unknown",
            "confidence": "low",
            "evidence": [*evidence, f"audio_stream_count:{audio_count}", f"video_stream_count:{video_count}"],
            **({"waveform": wav_stats} if wav_stats else {}),
        }
    channels = audio_channels(ffprobe_metadata, python_metadata)
    if channels == 1:
        kind = "speech_unknown"
        evidence.append("mono_audio")
    elif channels and channels >= 2:
        kind = "music_unknown"
        evidence.append(f"channels:{channels}")
    else:
        kind = "unknown_audio_content"
        evidence.append("insufficient_stream_or_tag_evidence")
    return {
        "kind": kind,
        "confidence": "low",
        "evidence": evidence,
        **({"waveform": wav_stats} if wav_stats else {}),
    }


def wav_audio_stats(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    try:
        with wave.open(str(path), "rb") as handle:
            channels = handle.getnchannels()
            sample_width = handle.getsampwidth()
            frame_rate = handle.getframerate()
            frame_count = handle.getnframes()
            max_frames = min(frame_count, max(frame_rate * 5, 1))
            raw = handle.readframes(max_frames)
    except Exception as exc:
        return {"available": False, "error": str(exc)}
    if not raw or sample_width not in {1, 2, 4}:
        return {
            "available": False,
            "channels": channels,
            "sample_width": sample_width,
            "frame_rate": frame_rate,
            "frame_count": frame_count,
            "error": "unsupported_or_empty_wave_samples",
        }
    values: list[int] = []
    for offset in range(0, len(raw) - sample_width + 1, sample_width):
        chunk = raw[offset : offset + sample_width]
        if sample_width == 1:
            sample = int(chunk[0]) - 128
            max_abs_value = 128
        else:
            sample = int.from_bytes(chunk, "little", signed=True)
            max_abs_value = float(2 ** (8 * sample_width - 1))
        values.append(sample)
    if not values:
        return {"available": False, "error": "no_wave_samples_decoded"}
    square_sum = sum(float(value) * float(value) for value in values)
    rms = (square_sum / len(values)) ** 0.5
    peak = max(abs(value) for value in values)
    rms_normalized = float(rms) / float(max_abs_value)
    peak_normalized = float(peak) / float(max_abs_value)
    return {
        "available": True,
        "channels": channels,
        "sample_width": sample_width,
        "frame_rate": frame_rate,
        "frame_count": frame_count,
        "sampled_frames": max_frames,
        "duration_seconds": round(frame_count / frame_rate, 3) if frame_rate else None,
        "rms_normalized": round(rms_normalized, 6),
        "peak_normalized": round(peak_normalized, 6),
        "silence": rms_normalized < 0.001 and peak_normalized < 0.005,
    }


def audio_kind_from_tags(
    ffprobe_metadata: dict[str, object] | None,
    python_metadata: dict[str, object] | None,
) -> str | None:
    tag_text = " ".join(media_tag_tokens(ffprobe_metadata, python_metadata))
    if not tag_text:
        return None
    music_markers = ("artist", "album", "genre", "track", "musicbrainz", "composer", "discnumber")
    speech_markers = ("podcast", "audiobook", "spoken", "speech", "voice", "narrator")
    if any(marker in tag_text for marker in speech_markers):
        return "speech_unknown"
    if any(marker in tag_text for marker in music_markers):
        return "music_unknown"
    return None


def media_tag_tokens(
    ffprobe_metadata: dict[str, object] | None,
    python_metadata: dict[str, object] | None,
) -> list[str]:
    tokens: list[str] = []
    if isinstance(ffprobe_metadata, dict):
        fmt = ffprobe_metadata.get("format")
        if isinstance(fmt, dict) and isinstance(fmt.get("tags"), dict):
            for key, value in list(fmt["tags"].items())[:100]:
                tokens.append(str(key).casefold())
                tokens.append(str(value).casefold())
    if isinstance(python_metadata, dict) and isinstance(python_metadata.get("tags"), dict):
        for key, value in list(python_metadata["tags"].items())[:100]:
            tokens.append(str(key).casefold())
            tokens.append(str(value).casefold())
    return tokens


def audio_channels(
    ffprobe_metadata: dict[str, object] | None,
    python_metadata: dict[str, object] | None,
) -> int | None:
    if isinstance(ffprobe_metadata, dict):
        streams = ffprobe_metadata.get("streams")
        if isinstance(streams, list):
            for stream in streams:
                if isinstance(stream, dict) and stream.get("codec_type") == "audio":
                    try:
                        return int(stream.get("channels")) if stream.get("channels") is not None else None
                    except (TypeError, ValueError):
                        return None
    if isinstance(python_metadata, dict):
        try:
            return int(python_metadata.get("channels")) if python_metadata.get("channels") is not None else None
        except (TypeError, ValueError):
            return None
    return None


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
    rough_content = profile.get("rough_content") if isinstance(profile.get("rough_content"), dict) else {}
    audio_kind = profile.get("audio_kind") if isinstance(profile.get("audio_kind"), dict) else {}
    speech_likely = rough_content.get("kind") in {"audio_speech_or_voice", "video_with_speech_or_voice"} or audio_kind.get("kind") == "speech_unknown"
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
            "rough_content": profile.get("rough_content"),
            "confidence": (profile.get("rough_content") or {}).get("confidence") if isinstance(profile.get("rough_content"), dict) else "low",
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
        plan["reason"] = "speech execution hook is configured and will run without model downloads"
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


def run_frame_sampling_if_configured(
    path: Path,
    classification: Classification,
    profile: dict[str, Any],
    statuses: list[Any],
    config: Any | None,
) -> dict[str, Any]:
    cfg = config_for_context(config)
    provider = effective_provider(cfg, "video_frames")
    status = next((item for item in statuses if item.name == "video_frames"), None)
    max_frames = positive_int(provider.get("max_frames")) or 5
    interval_seconds = positive_float(provider.get("interval_seconds")) or 10.0
    timestamps = sample_timestamps(profile.get("duration_seconds"), max_frames, interval_seconds)
    result: dict[str, Any] = {
        "attempted": False,
        "used": False,
        "provider": getattr(provider, "name", "none"),
        "mode": str(provider.get("mode", "interval") or "interval"),
        "max_frames": max_frames,
        "interval_seconds": interval_seconds,
        "sample_timestamps_seconds": timestamps,
        "sampled_frame_count": 0,
        "sampled_frames": [],
        "preserve_frames": bool(provider.get("preserve_frames", False)),
        "warnings": [],
        "reason": "",
    }
    if classification.rough_category != "video":
        result["reason"] = "not_a_video_file"
        return result
    if not bool(provider.get("sample_frames", False)):
        result["reason"] = "frame sampling disabled by video_frames provider config"
        return result
    if status is None or not status.available:
        result["reason"] = getattr(status, "error", None) or "video frame provider unavailable"
        return result
    if not bool(provider.get("auto_invoke", False)):
        result["reason"] = "video frame provider configured but auto_invoke=false"
        return result
    tool = resolve_external_tool(cfg, "ffmpeg")
    ffmpeg_bin = str(tool.get("source") or "")
    if not ffmpeg_bin:
        result["reason"] = str(tool.get("error") or "ffmpeg executable not found")
        return result
    result["attempted"] = True
    output_format = normalized_frame_format(provider.get("output_format", "png"))
    timeout = int(provider.get("timeout_seconds", tool.get("timeout_seconds") or 120) or 120)
    preserve = bool(provider.get("preserve_frames", False))
    output_dir = str(provider.get("output_dir", provider.get("frame_output_dir", "")) or "")
    if preserve:
        workdir = Path(output_dir).expanduser() if output_dir else Path(tempfile.mkdtemp(prefix="all2text_frames_"))
        workdir.mkdir(parents=True, exist_ok=True)
        cleanup = None
    else:
        cleanup = tempfile.TemporaryDirectory(prefix="all2text_frames_")
        workdir = Path(cleanup.name)
    try:
        if str(result["mode"]).casefold() == "keyframe":
            frames, frame_warnings = extract_keyframes(
                path,
                ffmpeg_bin=ffmpeg_bin,
                output_dir=workdir,
                output_format=output_format,
                max_frames=max_frames,
                timeout_seconds=timeout,
                preserve_paths=preserve,
            )
        else:
            frames, frame_warnings = extract_interval_frames(
                path,
                ffmpeg_bin=ffmpeg_bin,
                output_dir=workdir,
                output_format=output_format,
                timestamps=timestamps,
                timeout_seconds=timeout,
                preserve_paths=preserve,
            )
        result["warnings"].extend(frame_warnings)
        result["sampled_frames"] = frames
        result["sampled_frame_count"] = len(frames)
        result["used"] = bool(frames)
        result["reason"] = "ffmpeg_frame_sampling_completed" if frames else "ffmpeg_returned_no_frames"
    finally:
        if cleanup is not None:
            cleanup.cleanup()
            result["temporary_directory_cleaned"] = True
        else:
            result["temporary_directory_cleaned"] = False
    return result


def normalized_frame_format(value: Any) -> str:
    output_format = str(value or "png").casefold().lstrip(".")
    if output_format in {"jpg", "jpeg"}:
        return "jpg"
    if output_format in {"png", "webp"}:
        return output_format
    return "png"


def extract_interval_frames(
    path: Path,
    *,
    ffmpeg_bin: str,
    output_dir: Path,
    output_format: str,
    timestamps: list[float],
    timeout_seconds: int,
    preserve_paths: bool,
) -> tuple[list[dict[str, Any]], list[str]]:
    frames: list[dict[str, Any]] = []
    warnings: list[str] = []
    for index, timestamp in enumerate(timestamps, start=1):
        frame_path = output_dir / f"frame_{index:03d}_{int(timestamp * 1000):09d}ms.{output_format}"
        cmd = [
            ffmpeg_bin,
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            f"{timestamp:.3f}",
            "-i",
            str(path),
            "-frames:v",
            "1",
            "-an",
            "-y",
            str(frame_path),
        ]
        warning = run_ffmpeg_command(cmd, timeout_seconds=timeout_seconds)
        if warning:
            warnings.append(warning)
        if frame_path.exists() and frame_path.stat().st_size > 0:
            frames.append(frame_record(frame_path, timestamp=timestamp, preserve_path=preserve_paths))
    return frames, warnings


def extract_keyframes(
    path: Path,
    *,
    ffmpeg_bin: str,
    output_dir: Path,
    output_format: str,
    max_frames: int,
    timeout_seconds: int,
    preserve_paths: bool,
) -> tuple[list[dict[str, Any]], list[str]]:
    pattern = output_dir / f"keyframe_%03d.{output_format}"
    cmd = [
        ffmpeg_bin,
        "-hide_banner",
        "-loglevel",
        "error",
        "-skip_frame",
        "nokey",
        "-i",
        str(path),
        "-vsync",
        "0",
        "-frames:v",
        str(max_frames),
        "-an",
        "-y",
        str(pattern),
    ]
    warnings = []
    warning = run_ffmpeg_command(cmd, timeout_seconds=timeout_seconds)
    if warning:
        warnings.append(warning)
    frames = [
        frame_record(item, timestamp=None, preserve_path=preserve_paths)
        for item in sorted(output_dir.glob(f"keyframe_*.{output_format}"))[:max_frames]
        if item.stat().st_size > 0
    ]
    return frames, warnings


def run_ffmpeg_command(cmd: list[str], *, timeout_seconds: int) -> str | None:
    try:
        completed = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except Exception as exc:
        return f"ffmpeg_frame_extract_error:{exc}"
    if completed.returncode != 0:
        stderr = completed.stderr.strip().replace("\n", " ")[:1000]
        return f"ffmpeg_frame_extract_exit_code:{completed.returncode}:{stderr}"
    return None


def frame_record(frame_path: Path, *, timestamp: float | None, preserve_path: bool) -> dict[str, Any]:
    return {
        "path": str(frame_path) if preserve_path else None,
        "file_name": frame_path.name,
        "timestamp_seconds": timestamp,
        "size_bytes": frame_path.stat().st_size,
        "path_preserved": preserve_path,
    }


def run_speech_if_configured(
    path: Path,
    classification: Classification,
    profile: dict[str, Any],
    statuses: list[Any],
    config: Any | None,
) -> dict[str, Any]:
    cfg = config_for_context(config)
    provider = effective_provider(cfg, "speech")
    status = next((item for item in statuses if item.name == "speech"), None)
    requested = any(
        bool(provider.get(key, False))
        for key in ("transcribe", "translate", "language_detection")
    )
    result: dict[str, Any] = {
        "attempted": False,
        "used": False,
        "provider": getattr(provider, "name", "none"),
        "text": "",
        "language": None,
        "segments": [],
        "warnings": [],
        "reason": "",
    }
    if classification.rough_category not in {"audio", "video"}:
        result["reason"] = "not_audio_or_video"
        return result
    if not requested:
        result["reason"] = "speech tasks disabled by provider config"
        return result
    if int(profile.get("audio_stream_count") or 0) <= 0:
        result["reason"] = "no audio stream/profile evidence that speech is possible"
        return result
    if status is None or not status.available:
        result["reason"] = getattr(status, "error", None) or "speech provider unavailable"
        return result
    if not bool(provider.get("auto_invoke", False)):
        result["reason"] = "speech provider configured but auto_invoke=false"
        return result
    result["attempted"] = True
    if provider.name == "faster_whisper":
        return run_faster_whisper(path, provider, result)
    if provider.name == "whisper_cpp":
        return run_whisper_cpp(path, provider, result)
    result["reason"] = f"{provider.name} speech execution adapter is not implemented"
    return result


def run_faster_whisper(path: Path, provider: Any, result: dict[str, Any]) -> dict[str, Any]:
    model_ref = str(provider.get("model_path", "") or provider.get("model", "") or "")
    model_path = Path(model_ref).expanduser()
    if not model_ref or not model_path.exists():
        result["reason"] = "faster-whisper model_path/model is not a local path; no download performed"
        return result
    try:
        from faster_whisper import WhisperModel
    except Exception as exc:
        result["warnings"].append(f"faster_whisper_unavailable:{exc}")
        result["reason"] = "faster-whisper Python package unavailable"
        return result
    try:
        device = str(provider.get("device", "auto") or "auto")
        if device == "auto":
            device = "cpu"
        compute_type = str(provider.get("compute_type", "default") or "default")
        model = WhisperModel(str(model_path), device=device, compute_type=compute_type)
        segments_iter, info = model.transcribe(
            str(path),
            beam_size=int(provider.get("beam_size", 1) or 1),
            task="translate" if bool(provider.get("translate", False)) else "transcribe",
            vad_filter=bool(provider.get("vad_filter", False)),
        )
        max_segments = int(provider.get("max_segments", 200) or 200)
        segments = []
        for segment in segments_iter:
            if len(segments) >= max_segments:
                break
            text = str(getattr(segment, "text", "") or "").strip()
            segments.append(
                {
                    "start": round(float(getattr(segment, "start", 0.0)), 3),
                    "end": round(float(getattr(segment, "end", 0.0)), 3),
                    "text": text,
                }
            )
        text = " ".join(item["text"] for item in segments if item.get("text")).strip()
        result.update(
            {
                "used": bool(text),
                "text": text,
                "language": getattr(info, "language", None),
                "language_probability": round(float(getattr(info, "language_probability", 0.0)), 4)
                if getattr(info, "language_probability", None) is not None
                else None,
                "duration": round(float(getattr(info, "duration", 0.0)), 3)
                if getattr(info, "duration", None) is not None
                else None,
                "segments": segments,
                "truncated": len(segments) >= max_segments,
                "reason": "faster_whisper_transcription_completed" if text else "faster_whisper_returned_no_text",
            }
        )
    except Exception as exc:
        result["warnings"].append(f"faster_whisper_failed:{exc}")
        result["reason"] = "faster-whisper execution failed"
    return result


def run_whisper_cpp(path: Path, provider: Any, result: dict[str, Any]) -> dict[str, Any]:
    model_ref = str(provider.get("model_path", "") or provider.get("model", "") or "")
    executable = str(provider.get("executable", "") or shutil.which("whisper-cli") or shutil.which("whisper.cpp") or shutil.which("main") or "")
    if not executable:
        result["reason"] = "whisper.cpp executable not found: whisper-cli or whisper.cpp"
        return result
    if not model_ref or not Path(model_ref).expanduser().exists():
        result["reason"] = "whisper.cpp model_path/model is not a local path"
        return result
    with tempfile.TemporaryDirectory(prefix="all2text_whisper_cpp_") as tmpdir:
        output_base = Path(tmpdir) / "transcript"
        cmd = [
            executable,
            "-m",
            str(Path(model_ref).expanduser()),
            "-f",
            str(path),
            "-otxt",
            "-of",
            str(output_base),
        ]
        warning = run_ffmpeg_command(cmd, timeout_seconds=int(provider.get("timeout_seconds", 300) or 300))
        if warning:
            result["warnings"].append(warning.replace("ffmpeg_frame_extract", "whisper_cpp"))
            result["reason"] = "whisper.cpp execution failed"
            return result
        transcript_path = output_base.with_suffix(".txt")
        if transcript_path.exists():
            text = transcript_path.read_text(encoding="utf-8", errors="replace").strip()
        else:
            text = ""
    result.update(
        {
            "used": bool(text),
            "text": text,
            "segments": [],
            "reason": "whisper_cpp_transcription_completed" if text else "whisper_cpp_returned_no_text",
        }
    )
    return result


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
        "Rough content:",
        json.dumps(profile.get("rough_content") or {}, indent=2, ensure_ascii=False),
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
