from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

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
        if classification.is_textual:
            extra.extend(["", "Source text:", safe_text_source(path)])
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
    if fmt == "GEOJSON" or path.suffix.casefold() == ".geojson":
        return geojson_schema(path)
    if fmt == "KML" or path.suffix.casefold() == ".kml":
        return kml_schema(path)
    if fmt == "SHAPEFILE" or path.suffix.casefold() == ".shp":
        return shapefile_schema(path)
    if fmt == "GEOPACKAGE" or path.suffix.casefold() == ".gpkg":
        return geopackage_schema(path)
    return {}, [], []


def geojson_schema(path: Path) -> tuple[dict[str, Any], list[str], list[str]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception as exc:
        return {}, [f"geojson_schema_probe_failed:{exc}"], []
    try:
        features = geojson_features(data)
        geometry_types: dict[str, int] = {}
        property_keys: set[str] = set()
        bounds = None
        for feature in features[:1000]:
            geometry = feature.get("geometry") if isinstance(feature, dict) else None
            geometry_type = str((geometry or {}).get("type") or "unknown") if isinstance(geometry, dict) else "unknown"
            geometry_types[geometry_type] = geometry_types.get(geometry_type, 0) + 1
            properties = feature.get("properties") if isinstance(feature, dict) else None
            if isinstance(properties, dict):
                property_keys.update(str(key) for key in properties.keys())
            bounds = merge_bounds(bounds, shapely_bounds(geometry))
        crs = geojson_crs(data)
        schema = {
            "provider": "stdlib_json_shapely_pyproj",
            "format": "geojson",
            "root_type": str(data.get("type")) if isinstance(data, dict) else type(data).__name__,
            "feature_count": len(features),
            "sampled_feature_count": min(len(features), 1000),
            "geometry_type_counts": dict(sorted(geometry_types.items())),
            "property_keys_sample": sorted(property_keys)[:200],
            "bbox": bounds,
            "crs": crs,
            "features_dumped": False,
        }
        return schema, [], ["geojson_schema_probe"]
    except Exception as exc:
        return {}, [f"geojson_schema_probe_failed:{exc}"], []


def kml_schema(path: Path) -> tuple[dict[str, Any], list[str], list[str]]:
    try:
        root = ET.fromstring(path.read_text(encoding="utf-8", errors="replace"))
    except Exception as exc:
        return {}, [f"kml_schema_probe_failed:{exc}"], []
    namespaces = {"kml": "http://www.opengis.net/kml/2.2"}
    placemarks = root.findall(".//kml:Placemark", namespaces) or root.findall(".//Placemark")
    geometry_tags = {}
    for tag in ("Point", "LineString", "Polygon", "MultiGeometry"):
        count = len(root.findall(f".//kml:{tag}", namespaces)) + len(root.findall(f".//{tag}"))
        if count:
            geometry_tags[tag] = count
    return {
        "provider": "stdlib_xml",
        "format": "kml",
        "root_tag": strip_xml_namespace(root.tag),
        "placemark_count": len(placemarks),
        "geometry_tag_counts": geometry_tags,
        "features_dumped": False,
    }, [], ["kml_schema_probe"]


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


def geojson_features(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, dict) and data.get("type") == "FeatureCollection":
        features = data.get("features")
        return [item for item in features if isinstance(item, dict)] if isinstance(features, list) else []
    if isinstance(data, dict) and data.get("type") == "Feature":
        return [data]
    if isinstance(data, dict) and data.get("type"):
        return [{"type": "Feature", "geometry": data, "properties": {}}]
    return []


def shapely_bounds(geometry: Any) -> list[float] | None:
    if not isinstance(geometry, dict):
        return None
    try:
        from shapely.geometry import shape

        geom = shape(geometry)
        if geom.is_empty:
            return None
        return [round(float(value), 8) for value in geom.bounds]
    except Exception:
        return None


def merge_bounds(current: list[float] | None, new: list[float] | None) -> list[float] | None:
    if not new:
        return current
    if not current:
        return list(new)
    return [
        min(current[0], new[0]),
        min(current[1], new[1]),
        max(current[2], new[2]),
        max(current[3], new[3]),
    ]


def geojson_crs(data: Any) -> dict[str, Any] | None:
    if not isinstance(data, dict) or not data.get("crs"):
        return None
    crs_value = data.get("crs")
    try:
        from pyproj import CRS

        parsed = CRS.from_user_input(crs_value)
        return {"input": crs_value, "authority": parsed.to_authority(), "name": parsed.name}
    except Exception as exc:
        return {"input": crs_value, "parse_error": str(exc)}


def strip_xml_namespace(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def safe_text_source(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        return f"<source text unavailable: {exc}>"
