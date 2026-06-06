from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from all2text.backends.binary import binary_summary_text
from all2text.models import Classification, ConversionContext, ConversionResult


class GeospatialPlaceholderBackend:
    name = "geospatial_placeholder_backend"

    def can_handle(self, classification: Classification, entry_type: str) -> bool:
        return entry_type == "file" and classification.rough_category == "geospatial"

    def convert(
        self,
        path: Path,
        rel_path: Path,
        classification: Classification,
        metadata: dict[str, object],
        ctx: ConversionContext,
    ) -> ConversionResult:
        schema, warnings, methods = geospatial_schema_probe(path, classification)
        limitation = (
            "Binary geospatial conversion emits bounded schema/metadata only. GeoJSON and KML text "
            "are preserved by the text backend; no coordinate transformation or raster dump is performed."
        )
        extra = [f"- limitation: {limitation}"]
        if schema:
            extra.extend(["- schema_probe:", json.dumps(schema, ensure_ascii=False, sort_keys=True)[:4000]])
        return ConversionResult(
            text=binary_summary_text(
                path,
                classification,
                ctx,
                heading="Geospatial safe summary",
                extra_lines=extra,
            ),
            converter_used=self.name,
            extraction_methods_used=["geospatial_placeholder_summary", *methods],
            warnings=warnings,
            metadata={"schema_probe": schema},
            limitations=[limitation],
        )


def geospatial_schema_probe(path: Path, classification: Classification) -> tuple[dict[str, Any], list[str], list[str]]:
    fmt = classification.concrete_format.upper()
    if fmt == "SHAPEFILE" or path.suffix.casefold() == ".shp":
        return shapefile_schema(path)
    if fmt == "GEOPACKAGE" or path.suffix.casefold() == ".gpkg":
        return geopackage_schema(path)
    return {}, [], []


def shapefile_schema(path: Path) -> tuple[dict[str, Any], list[str], list[str]]:
    try:
        import shapefile
    except Exception as exc:
        return {}, [f"pyshp_unavailable:{exc}"], []
    try:
        reader = shapefile.Reader(str(path))
        fields = [
            {"name": str(field[0]), "type": str(field[1]), "size": int(field[2]), "decimal": int(field[3])}
            for field in reader.fields[1:201]
        ]
        schema = {
            "provider": "pyshp",
            "format": "shapefile",
            "shape_type": str(reader.shapeTypeName),
            "record_count": len(reader),
            "fields": fields,
            "bbox": [float(value) for value in getattr(reader, "bbox", [])],
            "geometry_dumped": False,
        }
        return schema, [], ["pyshp_schema_probe"]
    except Exception as exc:
        return {}, [f"pyshp_schema_probe_failed:{exc}"], []


def geopackage_schema(path: Path) -> tuple[dict[str, Any], list[str], list[str]]:
    import sqlite3

    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            tables = [
                row[0]
                for row in con.execute(
                    "select name from sqlite_master where type in ('table','view') order by name limit 200"
                )
            ]
            gpkg_contents = []
            if "gpkg_contents" in tables:
                gpkg_contents = [
                    {
                        "table_name": row[0],
                        "data_type": row[1],
                        "identifier": row[2],
                        "srs_id": row[3],
                    }
                    for row in con.execute(
                        "select table_name, data_type, identifier, srs_id from gpkg_contents limit 200"
                    )
                ]
        finally:
            con.close()
        return {
            "provider": "sqlite3",
            "format": "geopackage",
            "tables": tables,
            "gpkg_contents": gpkg_contents,
            "feature_rows_dumped": False,
        }, [], ["geopackage_schema_probe"]
    except Exception as exc:
        return {}, [f"geopackage_schema_probe_failed:{exc}"], []
