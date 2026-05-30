from __future__ import annotations

import argparse
import json
from pathlib import Path

from all2text.api import run
from all2text.models import RunOptions
from all2text.version import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="all2text",
        description="Convert a folder tree into mirrored plain-text outputs with metadata and reports.",
    )
    parser.add_argument("source_folder", nargs="?")
    parser.add_argument("target_folder", nargs="?")
    parser.add_argument("--version", action="store_true", help="Print the all2text version and exit.")
    parser.add_argument("--no-file-command", action="store_true", help="Disable the optional system file(1) probe.")
    parser.add_argument("--no-copy-source-stat", action="store_true", help="Do not copy basic source file stat metadata to outputs.")
    parser.add_argument(
        "--allow-target-inside-source",
        action="store_true",
        help="Allow writing the target folder inside the source tree. Not recommended.",
    )
    parser.add_argument("--max-archive-members", type=int, default=5000, help="Maximum archive members to list.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.version:
        print(__version__)
        return 0
    if not args.source_folder or not args.target_folder:
        parser.error("source_folder and target_folder are required unless --version is used")
    options = RunOptions(
        use_file_command=not args.no_file_command,
        copy_source_stat=not args.no_copy_source_stat,
        reject_target_inside_source=not args.allow_target_inside_source,
        max_archive_members=args.max_archive_members,
    )
    manifest = run(Path(args.source_folder), Path(args.target_folder), options=options)
    print(json.dumps(manifest["summary"], indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

