# Roadmap

Near-term:

- Harden the pip-invoked/manual external setup flow with more provider-specific installers as upstream
  Jetson/aarch64 packages become practical.
- MarkItDown backend for broad document extraction.
- PDF scanned-page rendering/OCR fallback with bounded external commands.
- More complete OpenDocument spreadsheet/presentation handling.
- Provider execution adapters for chart specialists and document intelligence.
- Deeper scene/keyframe analysis after the bounded ffmpeg frame sampler.
- Additional geospatial schema/layer probes beyond current GeoJSON, KML, Shapefile, and GeoPackage metadata.

Medium-term:

- Broader audio transcription support beyond current faster-whisper and whisper.cpp local-model hooks.
- Video frame OCR/VLM backend that consumes sampled frames and records per-frame evidence.
- HDF5/NetCDF/FITS/Parquet bounded sample extractors beyond current schema metadata.
- CAD-specific STEP readers and richer DXF layer/entity summaries.
- Rich EPUB chapter extraction.
- MSG/MBOX mail parsers with attachment conversion hooks.
- Document-intelligence adapter contract for scanned PDFs and image-heavy office documents.

Long-term:

- Backend capability discovery beyond the current manifest-level provider status diagnostics.
- Streaming manifests for very large trees.
- Policy controls for recursive archive extraction into isolated work directories.
- Optional document-intelligence and VLM provider integrations.
- Stable JSON schema versioning for manifests and per-file output sections.
- Golden corpus parity checks against historical `rag_tests` universal converter fixtures.

## Quality Gates

New roadmap items should preserve these gates:

- no external model or binary artifact committed to the repository;
- pip source installs keep the external setup hook no-hang and user-confirmed; wheel installs use the
  documented `all2text setup` rerun path and user/runtime storage;
- placeholder behavior remains truthful when optional dependencies are absent;
- exact text preservation tests cover every text-like format added;
- external command integrations use bounded timeouts and record command availability;
- manifests stay JSON-safe for custom backend metadata.


See also: [Open-source extraction research](open-source-extraction-research-2026.md) for the researched provider/model roadmap.

Manual Jetson setup update, 2026-06-08: radare2 was installed through the OS package manager; faster-whisper base and small plus whisper.cpp base models were downloaded into external model storage; Docling 2.91.0 was installed in an isolated Python 3.11 CPU environment with a smoke conversion. The setup planner now detects that environment as satisfied and uses a pinned CPU-index install command for future Docling setup.

Docling Jetson fix: the isolated Docling environment uses the CPU PyTorch index and replaces the full OpenCV wheel with opencv-python-headless to avoid the Jetson static TLS OpenGL loader failure during RapidOCR/table-model imports.
