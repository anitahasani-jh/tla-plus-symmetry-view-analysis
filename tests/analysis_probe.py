"""End-to-end analysis check on public models with known expected verdicts."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from symview.analysis.history import analyze_history  # noqa: E402
from symview.analysis.program import SpecProgram  # noqa: E402
from symview.analysis.symmetry import analyze_symmetry  # noqa: E402
from symview.context import load_context, probe_constant_values  # noqa: E402
from symview.tlc import TlcBudget  # noqa: E402
from symview.util import ensure_utf8_stdio  # noqa: E402

JAR = ROOT / "tools" / "tla2tools-1.7.1.jar"
SUPPORT = [ROOT / "benchmarks" / "support"]
WORK = ROOT.parent / "_scratch_lab" / "analysis"

MODELS = [
    ("transaction_commit", "TCommit", "TCommit.cfg"),
    ("transaction_commit", "PaxosCommit", "PaxosCommit.cfg"),
    ("Prisoners", "Prisoners", "Prisoners.cfg"),
    ("allocator", "SchedulingAllocator", "SchedulingAllocator.cfg"),
    ("ewd840", "EWD840", "EWD840.cfg"),
    ("locks_auxiliary_vars", "Lock", "Lock.cfg"),
    ("Paxos", "MCPaxos", "MCPaxos.cfg"),
    ("GermanProtocol", "MCGermanData", "MCGermanData.cfg"),
]


def run(model_dir: str, module: str, cfg: str) -> None:
    spec_dir = ROOT / "benchmarks" / "public" / model_dir
    ctx = load_context(spec_dir, module, spec_dir / cfg, support_dirs=SUPPORT)
    budget = TlcBudget(jar=JAR, community_jar=None, workers=1, heap_mb=2048,
                       timeout_s=90)
    probe_constant_values(ctx, WORK / module, budget, support_dirs=SUPPORT)
    program = SpecProgram.build(ctx)
    symmetry = analyze_symmetry(program)
    history = analyze_history(program)
    print("=" * 78)
    print(f"{module}  ({model_dir})")
    print(f"  vars={ctx.variables} init={program.init_name} next={program.next_name} "
          f"reachable={len(program.reachable)} unresolved={ctx.unresolved_modules}")
    print(f"  liveness={program.liveness} {program.liveness_reasons[:1]}")
    print(f"  cfg symmetry={ctx.cfg.symmetry} view={ctx.cfg.view}")
    print(f"  SYMMETRY -> selected={symmetry.selected}")
    for candidate in symmetry.candidates:
        print(f"    {candidate.constant}={{{','.join(candidate.atoms)}}} "
              f"verdict={candidate.verdict} flags={len(candidate.flags)} "
              f"unknown_ops={list(candidate.unknown_operators)[:4]}")
        for reason in candidate.reasons[:3]:
            print(f"      - {reason[:150]}")
        for flag in candidate.flags[:3]:
            print(f"      ! {flag.operator} in {flag.definition} line {flag.line} "
                  f"tainted={flag.tainted_operands}")
    print(f"  VIEW -> verdict={history.verdict} dropped={history.dropped} "
          f"retained={history.retained}")
    for reason in history.reasons[:3]:
        print(f"      - {reason[:160]}")


def main() -> int:
    ensure_utf8_stdio()
    targets = sys.argv[1:]
    for model_dir, module, cfg in MODELS:
        if targets and module not in targets:
            continue
        try:
            run(model_dir, module, cfg)
        except Exception as exc:
            import traceback
            print("=" * 78)
            print(f"{module}: EXCEPTION {type(exc).__name__}: {exc}")
            traceback.print_exc(limit=3)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
