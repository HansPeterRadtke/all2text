from __future__ import annotations

import bz2
import json
import lzma
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pytest

from all2text import run
from all2text.backends.binary import BinaryFallbackBackend
from all2text.backends.filesystem import FilesystemBackend
from all2text.models import Classification, ConversionContext, ConversionResult
from all2text.registry import ConversionRegistry
from tests.conftest import entry, extracted_text, make_options


def conversion_block(path: Path) -> dict[str, object]:
    text = path.read_text(encoding="utf-8")
    raw = text.split("=== Conversion ===\n", 1)[1].split("\n\n=== Extracted Content ===\n", 1)[0]
    return json.loads(raw)


@pytest.mark.parametrize(
    ("filename", "original", "expected_format", "metadata_snippet"),
    [
        ("notes.md", "# Title\n\nBody\n", "Markdown", '"heading_count": 1'),
        ("data.jsonl", "{\"a\": 1}\n{\"b\": 2}\n", "JSON Lines", '"parsed_lines": 2'),
        ("config.yaml", "alpha: 1\nitems:\n  - one\n", "YAML", "top_level_key_candidates"),
        ("page.html", "<html><head><title>Demo</title></head><body>Hello</body></html>\n", "HTML", '"title": "Demo"'),
        ("doc.xml", "<?xml version='1.0'?><root><child /></root>\n", "XML", '"root_tag": "root"'),
        ("note.rtf", "{\\rtf1\\ansi Hello RTF}\n", "RTF", "control_word_count"),
    ],
)
def test_structured_text_formats_preserve_original_and_record_parse_metadata(
    tmp_path: Path,
    filename: str,
    original: str,
    expected_format: str,
    metadata_snippet: str,
) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    (source / filename).write_text(original, encoding="utf-8")

    manifest = run(source, target, options=make_options())

    output = target / f"{filename}.txt"
    record = entry(manifest, filename)
    assert record["classification"]["concrete_format"] == expected_format
    assert extracted_text(output) == original
    assert metadata_snippet in output.read_text(encoding="utf-8")


def test_eml_preserves_original_source_after_parsed_metadata(tmp_path: Path) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    original = (
        "From: a@example.test\n"
        "To: b@example.test\n"
        "Subject: Preserve raw\n"
        "Date: Sat, 30 May 2026 10:00:00 +0000\n"
        "X-Custom: keep-me\n"
        "\n"
        "Hello body\n"
    )
    (source / "message.eml").write_text(original, encoding="utf-8")

    manifest = run(source, target, options=make_options())

    record = entry(manifest, "message.eml")
    assert record["converter_used"] == "email_metadata_backend"
    text = extracted_text(target / "message.eml.txt")
    assert "Subject: Preserve raw" in text
    assert text.split("Original message source:\n", 1)[1] == original


def test_name_hint_classifies_extensionless_source_file(tmp_path: Path) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    original = "build:\n\tcc main.c\n"
    (source / "Makefile").write_text(original, encoding="utf-8")

    manifest = run(source, target, options=make_options())

    record = entry(manifest, "Makefile")
    assert record["classification"]["rough_category"] == "source_code"
    assert record["classification"]["concrete_format"] == "Makefile"
    assert "layer1_name_hint" in record["classification"]["evidence"]
    assert extracted_text(target / "Makefile.txt") == original


def test_geospatial_text_is_preserved_and_binary_geospatial_is_placeholder(tmp_path: Path) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    geojson = '{"type": "FeatureCollection", "features": []}\n'
    (source / "map.geojson").write_text(geojson, encoding="utf-8")
    (source / "shape.shp").write_bytes(b"\x00\x00'\n" + b"\x00" * 120)

    manifest = run(source, target, options=make_options())

    geo = entry(manifest, "map.geojson")
    shp = entry(manifest, "shape.shp")
    assert geo["classification"]["concrete_format"] == "GeoJSON"
    assert geo["converter_used"] == "geospatial_placeholder_backend"
    assert geo["converter_metadata"]["schema_probe"]["format"] == "geojson"
    assert "Source text:\n" + geojson in extracted_text(target / "map.geojson.txt")
    assert shp["classification"]["rough_category"] == "geospatial"
    assert shp["converter_used"] == "geospatial_placeholder_backend"
    assert "Geospatial safe summary" in (target / "shape.shp.txt").read_text(encoding="utf-8")


def test_compressed_streams_are_summarized_without_unsafe_extraction(tmp_path: Path) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    (source / "payload.bz2").write_bytes(bz2.compress(b"compressed bzip2 text"))
    (source / "payload.xz").write_bytes(lzma.compress(b"compressed xz text"))

    manifest = run(source, target, options=make_options())

    assert entry(manifest, "payload.bz2")["converter_used"] == "archive_listing_backend"
    assert "BZIP2 stream:" in (target / "payload.bz2.txt").read_text(encoding="utf-8")
    assert entry(manifest, "payload.xz")["converter_used"] == "archive_listing_backend"
    assert "XZ stream:" in (target / "payload.xz.txt").read_text(encoding="utf-8")


@dataclass
class UnsafeMetadata:
    path: Path
    when: datetime


def test_manifest_json_serialization_and_output_reservation_are_safe(tmp_path: Path) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    (source / "unsafe.txt").write_text("unsafe\n", encoding="utf-8")

    class ReservationBackend:
        name = "reservation_backend"

        def can_handle(self, classification: Classification, entry_type: str) -> bool:
            return entry_type == "file" and classification.is_textual

        def convert(
            self,
            path: Path,
            rel_path: Path,
            classification: Classification,
            metadata: dict[str, object],
            ctx: ConversionContext,
        ) -> ConversionResult:
            assert (ctx.target_root / f"{rel_path.name}.txt").exists()
            return ConversionResult(
                text="reserved\n",
                converter_used=self.name,
                extraction_methods_used=["reservation_probe"],
                metadata={
                    "path": path,
                    "bytes": b"abc",
                    "set": {"b", "a"},
                    "exception": ValueError("bad metadata"),
                    "dataclass": UnsafeMetadata(path=path, when=datetime(2026, 5, 30, tzinfo=timezone.utc)),
                },
            )

    registry = ConversionRegistry([FilesystemBackend(), ReservationBackend(), BinaryFallbackBackend()])
    manifest = run(source, target, options=make_options(), registry=registry)

    record = entry(manifest, "unsafe.txt")
    assert record["converter_metadata"]["path"].endswith("unsafe.txt")
    assert record["converter_metadata"]["bytes"]["type"] == "bytes"
    assert record["converter_metadata"]["set"] == ["a", "b"]
    assert record["converter_metadata"]["exception"]["type"] == "ValueError"
    loaded = json.loads((target / "_conversion_manifest.json").read_text(encoding="utf-8"))
    assert entry(loaded, "unsafe.txt")["converter_metadata"]["dataclass"]["when"] == "2026-05-30T00:00:00+00:00"


def test_metadata_includes_acl_and_os_fields(tmp_path: Path) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    (source / "meta.txt").write_text("meta\n", encoding="utf-8")

    manifest = run(source, target, options=make_options())

    metadata = entry(manifest, "meta.txt")["metadata"]
    assert "acl_summary" in metadata
    assert "os" in metadata
    assert "platform_system" in metadata["os"]
