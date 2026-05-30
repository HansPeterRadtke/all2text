# File Format Coverage

The core package is useful without heavy dependencies, but it is strict about not overstating what it
extracts.

## Native Core Extraction

| Category | Formats | Behavior |
| --- | --- | --- |
| Plain text | `.txt`, `.log`, extensionless printable files | Decodes and preserves text exactly in extracted content. |
| Structured text | Markdown, HTML/XML-like text, JSON, JSONL, YAML/TOML/INI hints, CSV, TSV | Preserves original text and records lightweight parse metadata where safe. |
| Source code | Common source/script extensions | Preserves exact source text. |
| Notebook | `.ipynb` | Preserves JSON text and records notebook cell count when parseable. |
| Geospatial text | GeoJSON, KML | Preserves source text and classifies geospatial signatures. |
| Text CAD | DXF/STEP/STL/OBJ/IGES when printable | Preserves text instead of pretending geometry analysis. |
| Archives | ZIP, TAR, TAR.GZ/TAR.BZ2/TAR.XZ, GZIP | Lists members or stream metadata safely; no extraction. |
| EPUB | `.epub` | Lists package members and container XML preview; no chapter extraction claim. |
| Email | `.eml`, `.mbox` text messages | Parses headers/plain text body and lists attachment metadata. |
| SQLite | `.sqlite`, `.sqlite3`, `.db` with SQLite header | Opens read-only and lists schema objects when possible. |

## Safe Placeholder Coverage

| Category | Examples | Core behavior |
| --- | --- | --- |
| Image | PNG, JPEG, GIF, TIFF, BMP, WebP, HEIC, SVG | Records byte signature and light dimensions where possible. SVG text is preserved as markup. No OCR/VLM claim. |
| Audio | WAV, MP3, FLAC, OGG, AAC, MIDI | Records media metadata and optional `ffprobe` output. No transcription. |
| Video | MP4, MOV, MKV, AVI, WebM | Records media metadata and optional `ffprobe` output. No frame/text/scene extraction. |
| Documents | PDF, DOC, DOCX, RTF, ODT | Safe summary and light PDF markers. Optional deep parsers are future backends. |
| Spreadsheets | XLS, XLSX, ODS | Safe summary. No formula/table extraction in core. |
| Presentations | PPT, PPTX, ODP | Safe summary. No slide extraction in core. |
| Scientific data | HDF5, NetCDF, Parquet, FITS, MAT, NPY/NPZ | Safe byte/string summary. No dataset traversal in core. |
| Binary CAD | DWG and other non-text CAD | Safe summary. No geometry/layer extraction. |
| Fonts | TTF, OTF, WOFF, WOFF2 | Safe summary. No glyph tables. |
| Executables | ELF, PE/MZ, Mach-O, shared libraries | Safe summary. No execution, disassembly, or decompilation. |
| Containers | ISO, DMG, VHD, QCOW2 | Safe summary. No mounting or filesystem traversal. |
| Unknown binary | Any unmapped binary | Header and printable string samples. |

## Extension/Content Mismatches

Content signatures override misleading extensions when strong. A PNG named `actually_png.txt` is
classified as image/PNG, not text, and still receives `actually_png.txt.txt` as its output path.

