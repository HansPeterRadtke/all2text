# Testing and Development

## Setup

```bash
cd /data/src/github/all2text
python -m pip install -e '.[dev]'
```

Core tests use only the Python standard library plus pytest.

## Checks

```bash
python -m compileall -q src
pytest
```

## Test Coverage Goals

The test suite covers:

- scan-first behavior;
- mirrored folder layout;
- exact text preservation;
- structured text preservation and parse metadata;
- extension/content mismatch classification;
- safe binary fallback;
- archive listing and archive path safety;
- manifest and report generation;
- symlink safety;
- deterministic collision handling;
- CLI and public API behavior;
- registry selection;
- placeholder coverage for image, audio, video, document, scientific, CAD, database, email, ebook,
  font, executable, and container categories.

## Repository Hygiene

Generated conversion outputs, caches, logs, temporary model files, and local runtime artifacts should
not be committed. Runtime experiments belong under `/data/var`, not under the repository.

