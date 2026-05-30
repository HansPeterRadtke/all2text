# Architecture

`all2text` is organized around a scan-plan-convert-report pipeline.

## Pipeline

1. `all2text.core.run` validates source and target roots.
2. `scanning.scan_source_tree` walks the tree with `os.scandir`, records directories, files,
   symlinks, and other filesystem entries, and never follows symlinks.
3. `planning.create_target_directories` mirrors directories under the target root.
4. `planning.reserve_output_files` assigns one output per non-directory entry by appending
   `.txt` to the complete source filename.
5. `metadata.collect_metadata` records stat, MIME, header, hash, xattr, and symlink metadata.
6. `detection.classify_path` combines extension hints, Python/system MIME hints, and content
   signatures into a layered classification record.
7. `registry.ConversionRegistry` selects a backend for the entry and classification.
8. `rendering.render_text_output` writes metadata, classification, conversion details, and
   extracted content into the per-file `.txt` artifact.
9. `reporting` writes `_conversion_manifest.json` and `_conversion_report.txt`.

The source scan is complete before target files are written. This prevents generated output from
affecting the conversion set and makes conversion manifests reproducible.

## Source Tree

```text
src/all2text/
  api.py              public run() entrypoint
  cli.py              argparse CLI
  core.py             orchestration
  detection.py        layered type detection and classification
  metadata.py         filesystem/content metadata collection
  models.py           dataclasses and runtime options
  planning.py         output path planning and collision naming
  registry.py         backend registry
  rendering.py        per-file text wrapper
  reporting.py        manifest/report summaries
  scanning.py         source tree traversal
  taxonomy.py         extension/MIME/category knowledge
  backends/           converter backend implementations
```

## Collision Policy

The planner uses casefolded names so a case-sensitive development machine still notices names that
would collide on case-insensitive filesystems. When a collision is detected, the output name receives
a deterministic `.collision-<hash>.txt` suffix. The manifest records the desired and actual names.

Directory-name collisions and output-file collisions are handled separately.

## Safety Policies

- Symlinks are recorded and never followed.
- Archives are listed but not extracted.
- Disk images are not mounted.
- Executables are not run or disassembled.
- Unsupported binary formats get byte signatures and printable string samples only.
- The target folder is rejected when it is inside the source folder unless explicitly allowed.

