from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from all2text import run
from all2text.backends.image import image_profile
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
