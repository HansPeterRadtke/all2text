# CLI and API Usage

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

## Python API

```python
from all2text import run

manifest = run("source", "out")
```

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

