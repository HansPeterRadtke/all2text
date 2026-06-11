from __future__ import annotations

from pathlib import Path

import pytest

from all2text.detection import classify_path
from all2text.models import RunOptions
from tests.conftest import PNG_1X1


@pytest.mark.parametrize(
    ("filename", "payload", "mime_type", "expected_format"),
    [
        ("drawing.dwg", b"\x00DWG-binary-placeholder\x00", "image/png", "DWG"),
        ("drawing.dxf", b"0\nSECTION\n2\nENTITIES\n0\nENDSEC\n0\nEOF\n", "image/png", "DXF"),
        ("model.stl", b"solid bracket\nendsolid bracket\n", "image/png", "STL"),
        (
            "observation.fits",
            b"not-a-real-fits-header-but-extension-is-known\n",
            "image/png",
            "FITS",
        ),
    ],
)
def test_specialist_extensions_are_not_overridden_by_misleading_image_mime(
    tmp_path: Path,
    filename: str,
    payload: bytes,
    mime_type: str,
    expected_format: str,
) -> None:
    path = tmp_path / filename
    path.write_bytes(payload)

    classification = classify_path(
        path,
        metadata={"file_mime_type": mime_type, "python_mimetype": mime_type, "looks_text": False},
        options=RunOptions(use_file_command=False),
    )

    assert classification.rough_category in {"cad_or_technical", "scientific_data"}
    assert classification.concrete_format == expected_format
    if "layer2_content_signature_override" in classification.evidence:
        assert classification.content_signature.concrete_format == expected_format
    else:
        assert "layer2_mime_conflict_ignored_for_specialist_extension" in classification.evidence
        assert any(
            "mime_conflicts_with_specialist_extension" in warning
            for warning in classification.warnings
        )


@pytest.mark.parametrize(
    ("filename", "mime_type", "expected_format"),
    [
        ("drawing.dwg", "image/vnd.dwg", "DWG"),
        ("drawing.dxf", "image/vnd.dxf", "DXF"),
        ("drawing.dwg", "application/x-dwg", "DWG"),
        ("drawing.dxf", "application/x-dxf", "DXF"),
    ],
)
def test_cad_vendor_mimes_classify_as_cad_not_generic_image(
    tmp_path: Path,
    filename: str,
    mime_type: str,
    expected_format: str,
) -> None:
    path = tmp_path / filename
    path.write_bytes(b"\x00cad-placeholder\x00")

    classification = classify_path(
        path,
        metadata={"file_mime_type": mime_type, "looks_text": False},
        options=RunOptions(use_file_command=False),
    )

    assert classification.rough_category == "cad_or_technical"
    assert classification.concrete_format == expected_format


def test_actual_image_magic_still_overrides_specialist_extension(tmp_path: Path) -> None:
    path = tmp_path / "misnamed.dwg"
    path.write_bytes(PNG_1X1)

    classification = classify_path(
        path,
        metadata={"file_mime_type": "image/png", "looks_text": False},
        options=RunOptions(use_file_command=False),
    )

    assert classification.rough_category == "image"
    assert classification.concrete_format == "PNG"
    assert "layer2_content_signature_override" in classification.evidence


def test_mime_still_classifies_unmapped_extension_without_content_signature(tmp_path: Path) -> None:
    path = tmp_path / "image.payload"
    path.write_bytes(b"not an image header")

    classification = classify_path(
        path,
        metadata={"file_mime_type": "image/png", "looks_text": False},
        options=RunOptions(use_file_command=False),
    )

    assert classification.rough_category == "image"
    assert classification.concrete_format == "PNG"


def test_ifc_extension_routes_to_cad_backend(tmp_path: Path) -> None:
    from all2text.detection import classify_path
    from all2text.metadata import collect_metadata
    from tests.conftest import make_options

    path = tmp_path / "model.ifc"
    path.write_text("ISO-10303-21;\nDATA;\n#1=IFCPROJECT('x',$,'Project',$,$,$,$,$,$);\nENDSEC;\nEND-ISO-10303-21;\n", encoding="utf-8")
    options = make_options()
    metadata = collect_metadata(path, entry_type="file", link_target=None, options=options)
    classification = classify_path(path, metadata=metadata, entry_type="file", options=options)

    assert classification.rough_category == "cad_or_technical"
    assert classification.concrete_format == "IFC"
    assert classification.is_textual is True
