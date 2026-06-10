from __future__ import annotations

import wave
from pathlib import Path

from all2text.backends.image import image_rough_content
from all2text.backends.media import media_profile
from all2text.models import Classification, LayerEvidence


def _classification(category: str, fmt: str) -> Classification:
    empty = LayerEvidence(source="test")
    return Classification(
        extension_hint=empty,
        name_hint=empty,
        mime_hint=empty,
        content_signature=empty,
        rough_category=category,
        concrete_format=fmt,
        content_profile="test",
        confidence="strong",
    )


def test_image_rough_content_labels_chart_and_photo() -> None:
    chart = image_rough_content(
        {
            "taxonomy": "chart_plot",
            "taxonomy_source": "deterministic_content_features",
            "taxonomy_evidence": ["axis_lines"],
        }
    )
    photo = image_rough_content(
        {
            "taxonomy": "photo_scene",
            "taxonomy_source": "default_low_confidence",
            "taxonomy_evidence": [],
        }
    )

    assert chart["kind"] == "image_chart_or_plot"
    assert chart["confidence"] == "medium"
    assert photo["kind"] == "image_photo_or_scene"
    assert "default_photo_scene_when_no_specific_evidence" in photo["evidence"]


def test_audio_rough_content_labels_silence(tmp_path: Path) -> None:
    path = tmp_path / "silence.wav"
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16000)
        handle.writeframes(b"\x00\x00" * 1600)

    profile = media_profile(
        _classification("audio", "WAV"),
        None,
        {"streams": [{"type": "audio", "source": "test"}], "channels": 1, "duration_seconds": 0.1},
        path=path,
    )

    assert profile["rough_content"]["kind"] == "audio_silence"
    assert profile["rough_content"]["confidence"] == "high"


def test_audio_rough_content_labels_speech_and_music() -> None:
    speech = media_profile(
        _classification("audio", "MP3"),
        None,
        {"streams": [{"type": "audio"}], "channels": 1, "duration_seconds": 10.0},
        path=None,
    )
    music = media_profile(
        _classification("audio", "MP3"),
        None,
        {"streams": [{"type": "audio"}], "channels": 2, "duration_seconds": 10.0},
        path=None,
    )

    assert speech["rough_content"]["kind"] == "audio_speech_or_voice"
    assert music["rough_content"]["kind"] == "audio_music_or_stereo_content"


def test_video_rough_content_labels_visual_and_tagged_music() -> None:
    visual_only = media_profile(
        _classification("video", "MP4"),
        {"streams": [{"codec_type": "video"}], "format": {"duration": "2.0"}},
        None,
        path=None,
    )
    music_video = media_profile(
        _classification("video", "MP4"),
        {
            "streams": [{"codec_type": "video"}, {"codec_type": "audio", "channels": 2}],
            "format": {"duration": "2.0", "tags": {"genre": "music"}},
        },
        None,
        path=None,
    )

    assert visual_only["rough_content"]["kind"] == "video_visual_only_or_silent"
    assert music_video["rough_content"]["kind"] == "video_with_music_or_stereo_audio"


def test_image_content_taxonomy_labels_sparse_screenshot() -> None:
    from all2text.backends.image import content_taxonomy_for

    taxonomy, evidence = content_taxonomy_for(
        width=1280,
        height=720,
        aspect=1.778,
        non_white_ratio=0.05,
        color_count_estimate=900,
        structure={"available": True, "horizontal_line_rows": 0, "vertical_line_columns": 0},
    )

    assert taxonomy == "screenshot_ui"
    assert any(item.startswith("dimensions:1280x720") for item in evidence)


def test_screenshot_filename_hint_overrides_weak_linework(tmp_path: Path) -> None:
    from all2text.backends.image import classify_profile

    path = tmp_path / "screenshot_ui.png"
    result = classify_profile(
        fmt="PNG",
        width=1280,
        height=720,
        aspect=1.778,
        non_white_ratio=0.05,
        color_count_estimate=3,
        structure={"available": True, "horizontal_line_rows": 25, "vertical_line_columns": 0, "sparse_linework": True},
        path=path,
    )

    assert result["taxonomy"] == "screenshot_ui"
    assert result["taxonomy_source"] == "filename_hint_over_weak_linework"


def test_video_visual_only_ffprobe_overrides_weak_python_audio_count() -> None:
    profile = media_profile(
        _classification("video", "MP4"),
        {"streams": [{"codec_type": "video"}], "format": {"duration": "2.0"}},
        {"streams": [{"type": "audio"}], "duration_seconds": 2.0},
        path=None,
    )

    assert profile["coarse_classification"] == "visual_only_video"
    assert profile["rough_content"]["kind"] == "video_visual_only_or_silent"
