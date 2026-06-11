from __future__ import annotations

import shutil
from pathlib import Path

from all2text import run
from all2text.models import RunOptions
from tests.conftest import entry

FIXTURE = Path(__file__).parent / "fixtures" / "all_in_one_corpus"


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


EXPECTED: dict[str, tuple[str, str, str]] = {
    "README_all_in_one_corpus.txt": ("text", "TXT", "text_exact_backend"),
    "archives/bundle.tar": ("archive", "TAR", "archive_listing_backend"),
    "archives/bundle.zip": ("archive", "ZIP", "archive_listing_backend"),
    "archives/stream.bz2": ("compressed", "BZIP2", "archive_listing_backend"),
    "archives/stream.gz": ("compressed", "GZIP", "archive_listing_backend"),
    "archives/stream.xz": ("compressed", "XZ", "archive_listing_backend"),
    "cad/drawing.dxf": ("cad_or_technical", "DXF", "cad_placeholder_backend"),
    "cad/model.ifc": ("cad_or_technical", "IFC", "cad_placeholder_backend"),
    "cad/model.stl": ("cad_or_technical", "STL", "cad_placeholder_backend"),
    "database/sample.sqlite": ("database", "SQLite", "database_metadata_backend"),
    "disk/disk.iso": ("disk_image_or_container", "ISO disk image", "container_placeholder_backend"),
    "documents/document.docx": ("document", "DOCX", "document_placeholder_backend"),
    "documents/document.pdf": ("document", "PDF", "document_placeholder_backend"),
    "documents/open.odt": ("document", "ODT", "opendocument_native_backend"),
    "documents/slides.pptx": ("presentation", "PPTX", "document_placeholder_backend"),
    "documents/workbook.xlsx": ("spreadsheet", "XLSX", "document_placeholder_backend"),
    "ebook/book.epub": ("ebook", "EPUB", "ebook_placeholder_backend"),
    "email/message.eml": ("email", "EML", "email_metadata_backend"),
    "executables/program.elf": ("executable_or_binary", "ELF executable/shared object", "executable_placeholder_backend"),
    "executables/program.exe": ("executable_or_binary", "Windows executable", "executable_placeholder_backend"),
    "font/font.woff": ("font", "WOFF", "font_placeholder_backend"),
    "geospatial/map.geojson": ("geospatial", "GeoJSON", "geospatial_placeholder_backend"),
    "geospatial/map.kml": ("geospatial", "KML", "geospatial_placeholder_backend"),
    "images/pixel.png": ("image", "PNG", "image_analysis_backend"),
    "images/vector.svg": ("image", "SVG", "image_analysis_backend"),
    "media/sample.mp4": ("video", "MP4", "media_analysis_backend"),
    "media/silence.wav": ("audio", "WAV", "media_analysis_backend"),
    "nested/readme.txt": ("text", "TXT", "text_exact_backend"),
    "scientific/array.npy": ("scientific_data", "NumPy NPY", "scientific_placeholder_backend"),
    "scientific/data.h5": ("scientific_data", "HDF5", "scientific_placeholder_backend"),
    "scientific/image.fits": ("scientific_data", "FITS", "scientific_placeholder_backend"),
    "scientific/table.parquet": ("scientific_data", "Parquet", "scientific_placeholder_backend"),
    "source/script.py": ("source_code", "PY", "text_exact_backend"),
    "structured/config.yaml": ("structured_text", "YAML", "text_exact_backend"),
    "structured/data.json": ("structured_text", "JSON", "text_exact_backend"),
    "structured/page.html": ("structured_text", "HTML", "text_exact_backend"),
    "structured/table.csv": ("structured_text", "CSV", "text_exact_backend"),
    "text/plain.txt": ("text", "TXT", "text_exact_backend"),
    "text/plain_without_extension": ("text", "TXT", "text_exact_backend"),
    "unknown/random.random": ("unknown", "unknown", "binary_fallback"),
    "wrong_extension/csv_named_binary.bin": ("structured_text", "CSV", "text_exact_backend"),
    "wrong_extension/docx_named_movie.mp4": ("document", "DOCX", "document_placeholder_backend"),
    "wrong_extension/dxf_named_video.mp4": ("cad_or_technical", "DXF", "cad_placeholder_backend"),
    "wrong_extension/elf_named_picture.jpg": ("executable_or_binary", "ELF executable/shared object", "executable_placeholder_backend"),
    "wrong_extension/email_named_picture.png": ("email", "EML", "email_metadata_backend"),
    "wrong_extension/epub_named_binary.bin": ("ebook", "EPUB", "ebook_placeholder_backend"),
    "wrong_extension/exe_named_text.txt": ("executable_or_binary", "Windows executable", "executable_placeholder_backend"),
    "wrong_extension/fits_named_image.png": ("scientific_data", "FITS", "scientific_placeholder_backend"),
    "wrong_extension/geojson_named_blob.nope": ("geospatial", "GeoJSON", "geospatial_placeholder_backend"),
    "wrong_extension/gzip_named_table.csv": ("compressed", "GZIP", "archive_listing_backend"),
    "wrong_extension/hdf5_named_text.txt": ("scientific_data", "HDF5", "scientific_placeholder_backend"),
    "wrong_extension/html_named_database.sqlite": ("structured_text", "HTML", "text_exact_backend"),
    "wrong_extension/ifc_named_photo.jpg": ("cad_or_technical", "IFC", "cad_placeholder_backend"),
    "wrong_extension/json_named_audio.wav": ("structured_text", "JSON", "text_exact_backend"),
    "wrong_extension/kml_named_audio.mp3": ("geospatial", "KML", "geospatial_placeholder_backend"),
    "wrong_extension/mp4_named_plain_text.txt": ("video", "MP4", "media_analysis_backend"),
    "wrong_extension/npy_named_photo.jpg": ("scientific_data", "NumPy NPY", "scientific_placeholder_backend"),
    "wrong_extension/parquet_named_audio.wav": ("scientific_data", "Parquet", "scientific_placeholder_backend"),
    "wrong_extension/pdf_named_picture.png": ("document", "PDF", "document_placeholder_backend"),
    "wrong_extension/png_named_song.mp3": ("image", "PNG", "image_analysis_backend"),
    "wrong_extension/pptx_named_photo.jpg": ("presentation", "PPTX", "document_placeholder_backend"),
    "wrong_extension/sqlite_named_notes.md": ("database", "SQLite", "database_metadata_backend"),
    "wrong_extension/stl_named_text.txt": ("cad_or_technical", "STL", "cad_placeholder_backend"),
    "wrong_extension/text_named_photo.jpg": ("text", "TXT", "text_exact_backend"),
    "wrong_extension/wav_named_photo.jpg": ("audio", "WAV", "media_analysis_backend"),
    "wrong_extension/woff_named_text.txt": ("font", "WOFF", "font_placeholder_backend"),
    "wrong_extension/xlsx_named_audio.wav": ("spreadsheet", "XLSX", "document_placeholder_backend"),
    "wrong_extension/zip_named_scan.jpeg": ("archive", "ZIP", "archive_listing_backend"),
}

