# Bootstrap Report

Date: 2026-05-30

Repository: `https://github.com/HansPeterRadtke/all2text`

Working path: `/data/src/github/all2text`

## Source Analysis

The bootstrap reviewed `/data/src/github/devtests/rag_tests` read-only. The most relevant prior work
was the universal converter, which demonstrated:

- scan-first tree traversal;
- mirrored output paths with `.txt` appended to the complete original filename;
- layered extension/MIME/content-signature classification;
- strong content signatures overriding misleading extensions;
- rich metadata and classification sections in every output;
- manifest/report generation;
- archive listing without extraction;
- symlink recording without traversal;
- deterministic collision naming;
- safe binary fallback;
- explicit limitations for audio/video/specialist formats.

## Implemented Repository

`all2text` is an independent Python package with:

- `src/all2text` package layout;
- public `run(source_folder, target_folder)` API;
- `all2text` CLI;
- modular scan, planning, detection, metadata, registry, backend, rendering, and reporting modules;
- core exact-text backend;
- archive, email, EPUB, SQLite metadata, media metadata, image placeholder, document placeholder,
  scientific placeholder, CAD placeholder, font placeholder, executable placeholder, container
  placeholder, and binary fallback backends;
- detailed docs and examples;
- comprehensive tests.

## Truthfulness Policy

Core backends do not claim deep semantic extraction for formats they only summarize. Placeholder
outputs include limitation text and metadata so downstream systems can route those files to stronger
optional backends later.

## Verification

Final verification was run on the Jetson default Python 3.8 environment:

```bash
python -m compileall -q src tests
python -m pytest -q tests/test_placeholder_coverage.py \
  tests/test_workflow_outputs.py::test_content_signature_overrides_misleading_extension \
  tests/test_workflow_outputs.py::test_archive_listing_is_safe_and_manifested
python -m pytest -q
```

Results:

- compile check: passed
- targeted tests: `14 passed`
- full tests: `24 passed`

Initial implementation commit:

```text
d40e138 Bootstrap all2text package
```

The initial commit was pushed to `origin/master`. The operational report is stored under
`/data/var/codex_logs/all2text_bootstrap_20260530.md`.

## 2026-05-30 Parity Update

This follow-up compared the package again against `/data/src/github/devtests/rag_tests` with special
attention to `rag_tests/rag_tests/universal.py`, CLI wiring, converter behavior, metadata handling,
detection/classification, reports, and universal converter tests.

Implemented additions:

- ACL summary collection with safe warnings when `getfacl` is unavailable.
- Recursive JSON-safe manifest/conversion metadata rendering for paths, dataclasses, bytes,
  datetimes, sets, exceptions, and platform objects.
- Layered name hints for extensionless convention files such as `Makefile`, `Dockerfile`, `README`,
  `LICENSE`, and related files.
- Classification precedence so generic printable text does not override more specific extension/name
  evidence, while strong content signatures still override misleading extensions.
- RTF structured-text preservation with lightweight metadata.
- EML original source preservation alongside parsed header/body/attachment metadata.
- Binary geospatial placeholder behavior while preserving GeoJSON/KML text.
- BZIP2/XZ compressed stream summaries.
- Explicit image/media placeholder status for OCR, VLM, chart, document, transcription, and
  frame/scene analysis when no provider is configured.
- Output file reservation before backend conversion.
- Manifest `converter_metadata` entries.
- Expanded parity tests.
- Dedicated llama.cpp/model setup documentation for external Jetson model artifacts.

Verification for this update is tracked in `docs/operational-log.md` and the runtime log
`/data/var/codex_logs/all2text_20260530T104100Z.md`.
