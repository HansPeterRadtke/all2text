# Configuration

`all2text` accepts a TOML config file with these main sections:

- `[run]` controls automatic discovery, safety gates, and resource limits.
- `[modules]` chooses a backend by file family or format key.
- `[tools.<name>]` overrides external executable discovery.
- `[providers.<task>]` configures optional engines used by those backends.

Start with [`../all2text.default.toml`](../all2text.default.toml):

```bash
all2text --config /path/to/all2text.toml /path/to/source /path/to/output
```

The Python API can use the same file:

```python
from all2text import load_config, run

config = load_config("/path/to/all2text.toml")
manifest = run("source", "out", config=config)
```

## Automatic Discovery

The default profile is `auto`. A normal run needs no config: all2text uses deterministic core
extractors, imports optional Python/PyPI libraries when installed, detects safe external tools on
PATH/default configured locations, and probes configured/common local OpenAI-compatible endpoints
with short `/v1/models` GET requests. Missing optional tools, libraries, and local endpoints are
reported clearly and do not fail the run.

```toml
[run]
profile = "auto"
auto_detect_python = true
auto_detect_tools = true
auto_detect_local_models = true
allow_optional_python = true
allow_external_tools = true
allow_local_models = true
interactive_setup_prompt = true
setup_tools_dir = ""
setup_models_dir = ""
setup_report_path = ""
```

Config is mainly for overrides and controls. Explicit config wins over automatic discovery:

- set `auto_detect_python = false` to avoid importing optional PyPI libraries;
- set `auto_detect_tools = false` to avoid PATH/default executable discovery unless a tool path is
  explicitly configured;
- set `auto_detect_local_models = false` to avoid common local endpoint discovery;
- set `allow_external_tools = false` or `allow_local_models = false` to block those classes entirely;
- set tool paths, executable names, provider base URLs, models, timeouts, and `auto_invoke`
  behavior in the relevant sections.

## External Setup

Normal package installation is the official user path:

```bash
python -m pip install .
```

When pip installs from source and invokes the setuptools build backend, all2text runs an external
setup hook. If stdin/stdout are real terminals, the hook asks a simple yes/no question before
downloading or building safe user-space tools and bounded default models. If the install is
noninteractive, it never waits for input; it writes a setup report and prints the exact rerun command.
An already-built wheel install cannot run arbitrary postinstall code, so the same setup planner is
also exposed as a manual/developer rerun:

```bash
python -m all2text setup --dry-run --profile full
python -m all2text setup --yes --profile minimal
python -m all2text /path/to/source /path/to/output
```

`all2text setup` generates a platform-aware plan for Linux, macOS, and Windows. It records OS,
architecture, Jetson/NVIDIA signals, package managers, build tools, Python 3.10/3.11 candidates,
reachable local model endpoints, and local model roots. It marks tools and models as `satisfied`,
`installable`, or `blocked`, records exact apt/brew/winget/choco/manual commands where root or
platform setup is required, and writes its last report under a user state path by default. It
supports noninteractive-safe flags: `--yes`, `--assume-yes`, `--noninteractive`, `--dry-run`,
`--plan`, `--json`, `--tools`, `--models`, `--target`, `--skip-models`, `--skip-root`,
`--skip-heavy`, `--mode`, and `--profile`.

Pip/developer automation variables:

```bash
ALL2TEXT_SETUP_ASSUME_YES=1
ALL2TEXT_SETUP_MODE=minimal|full|tools|models|plan|skip
ALL2TEXT_SETUP_NONINTERACTIVE=1
ALL2TEXT_SETUP_SKIP_HEAVY=0|1
ALL2TEXT_SETUP_SKIP_MODELS=1
ALL2TEXT_SETUP_TOOLS=whisper_cpp,capa
ALL2TEXT_SETUP_MODELS=faster_whisper_tiny,whisper_cpp_tiny
ALL2TEXT_SETUP_TARGET=/data/opt/all2text
ALL2TEXT_TOOLS_DIR=/data/opt/all2text-tools
ALL2TEXT_MODELS_DIR=/data/models/all2text
ALL2TEXT_SETUP_REPORT=/tmp/all2text-setup-report.json
ALL2TEXT_SETUP_COMMAND_TIMEOUT_SECONDS=14400
```

`minimal` is the bounded default and selects useful small models such as tiny Whisper variants while
skipping heavy builds/downloads. `full` plans the best feasible local stack for the machine and can
run heavier safe actions only with `--yes` or `ALL2TEXT_SETUP_ASSUME_YES=1`; huge or gated model
families still require explicit files, service setup, or external-env/container work.

Setup storage can be configured without changing provider settings:

