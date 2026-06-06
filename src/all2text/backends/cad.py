from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from all2text.backends.binary import binary_summary_text
from all2text.models import Classification, ConversionContext, ConversionResult


class CadPlaceholderBackend:
    name = "cad_placeholder_backend"

    def can_handle(self, classification: Classification, entry_type: str) -> bool:
        return entry_type == "file" and classification.rough_category == "cad_or_technical"

    def convert(
        self,
        path: Path,
        rel_path: Path,
        classification: Classification,
        metadata: dict[str, object],
        ctx: ConversionContext,
    ) -> ConversionResult:
        schema, warnings, methods = cad_schema_probe(path, classification)
        limitation = (
            "CAD/technical conversion emits bounded schema/metadata only. It does not render, "
            "execute macros, or infer engineering meaning."
        )
        extra = [f"- limitation: {limitation}"]
        if schema:
            extra.extend(["- schema_probe:", json.dumps(schema, ensure_ascii=False, sort_keys=True)[:4000]])
        if classification.is_textual:
            extra.extend(["", "Source text:", safe_text_source(path)])
        return ConversionResult(
            text=binary_summary_text(
                path,
                classification,
                ctx,
                heading="CAD/technical safe summary",
                extra_lines=extra,
            ),
            converter_used=self.name,
            extraction_methods_used=["cad_placeholder_summary", *methods],
            warnings=warnings,
            metadata={"schema_probe": schema},
            limitations=[limitation],
        )


def cad_schema_probe(path: Path, classification: Classification) -> tuple[dict[str, Any], list[str], list[str]]:
    fmt = classification.concrete_format.upper()
    if fmt == "DXF":
        return dxf_schema(path)
    if fmt == "IFC":
        return ifc_schema(path)
    return {}, [], []


def dxf_schema(path: Path) -> tuple[dict[str, Any], list[str], list[str]]:
    try:
        import ezdxf
    except Exception as exc:
        return {}, [f"ezdxf_unavailable:{exc}"], []
    try:
        doc = ezdxf.readfile(path)
        modelspace = doc.modelspace()
        entity_counts: dict[str, int] = {}
        for entity in modelspace:
            kind = str(entity.dxftype())
            entity_counts[kind] = entity_counts.get(kind, 0) + 1
        layers = [
            {"name": str(layer.dxf.name), "color": int(layer.dxf.color), "linetype": str(layer.dxf.linetype)}
            for layer in list(doc.layers)[:200]
        ]
        schema = {
            "provider": "ezdxf",
            "format": "dxf",
            "version": str(doc.dxfversion),
            "layer_count": len(doc.layers),
            "layers": layers,
            "modelspace_entity_counts": dict(sorted(entity_counts.items())),
            "geometry_dumped": False,
        }
        return schema, [], ["ezdxf_schema_probe"]
    except Exception as exc:
        return {}, [f"ezdxf_schema_probe_failed:{exc}"], []


def ifc_schema(path: Path) -> tuple[dict[str, Any], list[str], list[str]]:
    try:
        import ifcopenshell
    except Exception as exc:
        return {}, [f"ifcopenshell_unavailable:{exc}"], []
    try:
        model = ifcopenshell.open(str(path))
        counts: dict[str, int] = {}
        for item in model:
            kind = str(item.is_a())
            counts[kind] = counts.get(kind, 0) + 1
        return {
            "provider": "ifcopenshell",
            "format": "ifc",
            "entity_counts": dict(sorted(counts.items())[:200]),
            "geometry_dumped": False,
        }, [], ["ifcopenshell_schema_probe"]
    except Exception as exc:
        return {}, [f"ifcopenshell_schema_probe_failed:{exc}"], []


def safe_text_source(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        return f"<source text unavailable: {exc}>"
