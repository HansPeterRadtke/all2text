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


def test_config_normalizes_numeric_and_boolean_values_for_runtime(tmp_path: Path) -> None:
    config = config_from_dict(
        {
            "run": {
                "max_header_bytes": "8.0",
                "max_hash_bytes": 1024.0,
                "max_binary_sample_bytes": "16",
                "max_archive_members": "2",
                "use_file_command": "false",
                "copy_source_stat": "0",
                "reject_target_inside_source": "yes",
            },
            "modules": {
                "spreadsheet": {
                    "backend": "document_native_backend",
                    "include_hidden_sheets": "false",
                    "max_cells_per_sheet": "3.0",
                },
                "video": {
                    "backend": "media_analysis_backend",
                    "max_ffprobe_json_chars": "80.0",
                },
            },
            "providers": {
                "ocr": {
                    "name": "none",
                    "enabled": "false",
                    "min_alnum_ratio": "0.5",
                    "min_confidence": "35.0",
                    "auto_invoke": "off",
                },
                "video_frames": {
                    "name": "ffmpeg",
                    "enabled": "true",
                    "sample_frames": "yes",
                    "max_frames": "3.0",
                    "interval_seconds": "2.5",
                    "auto_invoke": "false",
                    "ocr": "0",
                    "vlm": "1",
                },
            },
        }
    )

    assert config.options.max_header_bytes == 8
    assert type(config.options.max_header_bytes) is int
    assert config.options.use_file_command is False
    assert config.options.copy_source_stat is False
    assert config.options.reject_target_inside_source is True
    assert config.module_params("spreadsheet")["include_hidden_sheets"] is False
    assert config.module_params("spreadsheet")["max_cells_per_sheet"] == 3
    assert config.module_params("video")["max_ffprobe_json_chars"] == 80
    assert config.provider("video_frames").enabled is True
    assert config.provider("video_frames").get("sample_frames") is True
    assert config.provider("video_frames").get("max_frames") == 3
    assert config.provider("video_frames").get("interval_seconds") == 2.5
    assert config.provider("video_frames").get("auto_invoke") is False
    assert config.provider("video_frames").get("ocr") is False
    assert config.provider("video_frames").get("vlm") is True
    assert config.provider("ocr").get("min_alnum_ratio") == 0.5
    assert config.provider("ocr").get("min_confidence") == 35.0

    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    (source / "payload.bin").write_bytes(b"0123456789abcdef")

    manifest = run(source, target, config=config)

    assert manifest["options"]["max_header_bytes"] == 8
    assert manifest["options"]["use_file_command"] is False
    assert entry(manifest, "payload.bin")["metadata"]["magic_header"]["bytes_read"] == 8


def test_config_rejects_bad_boolean_values() -> None:
    with pytest.raises(ValueError, match="run.use_file_command must be a boolean"):
        config_from_dict({"run": {"use_file_command": "sometimes"}})
    with pytest.raises(ValueError, match="providers.vlm.enabled must be a boolean"):
        config_from_dict({"providers": {"vlm": {"enabled": "sometimes"}}})
    with pytest.raises(ValueError, match="providers.vlm.auto_invoke must be a boolean"):
        config_from_dict({"providers": {"vlm": {"auto_invoke": "sometimes"}}})
    with pytest.raises(ValueError, match="modules.spreadsheet.include_hidden_sheets must be a boolean"):
        config_from_dict(
            {
                "modules": {
                    "spreadsheet": {
                        "backend": "document_native_backend",
                        "include_hidden_sheets": "sometimes",
                    }
                }
            }
        )


def test_config_rejects_fractional_integer_fields() -> None:
    with pytest.raises(ValueError, match="run.max_header_bytes must be an integer"):
        config_from_dict({"run": {"max_header_bytes": 4.5}})
    with pytest.raises(ValueError, match="providers.video_frames.max_frames must be an integer"):
        config_from_dict(
            {
                "providers": {
                    "video_frames": {
                        "name": "ffmpeg",
                        "enabled": True,
                        "max_frames": "2.5",
                    }
                }
            }
        )


def test_config_rejects_non_table_sections() -> None:
    with pytest.raises(ValueError, match="config root must be a table"):
        config_from_dict("not-a-table")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="run must be a table"):
        config_from_dict({"run": ""})
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


def test_python_module_invocation_displays_version() -> None:
    import os
    import subprocess
    import sys

    env = dict(os.environ)
    env["PYTHONPATH"] = "src"
    completed = subprocess.run(
        [sys.executable, "-m", "all2text", "--version"],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )

    assert completed.returncode == 0
    assert completed.stdout.strip()


def test_python_module_invocation_can_print_capabilities() -> None:
    import os
    import subprocess
    import sys

    env = dict(os.environ)
    env["PYTHONPATH"] = "src"
    completed = subprocess.run(
        [sys.executable, "-m", "all2text", "--capabilities"],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )

    assert completed.returncode == 0
    assert '"profile"' in completed.stdout
    assert '"provider_statuses"' in completed.stdout


def test_normal_dependencies_markitdown_marker() -> None:
    from pathlib import Path

    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")
    assert "markitdown>=0.1; python_version >= '3.10'" in pyproject
    assert "  \"markitdown>=0.1\",\n" not in pyproject


def test_normal_dependencies_scientific_markers_cover_python38() -> None:
    from pathlib import Path

    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")
    assert "astropy>=5.2,<6; python_version < '3.9'" in pyproject
    assert "astropy>=6; python_version >= '3.9'" in pyproject


def test_normal_dependencies_cad_markers_cover_python38() -> None:
    from pathlib import Path

    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")
    assert "ezdxf>=1.1,<1.2; python_version < '3.9'" in pyproject
    assert "ezdxf>=1.3; python_version >= '3.9'" in pyproject


def test_normal_dependencies_lxml_marker_avoids_python38_source_builds() -> None:
    from pathlib import Path

    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")
    assert "lxml>=4.9,<6; python_version < '3.9'" in pyproject


def test_normal_dependencies_exclude_source_build_heavy_packages_on_python38() -> None:
    from pathlib import Path

    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")
    assert "h5py>=3.10; python_version >= '3.9'" in pyproject
    assert "py7zr>=0.21; python_version >= '3.9'" in pyproject


def test_cli_doctor_and_install_tools_commands(capsys) -> None:
    from all2text.cli import main

    assert main(["doctor"]) == 0
    doctor_out = capsys.readouterr().out
    assert '"profile"' in doctor_out
    assert '"provider_statuses"' in doctor_out

    assert main(["install-tools"]) == 0
    tools_out = capsys.readouterr().out
    assert "External tools are not installed by pip" in tools_out
