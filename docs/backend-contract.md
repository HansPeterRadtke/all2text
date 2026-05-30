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

## Future Backend Targets

The registry is ready for:

- Microsoft MarkItDown;
- textract;
- pypdf/python-docx/openpyxl/python-pptx native document backends;
- Tesseract/PaddleOCR and document intelligence services;
- `ffprobe` plus speech transcription;
- VLM image descriptions;
- HDF5/NetCDF/FITS/Parquet readers;
- CAD parsers such as ezdxf;
- specialist mail, ebook, and database parsers.

