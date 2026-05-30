# File Format Coverage

The core package is useful without heavy dependencies, but it is strict about not overstating what it
extracts.

## Native Core Extraction

| Category | Formats | Behavior |
| --- | --- | --- |
| Plain text | `.txt`, `.log`, extensionless printable files | Decodes and preserves text exactly in extracted content. |
| Structured text | Markdown, HTML, XML, JSON, JSONL, YAML/TOML/INI hints, CSV, TSV, RTF | Preserves original text and records lightweight parse metadata where safe. |
| Source code | Common source/script extensions | Preserves exact source text. |
| Notebook | `.ipynb` | Preserves JSON text and records notebook cell count when parseable. |
| Geospatial text | GeoJSON, KML | Preserves source text and classifies geospatial signatures. |
| Text CAD | DXF/STEP/STL/OBJ/IGES when printable | Preserves text instead of pretending geometry analysis. |
| Archives/compressed streams | ZIP, TAR, TAR.GZ/TAR.BZ2/TAR.XZ, GZIP, BZIP2, XZ | Lists members or stream metadata safely; no extraction. |
| EPUB | `.epub` | Lists package members and container XML preview; no chapter extraction claim. |
| Email | `.eml`, `.mbox` text messages | Parses headers/plain text body, lists attachment metadata, and preserves original message source. |
| SQLite | `.sqlite`, `.sqlite3`, `.db` with SQLite header | Opens read-only and lists schema objects when possible. |

## Safe Placeholder Coverage

| Category | Examples | Core behavior |
| --- | --- | --- |
| Image | PNG, JPEG, GIF, TIFF, BMP, WebP, HEIC, SVG | Records byte signature and light dimensions where possible. SVG text is preserved as markup. No OCR/VLM claim. |
| Audio | WAV, MP3, FLAC, OGG, AAC, MIDI | Records media metadata and optional `ffprobe` output. No transcription. |
| Video | MP4, MOV, MKV, AVI, WebM | Records media metadata and optional `ffprobe` output. No frame/text/scene extraction. |
| Documents | PDF, DOC, DOCX, ODT | Safe summary and light PDF markers. Optional deep parsers are future backends. |
| Spreadsheets | XLS, XLSX, ODS | Safe summary. No formula/table extraction in core. |
| Presentations | PPT, PPTX, ODP | Safe summary. No slide extraction in core. |
| Scientific data | HDF5, NetCDF, Parquet, FITS, MAT, NPY/NPZ | Safe byte/string summary. No dataset traversal in core. |
| Binary geospatial | Shapefile, GeoPackage, raster/sidecar geospatial formats | Safe byte/string summary. No GDAL/Fiona/Rasterio inspection in core. |
| Binary CAD | DWG and other non-text CAD | Safe summary. No geometry/layer extraction. |
| Fonts | TTF, OTF, WOFF, WOFF2 | Safe summary. No glyph tables. |
| Executables | ELF, PE/MZ, Mach-O, shared libraries | Safe summary. No execution, disassembly, or decompilation. |
| Containers | ISO, DMG, VHD, QCOW2 | Safe summary. No mounting or filesystem traversal. |
| Unknown binary | Any unmapped binary | Header and printable string samples. |

## Extension/Content Mismatches

Content signatures override misleading extensions when strong. A PNG named `actually_png.txt` is
classified as image/PNG, not text, and still receives `actually_png.txt.txt` as its output path.

Generic printable text is not allowed to erase more specific extension or name evidence. For
example, a small Markdown or YAML file that only looks like generic text is still classified as its
structured format, while a strong binary magic signature still wins over a misleading extension.

## Placeholder Truthfulness

Placeholder outputs are intentionally explicit. Images state that OCR, VLM, chart, and document
analysis were not run unless a configured backend actually does that work. Audio/video outputs state
that transcription and frame/scene analysis were not performed by core. Advanced document,
spreadsheet, presentation, ebook, database, geospatial, CAD, scientific, font, executable, and disk
image formats all produce useful metadata without claiming semantic extraction.