```toml
[run]
interactive_setup_prompt = true
setup_tools_dir = "/data/opt/all2text-tools"
setup_models_dir = "/data/models/all2text"
setup_report_path = "/home/user/.local/state/all2text/setup-report.json"
```

When a conversion needs an enabled external provider and `interactive_setup_prompt = true`, all2text
offers the setup helper only when stdin and stdout are real terminals. In CI, scripts, pipes, and
other noninteractive runs, it never waits for input; it prints the exact setup command to stderr and
continues with truthful fallback behavior.

## Advanced Profiles

Profiles remain as safety presets, but the normal UX is not profile-first. Supported profiles:

- `core`: stdlib-only deterministic extraction. Optional PyPI libraries, shell tools, and local
  model providers are disabled by profile.
- `pip`: Python/PyPI-only mode. Optional Python/PyPI extractors are enabled when installed.
  External shell tools and local model providers are disabled by profile.
- `tools`: enables optional shell tools such as `file`, `ffprobe`, `ffmpeg`, `getfacl`, and
  Tesseract when configured and available. Local model providers remain disabled.
- `local-models`: enables configured local/remote-compatible model providers without enabling shell
  tools.
- `full`: enables installed Python libraries, configured shell tools, and configured local model
  providers.

Profile aliases `base`, `default`, `automatic`, `lowest`, and `lowest-detail` normalize to `auto`.
`python` and `python-only` normalize to `pip`, `local_models` normalizes to `local-models`, and
`all` normalizes to `full`.

Explicit run booleans can tighten a profile. For example, `profile = "tools"` with
`use_file_command = false` still allows ffprobe/getfacl/Tesseract but disables the `file(1)` MIME
probe. A restrictive profile wins over provider config: enabling `[providers.vlm]` under `pip` is
reported as `VLM disabled by profile:pip` and no endpoint is called.

## Module Selection

Example:

```toml
[modules]
document = "document_native_backend"
spreadsheet = "document_native_backend"
presentation = "document_native_backend"
image = "image_analysis_backend"
audio = "media_analysis_backend"
video = "media_analysis_backend"
```

The registry still verifies that a selected backend can handle the classified entry. If it cannot,
selection falls back through the normal ordered registry. The default geospatial and CAD backends
emit safe schema metadata and preserve source text for textual variants such as GeoJSON, KML, and
DXF.

Backend names are validated when the config is loaded. A typo such as
`image = "image_analysis_backned"` raises a `ValueError` instead of silently using another backend.

Module tables can also carry human-readable parameters. Family keys such as `document` or
`spreadsheet` apply broadly, and concrete-format keys such as `pdf` or `xlsx` can override or add
format-specific knobs:

```toml
[modules.document]
backend = "document_native_backend"
max_pdf_pages = 100
max_text_blocks = 5000

[modules.spreadsheet]
backend = "document_native_backend"
include_hidden_sheets = true
max_cells_per_sheet = 20000

[modules.xlsx]
backend = "document_native_backend"
max_cells_per_sheet = 25000

[modules.video]
backend = "media_analysis_backend"
max_ffprobe_json_chars = 20000
```

Current native document parameters:

- `document.max_pdf_pages`: limits PDF page text extraction; default is `100`, and `0` means all pages.
- `document.max_text_blocks`: limits OpenDocument text block output; default is `5000`, and `0`
  means all blocks.
- `spreadsheet.include_hidden_sheets`: defaults to `true`; set `false` to list but not extract hidden sheets.
- `spreadsheet.max_cells_per_sheet`: bounds non-empty XLSX cells emitted per worksheet; default is
  `20000`, and `0` means no per-sheet cell cap.
- `audio.max_ffprobe_json_chars` and `video.max_ffprobe_json_chars`: bound ffprobe JSON emitted in
  outputs and manifests when ffprobe is detected and allowed; default is `20000`, and `0` means no
  ffprobe JSON cap.

When a module limit skips content, the output and manifest record the limit, warning, and limitation.
Numeric parameters are validated. Negative limits, zero where a positive runtime value is required,
or non-numeric strings fail during config loading with the field name in the error. Integer-like
strings and integer-valued floats are normalized before runtime use, and ambiguous boolean strings
such as `"maybe"` are rejected instead of being treated as truthy or falsey by accident.

The manifest includes `module_statuses` for every configured module. A module can be `used`,
`configured_not_run_no_matching_entries`, or `configured_backend_not_selected_for_matching_entries`,
which makes it clear when a route was configured but no source entry exercised it.

## Provider Settings

Providers are deliberately layered. A provider can be configured, unavailable, skipped, attempted,
or used; those states are recorded in per-file metadata.

