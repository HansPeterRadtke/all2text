from __future__ import annotations

from pathlib import Path

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
        limitation = (
            "Binary geospatial conversion is safe-summary only in the core package. GeoJSON and KML "
            "text are preserved by the text backend; Shapefile, GeoPackage, raster, projection, and "
            "coordinate-system inspection require optional geospatial libraries such as GDAL/Fiona/Rasterio."
        )
        return ConversionResult(
            text=binary_summary_text(
                path,
                classification,
                ctx,
                heading="Geospatial safe summary",
                extra_lines=[f"- limitation: {limitation}"],
            ),
            converter_used=self.name,
            extraction_methods_used=["geospatial_placeholder_summary"],
            limitations=[limitation],
        )
