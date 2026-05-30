# Limitations

The core package favors truthful, auditable output over broad but shallow claims.

Current limitations:

- PDF, DOCX, XLSX, PPTX, ODT, ODS, and ODP are not semantically extracted by core backends.
- RTF is preserved as structured source text with lightweight metadata, but rich text layout is not
  rendered or semantically normalized.
- Images do not receive OCR, captions, chart tables, or visual scene understanding in core.
- Audio and video are not transcribed; `ffprobe` metadata is used only when available.
- Binary geospatial files are not inspected for coordinate reference systems, layers, features, or
  raster bands in core.
- Scientific data files are not traversed for datasets or arrays in core.
- Binary CAD files are not parsed for geometry, layers, units, or drawings.
- Disk images are not mounted or traversed.
- Executables are not run, disassembled, or decompiled.
- Archive members are listed but not recursively extracted.
- Compressed streams are only summarized or lightly peeked; nested payload conversion is not enabled
  by default.
- Formula cached values, rendered spreadsheet charts, and embedded document images require optional
  document-specific backends.
- Local LLM/VLM/OCR models are not bundled with the repository. Model files must stay external and
  be supplied by the operator.

These limitations are also emitted in per-file conversion metadata so downstream systems can tell
the difference between extracted text and safe summaries.

## Intentional Safety Boundaries

The default package avoids operations that can surprise an operator during a bulk tree conversion:

- no symlink traversal;
- no archive extraction to disk;
- no disk image mounting;
- no executable execution;
- no network calls;
- no automatic model downloads;
- no mutation of source files.

Backends that cross any of these boundaries must make that behavior opt-in and document it clearly.
