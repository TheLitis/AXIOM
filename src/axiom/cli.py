"""Command-line entry point for reproducible offline research."""

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .report import render_report
from .timing import analyze_scenario


def parser():
    cli = argparse.ArgumentParser(prog="axiom", description="AXIOM · Geometry Dash Difficulty Lab")
    cli.add_argument("--version", action="version", version=__version__)
    commands = cli.add_subparsers(dest="command", required=True)
    timing = commands.add_parser("timing", help="Analyze supplied timing windows and coupled constraints")
    timing.add_argument("input", type=Path)
    timing.add_argument("--trials", type=int, default=20000)
    timing.add_argument("--seed", type=int, default=0)
    timing.add_argument("--sigma-ms", type=float, help="Override independent timing jitter (assumed)")
    cohort = commands.add_parser("cohort", help="Estimate first-completion curve with right censoring")
    cohort.add_argument("input", type=Path)
    cohort.add_argument("--bootstrap", type=int, default=1000)
    cohort.add_argument("--seed", type=int, default=0)
    level = commands.add_parser("level", help="Inspect raw level metadata; no inferred physics or difficulty")
    level.add_argument("input", type=Path)
    level.add_argument("--encoding", choices=["plain", "base64-gzip", "base64-zlib"], default="plain")
    replay = commands.add_parser("replay", help="Inspect GDR 1 JSON replay events and declared timebase")
    replay.add_argument("input", type=Path)
    oracle = commands.add_parser("trials", help="Check a supplied full-run terminal oracle trial ledger")
    oracle.add_argument("input", type=Path)
    demo = commands.add_parser("demo", help="Create an offline report from explicitly synthetic examples")
    demo.add_argument("--examples", type=Path, default=Path("examples"))
    demo.add_argument("--out", type=Path, default=Path("reports/demo"))
    demo.add_argument("--trials", type=int, default=20000)
    demo.add_argument("--seed", type=int, default=42)
    for command in (timing, cohort, level, replay, oracle):
        command.add_argument("--json", type=Path, help="Write machine-readable result (otherwise stdout)")
    for command in (timing, cohort):
        command.add_argument("--html", type=Path, help="Write a self-contained interactive report")
    return cli


def write_json(path, result):
    content = json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    if path is None:
        print(content, end="")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def main(argv=None):
    cli = parser()
    args = cli.parse_args(argv)
    try:
        if args.command == "timing":
            result = analyze_scenario(args.input, args.trials, args.seed, args.sigma_ms)
            if args.html:
                render_report(args.html, timing=result)
        elif args.command == "cohort":
            from .survival import analyze_cohort

            result = analyze_cohort(args.input, args.bootstrap, args.seed)
            if args.html:
                render_report(args.html, cohort=result)
        elif args.command == "level":
            from .ingest import inspect_level

            result = inspect_level(args.input, encoding=args.encoding)
        elif args.command == "replay":
            from .ingest import inspect_replay

            result = inspect_replay(args.input)
        elif args.command == "trials":
            from .oracle import inspect_trials

            result = inspect_trials(args.input)
        else:
            from .survival import analyze_cohort

            timing = analyze_scenario(args.examples / "timing.json", args.trials, args.seed)
            cohort = analyze_cohort(args.examples / "cohort.json", 1000, args.seed)
            write_json(args.out / "timing.json", timing)
            write_json(args.out / "cohort.json", cohort)
            render_report(args.out / "index.html", timing=timing, cohort=cohort)
            print(f"Synthetic demo report: {(args.out / 'index.html').resolve()}")
            return 0
        write_json(args.json, result)
        return 0
    except (ValueError, OSError) as exc:
        print(f"axiom: {exc}", file=sys.stderr)
        return 2
