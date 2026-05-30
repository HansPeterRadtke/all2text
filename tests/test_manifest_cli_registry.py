from __future__ import annotations

import json
from pathlib import Path

from all2text import run
from all2text.cli import main
from all2text.detection import classify_path
from all2text.metadata import collect_metadata
from all2text.registry import build_default_registry
from tests.conftest import PNG_1X1, entry, make_options


def test_manifest_and_report_are_written(tmp_path: Path) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    (source / "notes.md").write_text("# Title\n\nBody\n", encoding="utf-8")

    manifest = run(source, target, options=make_options())

    manifest_path = target / "_conversion_manifest.json"
    report_path = target / "_conversion_report.txt"
    assert manifest_path.exists()
    assert report_path.exists()
    loaded = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert loaded["schema"] == "all2text.conversion_manifest.v1"
    assert loaded["summary"]["converted_text_file_count"] == 1
    assert "Category counts:" in report_path.read_text(encoding="utf-8")
    record = entry(manifest, "notes.md")
    assert record["output_relative_path"] == "notes.md.txt"
    assert record["metadata"]["hashes"]["sha256"]


def test_cli_and_api_convert_tree(tmp_path: Path, capsys) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    (source / "cli.txt").write_text("from cli\n", encoding="utf-8")

    rc = main(["--no-file-command", "--no-copy-source-stat", str(source), str(target)])

    assert rc == 0
    assert (target / "cli.txt.txt").exists()
    printed = json.loads(capsys.readouterr().out)
    assert printed["converted_text_file_count"] == 1


def test_registry_contains_expected_backends_and_selects_image(tmp_path: Path) -> None:
    source = tmp_path / "image.png"
    source.write_bytes(PNG_1X1)
    metadata = collect_metadata(source, entry_type="file", link_target=None, options=make_options())
    classification = classify_path(source, metadata=metadata, entry_type="file", options=make_options())
    registry = build_default_registry()

    assert "text_exact_backend" in registry.names()
    assert "document_placeholder_backend" in registry.names()
    assert "scientific_placeholder_backend" in registry.names()
    assert registry.select(classification, "file").name == "image_placeholder_backend"
