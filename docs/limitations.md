# Limitations

The core package favors truthful, auditable output over broad but shallow claims.

Current limitations:

- DOCX, XLSX, PPTX, PDF, ODT, ODS, and ODP extraction depends on optional libraries and parser
  success. When the dependency is absent or parsing fails, all2text emits a safe summary with the
  exact limitation.
- Native PDF, XLSX, OpenDocument, and media metadata output is bounded by default to avoid surprise
  output from very large files. Operators can raise the limits, or set document/spreadsheet/media
  limits to `0` for an unbounded run.
- PDF extraction is native-text first. Scanned-page rendering/OCR is not automatic unless configured
  providers are added.
- RTF is preserved as structured source text with lightweight metadata, but rich text layout is not
  rendered or semantically normalized.
- Images include metadata/profile/provider-route reports. OCR, captions, chart tables, document
  understanding, and visual scene analysis require explicit provider configuration and are only
  marked used when providers return content.
- Audio and video are not transcribed by default; `ffprobe` metadata is used only when available,
  and speech/frame stages remain provider hooks unless configured adapters are added.
- Binary geospatial files are not inspected for coordinate reference systems, layers, features, or
  raster bands in core.
- Scientific data files are not traversed for datasets or arrays in core.
- Binary CAD files are not parsed for geometry, layers, units, or drawings.
- Disk images are not mounted or traversed.
- Executables are not run, disassembled, or decompiled.
- Archive members are listed but not recursively extracted.
- Compressed streams are only summarized or lightly peeked; nested payload conversion is not enabled
  by default.
- Formula cached values in XLSX are reported when available in the file. all2text does not evaluate
  formulas. Rendered spreadsheet charts and embedded document-image OCR/VLM analysis require
  optional providers.
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
