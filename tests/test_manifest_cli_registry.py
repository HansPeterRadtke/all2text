from __future__ import annotations

import json
from pathlib import Path

import pytest

from all2text import run
from all2text.cli import main
from all2text.config import config_from_dict, default_config, load_config
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
    assert "document_native_backend" in registry.names()
    assert "scientific_placeholder_backend" in registry.names()
    assert registry.select(classification, "file").name == "image_analysis_backend"


def test_config_parsing_defaults_and_custom_provider_params(tmp_path: Path) -> None:
    config_path = tmp_path / "all2text.toml"
    config_path.write_text(
        """
[run]
max_archive_members = 12
use_file_command = false

[modules]
image = "binary_fallback"

[providers.vlm]
name = "openai_compatible"
enabled = true
base_url = "http://127.0.0.1:14830/v1"
model = "vision-model.gguf"
temperature = 0.0
auto_invoke = false
""".strip()
        + "\n",
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.options.max_archive_members == 12
    assert config.options.use_file_command is False
    assert config.module_backend("image") == "binary_fallback"
    assert config.provider("vlm").enabled is True
    assert config.provider("vlm").get("temperature") == 0.0


def test_default_config_has_safe_document_and_spreadsheet_limits() -> None:
    config = default_config()

    assert config.module_params("document")["max_pdf_pages"] == 100
    assert config.module_params("document")["max_text_blocks"] == 5000
    assert config.module_params("spreadsheet")["max_cells_per_sheet"] == 20000
    assert config.module_params("audio")["max_ffprobe_json_chars"] == 20000
    assert config.module_params("video")["max_ffprobe_json_chars"] == 20000


def test_config_rejects_unknown_backend_name() -> None:
    with pytest.raises(ValueError, match="unknown backend for modules.image"):
        config_from_dict({"modules": {"image": "not_a_backend"}})


def test_config_rejects_unknown_provider_name() -> None:
    with pytest.raises(ValueError, match="unknown provider name for providers.vlm"):
        config_from_dict({"providers": {"vlm": {"name": "not_a_provider", "enabled": True}}})


def test_config_rejects_bad_numeric_provider_param() -> None:
    with pytest.raises(ValueError, match=r"providers.video_frames.max_frames must be >= 1"):
        config_from_dict(
            {"providers": {"video_frames": {"name": "ffmpeg", "enabled": True, "max_frames": 0}}}
        )


def test_config_rejects_bad_numeric_module_param() -> None:
    with pytest.raises(ValueError, match=r"modules.video.max_ffprobe_json_chars must be >= 0"):
        config_from_dict(
            {
                "modules": {
                    "video": {
                        "backend": "media_analysis_backend",
                        "max_ffprobe_json_chars": -1,
                    }
                }
            }
        )


def test_config_rejects_non_table_sections() -> None:
    with pytest.raises(ValueError, match="config root must be a table"):
        config_from_dict("not-a-table")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="modules must be a table"):
        config_from_dict({"modules": ""})
    with pytest.raises(ValueError, match="providers must be a table"):
        config_from_dict({"providers": ""})


def test_cli_rejects_bad_max_archive_members(tmp_path: Path, capsys) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()

    with pytest.raises(SystemExit) as exc:
        main(["--max-archive-members", "0", str(source), str(target)])

    assert exc.value.code == 2
    assert "--max-archive-members must be a positive integer" in capsys.readouterr().err


def test_configurable_registry_selection_can_route_image_to_fallback(tmp_path: Path) -> None:
    source = tmp_path / "image.png"
    source.write_bytes(PNG_1X1)
    options = make_options()
    metadata = collect_metadata(source, entry_type="file", link_target=None, options=options)
    classification = classify_path(source, metadata=metadata, entry_type="file", options=options)
    config = config_from_dict({"modules": {"image": "binary_fallback"}})
    registry = build_default_registry(config)

    assert registry.select(classification, "file").name == "binary_fallback"


def test_manifest_module_statuses_show_configured_but_not_run_routes(tmp_path: Path) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    (source / "notes.txt").write_text("plain text\n", encoding="utf-8")

    manifest = run(source, target, options=make_options())

    statuses = manifest["module_statuses"]
    assert statuses["text"]["status"] == "used"
    assert statuses["image"]["status"] == "configured_not_run_no_matching_entries"
    assert statuses["image"]["backend"] == "image_analysis_backend"
