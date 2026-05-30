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

The final verification commands and commit details are recorded in the operational report under
`/data/var/codex_logs`.

