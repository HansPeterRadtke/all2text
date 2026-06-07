from __future__ import annotations

import os
import sys
from dataclasses import replace
from typing import Any

from all2text.external_setup import (
    build_setup_plan,
    execute_setup,
    is_interactive,
    setup_command,
    setup_options_from_environment,
    setup_report,
    write_setup_report,
)


def run_install_hook(
    *,
    env: dict[str, str] | None = None,
    input_stream: Any = None,
    output_stream: Any = None,
    source: str = "pip_install",
) -> dict[str, Any]:
    """Run the pip-invoked external setup path without hanging automation."""

    values = env if env is not None else os.environ
    input_stream = input_stream or sys.stdin
    output_stream = output_stream or sys.stdout
    options = setup_options_from_environment(values, source=source)

    if options.mode == "skip":
        plan = build_setup_plan(options=options)
        report = setup_report(plan, [], "skipped", options, note="ALL2TEXT_SETUP_MODE=skip")
        write_setup_report(report, plan["paths"]["report_path"])
        print("all2text external setup hook skipped by ALL2TEXT_SETUP_MODE=skip.", file=output_stream)
        return report

    interactive = not options.noninteractive and is_interactive(input_stream, output_stream)
    if not interactive and not options.yes and not options.dry_run:
        options = replace(options, noninteractive=True)
        print("all2text external setup: noninteractive pip install detected; not prompting.", file=output_stream)
        print(
            f"Inspect later: {setup_command(options.profile, minimal=options.profile == 'minimal')}",
            file=output_stream,
        )
        print(
            "Run unattended: "
            f"ALL2TEXT_SETUP_ASSUME_YES=1 {setup_command(options.profile, yes=True, minimal=options.profile == 'minimal')}",
            file=output_stream,
        )
    elif interactive and not options.dry_run and not options.yes:
        print("all2text external setup hook is running from pip install.", file=output_stream)

    report = execute_setup(
        options=options,
        input_stream=input_stream,
        output_stream=output_stream,
    )
    if report.get("status") == "failed" and options.strict:
        raise RuntimeError("all2text external setup failed and ALL2TEXT_SETUP_STRICT=1 is set")
    return report
