from __future__ import annotations

import shutil
import wave
from pathlib import Path

from PIL import Image, ImageDraw
import pytest

from all2text import run
from all2text.backends.image import image_profile, run_ocr_if_configured
from all2text.backends.media import media_profile, media_stages
from all2text.config import config_from_dict, default_config
from all2text.detection import classify_path
from all2text.models import Classification, LayerEvidence
from all2text.providers import discover_model_hints, provider_family_statuses, provider_statuses
from tests.conftest import entry, make_options


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


def test_provider_family_statuses_include_lifecycle_and_blockers(monkeypatch, tmp_path: Path) -> None:
    model_dir = tmp_path / "models" / "google_deplot"
    model_dir.mkdir(parents=True)
    (model_dir / "config.json").write_text("{}", encoding="utf-8")
    discover_model_hints.cache_clear()
    monkeypatch.setattr("all2text.providers.model_roots", lambda: [tmp_path / "models"])
    monkeypatch.setattr("all2text.providers.candidate_external_python", lambda name, config: None)

    statuses = provider_family_statuses(default_config())
    by_name = {status.name: status for status in statuses}

    assert by_name["deterministic_image_profile"].available is True
    assert by_name["deterministic_image_profile"].lifecycle["configured"] is True
    assert by_name["docling"].available is False
    assert "Python dependency missing" in str(by_name["docling"].error)
    assert by_name["deplot"].details["model_matches"]
    assert by_name["deplot"].lifecycle["missing"] is True


def test_image_taxonomy_prefers_content_chart_over_weak_filename_hint(tmp_path: Path) -> None:
    path = tmp_path / "diagram_named_but_bars_content.png"
    image = Image.new("RGB", (360, 260), "white")
    draw = ImageDraw.Draw(image)
    draw.line([(55, 25), (55, 220), (320, 220)], fill="black", width=3)
    for box in [(85, 150, 125, 220), (155, 90, 195, 220), (225, 125, 265, 220)]:
        draw.rectangle(box, fill=(230, 120, 30), outline="black")
    image.save(path)

    profile, warnings, _ = image_profile(
        path,
        classify_path(path, metadata={"looks_text": False}, options=make_options()),
        {},
    )

    assert warnings == []
    assert profile["taxonomy"] == "chart_plot"
    assert profile["taxonomy_source"] == "deterministic_content_features"
    assert profile["source_hint_taxonomy"] == "diagram_flowchart_uml_network"
    assert profile["chart_candidate"] is True


def test_image_taxonomy_routes_grid_as_table_not_chart(tmp_path: Path) -> None:
    path = tmp_path / "sales_chart_name_but_table_content.png"
    image = Image.new("RGB", (300, 180), "white")
    draw = ImageDraw.Draw(image)
    for x in [20, 110, 200, 280]:
        draw.line([(x, 20), (x, 160)], fill="black", width=2)
    for y in [20, 55, 90, 125, 160]:
        draw.line([(20, y), (280, y)], fill="black", width=2)
    image.save(path)

    profile, _warnings, _ = image_profile(
        path,
        classify_path(path, metadata={"looks_text": False}, options=make_options()),
        {},
    )

    assert profile["taxonomy"] == "table_screenshot"
    assert profile["chart_candidate"] is False


def test_audio_classifier_and_diarization_stage_plans_are_truthful() -> None:
    config = config_from_dict(
        {
            "providers": {
                "audio_classifier": {"name": "yamnet", "enabled": True, "auto_invoke": False},
                "diarization": {"name": "pyannote", "enabled": True, "auto_invoke": False},
            }
        }
    )
    classification = _classification("audio", "WAV")
    profile = media_profile(classification, {"streams": [{"codec_type": "audio"}], "format": {"duration": "2"}})
    stages = media_stages(classification, profile, provider_statuses(config, family="audio"), config)

    assert stages["audio_kind_classification"]["planned"] is True
    assert stages["audio_kind_classification"]["attempted"] is False
    assert stages["audio_kind_classification"]["provider_status"]["available"] is False
    assert stages["audio_kind_classification"]["reason"]
    assert stages["diarization"]["planned"] is True
    assert stages["diarization"]["attempted"] is False


def test_configured_speech_provider_requires_explicit_model_ref() -> None:
    config = config_from_dict(
        {
            "providers": {
                "speech": {
                    "name": "faster_whisper",
                    "enabled": True,
                    "auto_invoke": True,
                    "model_path": "",
                }
            }
        }
    )

    status = {item.name: item for item in provider_statuses(config, family="audio")}["speech"]

    assert status.enabled is True
    assert status.available is False
    assert "model_path/model is not configured" in str(status.error) or "Python package not installed" in str(status.error)


def test_configured_faster_whisper_requires_local_model_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr("all2text.providers.python_module_available", lambda module: module == "faster_whisper")
    model_dir = tmp_path / "tiny-model"
    model_dir.mkdir()
    config = config_from_dict(
        {
            "providers": {
                "speech": {
                    "name": "faster_whisper",
                    "enabled": True,
                    "auto_invoke": True,
                    "model_path": str(model_dir),
                    "transcribe": True,
                }
            }
        }
    )

    status = {item.name: item for item in provider_statuses(config, family="audio")}["speech"]

    assert status.available is True
    assert status.source == str(model_dir)


