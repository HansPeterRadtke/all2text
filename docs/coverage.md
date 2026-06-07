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
| Geospatial text | GeoJSON, KML | Uses the geospatial safe backend to emit bounded schema metadata while preserving source text in the extracted-content section. |
| Text CAD | DXF/STEP/STL/OBJ/IGES when printable | Uses the CAD safe backend to emit bounded schema metadata where available while preserving source text; no geometry analysis is invented. |
| DOCX | `.docx` with `python-docx` | Extracts core properties, paragraph/table order, raw XML paragraph counts, sections, headers/footers, hyperlinks, and embedded-image counts. |
| XLSX | `.xlsx` with `openpyxl` | Extracts workbook metadata, all sheets including hidden sheets, every non-empty cell, formulas, cached values when present, filters, tables, defined names, cross-sheet references, chart metadata, and embedded-image anchors. `spreadsheet.include_hidden_sheets` and `spreadsheet.max_cells_per_sheet` can bound output. |
| PPTX | `.pptx` with `python-pptx` | Extracts slide geometry, shape metadata, text paragraphs, notes, and embedded-image counts. |
| PDF | `.pdf` with `pypdf` | Extracts PDF metadata, page count, native page text, and image counts. `document.max_pdf_pages` can bound output. Scanned-page OCR remains provider-configured. |
| OpenDocument | ODT, ODS, ODP | Reads ZIP `content.xml` and extracts text nodes where feasible; `document.max_text_blocks` can bound output. Layout/styles/formulas are not deeply interpreted. |
| Archives/compressed streams | ZIP, TAR, TAR.GZ/TAR.BZ2/TAR.XZ, GZIP, BZIP2, XZ | Lists members or stream metadata safely; no extraction. |
| EPUB | `.epub` | Lists package members and container XML preview; no chapter extraction claim. |
| Email | `.eml`, `.mbox` text messages | Parses headers/plain text body, lists attachment metadata, and preserves original message source. |
| SQLite | `.sqlite`, `.sqlite3`, `.db` with SQLite header | Opens read-only and lists schema objects when possible. |
| Media metadata | Audio/video with `mutagen` installed | Records Python-only container/tag metadata where mutagen can read it, plus deterministic low-confidence audio-kind routing such as silence, very-short, speech-unknown, music-unknown, mixed-unknown, or unknown. |

## Safe Placeholder Coverage

| Category | Examples | Core behavior |
| --- | --- | --- |
| Image | PNG, JPEG, GIF, TIFF, BMP, WebP, HEIC, SVG | Records dimensions/profile, route plan, provider status, real Tesseract OCR when available/enabled, VLM/chart/document hooks, and SVG markup when textual. No specialist success is claimed unless a configured provider returns accepted content. |
| Audio | WAV, MP3, FLAC, OGG, AAC, MIDI | Records media profile, optional Python `mutagen` metadata, optional `ffprobe` when detected/allowed, deterministic audio-kind routing, configured faster-whisper/whisper.cpp speech hooks, and truthful blockers. |
| Video | MP4, MOV, MKV, AVI, WebM | Records media profile, optional Python `mutagen` metadata, optional `ffprobe` when detected/allowed, subtitles count, opt-in real ffmpeg frame sampling, configured frame OCR/VLM stage plans, audio transcription hooks, and truthful blockers. |
| Documents without native parser | DOC, malformed office/PDF files, XLS without `xlrd` | Safe summary with dependency/parser warning. |
| Scientific data | HDF5, NetCDF, Parquet, FITS, MAT, NPY/NPZ | Safe byte/string summary plus bounded schema probes when installed libraries are available: NumPy for NPY/NPZ, h5py for HDF5, netCDF4 for NetCDF, astropy for FITS, pyarrow for Parquet, scipy for MAT. Array values are not dumped. |
| Binary geospatial | Shapefile, GeoPackage, raster/sidecar geospatial formats | Safe byte/string summary plus bounded GeoJSON/KML/pyshp/SQLite GeoPackage schema metadata when available. Shapely may compute bounds and pyproj may parse CRS metadata; no coordinate transformation, feature dump, or raster dump. |
| Binary CAD | DWG and other non-text CAD | Safe summary plus bounded ezdxf/IfcOpenShell schema metadata when available. No rendering, geometry dump, macro execution, or engineering interpretation. |
| Fonts | TTF, OTF, WOFF, WOFF2 | Safe summary. No glyph tables. |
| Executables | ELF, PE/MZ, Mach-O, shared libraries | Safe summary plus bounded ELF header parsing, pefile PE metadata, macholib Mach-O metadata, and optional LIEF summary when installed. No execution, disassembly, decompilation, unpacking, or behavioral claims. |
| Containers | ISO, DMG, VHD, QCOW2 | Safe summary. No mounting or filesystem traversal. |
| Unknown binary | Any unmapped binary | Header and printable string samples. |

## Extension/Content Mismatches

Content signatures override misleading extensions when strong. A PNG named `actually_png.txt` is
classified as image/PNG, not text, and still receives `actually_png.txt.txt` as its output path.

Generic printable text is not allowed to erase more specific extension or name evidence. For
example, a small Markdown or YAML file that only looks like generic text is still classified as its
structured format, while a strong binary magic signature still wins over a misleading extension.

Known specialist extensions such as DWG, DXF, STL, FITS, HDF5, SQLite, fonts, disk images, and
OpenDocument/Office formats are not displaced by generic conflicting MIME metadata. This matters on
systems where `file(1)` or Python MIME tables report vendor CAD or scientific formats under an
image-like MIME. Actual strong content signatures, such as a PNG magic header in a misnamed file,
still override the extension.

## Placeholder Truthfulness

Placeholder and provider-route outputs are intentionally explicit. Images state whether OCR, VLM,
chart, and document-image providers were disabled, unavailable, skipped, attempted, or used. OCR is
accepted only after configured confidence/text-quality gates. Audio/video outputs expose metadata,
deterministic audio-kind routing, and speech/frame stages without inventing transcripts or scene
labels. Advanced ebook, database, geospatial, CAD,
scientific, font, executable, and disk-image formats all produce useful metadata without claiming
semantic extraction beyond what the backend actually performed.

The top-level manifest also records capability and provider statuses for configured OCR, VLM/local
llama.cpp, chart, document-intelligence, audio classifier, speech, diarization, shell-tool,
Python-library, CAD/scientific/geospatial/binary metadata, and video-frame routes. It also records
`provider_family_statuses`, a broader catalog of researched provider candidates and blockers. The
manifest and doctor output also include `provider_execution_summary` to separate installed Python
providers, external tools, reachable endpoints, discovered local model files, executable providers,
contract-only providers, and blockers. `all2text doctor` also includes the external setup plan and
last setup report when present, so missing ffmpeg/Tesseract/LibreOffice/whisper.cpp/llama.cpp/
radare2/capa tools and local model roots can be audited before conversion. This
makes a run auditable even when no file happened to exercise a provider family. It also records
module statuses so configured extraction routes that had no matching files, or were not selected for
matching files, are explicit.
