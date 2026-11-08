"""Command line interface.

    python -m symview analyze --spec-dir benchmarks/public/transaction_commit \\
        --module TCommit --config TCommit.cfg

    python -m symview report  --spec-dir benchmarks/lab/LabLog --module LabLog \\
        --config LabLog.cfg --arms plain symmetry view both

``analyze`` prints the proposal a human has to review; ``run`` executes one
experimental arm through TLC; ``report`` does both and writes JSON.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .pipeline import AnalysisResult, ModelSpec, analyze_model, arm_plan, run_arm
from .tlc import TlcBudget
from .util import ensure_utf8_stdio, write_json

ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_JAR = ROOT / "tools" / "tla2tools-1.7.1.jar"
DEFAULT_SUPPORT = ROOT / "benchmarks" / "support"


def _common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--spec-dir", required=True, type=Path,
                        help="directory holding the .tla and .cfg files")
    parser.add_argument("--module", required=True, help="root TLA+ module name")
    parser.add_argument("--config", required=True, help="TLC .cfg file name")
    parser.add_argument("--jar", type=Path, default=DEFAULT_JAR, help="tla2tools.jar")
    parser.add_argument("--java", default="java", help="java executable")
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--heap-mb", type=int, default=2048)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--work-dir", type=Path,
                        default=ROOT.parent / "_scratch_lab" / "cli")
    parser.add_argument("--json", type=Path, help="write the result as JSON here")
    parser.add_argument("--accept-liveness", action="store_true",
                        help="emit SYMMETRY even if the model checks liveness")
    parser.add_argument("--no-probe", action="store_true",
                        help="do not ask TLC for the constant values")


def _budget(args: argparse.Namespace) -> TlcBudget:
    return TlcBudget(jar=args.jar, java=args.java, community_jar=None,
                     workers=args.workers, heap_mb=args.heap_mb,
                     timeout_s=args.timeout)


def _print_analysis(result: AnalysisResult) -> None:
    symmetry = result.symmetry
    history = result.history
    model = result.model
    print(f"model      : {model.module}  ({model.family or 'unclassified'})")
    print(f"spec dir   : {model.spec_dir}")
    print(f"config     : {model.config.name}")
    print(f"probe      : {result.probe.get('verdict', 'skipped')} "
          f"{result.probe.get('seconds', '')}s")
    print(f"analysis   : {result.analysis_seconds}s")
    print()
    print("SYMMETRY")
    if not symmetry["candidates"]:
        print("  no constant evaluates to a set of model values")
    for candidate in symmetry["candidates"]:
        mark = {"sound": "ACCEPT", "unsound": "REJECT", "trivial": "TRIVIAL",
                "unknown": "UNKNOWN"}[candidate["verdict"]]
        print(f"  [{mark}] {candidate['constant']} = "
              f"{{{', '.join(candidate['atoms'])}}}  (group order "
              f"{candidate['group_order']})")
        for reason in candidate["reasons"][:6]:
            print(f"           - {reason}")
        for flag in candidate["flags"][:4]:
            print(f"           ! {flag['operator']} at {flag['definition']}:"
                  f"{flag['line']} on {', '.join(flag['tainted_operands']) or '?'}")
    print(f"  selected: {', '.join(symmetry['selected']) or '-'}")
    for note in symmetry["notes"]:
        print(f"  note: {note}")
    print()
    print("VIEW")
    print(f"  verdict   : {history['verdict']}")
    print(f"  dropped   : {', '.join(history['dropped']) or '-'}")
    print(f"  retained  : {', '.join(history['retained']) or '-'}")
    for reason in history["reasons"][:6]:
        print(f"           - {reason}")
    print()
    if result.notes:
        print("GENERATED ARTIFACTS")
        for note in result.notes:
            print(f"  note: {note}")
        for name in result.artifacts.files:
            print(f"  file: {name}")
    print()
    print(f"applicable arms: {', '.join(k for k, v in result.artifacts.applicable.items() if v)}")


def cmd_analyze(args: argparse.Namespace) -> int:
    model = ModelSpec(model_id=args.module, spec_dir=args.spec_dir,
                      module=args.module, config=args.spec_dir / args.config)
    result = analyze_model(model, _budget(args), [DEFAULT_SUPPORT], args.work_dir,
                          allow_liveness=args.accept_liveness,
                          skip_probe=args.no_probe, version=__version__)
    _print_analysis(result)
    if args.json:
        write_json(args.json, result.to_dict())
        print(f"[json] {args.json}")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    model = ModelSpec(model_id=args.module, spec_dir=args.spec_dir,
                      module=args.module, config=args.spec_dir / args.config)
    result = analyze_model(model, _budget(args), [DEFAULT_SUPPORT], args.work_dir,
                          allow_liveness=args.accept_liveness, version=__version__)
    plan = arm_plan(model, result.artifacts)
    print(f"arms available: {', '.join(plan)}")
    payload = {"model": model.to_dict(), "arms": {}}
    for arm in args.arms:
        run = run_arm(model, arm, result.artifacts, _budget(args), [DEFAULT_SUPPORT],
                      args.work_dir)
        payload["arms"][arm] = run.to_dict()
        print(f"  {arm:<9} verdict={run.verdict:<12} "
              f"states={run.states_generated} distinct={run.distinct_states} "
              f"time={run.wall_seconds}s")
        for line in run.error_lines[:3]:
            print(f"            {line}")
    if args.json:
        write_json(args.json, payload)
        print(f"[json] {args.json}")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    model = ModelSpec(model_id=args.module, spec_dir=args.spec_dir,
                      module=args.module, config=args.spec_dir / args.config)
    result = analyze_model(model, _budget(args), [DEFAULT_SUPPORT], args.work_dir,
                          allow_liveness=args.accept_liveness, version=__version__)
    _print_analysis(result)
    runs = {}
    for arm in args.arms:
        run = run_arm(model, arm, result.artifacts, _budget(args),
                      [DEFAULT_SUPPORT], args.work_dir)
        runs[arm] = run.to_dict()
        print(f"  {arm:<9} verdict={run.verdict:<12} states={run.states_generated} "
              f"distinct={run.distinct_states} time={run.wall_seconds}s")
    if args.json:
        write_json(args.json, {"analysis": result.to_dict(), "runs": runs})
        print(f"[json] {args.json}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="symview", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--version", action="version", version=f"SymView {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    analyze = sub.add_parser("analyze", help="print the reduction proposal")
    _common(analyze)
    analyze.set_defaults(func=cmd_analyze)

    run = sub.add_parser("run", help="run selected arms through TLC")
    _common(run)
    run.add_argument("--arms", nargs="+", default=["plain", "symmetry"],
                     choices=["direct", "plain", "symmetry", "view", "both", "manual"])
    run.set_defaults(func=cmd_run)

    report = sub.add_parser("report", help="analyse, run all arms and write JSON")
    _common(report)
    report.add_argument("--arms", nargs="+",
                        default=["direct", "plain", "symmetry", "view", "both"],
                        choices=["direct", "plain", "symmetry", "view", "both", "manual"])
    report.set_defaults(func=cmd_report)
    return parser


def main(argv: list[str] | None = None) -> int:
    ensure_utf8_stdio()
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
