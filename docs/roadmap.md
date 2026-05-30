# Roadmap

Near-term:

- MarkItDown backend for broad document extraction.
- Native PDF backend with pypdf and optional OCR fallback.
- Native DOCX/XLSX/PPTX backends derived from the proven `rag_tests` extraction patterns.
- Optional image OCR backend with confidence filtering.
- Better HTML visible-text extraction while preserving raw markup as source.

Medium-term:

- Audio transcription backend with clear model/provider metadata.
- Video keyframe and frame-OCR backend.
- HDF5/NetCDF/FITS/Parquet schema and sample extractors.
- CAD-specific DXF and STEP readers.
- Rich EPUB chapter extraction.
- MSG/MBOX mail parsers with attachment conversion hooks.

Long-term:

- Backend capability discovery and diagnostics.
- Streaming manifests for very large trees.
- Policy controls for recursive archive extraction into isolated work directories.
- Optional document-intelligence and VLM provider integrations.
- Stable JSON schema versioning for manifests and per-file output sections.

