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
```

Config is mainly for overrides and controls. Explicit config wins over automatic discovery:

- set `auto_detect_python = false` to avoid importing optional PyPI libraries;
- set `auto_detect_tools = false` to avoid PATH/default executable discovery unless a tool path is
  explicitly configured;
- set `auto_detect_local_models = false` to avoid common local endpoint discovery;
- set `allow_external_tools = false` or `allow_local_models = false` to block those classes entirely;
- set tool paths, executable names, provider base URLs, models, timeouts, and `auto_invoke`
  behavior in the relevant sections.

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
selection falls back through the normal ordered registry. This lets text GeoJSON or text CAD stay
exactly preserved while binary variants fall through to safe placeholders.

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
auto_invoke = false

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

Known tool keys are `file`, `getfacl`, `ffprobe`, `ffmpeg`, `tesseract`, and `libreoffice`.
Missing tools are reported in the manifest/report/stdout capability summary and do not fail normal
conversion.

Current core provider behavior:

- OCR: Tesseract can be invoked when explicitly enabled and available.
- VLM: OpenAI-compatible HTTP vision calls can be invoked when explicitly enabled.
- Chart, document intelligence, speech, and video frame providers expose status and routing hooks;
  execution adapters remain roadmap unless a custom backend implements them.
- Video frame settings (`sample_frames`, `max_frames`, `interval_seconds`, `output_format`, `ocr`,
  and `vlm`) are reflected in per-video stage plans even when `auto_invoke=false`, so downstream
  jobs can see exactly what would run and why it did not.
- Speech settings (`transcribe`, `translate`, `language_detection`, `model_path`, `device`,
  `timeout_seconds`) are reflected in audio/video stage plans with clear provider blockers.

Custom keys are preserved in provider `params`, so local deployments can add model paths,
temperature, prompt policy, tenant IDs, or tool-specific settings without changing the schema.

The top-level manifest includes `provider_statuses` for the configured providers even if the run
contains no image/audio/video files. Per-file image and media records also include family-specific
provider statuses, route plans, and stage blockers.

The top-level manifest also includes `capabilities`, which lists:

- active automatic settings and safety gates;
- available/missing optional Python libraries;
- external tool status, including configured paths, disabled states, and executable-not-found states;
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
