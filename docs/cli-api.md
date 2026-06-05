# CLI and API Usage

## Installation

Core install:

```bash
cd /data/src/github/all2text
python -m pip install -e .
```

Development install:

```bash
python -m pip install -e '.[all-pip,dev]'
```

Future package install:

```bash
python -m pip install 'all2text[all-pip]'
```

`all-pip` installs normal Python/PyPI packages only. It does not install external binaries,
llama.cpp servers, local models, Tesseract itself, ffmpeg/ffprobe, LibreOffice, or system `file`.
Optional dependency groups enable native paths and future/external backends. Installed optional
Python packages are used automatically. External binaries and local model endpoints are detected
automatically when allowed and available; missing capabilities are reported and are not fatal.

```bash
python -m pip install -e '.[documents,images,media,ocr,scientific,cad,geospatial]'
```

## CLI

```bash
python -m all2text /path/to/source /path/to/output
all2text SOURCE_FOLDER TARGET_FOLDER
all2text --config all2text.default.toml SOURCE_FOLDER TARGET_FOLDER
all2text --capabilities
```

The target folder must not be inside the source folder by default.

Options:

- `--version`: print package version.
- `--config PATH`: load a TOML config for module and provider selection.
- `--capabilities` / `--detect-capabilities`: print automatic discovery status and exit.
- `--profile PROFILE`: advanced safety override; choose `auto`, `core`, `pip`, `tools`,
  `local-models`, or `full`.
- `--no-file-command`: skip the optional `file(1)` probe.
- `--no-copy-source-stat`: skip `copystat`/xattr copying to outputs.
- `--allow-target-inside-source`: bypass the target-inside-source guard.
- `--max-archive-members N`: cap archive member listing length.

The command prints the manifest summary as JSON and writes:

```text
TARGET_FOLDER/_conversion_manifest.json
TARGET_FOLDER/_conversion_report.txt
```

Default behavior is automatic: deterministic core extraction plus installed optional Python
libraries, safe external tools found on PATH/configured paths, and configured/reachable local
OpenAI-compatible endpoints. Endpoint discovery uses bounded local `/v1/models` GET requests and
does not send source files. Actual model/VLM calls require enabled providers and `auto_invoke=true`.

Profile meanings as safety presets:

- `core`: stdlib-only deterministic extraction; no optional Python libraries, shell tools, or models.
- `pip`: Python/PyPI-only extraction; disables shell tools and local models.
- `tools`: allow optional shell tools when configured and available.
- `local-models`: allow configured model endpoints/providers without enabling shell tools.
- `full`: allow installed Python libraries, configured tools, and configured model providers.

The printed summary includes automatic detection gates, `capability_summary`, and
`provider_summary`. The manifest and report include full optional Python package status, external
tool status, and provider status.

Every source non-directory entry receives one output path by appending `.txt` to the full original
filename. Examples:

```text
report.pdf -> report.pdf.txt
archive.tar.gz -> archive.tar.gz.txt
Makefile -> Makefile.txt
```

## Python API

```python
from all2text import run

manifest = run("source", "out")
```

`run(source_folder, target_folder)` is the public entrypoint. The source tree is scanned before
target paths are created and before conversion starts.

With options:

```python
from all2text import run
from all2text.models import RunOptions

manifest = run(
    "source",
    "out",
    options=RunOptions(use_file_command=False, copy_source_stat=False),
)
```

With config:

```python
from all2text import load_config, run

config = load_config("all2text.default.toml")
manifest = run("source", "out", config=config)
```

The config file can choose backends per file family and configure provider parameters:

```toml
[modules]
image = "image_analysis_backend"
document = "document_native_backend"

[providers.vlm]
name = "openai_compatible"
enabled = true
base_url = "http://127.0.0.1:14830/v1"
model = "Qwen2.5-VL-3B-Instruct-Q4_K_M.gguf"
auto_invoke = false
```

`auto_invoke = false` records provider status without making network/model calls. Set it to `true`
only when the local service is running and you want the backend to call it.

With a custom registry:

```python
from all2text import run
from all2text.registry import build_default_registry

registry = build_default_registry()
registry.register(MySpecialBackend())
manifest = run("source", "out", registry=registry)
```

Custom backends are selected in registration order, so register more specific backends before broad
fallbacks when building a custom registry.

The returned manifest is already JSON-safe. It has the same structure as
`_conversion_manifest.json`, including source metadata, classification, converter name,
`converter_metadata`, warnings/errors, limitations, and output paths for each source entry.


`python -m all2text ...` and `all2text ...` are equivalent entry points. Both call `all2text.cli:main`.
