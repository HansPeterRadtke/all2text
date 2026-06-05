# Testing and Development

## Setup

```bash
cd /data/src/github/all2text
python -m pip install -e '.[dev]'
```

Core tests use only the Python standard library plus pytest.

## Checks

```bash
python -m compileall -q src tests
python -m pytest
```

Use `python -m pytest` when the shell `pytest` executable is attached to a different interpreter or
does not see the editable package. The repository also includes a root `conftest.py` bootstrap so
older pytest executables can import the local `src` package during development.

## Test Coverage Goals

The test suite covers:

- scan-first behavior;
- mirrored folder layout;
- exact text preservation;
- structured text preservation and parse metadata;
- RTF preservation as structured text;
- EML parsed metadata plus original source preservation;
- name-hint classification for extensionless convention files;
- extension/content mismatch classification;
- generic-text-vs-extension classification precedence;
- safe binary fallback;
- archive listing, compressed stream summaries, and archive path safety;
- manifest and report generation;
- JSON-safe manifest/conversion metadata for custom backend values;
- precreated output reservation before backend conversion;
- symlink safety;
- deterministic collision handling;
- CLI and public API behavior;
- config parsing, custom provider parameters, and CLI config usage;
- registry selection and configurable backend overrides;
- native DOCX/XLSX/PPTX/PDF extraction when optional dependencies are visible to the test
  interpreter;
- optional dependency fallback behavior;
- image provider routing without requiring a model server;
- layered audio/video stage reporting;
- placeholder coverage for image, audio, video, document, scientific, geospatial, CAD, database,
  email, ebook, font, executable, and container categories.

## Repository Hygiene

Generated conversion outputs, caches, logs, temporary model files, and local runtime artifacts should
not be committed. Runtime experiments belong under `/data/var`, not under the repository.


Module invocation smoke check:

```bash
PYTHONPATH=src python -m all2text --version
PYTHONPATH=src python -m all2text --capabilities
```
