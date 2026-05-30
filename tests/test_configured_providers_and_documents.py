from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from all2text import run
from all2text.cli import main
from all2text.config import config_from_dict
from tests.conftest import PNG_1X1, entry, make_options


def test_cli_uses_configured_backend_selection(tmp_path: Path, capsys) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    config_path = tmp_path / "all2text.toml"
    source.mkdir()
    (source / "image.png").write_bytes(PNG_1X1)
    config_path.write_text("[modules]\nimage = \"binary_fallback\"\n", encoding="utf-8")

    rc = main(["--config", str(config_path), "--no-file-command", "--no-copy-source-stat", str(source), str(target)])

    assert rc == 0
    assert entry_json(target, "image.png")["converter_used"] == "binary_fallback"
    assert "converted_text_file_count" in capsys.readouterr().out


def test_image_provider_configuration_records_vlm_without_requiring_server(tmp_path: Path) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    (source / "chart_like.png").write_bytes(PNG_1X1)
    config = config_from_dict(
        {
            "providers": {
                "vlm": {
                    "name": "openai_compatible",
                    "enabled": True,
                    "base_url": "http://127.0.0.1:14830/v1",
                    "model": "local-vlm",
                    "auto_invoke": False,
                    "custom_prompt_tag": "unit-test",
                }
            }
        }
    )

    manifest = run(source, target, options=make_options(), config=config)

    record = entry(manifest, "chart_like.png")
    assert record["converter_used"] == "image_analysis_backend"
    assert record["vlm_used"] is False
    assert record["converter_metadata"]["provider_statuses"]
    assert record["converter_metadata"]["vlm"]["model"] == "local-vlm"
    assert "vlm_call_skipped_auto_invoke_false" in record["warnings"]


def test_docx_native_extraction_when_dependency_available(tmp_path: Path) -> None:
    docx = pytest.importorskip("docx")
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    document = docx.Document()
    document.add_heading("Quarterly Report", level=1)
    document.add_paragraph("Revenue grew.")
    table = document.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "Metric"
    table.cell(0, 1).text = "Value"
    table.cell(1, 0).text = "Revenue"
    table.cell(1, 1).text = "42"
    document.save(source / "report.docx")

    manifest = run(source, target, options=make_options())

    record = entry(manifest, "report.docx")
    text = (target / "report.docx.txt").read_text(encoding="utf-8")
    assert record["converter_used"] == "docx_native_backend"
    assert "Quarterly Report" in text
    assert "table_1 row 2: Revenue | 42" in text
    assert record["converter_metadata"]["raw_wordprocessingml_paragraph_count"] >= 2


def test_xlsx_native_extraction_preserves_sheets_formulas_and_values(tmp_path: Path) -> None:
    openpyxl = pytest.importorskip("openpyxl")
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    workbook = openpyxl.Workbook()
    main = workbook.active
    main.title = "Main"
    main["A1"] = 10
    main["A2"] = 32
    main["B1"] = "=SUM(A1:A2)"
    hidden = workbook.create_sheet("HiddenInputs")
    hidden.sheet_state = "hidden"
    hidden["A1"] = 7
    main["B2"] = "=SUM(HiddenInputs!A1:A1)"
    workbook.save(source / "metrics.xlsx")

    manifest = run(source, target, options=make_options())

    record = entry(manifest, "metrics.xlsx")
    text = (target / "metrics.xlsx.txt").read_text(encoding="utf-8")
    assert record["converter_used"] == "xlsx_native_backend"
    assert "Worksheet 1: Main" in text
    assert "Worksheet 2: HiddenInputs" in text
    assert "- visibility: hidden" in text
    assert "coordinate=B1" in text and "formula='=SUM(A1:A2)'" in text
    assert "cross_sheet_formula_references: HiddenInputs!A1:A1" in text
    assert record["converter_metadata"]["formula_count"] == 2


def test_pptx_native_extraction_when_dependency_available(tmp_path: Path) -> None:
    pptx = pytest.importorskip("pptx")
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    presentation = pptx.Presentation()
    slide = presentation.slides.add_slide(presentation.slide_layouts[5])
    slide.shapes.title.text = "Slide Title"
    textbox = slide.shapes.add_textbox(100, 100, 400, 100)
    textbox.text_frame.text = "Body text"
    presentation.save(source / "deck.pptx")

    manifest = run(source, target, options=make_options())

    record = entry(manifest, "deck.pptx")
    text = (target / "deck.pptx.txt").read_text(encoding="utf-8")
    assert record["converter_used"] == "pptx_native_backend"
    assert "Slide 1:" in text
    assert "Slide Title" in text
    assert "Body text" in text


def test_pdf_native_text_extraction_when_dependency_available(tmp_path: Path) -> None:
    pytest.importorskip("pypdf")
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    (source / "simple.pdf").write_bytes(minimal_pdf_bytes("Hello PDF"))

    manifest = run(source, target, options=make_options())

    record = entry(manifest, "simple.pdf")
    text = (target / "simple.pdf.txt").read_text(encoding="utf-8")
    assert record["converter_used"] == "pdf_native_backend"
    assert "Hello PDF" in text
    assert record["converter_metadata"]["native_text_characters"] > 0


def test_legacy_xls_truthful_fallback_when_xlrd_absent(tmp_path: Path) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    (source / "legacy.xls").write_bytes(b"\xd0\xcf\x11\xe0legacy-xls-placeholder")

    manifest = run(source, target, options=make_options())

    record = entry(manifest, "legacy.xls")
    if importlib.util.find_spec("xlrd") is None:
        assert record["converter_used"] == "document_placeholder_backend"
        assert any("xlrd unavailable" in warning for warning in record["warnings"])
    else:
        assert record["converter_used"] in {"xls_native_backend", "document_placeholder_backend"}


def entry_json(target: Path, relative_path: str) -> dict[str, object]:
    import json

    manifest = json.loads((target / "_conversion_manifest.json").read_text(encoding="utf-8"))
    return entry(manifest, relative_path)


def minimal_pdf_bytes(text: str) -> bytes:
    safe = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    content = f"BT /F1 24 Tf 100 700 Td ({safe}) Tj ET".encode("ascii")
    objects = [
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n",
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>\nendobj\n",
        b"4 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n",
        b"5 0 obj\n<< /Length "
        + str(len(content)).encode("ascii")
        + b" >>\nstream\n"
        + content
        + b"\nendstream\nendobj\n",
    ]
    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for item in objects:
        offsets.append(len(output))
        output.extend(item)
    xref = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    output.extend(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode("ascii"))
    return bytes(output)
