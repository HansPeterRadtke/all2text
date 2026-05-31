# all2text

`all2text` converts heterogeneous folder trees into auditable plain-text outputs.

It is designed for RAG ingestion, migration audits, discovery jobs, and other workflows where a
folder must be mirrored as text without pretending unsupported formats were semantically extracted.

Core behavior:

- scan the source tree first, then write outputs;
- mirror the source directory layout;
- write one `.txt` output per source entry by appending `.txt` to the complete original filename;
- reserve the target output tree before conversion so the manifest and generated files are stable;
- collect filesystem, stat, ACL, xattr, MIME, hash, header, classification, converter, warning, and
  limitation metadata;
- preserve decoded text and structured text exactly in the extracted-content section, including
  Markdown, JSON, JSONL, YAML, XML, HTML, RTF, notebooks, GeoJSON/KML, and source code;
- extract DOCX, XLSX, PPTX, PDF, and OpenDocument text/structure when the optional document
  dependencies for those formats are installed, with truthful fallback otherwise;
- list ZIP/TAR/GZIP/BZIP2/XZ-style archives or compressed streams safely without extracting them;
- record symlinks without following them;
- provide explicit safe summaries and provider-route reports for binary and unsupported deep formats;
- generate `_conversion_manifest.json` and `_conversion_report.txt`.

Example:

```text
source: source/reports/final.pdf
output: out/reports/final.pdf.txt
```

## Install

```bash
cd /data/src/github/all2text
python -m pip install -e .
```

Core `all2text` intentionally keeps heavy dependencies optional. The config loader uses Python
3.11+ `tomllib`, optional `tomli`, or a small fallback parser for the simple template shipped here.
Optional groups enable native extraction paths when installed:

```bash
python -m pip install -e '.[documents,ocr,scientific,cad]'
```

## CLI

```bash
all2text /path/to/source /path/to/output
all2text --config /path/to/all2text.toml /path/to/source /path/to/output
```

Useful options:

```bash
all2text --no-file-command --no-copy-source-stat /path/to/source /path/to/output
all2text --max-archive-members 100 /path/to/source /path/to/output
all2text --version
```

The command prints the manifest summary as JSON and writes:

```text
<output>/_conversion_manifest.json
<output>/_conversion_report.txt
```

## API

```python
from all2text import run

manifest = run("/path/to/source", "/path/to/output")
print(manifest["summary"])
```

The primary API is intentionally small. Advanced users can pass `RunOptions` or a custom
`ConversionRegistry` to plug in backends without changing the workflow.

```python
from all2text import load_config, run
from all2text.models import RunOptions

config = load_config("all2text.default.toml")
manifest = run(
    "source",
    "out",
    options=RunOptions(use_file_command=False, copy_source_stat=False),
    config=config,
)
```

Configuration is TOML-oriented and keeps module/provider selection outside code. Start from
[`all2text.default.toml`](all2text.default.toml) to choose backends per file family and configure
providers such as OCR, local llama.cpp VLM, speech transcription, frame sampling, or chart
specialists. Provider parameters are carried into manifests even when the provider is disabled or
unavailable.

Module config can also bound native extraction without swapping code. For example,
`[modules.document] max_pdf_pages = 50` limits PDF page extraction, while
`[modules.spreadsheet] max_cells_per_sheet = 10000` and `include_hidden_sheets = false` control
XLSX output size and hidden-sheet handling. Skips and limits are recorded in warnings, limitations,
and converter metadata.

## Current Format Coverage

Native core extraction:

- text, Markdown, source code, JSON, JSONL, CSV, TSV, YAML, XML, HTML, RTF, notebooks,
  GeoJSON/KML, and text-based CAD formats are decoded and preserved in the extracted-content
  section;
- DOCX uses `python-docx` when installed to emit properties, paragraph/table order, raw
  WordprocessingML paragraph counts, sections, headers, footers, hyperlinks, and embedded-image
  counts;
