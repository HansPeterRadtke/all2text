from __future__ import annotations

import sqlite3
import zipfile
from pathlib import Path

import pytest

from all2text import run
from tests.conftest import PNG_1X1, entry, make_options


def _write_epub(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", "application/epub+zip")
        archive.writestr(
            "META-INF/container.xml",
            "<?xml version='1.0'?><container><rootfiles><rootfile full-path='OPS/package.opf'/></rootfiles></container>",
        )
        archive.writestr("OPS/package.opf", "<package/>")


def _write_sqlite(path: Path) -> None:
    con = sqlite3.connect(path)
    try:
        con.execute("create table item(id integer primary key, name text)")
        con.commit()
    finally:
        con.close()


@pytest.mark.parametrize(
    ("filename", "payload", "expected_category", "expected_converter", "expected_text"),
    [
        ("image.png", PNG_1X1, "image", "image_placeholder_backend", "Image safe summary"),
        (
            "audio.wav",
            b"RIFF$\x00\x00\x00WAVEfmt " + b"\x10\x00\x00\x00\x01\x00\x01\x00" + b"\x40\x1f\x00\x00",
            "audio",
            "media_metadata_backend",
            "Media safe summary",
        ),
        ("video.mp4", b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42", "video", "media_metadata_backend", "Media safe summary"),
        ("doc.pdf", b"%PDF-1.4\n1 0 obj\n<< /Type /Page >>\n%%EOF\n", "document", "document_placeholder_backend", "Document safe summary"),
        ("data.h5", b"\x89HDF\r\n\x1a\n" + b"\x00" * 32, "scientific_data", "scientific_placeholder_backend", "Scientific data safe summary"),
        ("drawing.dwg", b"\x00DWG-binary-placeholder\x00", "cad_or_technical", "cad_placeholder_backend", "CAD/technical safe summary"),
        ("font.ttf", b"\x00\x01\x00\x00fontdata", "font", "font_placeholder_backend", "Font safe summary"),
        ("program", b"\x7fELF" + b"\x00" * 40, "executable_or_binary", "executable_placeholder_backend", "Executable/binary safe summary"),
        ("disk.iso", b"CD001" + b"\x00" * 40, "disk_image_or_container", "container_placeholder_backend", "Container safe summary"),
    ],
)
def test_placeholder_categories_are_classified_and_written(
    tmp_path: Path,
    filename: str,
    payload: bytes,
    expected_category: str,
    expected_converter: str,
    expected_text: str,
) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    (source / filename).write_bytes(payload)

    manifest = run(source, target, options=make_options())

    record = entry(manifest, filename)
    assert record["classification"]["rough_category"] == expected_category
    assert record["converter_used"] == expected_converter
    output = (target / f"{filename}.txt").read_text(encoding="utf-8")
    assert expected_text in output
    assert "limitation" in output.lower()


def test_database_placeholder_lists_sqlite_schema(tmp_path: Path) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    _write_sqlite(source / "sample.sqlite")

    manifest = run(source, target, options=make_options())

    record = entry(manifest, "sample.sqlite")
    assert record["classification"]["rough_category"] == "database"
    assert record["converter_used"] == "database_metadata_backend"
    output = (target / "sample.sqlite.txt").read_text(encoding="utf-8")
    assert "item" in output
    assert "Table data is not dumped" in output


def test_email_backend_extracts_headers_body_and_attachment_metadata(tmp_path: Path) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    (source / "message.eml").write_text(
        "From: a@example.test\nTo: b@example.test\nSubject: Demo\nDate: Sat, 30 May 2026 10:00:00 +0000\n\nHello body\n",
        encoding="utf-8",
    )

    manifest = run(source, target, options=make_options())

    record = entry(manifest, "message.eml")
    assert record["classification"]["rough_category"] == "email"
    assert record["converter_used"] == "email_metadata_backend"
    output = (target / "message.eml.txt").read_text(encoding="utf-8")
    assert "Subject: Demo" in output
    assert "Hello body" in output


def test_ebook_placeholder_lists_epub_container(tmp_path: Path) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    _write_epub(source / "book.epub")

    manifest = run(source, target, options=make_options())

    record = entry(manifest, "book.epub")
    assert record["classification"]["rough_category"] == "ebook"
    assert record["converter_used"] == "ebook_placeholder_backend"
    output = (target / "book.epub.txt").read_text(encoding="utf-8")
    assert "EPUB metadata:" in output
    assert "META-INF/container.xml" in output
