# Converter Backend Contract

Backends implement the protocol in `all2text.backends.base`.

```python
class ConverterBackend(Protocol):
    name: str

    def can_handle(self, classification: Classification, entry_type: str) -> bool:
        ...

    def convert(
        self,
        path: Path,
        rel_path: Path,
        classification: Classification,
        metadata: dict[str, object],
        ctx: ConversionContext,
    ) -> ConversionResult:
        ...
```

## Rules

- Do not mutate the source tree.
- Do not read outside the given `path` unless the backend has explicit configuration for a related
  sidecar file.
- Do not follow symlinks. Symlink handling belongs to `FilesystemBackend`.
- Report warnings and limitations explicitly.
- Do not claim semantic extraction when only metadata or byte summaries were produced.
- Keep heavy dependencies optional and import them inside the backend.
- Use timeouts for external tools.
- Return deterministic text where possible.

## Result Text

`ConversionResult.text` becomes the content after `=== Extracted Content ===`. For exact text
backends, this must be the decoded source text without extra explanations. Put parse details in
`ConversionResult.metadata`.

For placeholder backends, the text should clearly say what was recorded and what was not extracted.

`ConversionResult` also carries:

- `converter_used`: stable backend name;
- `extraction_methods_used`: ordered method identifiers;
- `llm_used`, `ocr_used`, `vlm_used`: truthful booleans for optional provider usage;
- `errors` and `warnings`: explicit recoverable and non-recoverable issues;
- `metadata`: JSON-safe or JSON-normalizable backend metadata;
- `limitations`: human-readable limitations emitted into manifests and reports.

The core renderer JSON-normalizes backend metadata, but backends should still avoid huge values.
Prefer compact counts, previews, and paths over embedding large raw payloads.

## Optional Provider Backends

Optional integrations should follow a strict truthfulness contract:

- If MarkItDown, textract, pypdf, python-docx, openpyxl, or python-pptx is used, record library name,
  version when practical, extraction method, and any skipped embedded assets.
- If OCR is used, record engine/provider, preprocessing, confidence, discard rules, and whether text
  was actually accepted.
- If a VLM or local llama.cpp provider is used, record endpoint/model identifier, request mode, and
  whether the result came from the provider or a fallback.
- If a provider is configured but not invoked, record that status separately from provider failure
  and from successful provider use.
- If ffprobe/ffmpeg is used, keep command timeouts and include stderr/exit warnings without failing
  the whole tree when a single media file is invalid.
- If CAD, scientific, geospatial, database, or document-intelligence libraries are used, keep file
  opening read-only and summarize schemas/objects before dumping large data.

## Future Backend Targets

The registry is ready for:

- Microsoft MarkItDown;
- textract;
- MarkItDown/textract-style broad document backends in addition to the current
  pypdf/python-docx/openpyxl/python-pptx native document paths;
- Tesseract/PaddleOCR and document intelligence services;
- `ffprobe` plus speech transcription;
- local llama.cpp text and vision providers for VLM image descriptions and text synthesis;
- HDF5/NetCDF/FITS/Parquet readers;
- CAD parsers such as ezdxf;
- specialist mail, ebook, and database parsers.
