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
- expose provider-family status for document OCR/layout, image routing, OCR, VLM, charts, audio,
  video, CAD/BIM, scientific/geospatial, and binary metadata without downloading model files;
- run Tesseract OCR, ffprobe metadata, opt-in ffmpeg frame sampling, and configured local
  faster-whisper or whisper.cpp speech hooks when the required local tools/models are present;
- emit bounded schema metadata for installed CAD/scientific/geospatial/binary libraries without
  dumping arrays, rendering geometry, executing files, or inventing semantic conclusions;
- generate `_conversion_manifest.json` and `_conversion_report.txt`.

Example:

```text
source: source/reports/final.pdf
output: out/reports/final.pdf.txt
```

## Install

Repository install:

```bash
cd /data/src/github/all2text
python -m pip install .
```

Future package install:

```bash
python -m pip install all2text
```

The normal install includes the safe PyPI dependency set and, when pip is installing from source and
the build backend is invoked, runs the all2text external setup hook. In an interactive terminal the
hook offers a simple yes/no prompt for missing safe user-space tools and bounded default models. In
noninteractive installs it never waits for input; it writes a setup report and prints the exact
rerun command. Installing an already-built wheel cannot run arbitrary postinstall code, so the same
setup path remains available as a manual/developer rerun:

```bash
python -m all2text setup --dry-run --profile full
python -m all2text setup --yes --profile minimal
python -m all2text SOURCE TARGET
```

The pip hook and `all2text setup` share the same planner. They detect OS, architecture, Jetson/NVIDIA
signals, package managers, build tools, Python 3.10/3.11 candidates, reachable local model endpoints,
and local model roots. Root/system package work is reported as exact apt/brew/winget/choco commands;
safe user-space builds such as whisper.cpp can run when selected and prerequisites exist. Bounded
defaults such as tiny Whisper models list rough size/time notes. Huge or gated model stacks are listed
explicitly and are not silently downloaded.

Automation controls use environment variables that pip can pass through:

```bash
ALL2TEXT_SETUP_ASSUME_YES=1 python -m pip install .
python -m all2text bootstrap --package all2text --yes
ALL2TEXT_SETUP_MODE=full ALL2TEXT_SETUP_ASSUME_YES=1 python -m pip install .
python -m all2text bootstrap --package all2text --yes
ALL2TEXT_SETUP_NONINTERACTIVE=1 python -m pip install .
ALL2TEXT_SETUP_MODE=skip python -m pip install .
```

Useful variables include `ALL2TEXT_SETUP_MODE=minimal|full|tools|models|plan|skip`,
`ALL2TEXT_SETUP_ASSUME_YES=1`, `ALL2TEXT_SETUP_NONINTERACTIVE=1`,
`ALL2TEXT_SETUP_SKIP_HEAVY=0|1`, `ALL2TEXT_SETUP_SKIP_MODELS=1`,
`ALL2TEXT_SETUP_TOOLS`, `ALL2TEXT_SETUP_MODELS`, `ALL2TEXT_SETUP_TARGET`,
`ALL2TEXT_TOOLS_DIR`, `ALL2TEXT_MODELS_DIR`, `ALL2TEXT_SETUP_REPORT`, and
`ALL2TEXT_SETUP_COMMAND_TIMEOUT_SECONDS` for long external environment installs.

At runtime all2text automatically uses installed Python packages from these extras, detects safe
external tools on PATH/default configured locations, and safely probes configured/common local
OpenAI-compatible endpoints. Missing optional capabilities are reported and are not fatal. If a
conversion needs an enabled external provider and stdin/stdout are interactive, all2text can offer
to run the setup helper; in noninteractive mode it never waits for input and prints the exact setup
command instead. The config loader uses Python 3.11+ `tomllib`, optional `tomli` on older Python, or
a small fallback parser for the simple template shipped here.
Developer extras are optional:

```bash
python -m pip install '.[dev]'
```

`legacy-textract` is available as a deliberate extra, but practical operation often depends on
external converter binaries and older Python dependency constraints. MarkItDown is installed only on
Python versions where the published package is resolvable; the native all2text document backends do
not depend on it.

## CLI

```bash
all2text /path/to/source /path/to/output
python -m all2text /path/to/source /path/to/output
all2text --config /path/to/all2text.toml /path/to/source /path/to/output
python -m all2text --capabilities
all2text doctor
all2text setup --dry-run --profile full
python -m all2text setup --yes --tools --models minimal
all2text install-tools
all2text --capabilities
```

Useful options:

```bash
all2text --detect-capabilities
all2text --profile core /path/to/source /path/to/output
all2text --profile pip /path/to/source /path/to/output
all2text --profile tools /path/to/source /path/to/output
all2text --profile local-models /path/to/source /path/to/output
all2text --profile full /path/to/source /path/to/output
all2text --no-file-command --no-copy-source-stat /path/to/source /path/to/output
all2text --max-archive-members 100 /path/to/source /path/to/output
all2text --version
```

