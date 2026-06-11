from __future__ import annotations

import shutil
from pathlib import Path

from all2text import run
from all2text.models import RunOptions
from tests.conftest import entry

FIXTURE = Path(__file__).parent / "fixtures" / "messy_all_in_one_corpus"


def corpus_options() -> RunOptions:
    return RunOptions(
        profile="core",
        use_file_command=False,
        auto_detect_python=False,
        auto_detect_tools=False,
        auto_detect_local_models=False,
        allow_optional_python=False,
        allow_external_tools=False,
        allow_local_models=False,
        copy_source_stat=False,
    )


def add_runtime_junk(source: Path) -> None:
    pycache = source / "__pycache__"
    pycache.mkdir()
    (pycache / "cache_file.cpython-38.pyc").write_bytes(b"\x00\x00pyc-cache")
    nested_pycache = source / "nested" / "__pycache__"
    nested_pycache.mkdir()
    (nested_pycache / "nested_cache.pyc").write_bytes(b"\x00\x00nested-cache")
    pytest_cache = source / ".pytest_cache" / "v" / "cache"
    pytest_cache.mkdir(parents=True)
    (pytest_cache / "nodeids").write_text("junk test cache\n", encoding="utf-8")
    build = source / "build" / "lib"
    build.mkdir(parents=True)
    (build / "copied.py").write_text("should be ignored\n", encoding="utf-8")
    (source / "Thumbs.db").write_bytes(b"ignored windows thumbnail cache")


def test_messy_all_in_one_corpus_classifies_by_content_not_extension(tmp_path: Path) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    shutil.copytree(FIXTURE, source)
    add_runtime_junk(source)

    manifest = run(source, target, options=corpus_options())

    expected = {
        "00_real_png_named_song.mp3": ("image", "PNG", "image_analysis_backend"),
        "01_silent_wav_named_photo.jpg": ("audio", "WAV", "media_analysis_backend"),
        "02_real_mp4_named_plain_text.txt": ("video", "MP4", "media_analysis_backend"),
        "03_real_pdf_named_picture.png": ("document", "PDF", "document_placeholder_backend"),
        "04_real_docx_named_movie.mp4": ("document", "DOCX", "document_placeholder_backend"),
        "05_real_zip_named_scan.jpeg": ("archive", "ZIP", "archive_listing_backend"),
        "06_real_gzip_named_table.csv": ("compressed", "GZIP", "archive_listing_backend"),
        "07_real_sqlite_named_notes.md": ("database", "SQLite", "database_metadata_backend"),
        "08_real_json_named_audio.wav": ("structured_text", "JSON", "text_exact_backend"),
        "09_real_csv_named_binary.bin": ("structured_text", "CSV", "text_exact_backend"),
        "10_real_geojson_named_blob.nope": ("geospatial", "GeoJSON", "geospatial_placeholder_backend"),
        "11_real_html_named_database.sqlite": ("structured_text", "HTML", "text_exact_backend"),
        "12_real_ifc_named_photo.jpg": ("cad_or_technical", "IFC", "cad_placeholder_backend"),
        "13_real_dxf_named_video.mp4": ("cad_or_technical", "DXF", "cad_placeholder_backend"),
        "14_unknown_payload.random": ("unknown", "unknown", "binary_fallback"),
        "nested/15_plain_text_without_extension": ("text", "TXT", "text_exact_backend"),
        "README_messy_corpus.txt": ("text", "TXT", "text_exact_backend"),
    }

    relative_paths = {record["relative_path"] for record in manifest["entries"]}
    assert manifest["summary"]["converted_text_file_count"] == len(expected)
    assert not any("__pycache__" in item for item in relative_paths)
    assert not any(".pytest_cache" in item for item in relative_paths)
    assert not any(item.startswith("build/") for item in relative_paths)
    assert "Thumbs.db" not in relative_paths
    assert not manifest["summary"]["files_with_errors"]

    for relative_path, (category, fmt, converter) in expected.items():
        record = entry(manifest, relative_path)
        classification = record["classification"]
        assert classification["rough_category"] == category, relative_path
        assert classification["concrete_format"] == fmt, relative_path
        assert record["converter_used"] == converter, relative_path

    for relative_path in expected:
        if relative_path == "14_unknown_payload.random":
            continue
        classification = entry(manifest, relative_path)["classification"]
        assert classification["content_signature"]["source"] == "content", relative_path

    assert "layer2_content_signature_override" in entry(manifest, "00_real_png_named_song.mp3")["classification"]["evidence"]
    assert "layer2_content_signature_override" in entry(manifest, "01_silent_wav_named_photo.jpg")["classification"]["evidence"]
    assert "layer2_content_signature_override" in entry(manifest, "02_real_mp4_named_plain_text.txt")["classification"]["evidence"]
    assert "layer2_content_signature_override" in entry(manifest, "12_real_ifc_named_photo.jpg")["classification"]["evidence"]
    assert "layer2_content_signature_override" in entry(manifest, "13_real_dxf_named_video.mp4")["classification"]["evidence"]

    wav_text = (target / "01_silent_wav_named_photo.jpg.txt").read_text(encoding="utf-8")
    assert "audio_silence" in wav_text
    mp4_text = (target / "02_real_mp4_named_plain_text.txt.txt").read_text(encoding="utf-8")
    assert "Rough content:" in mp4_text
    assert "video_" in mp4_text
