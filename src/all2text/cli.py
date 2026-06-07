from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path

from all2text.api import run
from all2text.capabilities import capability_report, provider_execution_summary
from all2text.config import PROFILE_DEFAULTS, load_config, options_with_profile
from all2text.external_setup import (
    SetupOptions,
    build_setup_plan,
    execute_setup,
    is_interactive,
    render_setup_text,
    setup_recommendation,
)
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
    parser.add_argument(
        "--no-copy-source-stat",
        action="store_true",
        help="Do not copy basic source file stat metadata to outputs.",
    )
    parser.add_argument(
        "--allow-target-inside-source",
        action="store_true",
        help="Allow writing the target folder inside the source tree. Not recommended.",
    )
    parser.add_argument("--max-archive-members", type=int, help="Maximum archive members to list.")
    return parser


def build_setup_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="all2text setup",
        description="Detect, plan, and optionally install external all2text tools and models.",
    )
    parser.add_argument("--config", help="Path to an all2text TOML config file.")
    parser.add_argument("--profile", choices=sorted(PROFILE_DEFAULTS), default="full")
    parser.add_argument("--yes", action="store_true", help="Run safe selected installers without prompting.")
    parser.add_argument("--dry-run", action="store_true", help="Print the setup plan without installing.")
    parser.add_argument("--plan", action="store_true", help="Alias for --dry-run.")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of a human-readable plan.")
    parser.add_argument(
        "--tools",
        nargs="?",
        const="all",
        help="Include tools, optionally limited to comma/space-separated ids such as whisper_cpp,capa.",
    )
    parser.add_argument(
        "--models",
        nargs="?",
        const="all",
        help="Include models, optionally limited to ids or minimal.",
    )
    parser.add_argument("--target", help="Base directory whose tools/ and models/ children should be used.")
    parser.add_argument("--tools-dir", help="Directory for user-space tool builds.")
    parser.add_argument("--models-dir", help="Directory for downloaded/detected model files.")
    parser.add_argument("--report", help="Setup report path. Defaults to the user state directory.")
    parser.add_argument("--skip-models", action="store_true", help="Do not include model setup actions.")
    parser.add_argument(
        "--skip-root",
        action="store_true",
        help="Do not plan root/system package installs as runnable.",
    )
    parser.add_argument(
        "--skip-heavy",
        action="store_true",
        help="Block heavy builds/downloads unless re-run explicitly.",
    )
    return parser


def setup_main(argv: list[str]) -> int:
    parser = build_setup_parser()
    args = parser.parse_args(argv)
    config = load_config(args.config)
    options = options_with_profile(config.options, args.profile)
    config = config.with_options(options)
    tools_requested = args.tools is not None
    models_requested = args.models is not None
    include_tools = True
    include_models = True
    if tools_requested and not models_requested:
        include_models = False
    if models_requested and not tools_requested:
        include_tools = False
    if args.skip_models:
        include_models = False
    setup_options = SetupOptions(
        profile=options.profile,
        include_tools=include_tools,
        include_models=include_models,
        selected_tools=split_selectors(args.tools) if tools_requested else (),
        selected_models=split_selectors(args.models) if models_requested else (),
        dry_run=args.dry_run or args.plan,
        json_output=args.json,
        yes=args.yes,
        skip_root=args.skip_root,
        skip_heavy=args.skip_heavy,
        skip_models=args.skip_models,
        target=args.target or "",
        tools_dir=args.tools_dir or "",
        models_dir=args.models_dir or "",
        report_path=args.report or options.setup_report_path,
    )
    report = execute_setup(config, options=setup_options)
    if args.json:
        print(json_dumps(report, indent=2))
    else:
        print(render_setup_text(report), end="")
        print(f"Setup status: {report.get('status')}")
        for result in report.get("results") or []:
            detail = result.get("error") or result.get("step") or result.get("target_path") or ""
            print(f"- {result.get('id')}: {result.get('status')}" + (f" ({detail})" if detail else ""))
        if report.get("note"):
            print(f"Note: {report['note']}")
    return 0 if report.get("status") not in {"failed"} else 1


def split_selectors(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(part for part in str(value).replace(",", " ").split() if part)


def print_setup_prompt_if_needed(config: object) -> None:
    options = getattr(config, "options", None)
    if not getattr(options, "interactive_setup_prompt", True):
        return
    recommendation = setup_recommendation(config)
    if not recommendation.get("needed"):
        return
    command = str(recommendation.get("command") or f"{sys.executable} -m all2text setup --dry-run --profile full")
    provider_names = ", ".join(
        sorted(str(item.get("name")) for item in recommendation.get("unavailable_enabled_providers") or [])
    )
    if is_interactive(sys.stdin, sys.stdout):
        print(
            f"Some enabled external providers are unavailable ({provider_names}). "
            "Run setup now? [y/N] ",
            end="",
            flush=True,
        )
        answer = sys.stdin.readline().strip().lower()
        if answer in {"1", "true", "yes", "y", "on"}:
            execute_setup(config, options=SetupOptions(profile=getattr(options, "profile", "full"), skip_heavy=True))
    else:
        print(
            "all2text external setup is available for missing enabled providers. "
            f"Run: {command}",
            file=sys.stderr,
        )


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    else:
        argv = list(argv)
    if argv and argv[0] == "setup":
        return setup_main(argv[1:])
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
        report["setup"] = build_setup_plan(
            config,
            options=SetupOptions(profile=options.profile, skip_heavy=True),
        )
        print(json_dumps(report, indent=2))
        return 0
    if not args.source_folder or not args.target_folder:
        parser.error("source_folder and target_folder are required unless --version or --capabilities is used")
    print_setup_prompt_if_needed(config)
    manifest = run(Path(args.source_folder), Path(args.target_folder), options=options, config=config)
    print(json_dumps(manifest["summary"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