```toml
[providers.ocr]
name = "tesseract"
enabled = true
language = "eng"
timeout_seconds = 30
preprocess = "none"
min_characters = 4
min_alnum_ratio = 0.35
min_confidence = 35
auto_invoke = true

[providers.vlm]
name = "openai_compatible"
enabled = true
base_url = "http://127.0.0.1:14830/v1"
model = "Qwen2.5-VL-3B-Instruct-Q4_K_M.gguf"
max_tokens = 300
temperature = 0
prompt = "Describe visible evidence only."
auto_invoke = false
```

`auto_invoke = false` records the provider configuration and route without making a model request.
Set it to `true` only when the endpoint is running and you want the backend to call it. Local
OpenAI-compatible discovery probes the configured base URL and common local defaults, including
Jetson examples:

```toml
[providers.llm_text]
base_url = "http://127.0.0.1:14829/v1"
auto_detect = true
auto_invoke = false

[providers.vlm]
base_url = "http://127.0.0.1:14830/v1"
auto_detect = true
auto_invoke = false
```

Discovery only sends a short GET to `/models`; source files are sent only by provider execution
paths, and only when the provider is enabled and `auto_invoke = true`.
Provider task names, provider names, and numeric runtime settings are validated at config load time.
Providers are also filtered by profile/runtime gates. Tool-backed providers such as Tesseract OCR
and ffmpeg frame sampling require external tools to be allowed. Model-backed providers such as VLM,
text LLM, speech, chart specialists, and document intelligence require local models to be allowed.

## Tool Overrides

External tools are detected automatically on PATH when allowed. Use `[tools.<name>]` only to pin a
path, change an executable name, set a timeout, or disable a tool:

```toml
[tools.ffprobe]
path = "/usr/bin/ffprobe"
timeout_seconds = 15

[tools.file]
enabled = false
```

Known tool keys are `file`, `getfacl`, `ffprobe`, `ffmpeg`, `tesseract`, `libreoffice`,
`whisper_cpp`, `radare2`, and `capa`.
Missing tools are reported in the manifest/report/stdout capability summary and do not fail normal
conversion.

Current core provider behavior:

- OCR: Tesseract is invoked when enabled, allowed by profile, and available. The backend uses
  `pytesseract` plus the `tesseract` executable, records language/config/timeout, and accepts text
  only after configured confidence, minimum-character, and alphanumeric-ratio checks.
- VLM: OpenAI-compatible HTTP vision calls can be invoked when explicitly enabled.
- Image route classification, chart, audio classifier, diarization, CAD, scientific, geospatial, and
  binary metadata providers expose status and routing hooks. Heavy model-backed adapters remain
  contract-only unless explicitly implemented and configured.
- Document intelligence: a Docling adapter is present, but it runs only when the `docling` Python
  package imports successfully, the provider is configured as `docling`, and `auto_invoke=true`.
  On Python 3.8 Jetson, setup creates an isolated Python 3.10/3.11 env when available and the
  adapter can bridge through that env. That stack can be large, so setup records size/time notes and
  uses a longer external-env timeout.
- Video frame settings (`sample_frames`, `max_frames`, `interval_seconds`, `output_format`, `ocr`,
  `vlm`, and `preserve_frames`) are reflected in per-video stage plans. When `sample_frames=true`,
  `auto_invoke=true`, and ffmpeg is available, frames are actually sampled into a temporary runtime
  directory. Paths are omitted and files are cleaned unless `preserve_frames=true` is explicitly
  configured.
- Speech settings (`transcribe`, `translate`, `language_detection`, `model_path`, `device`,
  `timeout_seconds`) are reflected in audio/video stage plans with clear provider blockers. The
  faster-whisper and whisper.cpp hooks execute only with a configured local model path; model ids
  are not downloaded implicitly.
- Audio classifier settings expose the route for `speech|music|noise|mixed|unknown` classification.
  The media backend also records a deterministic metadata-only audio kind such as `silence`,
  `very_short`, `speech_unknown`, `music_unknown`, `mixed_unknown`, or `unknown_audio_content`.
  Diarization settings expose the planned speaker-turn schema. Neither fabricates labels or
  transcripts when the configured model/provider is absent.
- CAD/scientific/geospatial/binary metadata providers are schema-only. They may use installed
  libraries such as `ezdxf`, `h5py`, `netCDF4`, `astropy`, `pyarrow`, `pyshp`, `pefile`,
  `macholib`, `shapely`, `pyproj`, or `lief`, but they do not execute files, render geometry, or
  dump large arrays.

Custom keys are preserved in provider `params`, so local deployments can add model paths,
temperature, prompt policy, tenant IDs, or tool-specific settings without changing the schema.

The top-level manifest includes `provider_statuses` for the configured providers even if the run
contains no image/audio/video files. Per-file image and media records also include family-specific
provider statuses, route plans, and stage blockers.