- XLSX uses `openpyxl` when installed to emit all sheets, hidden sheets, dimensions, every non-empty
  cell, formulas, cached values when available, tables, filters, defined names, cross-sheet
  references, chart metadata, and embedded-image anchors; config can bound cells per sheet or skip
  hidden-sheet extraction when needed;
- PPTX uses `python-pptx` when installed to emit slide geometry, shapes, paragraphs, notes, and
  embedded-image counts;
- PDF uses `pypdf` when installed to emit metadata, page count, native text per page, and image
  counts; config can cap extracted pages, and scanned-page OCR remains provider-configured work;
- ODT/ODS/ODP are read as OpenDocument ZIP packages and content.xml text nodes are extracted where
  feasible;
- ZIP/TAR/GZIP/BZIP2/XZ archives or streams are listed/summarized safely with path traversal
  warnings where member paths exist;
- EPUB packages are listed and probed as containers;
- EML/MBOX files are parsed with Python's standard email package, including headers, plain text
  body, attachment metadata, and original message source preservation;
- SQLite files are opened read-only when possible to list schema objects.

Safe placeholder coverage:

- image, audio, video, DOC, XLS without `xlrd`, scientific data,
  binary geospatial, binary CAD, fonts, executables, disk images, unknown binaries, and specialist
  containers.

Image and media outputs now include layered provider routing/status reports. Top-level manifests
also include configured provider statuses, so disabled/unavailable local llama.cpp, OCR, speech, and
video-frame routes are visible even when no matching files are present. Outputs do not claim OCR,
transcription, VLM understanding, chart values, CAD geometry analysis, or scientific array
extraction unless a configured provider actually returns accepted evidence.

See [docs/coverage.md](docs/coverage.md) for the detailed matrix.

## Design Lineage

This repository was bootstrapped from lessons learned in
`/data/src/github/devtests/rag_tests`, especially the universal converter work:

- layered extension/MIME/content-signature classification;
- output path planning before conversion;
- deterministic collision naming;
- metadata-rich text wrappers;
- archive listing instead of unsafe extraction;
- symlink recording without traversal;
- truthful limitations for unsupported binary formats.
- native DOCX/XLSX/PPTX/PDF extraction patterns and routed image-provider lessons, generalized into
  configurable all2text infrastructure.

`all2text` turns those lessons into an independent, modular package with a stable backend contract.

## Optional Backends and Local Models

The core package does not bundle external models or large converter stacks. Optional integrations are
expected to be implemented as backends that return truthful `ConversionResult` metadata:

- MarkItDown or textract for broad document extraction;
- pypdf, python-docx, openpyxl, and python-pptx for native document detail;
- ffprobe/ffmpeg plus speech or frame analyzers for audio/video;
- OCR, VLM, chart, and document-intelligence providers for images and scanned documents;
- GDAL/Fiona/Rasterio, ezdxf, HDF5/NetCDF/FITS/Parquet libraries for specialist data;
- local llama.cpp text and vision providers.

See [llama.cpp and model setup](docs/llama-cpp-models.md) for Jetson-oriented notes using
`Qwen2.5-14B-Instruct-Q4_K_M.gguf`, `Qwen2.5-VL-3B-Instruct-Q4_K_M.gguf`, and
`mmproj-Qwen2.5-VL-3B-Instruct-Q8_0.gguf` as external examples. These model files are not packaged
or committed in this repository.

## Development

```bash
python -m pip install -e '.[dev]'
python -m compileall -q src
pytest
```

Detailed docs:

- [Architecture](docs/architecture.md)
- [Configuration](docs/configuration.md)
- [Format coverage](docs/coverage.md)
- [Metadata strategy](docs/metadata.md)
- [CLI and API](docs/cli-api.md)
- [Backend contract](docs/backend-contract.md)
- [Limitations](docs/limitations.md)
- [Testing and development](docs/testing-development.md)
- [Roadmap](docs/roadmap.md)
- [llama.cpp and model setup](docs/llama-cpp-models.md)
- [Operational log](docs/operational-log.md)
- [Bootstrap report](docs/final-report.md)
