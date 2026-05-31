# Operational Log

## 2026-05-30 Jetson parity session

Context:

- Worktree: `/data/src/github/all2text`
- Read-only reference: `/data/src/github/devtests/rag_tests`
- Runtime log mirror: `/data/var/codex_logs/all2text_20260530T104100Z.md`

Required startup checks:

- `whoami`: `hans`
- `hostname`: `jetson`
- `pwd`: `/data/src/github/all2text`
- `git status --short --branch` in all2text: `## master...origin/master`
- `git log --oneline --decorate -n 20` in all2text:
  - `05a3548 (HEAD -> master, origin/master) Document bootstrap verification`
  - `d40e138 Bootstrap all2text package`
- `git status --short --branch` in `/data/src/github/devtests`: `## master...origin/master`, with unrelated untracked files under `DRT_tests/logs/`. No devtests files modified.

Baseline verification:

- `python -m compileall -q src tests`: passed.
- Bare `pytest`: failed before collection because the active executable could not import local `all2text`.
- `python -m pytest`: passed, 24 tests.

Comparison findings against `rag_tests/rag_tests/universal.py` and related tests:

- Existing all2text already mirrors the scan-first workflow, output naming, metadata/classification/content wrapper, deterministic collision naming, symlink recording, archive listing, media/image placeholders, and many advanced-format placeholders.
- Missing or weaker areas to implement now:
  - ACL summary collection from `getfacl` when available.
  - Explicit safe JSON serialization for `Path`, dataclass, bytes, datetime, sets, exceptions, and OS-specific objects.
  - Name-hint classification for extensionless or conventionally named text/source files.
  - Better classification priority so generic printable text does not override specific extensions such as Markdown/YAML/RTF.
  - RTF text preservation with safe parsed metadata instead of binary document placeholder behavior.
  - EML original-source preservation alongside parsed headers/body/attachment metadata.
  - Explicit geospatial placeholder behavior for binary geospatial formats such as Shapefile while preserving GeoJSON/KML text.
  - BZIP2/XZ stream summaries analogous to GZIP.
  - Clearer media/image placeholders for not-yet-transcribed/not-yet-analyzed optional-provider behavior.
  - Planned output file reservation before conversion, after scanning and target tree creation.
  - Documentation for llama.cpp/model setup and optional backend integration points.

Implementation plan:

1. Add operational logs before code edits.
2. Implement parity gaps in modular helpers/backends.
3. Expand tests for structured preservation, metadata, placeholders, serialization, output reservation, and classification precedence.
4. Update README and docs, including dedicated llama.cpp/model setup.
5. Run compileall, targeted tests, full `python -m pytest`, check bare `pytest`, commit, and push.

Implementation progress:

- Added recursive JSON-safe serialization and included `converter_metadata` in manifest entries.
- Added ACL summary collection and per-entry OS metadata.
- Added name-hint classification and refined precedence between generic text evidence and specific
  extension/name/MIME evidence.
- Added RTF structured-text handling, EML original-source preservation, binary geospatial
  placeholders, BZIP2/XZ stream summaries, media/image not-yet-analyzed placeholder status, and
  output file reservation before backend conversion.
- Added `tests/test_parity_contract.py` covering structured text preservation, EML raw source,
  name hints, geospatial behavior, compressed streams, JSON-safe metadata, output reservation, ACL,
  and OS metadata.

Interim verification:

- `python -m compileall -q src`: passed after implementation slice.
- `python -m pytest tests/test_parity_contract.py -q`: passed, 12 tests.
- `python -m pytest`: passed, 36 tests.

Final verification before commit:

- `python -m compileall -q src tests`: passed.
- `python -m pytest -q tests/test_parity_contract.py tests/test_workflow_outputs.py::test_content_signature_overrides_misleading_extension tests/test_placeholder_coverage.py`: passed, 25 tests.
- `python -m pytest`: passed, 36 tests.
- `pytest`: passed, 36 tests, with one warning from the older system pytest 6.2.5 about the unknown `pythonpath` config option. A root `conftest.py` keeps local `src` importable for that executable.
- `python -m ruff check .`: not run; `ruff` is not installed in `/data/venv`.

## 2026-05-31 configurable providers session

Context:

- Worktree: `/data/src/github/all2text`
- Read-only reference allowed: `/data/src/github/devtests/rag_tests`
- Baseline head: `ca21c9b Add configurable extraction providers`
- Baseline status: `## master...origin/master`

Baseline verification:

- `python -m py_compile $(rg --files src/all2text -g '*.py')`: passed.
- `pytest -q`: passed, 41 tests and 4 skipped.
- `python -m ruff --version`: unavailable in the active environment.

Implementation progress:

- Added module parameter accessors and wired native document parameters into XLSX/PDF/OpenDocument
  extraction.
- Added top-level manifest provider statuses so configured OCR, VLM/local llama.cpp, chart,
  document-intelligence, speech, and video-frame routes are visible even without matching files.
- Expanded provider defaults for OCR quality knobs, VLM/text LLM prompt/runtime settings, chart
  thresholds, document intelligence endpoint metadata, speech settings, and video frame sampling.
- Added configured media stage plans for speech, language detection, translation, frame sampling,
  frame OCR, and frame VLM without requiring model servers in tests.
- Added tests for global provider statuses, XLSX/PDF module limits, and video frame planning.

Verification:

- `python -m py_compile $(rg --files src/all2text -g '*.py')`: passed.
- `pytest tests/test_configured_providers_and_documents.py -q`: passed, 5 tests and 6 skipped.
- `python -m compileall -q src tests`: passed.
- `pytest -q`: passed, 43 tests and 6 skipped, with the existing pytest warning about `pythonpath`.
- `git diff --check`: passed.
- `python -m ruff check .`: not run; `ruff` is not installed in `/data/venv`.
