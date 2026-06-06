from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path

from all2text.api import run
from all2text.capabilities import capability_report, provider_execution_summary
from all2text.config import PROFILE_DEFAULTS, load_config, options_with_profile
from all2text.install_help import install_tools_guidance
from all2text.jsonsafe import json_dumps
from all2text.providers import provider_family_statuses, provider_statuses
from all2text.version import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="all2text",
        description="Convert a folder tree into mirrored plain-text outputs with metadata and reports.",
    )
    parser.add_argument("source_folder", nargs="?")
    parser.add_argument("target_folder", nargs="?")
    parser.add_argument("--version", action="store_true", help="Print the all2text version and exit.")
    parser.add_argument("--config", help="Path to an all2text TOML config file.")
    parser.add_argument(
        "--profile",
        choices=sorted(PROFILE_DEFAULTS),
        help=(
            "Advanced safety override. Default auto detects installed Python libraries, safe "
            "external tools, and configured/reachable local model endpoints."
        ),
    )
    parser.add_argument(
        "--capabilities",
        "--detect-capabilities",
        action="store_true",
        help="Print automatic capability detection JSON and exit without converting files.",
    )
    parser.add_argument("--no-file-command", action="store_true", help="Disable the optional system file(1) probe.")
    parser.add_argument("--no-copy-source-stat", action="store_true", help="Do not copy basic source file stat metadata to outputs.")
    parser.add_argument(
        "--allow-target-inside-source",
        action="store_true",
        help="Allow writing the target folder inside the source tree. Not recommended.",
    )
    parser.add_argument("--max-archive-members", type=int, help="Maximum archive members to list.")
    return parser


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        import sys

        argv = sys.argv[1:]
    else:
        argv = list(argv)
    if argv and argv[0] == "doctor":
        argv = ["--capabilities", *argv[1:]]
    if argv and argv[0] == "install-tools":
        print(install_tools_guidance())
        return 0
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.version:
        print(__version__)
        return 0
    config = load_config(args.config)
    options = config.options
    if args.profile:
        options = options_with_profile(options, args.profile)
    if args.no_file_command:
        options = replace(options, use_file_command=False)
    if args.no_copy_source_stat:
        options = replace(options, copy_source_stat=False)
    if args.allow_target_inside_source:
        options = replace(options, reject_target_inside_source=False)
    if args.max_archive_members is not None:
        if args.max_archive_members <= 0:
            parser.error("--max-archive-members must be a positive integer")
        options = replace(options, max_archive_members=args.max_archive_members)
    config = config.with_options(options)
    if args.capabilities:
        report = capability_report(config)
        configured_statuses = [status.to_dict() for status in provider_statuses(config)]
        family_statuses = [status.to_dict() for status in provider_family_statuses(config)]
        report["provider_statuses"] = configured_statuses
        report["provider_family_statuses"] = family_statuses
        report["provider_execution_summary"] = provider_execution_summary(
            report,
            configured_statuses,
            family_statuses,
        )
        print(json_dumps(report, indent=2))
        return 0
    if not args.source_folder or not args.target_folder:
        parser.error("source_folder and target_folder are required unless --version or --capabilities is used")
    manifest = run(Path(args.source_folder), Path(args.target_folder), options=options, config=config)
    print(json_dumps(manifest["summary"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