Default behavior is automatic. A normal run uses deterministic core extractors, installed optional
Python libraries, available safe external tools such as `file`, `ffprobe`, `getfacl`, and
Tesseract, and reachable/configured local model endpoints when provider `auto_invoke` permits
actual calls. The built-in local endpoint probes are short `/v1/models` GET requests and include
Jetson defaults `http://127.0.0.1:14829/v1` for text and `http://127.0.0.1:14830/v1` for vision.
No model files or external binaries are downloaded or bundled.

Profiles are advanced safety overrides:

- `core`: stdlib-only deterministic extraction; no optional PyPI libraries, shell tools, or models.
- `pip`: Python/PyPI-only extraction; disables shell tools and local model endpoints.
- `tools`: allows optional shell tools such as `file`, `ffprobe`, `ffmpeg`, `getfacl`, or Tesseract
  when configured and present.
- `local-models`: allows configured local/remote-compatible model endpoints without enabling shell
  tools.
- `full`: enables all configured Python, tool, and model routes that are available.

The CLI prints a JSON summary that includes the active automatic settings, capability summary,
missing optional Python libraries/tools, provider summary, and normal conversion counts. The
manifest and report include full capability/provider tables plus a compact
`provider_execution_summary` separating installed Python providers, external tools, reachable
endpoints, discovered model files, executable providers, contract-only providers, and blockers.

The installed console command and module invocation are equivalent: `all2text ...` and `python -m all2text ...` both call the same CLI entry point.

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
`[modules.document] max_pdf_pages = 100` is the default PDF page cap, while
`[modules.spreadsheet] max_cells_per_sheet = 20000` and `include_hidden_sheets = false` control
XLSX output size and hidden-sheet handling. Set these limits to `0` only when an unbounded run is
intended. Media ffprobe JSON is also capped in output/manifest previews by default. Skips and
limits are recorded in warnings, limitations, and converter metadata.

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
- SQLite files are opened read-only when possible to list schema objects;
- audio/video can include Python-only `mutagen` metadata when installed; `ffprobe` metadata is used
  automatically when the executable is available and allowed; ffmpeg frame sampling runs only when
  the `video_frames` provider has `sample_frames=true` and `auto_invoke=true`.

Safe placeholder coverage:

- image, audio, video, DOC, XLS without `xlrd`, scientific data,
  binary geospatial, binary CAD, fonts, executables, disk images, unknown binaries, and specialist
  containers.

Tesseract OCR is real when `pytesseract` and the `tesseract` executable are available. OCR output is
accepted only after configured confidence, minimum-character, and alphanumeric-ratio checks. Image
and media outputs include layered provider routing/status reports. Top-level manifests
also include configured provider statuses and capability status, so disabled/unavailable local
llama.cpp, OCR, chart, audio classifier, speech, diarization, shell tools, Python optional
libraries, CAD/scientific/geospatial/binary metadata probes, and video-frame routes are visible even
when no matching files are present. Outputs do not claim OCR, transcription, VLM understanding,
chart values, CAD geometry analysis, scientific array values, or binary behavior unless a configured
provider actually returns accepted evidence.

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
- [Open-source extraction research](docs/open-source-extraction-research-2026.md)

Current Jetson Docling note: the active Python 3.8 runtime is too old for current Docling wheels, so
setup plans an isolated Python 3.10/3.11 environment under the external tools directory when a newer
interpreter is available. That install can pull a large Torch/document stack and may take a long time
or hours on ARM. The adapter runs only when configured with
`providers.document_intelligence.name="docling"` and `auto_invoke=true`, using either the active
Python package or the setup-managed external env.

Scientific extras use Python-version markers so older supported Python runtimes receive compatible package versions where upstream wheels exist.

CAD extras use Python-version markers so older supported Python runtimes receive compatible ezdxf versions where upstream wheels exist.

Document extras constrain lxml on older supported Python runtimes to avoid forcing source builds that require libxml2/libxslt development headers.

Some source-build-heavy PyPI packages are guarded by Python-version markers on older runtimes so the advertised install command does not require system compiler headers or native development libraries.

A normal user does not need dependency extras. From a cloned repository, run `python -m pip install .`; after a future PyPI release, run `python -m pip install all2text`. Source installs invoke the setup hook when pip runs the build backend; wheel installs cannot run arbitrary postinstall code, so `all2text setup` remains the manual rerun. Use `all2text doctor` to inspect detection and `all2text install-tools` for OS-aware external-tool guidance.


## MCP server

all2text can also run as a local MCP 2026-07-28 tool server without changing the normal CLI. `all2text-mcp` (or `python -m all2text.mcp_server`) speaks newline-delimited MCP JSON-RPC over stdio and exposes `all2text_capabilities` and `all2text_convert`. The MCP layer deliberately delegates to the normal all2text CLI, so provider detection, OCR, document parsing, speech/model integrations, filesystem access, configuration, and manifests remain owned by all2text rather than by the consuming agent runtime.
