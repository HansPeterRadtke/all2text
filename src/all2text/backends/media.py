from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from all2text.config import config_for_context
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
        ffprobe_metadata, warnings = ffprobe(path)
        family = classification.rough_category
        statuses = provider_statuses(cfg, family=family)
        profile = media_profile(classification, ffprobe_metadata)
        stages = media_stages(classification, profile, statuses)
        limitation = (
            "Media conversion is layered metadata/provider reporting in the core package. "
            "Speech transcription, translation, frame OCR, scene analysis, and VLM understanding require configured providers."
        )
        text = render_media_text(classification, limitation, ffprobe_metadata, profile, stages, [status.to_dict() for status in statuses])
        methods = ["media_layered_metadata"]
        if ffprobe_metadata:
            methods.append("ffprobe_metadata")
        return ConversionResult(
            text=text,
            converter_used=self.name,
            extraction_methods_used=methods,
            warnings=warnings,
            metadata={
                "ffprobe": ffprobe_metadata or None,
                "profile": profile,
                "stages": stages,
                "provider_statuses": [status.to_dict() for status in statuses],
            },
            limitations=[limitation],
        )


MediaPlaceholderBackend = MediaAnalysisBackend


def ffprobe(path: Path) -> tuple[dict[str, object] | None, list[str]]:
    ffprobe_bin = shutil.which("ffprobe")
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
            timeout=15,
        )
    except Exception as exc:
        return None, [f"ffprobe_error:{exc}"]
    if completed.returncode != 0:
        return None, [f"ffprobe_exit_code:{completed.returncode}", f"ffprobe_stderr:{completed.stderr.strip()}"]
    try:
        return json.loads(completed.stdout or "{}"), []
    except Exception:
        return {"raw_stdout": completed.stdout[:4000]}, ["ffprobe_json_parse_failed"]


def media_profile(classification: Classification, ffprobe_metadata: dict[str, object] | None) -> dict[str, Any]:
    streams = ffprobe_metadata.get("streams", []) if isinstance(ffprobe_metadata, dict) else []
    if not isinstance(streams, list):
        streams = []
    audio_streams = [stream for stream in streams if isinstance(stream, dict) and stream.get("codec_type") == "audio"]
    video_streams = [stream for stream in streams if isinstance(stream, dict) and stream.get("codec_type") == "video"]
    subtitles = [stream for stream in streams if isinstance(stream, dict) and stream.get("codec_type") == "subtitle"]
    tags = (ffprobe_metadata.get("format", {}) or {}).get("tags", {}) if isinstance(ffprobe_metadata, dict) else {}
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
        "audio_stream_count": len(audio_streams),
        "video_stream_count": len(video_streams),
        "subtitle_stream_count": len(subtitles),
        "duration_seconds": _duration(ffprobe_metadata),
        "language_tags": language_tags,
        "format_tags_present": bool(tags),
        "classification_note": "Content class such as speech/music/song/noise/screen recording/lecture is not inferred without a configured analyzer.",
    }


def media_stages(classification: Classification, profile: dict[str, Any], statuses: list[Any]) -> dict[str, Any]:
    speech_status = next((status for status in statuses if status.name == "speech"), None)
    frame_status = next((status for status in statuses if status.name == "video_frames"), None)
    ocr_status = next((status for status in statuses if status.name == "ocr"), None)
    vlm_status = next((status for status in statuses if status.name == "vlm"), None)
    speech_likely = profile.get("coarse_classification") in {"unknown_audio_content", "mixed_audio_video", "audio_only_container"}
    stages: dict[str, Any] = {
        "metadata": {"attempted": True, "used": True, "provider": "ffprobe" if profile.get("duration_seconds") is not None else "header_or_ffprobe"},
        "coarse_classification": {
            "attempted": True,
            "label": profile.get("coarse_classification"),
            "confidence": "low",
            "limitation": profile.get("classification_note"),
        },
        "language_detection": {
            "attempted": False,
            "reason": "speech language detection requires a configured speech provider",
            "provider_status": speech_status.to_dict() if speech_status else None,
        },
        "transcription": {
            "attempted": False,
            "reason": "transcription requires a configured speech provider",
            "speech_possible": speech_likely,
            "provider_status": speech_status.to_dict() if speech_status else None,
        },
        "translation": {
            "attempted": False,
            "reason": "translation requires a configured speech provider with translation enabled",
            "provider_status": speech_status.to_dict() if speech_status else None,
        },
    }
    if classification.rough_category == "video":
        stages.update(
            {
                "subtitle_extraction": {
                    "attempted": profile.get("subtitle_stream_count", 0) > 0,
                    "subtitle_stream_count": profile.get("subtitle_stream_count", 0),
                    "limitation": "Subtitle streams are counted; subtitle text extraction is a future provider stage.",
                },
                "frame_sampling": {
                    "attempted": False,
                    "reason": "frame sampling requires configured ffmpeg/video frame provider",
                    "provider_status": frame_status.to_dict() if frame_status else None,
                },
                "frame_ocr": {
                    "attempted": False,
                    "reason": "frame OCR requires configured frame sampling and OCR providers",
                    "provider_status": ocr_status.to_dict() if ocr_status else None,
                },
                "frame_vlm": {
                    "attempted": False,
                    "reason": "frame VLM requires configured frame sampling and VLM providers",
                    "provider_status": vlm_status.to_dict() if vlm_status else None,
                },
            }
        )
    return stages


def render_media_text(
    classification: Classification,
    limitation: str,
    ffprobe_metadata: dict[str, object] | None,
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