def test_model_discovery_follows_snapshot_dirs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    snapshot = tmp_path / "models--Systran--faster-whisper-tiny" / "snapshots" / "abc123"
    snapshot.mkdir(parents=True)
    (snapshot / "config.json").write_text("{}", encoding="utf-8")
    discover_model_hints.cache_clear()
    monkeypatch.setattr("all2text.providers.model_roots", lambda: [tmp_path])

    matches = discover_model_hints(("faster-whisper", "faster_whisper"))

    assert str(snapshot) in matches


def test_tesseract_ocr_filters_by_confidence(monkeypatch: pytest.MonkeyPatch) -> None:
    pytesseract = pytest.importorskip("pytesseract")

    image = Image.new("RGB", (120, 40), "white")
    provider = config_from_dict(
        {
            "providers": {
                "ocr": {
                    "name": "tesseract",
                    "enabled": True,
                    "auto_invoke": True,
                    "min_confidence": 50,
                    "min_characters": 2,
                    "min_alnum_ratio": 0.1,
                }
            }
        }
    ).provider("ocr")

    def fake_image_to_data(*args: object, **kwargs: object) -> dict[str, list[object]]:
        return {
            "text": ["noise", "OK42"],
            "conf": ["12", "91"],
            "block_num": [1, 1],
            "par_num": [1, 1],
            "line_num": [1, 1],
        }

    monkeypatch.setattr(pytesseract, "image_to_data", fake_image_to_data)

    result = run_ocr_if_configured(image, provider)

    assert result["attempted"] is True
    assert result["used"] is True
    assert result["text"] == "OK42"
    assert result["confidence"] == 91.0
    assert result["word_count"] == 2
    assert result["accepted_word_count"] == 1


def test_real_tesseract_ocr_smoke_when_available(tmp_path: Path) -> None:
    pytest.importorskip("pytesseract")
    if shutil.which("tesseract") is None:
        pytest.skip("tesseract executable is not installed")
    path = tmp_path / "ocr.png"
    image = Image.new("RGB", (420, 120), "white")
    draw = ImageDraw.Draw(image)
    font = None
    font_path = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
    if font_path.exists():
        from PIL import ImageFont

        font = ImageFont.truetype(str(font_path), 48)
    draw.text((20, 30), "TEST 123", fill="black", font=font)
    image.save(path)
    provider = config_from_dict(
        {
            "providers": {
                "ocr": {
                    "name": "tesseract",
                    "enabled": True,
                    "auto_invoke": True,
                    "min_confidence": 0,
                    "min_characters": 3,
                    "min_alnum_ratio": 0.1,
                }
            }
        }
    ).provider("ocr")

    result = run_ocr_if_configured(Image.open(path), provider)

    assert result["attempted"] is True
    assert result["used"] is True
    assert "TEST" in result["text"].upper() or "123" in result["text"]


def test_wav_silence_audio_kind_uses_waveform_stats(tmp_path: Path) -> None:
    path = tmp_path / "silence.wav"
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(8000)
        handle.writeframes(b"\x00\x00" * 8000)
    classification = _classification("audio", "WAV")
    profile = media_profile(
        classification,
        {"streams": [{"codec_type": "audio", "channels": 1}], "format": {"duration": "1.0"}},
        path=path,
    )

    assert profile["audio_kind"]["kind"] == "silence"
    assert profile["audio_kind"]["waveform"]["silence"] is True


def test_numpy_schema_probe_does_not_dump_array_values(tmp_path: Path) -> None:
    import numpy as np

    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    np.save(source / "array.npy", np.arange(6, dtype=np.int16).reshape(2, 3))

    manifest = run(source, target, options=make_options())
    record = entry(manifest, "array.npy")
    schema = record["converter_metadata"]["schema_probe"]

    assert record["converter_used"] == "scientific_placeholder_backend"
    assert schema["provider"] == "numpy"
    assert schema["shape"] == [2, 3]
    assert schema["dtype"] == "int16"
    assert schema["array_values_dumped"] is False


def test_elf_header_metadata_probe_never_executes_binary(tmp_path: Path) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    # Minimal ELF-like header: magic, 64-bit, little-endian, executable type, AArch64 machine.
    (source / "program").write_bytes(
        b"\x7fELF" + bytes([2, 1, 1, 0]) + b"\x00" * 8 + (2).to_bytes(2, "little") + (183).to_bytes(2, "little")
    )

    manifest = run(source, target, options=make_options())
    schema = entry(manifest, "program")["converter_metadata"]["schema_probe"]

    assert schema["provider"] == "stdlib_header_parser"
    assert schema["format"] == "elf"
    assert schema["bits"] == 64
    assert schema["code_executed"] is False


def test_provider_family_status_detects_external_docling_env(monkeypatch, tmp_path: Path) -> None:
    python = tmp_path / "tools" / "docling-env" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.write_text("#!/bin/sh\n", encoding="utf-8")
    monkeypatch.setattr("all2text.providers.python_module_available", lambda module: False)
    monkeypatch.setattr("all2text.providers.external_python_module_available", lambda path, module: True)
    monkeypatch.setattr("all2text.providers.candidate_external_python", lambda name, config: python if name == "docling" else None)

    status = next(item for item in provider_family_statuses(default_config()) if item.name == "docling")

    assert status.available is True
    assert status.source == str(python)
    assert status.details["external_python"] == str(python)
