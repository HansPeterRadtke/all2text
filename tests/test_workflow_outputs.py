from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from all2text import run
from all2text.backends.archive import ArchiveBackend
from all2text.backends.base import ConverterBackend
from all2text.backends.binary import BinaryFallbackBackend
from all2text.backends.filesystem import FilesystemBackend
from all2text.backends.text import TextBackend
from all2text.models import Classification, ConversionContext, ConversionResult
from all2text.registry import ConversionRegistry
from tests.conftest import PNG_1X1, entry, extracted_text, make_options


def test_scan_first_behavior_excludes_files_created_during_conversion(tmp_path: Path) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    (source / "first.txt").write_text("first\n", encoding="utf-8")

    class CreatingBackend:
        name = "creating_text_backend"

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
            (ctx.source_root / "created_during_conversion.txt").write_text("late\n", encoding="utf-8")
            return TextBackend().convert(path, rel_path, classification, metadata, ctx)

    registry = ConversionRegistry([FilesystemBackend(), CreatingBackend(), ArchiveBackend(), BinaryFallbackBackend()])
    manifest = run(source, target, options=make_options(), registry=registry)

    assert manifest["summary"]["scan_first"] is True
    assert manifest["summary"]["converted_text_file_count"] == 1
    assert (source / "created_during_conversion.txt").exists()
    assert not (target / "created_during_conversion.txt.txt").exists()


def test_run_mirrors_folders_and_preserves_text_exactly(tmp_path: Path) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    nested = source / "Folder With Spaces"
    nested.mkdir(parents=True)
    original = " first line\nsecond line\n\n"
    (nested / "notes.txt").write_text(original, encoding="utf-8")

    manifest = run(source, target, options=make_options())

    output = target / "Folder With Spaces" / "notes.txt.txt"
    assert output.exists()
    assert extracted_text(output) == original
    assert manifest["summary"]["converted_text_file_count"] == 1
    assert entry(manifest, "Folder With Spaces/notes.txt")["classification"]["rough_category"] == "text"


def test_structured_text_is_preserved_and_parse_metadata_is_recorded(tmp_path: Path) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    original = '{"alpha": 1, "beta": [2, 3]}\n'
    (source / "data.json").write_text(original, encoding="utf-8")

    manifest = run(source, target, options=make_options())

    assert extracted_text(target / "data.json.txt") == original
    record = entry(manifest, "data.json")
    assert record["classification"]["concrete_format"] == "JSON"
    parsed = record["metadata"]  # source metadata remains separate from converter metadata
    assert parsed["looks_text"] is True
    output = (target / "data.json.txt").read_text(encoding="utf-8")
    assert '"top_level_keys": [' in output
    assert '"alpha"' in output


def test_content_signature_overrides_misleading_extension(tmp_path: Path) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    (source / "actually_png.txt").write_bytes(PNG_1X1)

    manifest = run(source, target, options=make_options())

    record = entry(manifest, "actually_png.txt")
    classification = record["classification"]
    assert classification["rough_category"] == "image"
    assert classification["concrete_format"] == "PNG"
    assert "layer2_content_signature_override" in classification["evidence"]
    assert record["converter_used"] == "image_placeholder_backend"
    assert (target / "actually_png.txt.txt").exists()


def test_unknown_binary_still_gets_safe_text_output(tmp_path: Path) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    (source / "payload.unknownext").write_bytes(b"\x00\x01\x02\xffembedded-text\x00")

    manifest = run(source, target, options=make_options())

    text = (target / "payload.unknownext.txt").read_text(encoding="utf-8")
    assert "Binary summary:" in text
    assert "embedded-text" in text
    record = entry(manifest, "payload.unknownext")
    assert record["converter_used"] == "binary_fallback"


def test_archive_listing_is_safe_and_manifested(tmp_path: Path) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    with zipfile.ZipFile(source / "bundle.zip", "w") as archive:
        archive.writestr("folder/item.txt", "hello")
        archive.writestr("../unsafe.txt", "blocked")

    manifest = run(source, target, options=make_options())

    text = (target / "bundle.zip.txt").read_text(encoding="utf-8")
    assert "ZIP members:" in text
    assert "folder/item.txt" in text
    assert "parent_directory_reference" in text
    assert entry(manifest, "bundle.zip")["classification"]["rough_category"] == "archive"


def test_symlink_is_recorded_without_following(tmp_path: Path) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    (source / "real.txt").write_text("real\n", encoding="utf-8")
    try:
        (source / "link.txt").symlink_to(source / "real.txt")
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")

    manifest = run(source, target, options=make_options())

    record = entry(manifest, "link.txt")
    assert record["entry_type"] == "symlink"
    assert "symlink_not_followed" in record["warnings"]
    assert record["converter_used"] == "symlink_metadata_backend"
    symlink_output = extracted_text(target / "link.txt.txt")
    assert "policy: symlinks are recorded but not followed" in symlink_output
    assert "\nreal\n" not in symlink_output


def test_case_insensitive_output_collision_uses_deterministic_safe_name(tmp_path: Path) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    (source / "Name").write_text("upper", encoding="utf-8")
    try:
        (source / "name").write_text("lower", encoding="utf-8")
    except OSError:
        pytest.skip("filesystem is case-insensitive")

    manifest = run(source, target, options=make_options())

    assert manifest["summary"]["output_collision_count"] == 1
    output_names = sorted(path.name for path in target.iterdir() if path.is_file() and path.name.lower().startswith("name"))
    assert len(output_names) == 2
    assert any("collision-" in name for name in output_names)


def test_target_inside_source_is_rejected_by_default(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "a.txt").write_text("a", encoding="utf-8")

    with pytest.raises(ValueError, match="target_folder must not be inside source_folder"):
        run(source, source / "out", options=make_options())
