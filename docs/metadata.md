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
- xattr names and small base64 previews when supported;
- ACL summary from `getfacl` on Linux when available;
- OS/platform information for the conversion environment;
- converter metadata in each manifest entry and in the per-file `=== Conversion ===` block.

Metadata collection is best-effort. Failures become explicit warnings or errors in the manifest.

## Classification Metadata

Classification is layered:

1. Extension hints from `taxonomy.EXTENSION_HINTS`.
2. Name hints for extensionless convention files such as `Makefile`, `Dockerfile`, `README`,
   `LICENSE`, and similar files.
3. MIME hints from Python and optional `file`.
4. Content signatures from magic bytes or lightweight text signatures.

Strong content signatures override extension/name/MIME hints. Specific MIME or content evidence can
also win, but generic printable-text evidence does not downgrade a known structured extension such as
`.md`, `.yaml`, `.jsonl`, or `.rtf` to plain `TXT`. The final classification records the chosen
category, concrete format, confidence, evidence list, warnings, content profile, and whether the file
is safe for exact text preservation.

## JSON Safety

Manifest and per-file conversion JSON is normalized before serialization. The normalizer handles:

- `Path` and path-like objects as strings;
- dataclasses as dictionaries;
- bytes as bounded base64 previews with size/truncation metadata;
- `datetime`, `date`, and `time` values as ISO strings;
- sets/frozensets as stable lists;
- exceptions as type/message/args dictionaries;
- unknown OS-specific objects as type/repr summaries.

This keeps custom backend metadata serializable without requiring every backend to pre-sanitize all
values.

## Manifest and Report

`_conversion_manifest.json` stores machine-readable records for every source entry. The summary
includes category, format, converter, warning, error, collision, and limitation counts.

`_conversion_report.txt` is a compact human-readable summary for quick inspection.

Each generated `.txt` output starts with source metadata, classification metadata, conversion
metadata, and then extracted content. For exact text backends, the extracted-content block is the
decoded original text. Parsed details stay in conversion metadata so the original text is not
interleaved with explanations.

## Metadata Copying

By default, `all2text` attempts `shutil.copystat` and xattr copying from source files to their text
outputs. This can be disabled:

```bash
all2text --no-copy-source-stat source out
```

Metadata copying is skipped for symlinks and non-regular entries.
