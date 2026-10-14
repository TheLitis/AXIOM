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
    native = commands.add_parser("native", help="Inspect a native observer capture and its recorded limits")
    native.add_argument("input", type=Path)
    cadence = commands.add_parser(
        "native-cadence", help="Describe recorded hook wall cadence and dt without performance attribution"
    )
    cadence.add_argument("input", type=Path)
    startup = commands.add_parser(
        "native-startup", help="Inspect retained startup diagnostics without inferring an exit cause"
    )
    startup.add_argument("input", type=Path, help="Hash-bound startup evidence bundle")
    startup_baseline = commands.add_parser(
        "native-startup-baseline", help="Record bounded runtime-log identity before a declared launch"
    )
    startup_baseline.add_argument("runtime", type=Path)
    startup_baseline.add_argument("--output", type=Path, required=True, help="New inventory JSON path")
    startup_baseline.set_defaults(json=None)
    startup_collect = commands.add_parser(
        "native-startup-collect", help="Retain bounded startup artifacts; does not launch the game"
    )
    startup_collect.add_argument("runtime", type=Path)
    startup_collect.add_argument("--attempt-manifest", type=Path, required=True)
    startup_collect.add_argument("--output", type=Path, required=True, help="New evidence directory")
    startup_collect.add_argument(
        "--baseline", type=Path, help="Prelaunch inventory; otherwise retrospectively unbound"
    )
    startup_collect.set_defaults(json=None)
    probe_plan = commands.add_parser(
        "probe-plan", help="Plan bounded full-start command-offset probes from a validated reference"
    )
    probe_plan.add_argument("reference", type=Path, help="Completed schema-4/5 owned fixed-Scheduler capture")
    probe_plan.add_argument("spec", type=Path, help="Frozen axes, repetitions and run budget")
    probe_export = commands.add_parser(
        "probe-export", help="Materialize canonical native replay files and an execution job manifest"
    )
    probe_export.add_argument("study", type=Path)
    probe_export.add_argument("--output", type=Path, required=True, help="Fresh exchange directory")
    probe_export.set_defaults(json=None)
    probe_map = commands.add_parser(
        "probe-map", help="Build a discrete map from synthetic or hash-bound native probe results"
    )
    probe_map.add_argument("study", type=Path)
    probe_map.add_argument("results", type=Path)
    probe_demo = commands.add_parser(
        "probe-demo", help="Run a disconnected coupled synthetic grid through the measurement pipeline"
    )
    probe_demo.add_argument(
        "--reference", type=Path, default=Path("examples/probes/synthetic-reference.json")
    )
    probe_demo.add_argument("--spec", type=Path, default=Path("examples/probes/coupled-grid.json"))
    probe_demo.add_argument(
        "--out", type=Path, default=Path("reports/probe-demo"), help="Fresh output directory"
    )
    compare = commands.add_parser(
        "native-compare", help="Compare recorded subsets of repeated native replays"
    )
    compare.add_argument("inputs", type=Path, nargs="+", help="Two to sixteen capture files")
    delivery = commands.add_parser(
        "native-delivery-compare", help="Compare a declared owned plan with its synthetic UI queue route"
    )
    delivery.add_argument("owned", type=Path)
    delivery.add_argument("ui", type=Path)
    recorded_plan = commands.add_parser(
        "native-replay-plan", help="Export an explicit recorded-cadence/request intervention"
    )
    recorded_plan.add_argument("source", type=Path)
    recorded_plan.add_argument("target_baseline", type=Path)
    recorded_compare = commands.add_parser(
        "native-recorded-compare", help="Compare a source recording with fresh recorded-plan replays"
    )
    recorded_compare.add_argument("source", type=Path)
    recorded_compare.add_argument("plan", type=Path)
    recorded_compare.add_argument(
        "replays", type=Path, nargs="+", help="Two to sixteen fresh replay captures"
    )
    fixtures = commands.add_parser(
        "fixtures", help="Validate generated fixture specifications; no native verification"
    )
    fixtures.add_argument("input", type=Path)
    fixtures.add_argument("--case", dest="case_id", help="Select a case with --run")
    fixtures.add_argument("--run", dest="run_id", help="Emit a validated run specification with --case")
    fixture_check = commands.add_parser(
        "fixture-check", help="Check supplied native observations against a fixture"
    )
    fixture_check.add_argument("input", type=Path, help="Fixture matrix")
    fixture_check.add_argument("capture", type=Path)
    fixture_check.add_argument("--case", dest="case_id", required=True)
    fixture_check.add_argument("--run", dest="run_id", required=True)
    fixture_response = commands.add_parser(
        "fixture-response", help="Check selected response to different owned input plans"
    )
    fixture_response.add_argument("input", type=Path, help="Fixture matrix")
    fixture_response.add_argument("reference", type=Path)
    fixture_response.add_argument("changed", type=Path)
    fixture_response.add_argument("--case", dest="case_id", required=True)
    fixture_response.add_argument("--check", dest="check_id", required=True)
    variants = commands.add_parser(
        "fixture-variants", help="Compare a frozen construction change with its same-plan native control"
    )
    variants.add_argument("study", type=Path)
    variants.add_argument("matrix", type=Path)
    variants.add_argument("positive", type=Path)
    variants.add_argument("control", type=Path)
    variants.add_argument("--case", dest="case_id", required=True)
    demo = commands.add_parser("demo", help="Create an offline report from explicitly synthetic examples")
    demo.add_argument("--examples", type=Path, default=Path("examples"))
    demo.add_argument("--out", type=Path, default=Path("reports/demo"))
    demo.add_argument("--trials", type=int, default=20000)
    demo.add_argument("--seed", type=int, default=42)
    for command in (
        timing,
        cohort,
        level,
        replay,
        oracle,
        native,
        cadence,
        startup,
        probe_plan,
        probe_map,
        probe_demo,
        compare,
        delivery,
        recorded_plan,
        recorded_compare,
        fixtures,
        fixture_check,
        fixture_response,
        variants,
    ):
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
        elif args.command == "native":
            from .native import inspect_native_capture

            result = inspect_native_capture(args.input)
        elif args.command == "native-cadence":
            from .cadence import inspect_native_cadence

            result = inspect_native_cadence(args.input)
        elif args.command == "native-startup":
            from .startup import inspect_startup_evidence

            if args.json and args.json.resolve().is_relative_to(args.input.resolve().parent):
                raise ValueError(
                    "Startup inspection JSON must remain outside the retained evidence directory"
                )
            result = inspect_startup_evidence(args.input)
        elif args.command == "native-startup-baseline":
            from .startup import snapshot_startup_logs

            result = snapshot_startup_logs(args.runtime, args.output)
        elif args.command == "native-startup-collect":
            from .startup import collect_startup_evidence

            result = collect_startup_evidence(args.runtime, args.attempt_manifest, args.output, args.baseline)
        elif args.command == "probe-plan":
            from .probeplan import create_probe_study

            result = create_probe_study(args.reference, args.spec)
        elif args.command == "probe-export":
            from .proberun import materialize_probe_study

            result = materialize_probe_study(args.study, args.output)
        elif args.command == "probe-map":
            from .probes import analyze_probe_results

            result = analyze_probe_results(args.study, args.results)
        elif args.command == "probe-demo":
            from .probes import synthetic_probe_demo

            result = synthetic_probe_demo(args.reference, args.spec, args.out)
        elif args.command == "native-compare":
            from .native import compare_native_captures

            result = compare_native_captures(args.inputs)
        elif args.command == "native-delivery-compare":
            from .equivalence import compare_native_delivery

            result = compare_native_delivery(args.owned, args.ui)
        elif args.command == "native-replay-plan":
            from .replaybridge import export_recorded_replay_plan

            result = export_recorded_replay_plan(args.source, args.target_baseline)
        elif args.command == "native-recorded-compare":
            from .replaybridge import compare_recorded_replay

            result = compare_recorded_replay(args.source, args.plan, args.replays)
        elif args.command == "fixtures":
            from .fixtures import get_fixture_run, load_fixture_matrix

            if bool(args.case_id) != bool(args.run_id):
                raise ValueError("--case and --run must be supplied together")
            matrix = load_fixture_matrix(args.input)
            result = get_fixture_run(matrix, args.case_id, args.run_id) if args.case_id else matrix
        elif args.command == "fixture-check":
            from .fixtures import inspect_fixture_capture

            result = inspect_fixture_capture(args.input, args.case_id, args.run_id, args.capture)
        elif args.command == "fixture-response":
            from .fixtures import compare_fixture_response

            result = compare_fixture_response(
                args.input, args.case_id, args.check_id, args.reference, args.changed
            )
        elif args.command == "fixture-variants":
            from .interactions import compare_fixture_variants

            result = compare_fixture_variants(
                args.study, args.matrix, args.case_id, args.positive, args.control
            )
        else:
            from .survival import analyze_cohort

            timing = analyze_scenario(args.examples / "timing.json", args.trials, args.seed)
            cohort = analyze_cohort(args.examples / "cohort.json", 1000, args.seed)
            write_json(args.out / "timing.json", timing)
            write_json(args.out / "cohort.json", cohort)
            render_report(args.out / "index.html", timing=timing, cohort=cohort)
            print(f"Synthetic demo report: {(args.out / 'index.html').resolve()}")
            return 0
        if args.command in {"probe-plan", "probe-map", "probe-demo"} and args.json:
            from .proberun import write_probe_json

            write_probe_json(args.json, result)
        else:
            write_json(args.json, result)
        return 0
    except (ValueError, OSError) as exc:
        print(f"axiom: {exc}", file=sys.stderr)
        return 2
