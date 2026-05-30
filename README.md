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
- list ZIP/TAR/GZIP/BZIP2/XZ-style archives or compressed streams safely without extracting them;
- record symlinks without following them;
- provide explicit safe summaries for binary and unsupported deep formats;
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

Core `all2text` intentionally has no required third-party runtime dependencies. Optional groups are
declared for future deep extraction backends:

```bash
python -m pip install -e '.[documents,ocr,scientific,cad]'
```

## CLI

```bash
all2text /path/to/source /path/to/output
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
from all2text import run
from all2text.models import RunOptions

manifest = run(
    "source",
    "out",
    options=RunOptions(use_file_command=False, copy_source_stat=False),
)
```

## Current Format Coverage

Native core extraction:

- text, Markdown, source code, JSON, JSONL, CSV, TSV, YAML, XML, HTML, RTF, notebooks,
  GeoJSON/KML, and text-based CAD formats are decoded and preserved in the extracted-content
  section;
- ZIP/TAR/GZIP/BZIP2/XZ archives or streams are listed/summarized safely with path traversal
  warnings where member paths exist;
- EPUB packages are listed and probed as containers;
- EML/MBOX files are parsed with Python's standard email package, including headers, plain text
  body, attachment metadata, and original message source preservation;
- SQLite files are opened read-only when possible to list schema objects.

Safe placeholder coverage:

- image, audio, video, PDF, DOC/DOCX, XLS/XLSX, PPT/PPTX, ODT/ODS/ODP, scientific data,
  binary geospatial, binary CAD, fonts, executables, disk images, unknown binaries, and specialist
  containers.

Placeholders detect, classify, emit metadata, summarize bytes/strings safely, and state exactly
what was not extracted. They do not claim OCR, transcription, VLM understanding, CAD geometry
analysis, spreadsheet formula evaluation, or scientific array extraction.

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
