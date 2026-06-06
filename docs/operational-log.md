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

## 2026-06-06 Jetson provider implementation session

Context:

- Worktree: `/data/src/github/all2text`
- Read-only reference only: `/data/src/github/devtests/rag_tests`
- No edits made to devtests, KnowMoreDiRT, model files, runtime caches, unrelated repos, or unrelated logs.
- Startup environment: `hans@jetson`, `pwd=/data/src/github/all2text`, Python 3.8.10 in the active `/data` environment.
- Visible model/reasoning settings were not exposed by the shell environment; the supervisor/user launch context stated `gpt-5.5` with `xhigh` reasoning.
- Baseline head: `df793f7 Expand research roadmap with ranked provider candidates`.
- Implementation checkpoint: `4a53b43 Implement provider catalog and schema probes`.

Read-only startup checks:

- `git status --short`: clean at baseline.
- Recent commits showed the normal install/module-entry-point sequence through `df793f7`.
- `all2text` was not initially installed as a command in the active shell, but `PYTHONPATH=src python -m all2text doctor` worked.
- External tools detected on Jetson: `ffmpeg`, `ffprobe`, `tesseract`, `file`, `getfacl`, and `libreoffice`.
- Local text endpoint `http://127.0.0.1:14829/v1` was reachable with `Qwen2.5-14B-Instruct-Q4_K_M.gguf`; the common local vision endpoint on `14830` was not reachable.

Installation findings:

- Installed or confirmed safe optional Python packages from normal pip/wheels: `ebooklib`, `odfpy`, `mutagen`, `piexif`, `rarfile`, `xlrd`, `pyshp`, `pyproj`, `pefile`, `ezdxf`, `netCDF4`, `astropy`, `pyarrow`, `h5netcdf`, `h5py`, `filetype`, `python-magic`, `py7zr`, `macholib`, `lief`, and `faster-whisper`.
- Did not install huge or gated model weights. No model files or runtime caches were placed in the repo.
- Did not install `torchaudio`; the active environment already has a Jetson/NVIDIA Torch stack, and replacing it blindly would be unsafe.
- Blockers documented: `docling` had no compatible distribution in the active index/runtime; `paddleocr` resolved only through a large OpenCV/Paddle stack and still needed external PaddleOCR-VL model files; `pyannote.audio` resolver backtracking hit unavailable GPU/torchaudio-era dependencies; `whisper.cpp`, `radare2`, and `capa` executables were not present.

Mechanisms implemented:

- Added a provider-family catalog and typed status surface for document OCR/layout, OCR, image routing, VLM, chart, audio classification, ASR, diarization, video, CAD/BIM, scientific/geospatial, and binary metadata providers.
- Added lifecycle/evidence flags: `configured`, `auto_detected`, `dependency_found`, `executable_found`, `endpoint_reachable`, `attempted`, `used`, `skipped`, `failed`, `disabled`, `missing`, and `error`.
- Extended `all2text --capabilities`, manifests, and text reports with `provider_family_statuses`.
- Added deterministic image structure profiling and a broader taxonomy: photo, screenshot/UI, document page, table screenshot, chart/plot, diagram/flowchart/UML/network, circuit schematic, mechanical technical drawing, architectural floor plan, map/plan/heatmap, scientific/medical image, painting/illustration/art, abstract/texture, logo/icon, and unknown.
- Added a chart schema that reports route/status/evidence and explicitly does not invent titles, axes, series, tables, or values.
- Added audio route planning for metadata, kind classification, ASR/language/translation, and diarization without fake transcription or speaker labels.
- Added bounded schema probes for installed libraries: NumPy NPY/NPZ, h5py HDF5, netCDF4, astropy FITS, pyarrow Parquet, scipy MAT, ezdxf DXF, IfcOpenShell IFC when available, pyshp Shapefile, SQLite GeoPackage, ELF headers, pefile PE, and macholib Mach-O.
- Kept binaries non-executable: no binary execution, disassembly, decompilation, unpacking, geometry rendering, feature dump, coordinate transform, or large array dump.
- Tightened configured ASR status so an installed package such as `faster-whisper` is not reported usable unless a local model reference is configured.

Capability snapshot after install:

- Installed `all2text --capabilities` reported `profile=auto`, 14 configured `provider_statuses`, and 53 `provider_family_statuses`.
- Available family providers were: `astropy`, `deterministic_chart_geometry`, `deterministic_image_profile`, `ezdxf`, `ffprobe`, `file`, `h5py`, `netcdf4`, `numpy`, `opencv`, `pefile`, `pyarrow`, `pyshp`, `scipy`, and `tesseract`.
- Missing or unavailable family providers numbered 38 and included the expected heavy/model-backed or absent-tool routes.
- Default configured speech status remained disabled by config. A configured `faster_whisper` provider without `model_path` is now unavailable with an explicit no-model-download blocker.

Validation:

