# Metadata Strategy

Every per-file output starts with three audit sections before extracted content:

```text
=== Metadata ===
=== Classification ===
=== Conversion ===
=== Extracted Content ===
```

## Collected Metadata

Core metadata includes:

- source path, filename, suffixes, entry type, symlink target;
- stat data, permissions, timestamps, inode/device when available, UID/GID and owner/group names;
- size;
- first header bytes as hex and safe ASCII;
- `looks_text` heuristic;
- SHA-256 for files up to `RunOptions.max_hash_bytes`;
- Python `mimetypes` guess;
- optional system `file` MIME and description;
- xattr names and small base64 previews when supported.

Metadata collection is best-effort. Failures become explicit warnings or errors in the manifest.

## Classification Metadata

Classification is layered:

1. Extension hints from `taxonomy.EXTENSION_HINTS`.
2. MIME hints from Python and optional `file`.
3. Content signatures from magic bytes or lightweight text signatures.

Strong content signatures override extension hints. The final classification records the chosen
category, concrete format, confidence, evidence list, warnings, and whether the file is safe for exact
text preservation.

## Manifest and Report

`_conversion_manifest.json` stores machine-readable records for every source entry. The summary
includes category, format, converter, warning, error, collision, and limitation counts.

`_conversion_report.txt` is a compact human-readable summary for quick inspection.

## Metadata Copying

By default, `all2text` attempts `shutil.copystat` and xattr copying from source files to their text
outputs. This can be disabled:

```bash
all2text --no-copy-source-stat source out
```

Metadata copying is skipped for symlinks and non-regular entries.

