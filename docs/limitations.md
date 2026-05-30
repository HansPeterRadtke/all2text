# Limitations

The core package favors truthful, auditable output over broad but shallow claims.

Current limitations:

- PDF, DOCX, XLSX, PPTX, ODT, ODS, and ODP are not semantically extracted by core backends.
- Images do not receive OCR, captions, chart tables, or visual scene understanding in core.
- Audio and video are not transcribed; `ffprobe` metadata is used only when available.
- Scientific data files are not traversed for datasets or arrays in core.
- Binary CAD files are not parsed for geometry, layers, units, or drawings.
- Disk images are not mounted or traversed.
- Executables are not run, disassembled, or decompiled.
- Archive members are listed but not recursively extracted.
- Formula cached values, rendered spreadsheet charts, and embedded document images require optional
  document-specific backends.

These limitations are also emitted in per-file conversion metadata so downstream systems can tell
the difference between extracted text and safe summaries.