- `PYTHONPYCACHEPREFIX=/data/tmp/all2text_pycache python -m py_compile src/all2text/providers.py tests/test_provider_contracts_and_routes.py`: passed.
- `PYTHONPATH=src PYTHONPYCACHEPREFIX=/data/tmp/all2text_pycache pytest -q tests/test_provider_contracts_and_routes.py`: passed, 7 tests.
- `PYTHONPYCACHEPREFIX=/data/tmp/all2text_pycache python -m compileall -q src tests`: passed.
- `PYTHONPATH=src PYTHONPYCACHEPREFIX=/data/tmp/all2text_pycache pytest -q`: passed, 90 passed and 6 skipped across 96 collected tests, with the pre-existing `pythonpath` pytest warning.
- `python -m pip install .`: passed and installed `all2text-0.1.0` through the normal wheel path.
- Installed CLI smoke: `all2text --capabilities` parsed successfully; a one-file conversion under `/data/tmp/all2text_smoke_src` completed with one text file converted.
- `git diff --check`: passed before the implementation commit.
- Ruff was not run because `python -m ruff --version` reported `No module named ruff`.

Hardcoding and scope scan:

- Production-code scan found no devtests, benchmark, fixture, question-ID, expected-answer, hidden-answer, or question-string branches.
- The only `owner` hit in production was the pre-existing OS filesystem metadata helper `owner_name`, not a domain-specific handler.
- Documentation references to `/data/src/github/devtests/rag_tests` remain read-only context references.
- Public all2text install/CLI path remains the normal `python -m pip install .`; no dependency extras were reintroduced for the normal user path.

Benchmark and score note:

- No rag_tests benchmark was rerun or modified; devtests was used only as read-only design context.
- There is no internal all2text score calculation comparable to the DRT benchmark in this session. The validation signal for this checkpoint is the full local pytest suite, installed CLI capability output, and smoke conversion.
- Official-score caveat: none claimed. This checkpoint improves provider architecture, truthfulness, route planning, and safe schema probes, but model-backed extraction quality still depends on external tools/models being installed and configured outside the repo.

Next best technical step:

- Implement one real heavy-provider execution adapter at a time behind the new contract, starting with the smallest safe target: bounded local chart model inference or `whisper.cpp` ASR once model files and executables are explicitly configured outside the repo.

## 2026-06-06 Jetson real provider execution continuation

Context and startup:

- Worktree: `/data/src/github/all2text`; edits were limited to this repository.
- Read-only reference only: `/data/src/github/devtests/rag_tests`; no devtests, KnowMoreDiRT, DRT,
  model, cache, runtime-log, or unrelated-repo files were modified.
- Visible shell settings did not expose model/reasoning variables; the supervisor/user context
  stated `gpt-5.5` with `xhigh` reasoning.
- Baseline status: `## master...origin/master`, head
  `d231a05 (HEAD -> master, origin/master) Record provider implementation session`.
- Recent commits inspected: `d231a05`, `4a53b43`, `df793f7`, `97828d6`, `4feb06b`, `1007569`,
  `6c5c403`, and `a010714`.

Runtime capability findings:

- External tools present: `/usr/bin/file`, `/usr/bin/getfacl`, `/usr/bin/ffprobe`,
  `/usr/bin/ffmpeg`, `/usr/bin/tesseract`, and `/usr/bin/libreoffice`.
- External tools absent: `whisper`, `whisper.cpp`, `whisper-cli`, `main`, `radare2`, `rabin2`,
  and `capa`.
- Python packages present in the active environment included `transformers`, `torch`,
  `pytesseract`, `PIL`, `cv2`, `faster_whisper`, `mutagen`, `ezdxf`, `netCDF4`, `astropy`,
  `pyarrow`, `scipy`, `pyproj`, `shapely`, `pefile`, `macholib`, `lief`, and `numpy`.
- Python packages absent included `docling`, `paddleocr`, `paddle`, `scenedetect`, `whisper`, and
  `ifcopenshell`.
- Local text endpoint `http://127.0.0.1:14829/v1` was reachable with
  `Qwen2.5-14B-Instruct-Q4_K_M.gguf`; the default vision endpoint on `14830` was not reachable.
- Local model roots contained faster-whisper snapshots, DePlot/UniChart chart model directories
  under `/data/models/rag_tests/vision`, Qwen text GGUFs, and Qwen2.5-VL llama.cpp files.
- Direct `python -m pip install docling` failed with `No matching distribution found for docling`.

Mechanisms implemented:

- Tesseract OCR now runs as a real adapter through `pytesseract` and the configured Tesseract
  executable. It records language, config, timeout, word counts, raw preview, mean confidence, and
  applies configurable minimum confidence, minimum character, and alphanumeric-ratio gates before
  setting `ocr_used=true`.
- ffmpeg is now reported as an available core-used tool when present, independent of whether frame
  sampling is configured. The video frame provider remains opt-in, but when `sample_frames=true` and
  `auto_invoke=true` it extracts interval or keyframe frames into a bounded runtime directory,
  records counts/metadata, and cleans temporary files unless `preserve_frames=true`.