WRONG_EXTENSION_FILES = {path for path in EXPECTED if path.startswith("wrong_extension/")}
EXTENSION_ONLY_ALLOWED = {"disk/disk.iso"}


def test_all_in_one_corpus_covers_supported_families_and_content_detection(tmp_path: Path) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    shutil.copytree(FIXTURE, source)
    add_runtime_junk(source)

    manifest = run(source, target, options=corpus_options())

    relative_paths = {record["relative_path"] for record in manifest["entries"]}
    assert set(EXPECTED).issubset(relative_paths)
    assert manifest["summary"]["converted_text_file_count"] == len(EXPECTED)
    assert not manifest["summary"]["files_with_errors"]
    assert not any("__pycache__" in item for item in relative_paths)
    assert not any(".pytest_cache" in item for item in relative_paths)
    assert not any(item.startswith("build/") for item in relative_paths)
    assert "Thumbs.db" not in relative_paths

    for relative_path, (category, fmt, converter) in EXPECTED.items():
        record = entry(manifest, relative_path)
        classification = record["classification"]
        assert classification["rough_category"] == category, relative_path
        assert classification["concrete_format"] == fmt, relative_path
        assert record["converter_used"] == converter, relative_path

    for relative_path in WRONG_EXTENSION_FILES:
        classification = entry(manifest, relative_path)["classification"]
        assert classification["content_signature"]["source"] == "content", relative_path
        assert "layer2_content_signature_override" in classification["evidence"], relative_path

    for relative_path in EXPECTED:
        if relative_path in EXTENSION_ONLY_ALLOWED or relative_path == "unknown/random.random":
            continue
        classification = entry(manifest, relative_path)["classification"]
        assert classification["content_signature"]["source"] == "content", relative_path

    silence = (target / "media" / "silence.wav.txt").read_text(encoding="utf-8")
    assert "audio_silence" in silence
    misnamed_wav = (target / "wrong_extension" / "wav_named_photo.jpg.txt").read_text(encoding="utf-8")
    assert "audio_silence" in misnamed_wav
    video = (target / "wrong_extension" / "mp4_named_plain_text.txt.txt").read_text(encoding="utf-8")
    assert "Rough content:" in video
    assert "video_" in video