The manifest and `all2text doctor` also include `provider_family_statuses`. This is a broader
catalog of researched provider candidates such as Docling, PaddleOCR-VL, GLM-OCR, olmOCR,
CLIP/SigLIP, DePlot, UniChart, ChartGemma, YAMNet/PANNs/OpenBEATs/CLAP, faster-whisper,
whisper.cpp, pyannote, ezdxf, IfcOpenShell, h5py/netCDF4/astropy/pyarrow/scipy, pyshp/pyproj,
pefile/macholib/LIEF/capa/radare2. Each row reports lifecycle flags such as `configured`,
`auto_detected`, `dependency_found`, `executable_found`, `endpoint_reachable`, `attempted`,
`used`, `skipped`, `failed`, `disabled`, `missing`, and `error`.

`provider_execution_summary` is a compact view over the same data. It separates installed Python
providers, installed-but-contract-only libraries, external tools, reachable OpenAI-compatible
endpoints, local model file matches, implemented/executable providers, contract-only providers, and
blockers.

The top-level manifest also includes `capabilities`, which lists:

- active automatic settings and safety gates;
- available/missing optional Python libraries;
- external tool status, including configured paths, disabled states, and executable-not-found states;
- discovered model-file matches under configured model roots;
- a compact summary copied into stdout and `_conversion_report.txt`.

## Truthfulness

Provider booleans in manifests mean what they say:

- `ocr_used=true` only when OCR returned accepted text.
- `vlm_used=true` only when a VLM request returned accepted text.
- `llm_used=true` only when a text LLM result was actually used.

Unavailable providers are not silent failures. Outputs include provider status, fallback reasons,
and limitations so downstream ingestion can distinguish extracted text from a safe summary.

MarkItDown is included in the PyPI extras only on Python versions where the published package is resolvable; the native all2text document backends do not depend on it.

Scientific extras use Python-version markers so older supported Python runtimes receive compatible package versions where upstream wheels exist.

CAD extras use Python-version markers so older supported Python runtimes receive compatible ezdxf versions where upstream wheels exist.

Document extras constrain lxml on older supported Python runtimes to avoid forcing source builds that require libxml2/libxslt development headers.

Some source-build-heavy PyPI packages are guarded by Python-version markers on older runtimes so the advertised install command does not require system compiler headers or native development libraries.

Install and diagnostics commands:

```bash
python -m pip install .
python -m all2text SOURCE_FOLDER TARGET_FOLDER
all2text doctor
all2text install-tools
```

The pip command installs the Python package and safe PyPI dependencies. External binaries and model files are detected at runtime or configured explicitly.

## Jetson Install Notes

On the current Jetson Python 3.8 environment, the following optional packages installed safely from
binary wheels or small pure-Python wheels: `ebooklib`, `odfpy`, `mutagen`, `piexif`, `rarfile`,
`xlrd`, `pyshp`, `pyproj`, `pefile`, `ezdxf`, `netCDF4`, `astropy`, `pyarrow`, `h5netcdf`, `h5py`,
`filetype`, `python-magic`, `py7zr`, `macholib`, `lief`, and `faster-whisper`.

Provider blockers and external-env notes observed on Jetson:

- `docling`: the active Python 3.8 runtime is too old for current Docling wheels. Setup uses a
  Python 3.10/3.11 venv under the external tools directory when available; the install can pull a
  large Torch/document stack and may take a long time or hours on ARM.
- `paddleocr`: package resolution is possible, but the dry-run plan adds a large pinned
  `opencv-contrib-python` stack alongside the existing OpenCV install and still does not install
  PaddleOCR-VL model files. Treat it as a deliberate external install, not a normal default.
- `pyannote.audio`: resolver backtracking ended at unavailable GPU/torchaudio-era dependencies.
  Installing torchaudio over NVIDIA's Jetson Torch build is not considered safe by default.
- Docling/PaddleOCR-VL/GLM-OCR/olmOCR/ChartGemma/UniChart/DePlot/faster-whisper model weights are
  external. Put them outside the repo, for example under `/data/models`, and configure `model_path`
  or a local endpoint. The faster-whisper hook requires that local path and will not download a
  model id implicitly. Do not commit model files or runtime caches.

Manual Jetson setup update, 2026-06-08: radare2 was installed through the OS package manager; faster-whisper base and small plus whisper.cpp base models were downloaded into external model storage; Docling 2.91.0 was installed in an isolated Python 3.11 CPU environment with a smoke conversion. The setup planner now detects that environment as satisfied and uses a pinned CPU-index install command for future Docling setup.

Docling Jetson fix: the isolated Docling environment uses the CPU PyTorch index and replaces the full OpenCV wheel with opencv-python-headless to avoid the Jetson static TLS OpenGL loader failure during RapidOCR/table-model imports.
