# Roadmap

Near-term:

- MarkItDown backend for broad document extraction.
- OCR confidence filtering and preprocessing for the current configurable Tesseract path.
- Optional PDF scanned-page rendering/OCR fallback with bounded external commands.
- More complete OpenDocument spreadsheet/presentation handling.
- Provider execution adapters for chart specialists and document intelligence.
- Geospatial schema/layer probes for GeoPackage and Shapefile with read-only libraries.

Medium-term:

- Audio transcription backend with clear model/provider metadata.
- Video keyframe and frame-OCR backend.
- HDF5/NetCDF/FITS/Parquet schema and sample extractors.
- CAD-specific DXF and STEP readers.
- Rich EPUB chapter extraction.
- MSG/MBOX mail parsers with attachment conversion hooks.
- Document-intelligence adapter contract for scanned PDFs and image-heavy office documents.

Long-term:

- Backend capability discovery and diagnostics.
- Streaming manifests for very large trees.
- Policy controls for recursive archive extraction into isolated work directories.
- Optional document-intelligence and VLM provider integrations.
- Stable JSON schema versioning for manifests and per-file output sections.
- Golden corpus parity checks against historical `rag_tests` universal converter fixtures.

## Quality Gates

New roadmap items should preserve these gates:

- no external model or binary artifact committed to the repository;
- placeholder behavior remains truthful when optional dependencies are absent;
- exact text preservation tests cover every text-like format added;
- external command integrations use bounded timeouts and record command availability;
- manifests stay JSON-safe for custom backend metadata.
