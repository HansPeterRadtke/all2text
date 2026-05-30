# CLI and API Usage

## Installation

Core install:

```bash
cd /data/src/github/all2text
python -m pip install -e .
```

Development install:

```bash
python -m pip install -e '.[dev]'
```

Optional dependency groups are declared for future/external backends. Installing them does not make
core placeholders claim extraction by itself; a backend still has to be registered or added to the
default registry.

```bash
python -m pip install -e '.[documents,markitdown,textract,ocr,scientific,cad]'
```

## CLI

```bash
all2text SOURCE_FOLDER TARGET_FOLDER
```

The target folder must not be inside the source folder by default.

Options:

- `--version`: print package version.
- `--no-file-command`: skip the optional `file(1)` probe.
- `--no-copy-source-stat`: skip `copystat`/xattr copying to outputs.
- `--allow-target-inside-source`: bypass the target-inside-source guard.
- `--max-archive-members N`: cap archive member listing length.

The command prints the manifest summary as JSON and writes:

```text
TARGET_FOLDER/_conversion_manifest.json
TARGET_FOLDER/_conversion_report.txt
```

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