- Media profiles now include deterministic audio-kind routing from streams, tags, duration,
  channels, and WAV waveform stats. It can report `silence`, `very_short`, `speech_unknown`,
  `music_unknown`, `mixed_unknown`, `no_audio_stream`, or `unknown_audio_content` with evidence and
  confidence.
- Speech hooks now execute configured local faster-whisper and whisper.cpp providers only when a
  local model path exists. Model ids are not downloaded implicitly. Parakeet/Canary and other heavy
  routes remain blocked unless dependencies and safe adapters exist.
- Docling has a real gated adapter path, but the current Jetson environment cannot install/import
  the package, so doctor reports an exact dependency blocker and PDF conversion falls back safely.
- Default CAD and geospatial routing now uses safe schema backends. Textual GeoJSON, KML, and CAD
  source text is preserved inside those outputs while bounded schema metadata is emitted.
- GeoJSON and KML schema probes were added, with optional Shapely bounds and pyproj CRS parsing.
- Executable metadata now augments ELF/PE/Mach-O probes with a bounded LIEF summary when installed.
- Doctor/capabilities and manifests now include `provider_execution_summary`, separating installed
  Python providers, installed-but-contract-only libraries, external tools, reachable endpoints,
  discovered model files, implemented/executable providers, contract-only providers, and blockers.
- The generated text report now includes the compact provider execution summary.

Validation results:

- Focused tests:
  `PYTHONPYCACHEPREFIX=/data/tmp/all2text_pycache PYTHONPATH=src python -m pytest -q tests/test_provider_contracts_and_routes.py tests/test_configured_providers_and_documents.py tests/test_parity_contract.py`
  passed, 39 selected tests.
- Full tests:
  `PYTHONPYCACHEPREFIX=/data/tmp/all2text_pycache python -m compileall -q src tests` passed, and
  `PYTHONPYCACHEPREFIX=/data/tmp/all2text_pycache PYTHONPATH=src python -m pytest -q` passed.
  Collection count after changes was 103 tests.
- `git diff --check` passed.
- `python -m ruff --version` failed with `No module named ruff`; ruff was not run.
- Plain install:
  `python -m pip install .` built and installed `all2text-0.1.0` successfully through the normal
  install path, with no extras.
- Installed doctor/capabilities:
  `python -m all2text doctor` and `all2text --capabilities` both emitted
  `provider_execution_summary`; installed reports showed available external tools
  `ffmpeg`, `ffprobe`, `file`, `getfacl`, and `tesseract`.
- Installed smoke conversion in `/data/tmp` converted five files. The smoke used Tesseract OCR on a
  PNG, sampled one MP4 frame with ffmpeg and cleaned it, classified a WAV as `silence`, and emitted
  GeoJSON schema metadata through the geospatial backend.
- Faster-whisper smoke with the local tiny.en snapshot executed on a 0.5 second silent WAV. It
  loaded `/data/models/faster_whisper/models--Systran--faster-whisper-tiny.en/snapshots/0d3d19a32d3338f10357c0889762bd8d64bbdeba`,
  returned language `en` with probability `1.0`, and correctly returned no transcript text for
  silence instead of fabricating content.

Hardcoding and scope scan:

- Production-code scan found no question IDs, benchmark labels, expected-answer literals,
  hidden-answer use, question-string branches, current-failure entities, fixture-name branches, or
  domain-specific owner/reviewer/customer/ticket/runbook handlers.
- The only production `owner` hit was the pre-existing filesystem metadata helper `owner_name`.
- Hits for `devtests`, `rag_tests`, `benchmark`, and `fixture` were documentation lineage notes or
  generic test wording, not production logic.

Score/failure-count note:

- No internal all2text benchmark was run, and no DRT-style score applies to this repository. The
  changed validation count is local tests increasing to 103 collected tests, with full pytest
  passing. Official benchmark score: not claimed.

Public API and install status:

- Public API remains unchanged: `run(source_folder, target_folder, *, options=None, registry=None,
  config=None)` and the CLI/module entry points remain compatible.
- Normal install remains exactly `python -m pip install .`; no normal-user dependency extras were
  added.

Commit/push:

- Commit hash: `c722447` before log-hash amend; final amended hash is recorded in git history for
  this entry.
- Push target: `origin/master`.

Remaining blockers and next best step:

- Docling is blocked by unavailable package resolution in this Python/runtime.
- PaddleOCR/PaddleOCR-VL, GLM-OCR, olmOCR, chart specialists, pyannote/diarization, radare2, capa,
  and whisper.cpp remain unavailable or contract-only unless their external packages, model files,
  and executables are deliberately installed/configured outside the repo.
- The next best technical step is PDF page rendering plus OCR fallback, followed by per-frame OCR/VLM
  analysis over the new ffmpeg frame sampler, because those build directly on executable providers
  now in place.
