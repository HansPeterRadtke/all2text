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
| DOCX | `.docx` with `python-docx` | Extracts core properties, paragraph/table order, raw XML paragraph counts, sections, headers/footers, hyperlinks, and embedded-image counts. |
| XLSX | `.xlsx` with `openpyxl` | Extracts workbook metadata, all sheets including hidden sheets, every non-empty cell, formulas, cached values when present, filters, tables, defined names, cross-sheet references, chart metadata, and embedded-image anchors. |
| PPTX | `.pptx` with `python-pptx` | Extracts slide geometry, shape metadata, text paragraphs, notes, and embedded-image counts. |
| PDF | `.pdf` with `pypdf` | Extracts PDF metadata, page count, native page text, and image counts. Scanned-page OCR remains provider-configured. |
| OpenDocument | ODT, ODS, ODP | Reads ZIP `content.xml` and extracts text nodes where feasible; layout/styles/formulas are not deeply interpreted. |
| Archives/compressed streams | ZIP, TAR, TAR.GZ/TAR.BZ2/TAR.XZ, GZIP, BZIP2, XZ | Lists members or stream metadata safely; no extraction. |
| EPUB | `.epub` | Lists package members and container XML preview; no chapter extraction claim. |
| Email | `.eml`, `.mbox` text messages | Parses headers/plain text body, lists attachment metadata, and preserves original message source. |
| SQLite | `.sqlite`, `.sqlite3`, `.db` with SQLite header | Opens read-only and lists schema objects when possible. |

## Safe Placeholder Coverage

| Category | Examples | Core behavior |
| --- | --- | --- |
| Image | PNG, JPEG, GIF, TIFF, BMP, WebP, HEIC, SVG | Records dimensions/profile, route plan, provider status, OCR/VLM/chart/document hooks, and SVG markup when textual. No specialist success is claimed unless a configured provider returns content. |
| Audio | WAV, MP3, FLAC, OGG, AAC, MIDI | Records media profile, optional `ffprobe`, speech/language/transcription/translation provider stages, and truthful blockers. |
| Video | MP4, MOV, MKV, AVI, WebM | Records media profile, optional `ffprobe`, subtitles count, frame sampling/OCR/VLM stages, audio transcription hooks, and truthful blockers. |
| Documents without native parser | DOC, malformed office/PDF files, XLS without `xlrd` | Safe summary with dependency/parser warning. |
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

Placeholder and provider-route outputs are intentionally explicit. Images state whether OCR, VLM,
chart, and document-image providers were disabled, unavailable, skipped, attempted, or used.
Audio/video outputs expose metadata, coarse unknown/safe classification, and speech/frame stages
without inventing transcripts or scene labels. Advanced ebook, database, geospatial, CAD,
scientific, font, executable, and disk-image formats all produce useful metadata without claiming
semantic extraction beyond what the backend actually performed.
