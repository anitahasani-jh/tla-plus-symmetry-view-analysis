"""Integration check: load a model context and read constant values from TLC."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from symview.context import load_context, probe_constant_values  # noqa: E402
from symview.tlc import TlcBudget  # noqa: E402
from symview.util import ensure_utf8_stdio  # noqa: E402

JAR = ROOT / "tools" / "tla2tools-1.7.1.jar"
# CommunityModules.jar is built against a newer TLC than 2.16 and its
# tlc2/overrides classes make TLC 2.16 abort with NoClassDefFoundError, so the
# pure TLA+ modules are used from benchmarks/support/community instead.
COMMUNITY = None
SUPPORT = [ROOT / "benchmarks" / "support"]


def show(model_dir: str, module: str, cfg: str) -> None:
    spec_dir = ROOT / "benchmarks" / "public" / model_dir
    ctx = load_context(spec_dir, module, spec_dir / cfg, support_dirs=SUPPORT)
    print("=" * 72)
    print(f"{module}  dir={model_dir}")
    print(f"  modules={sorted(ctx.modules)} builtin={sorted(ctx.builtin_modules)}")
    print(f"  unresolved={ctx.unresolved_modules}")
    print(f"  variables={ctx.variables}")
    print(f"  opdefs={len(ctx.opdefs)} instances={[i.text for i in ctx.instances]}")
    print(f"  cfg: init={ctx.cfg.init} next={ctx.cfg.next} spec={ctx.cfg.specification}")
    print(f"       invariants={ctx.cfg.invariants} properties={ctx.cfg.properties}")
    print(f"       symmetry={ctx.cfg.symmetry} view={ctx.cfg.view} "
          f"deadlock={ctx.cfg.check_deadlock}")
    print(f"  constants:")
    for name, info in sorted(ctx.constants.items()):
        print(f"    {name:<14} arity={info.arity} declared_in={info.declared_in:<12} "
              f"cfg={info.assignment_form}{info.assignment_text!r}")
    work = ROOT.parent / "_scratch_lab" / f"ctx_{module}"
    budget = TlcBudget(jar=JAR, community_jar=COMMUNITY, workers=1, heap_mb=1024,
                       timeout_s=60)
    result = probe_constant_values(ctx, work, budget, support_dirs=SUPPORT,
                                   log_dir=work / "logs")
    print(f"  probe: verdict={result.verdict} wall={result.wall_seconds}s "
          f"returncode={result.returncode}")
    for name, info in sorted(ctx.constants.items()):
        if info.value is not None:
            print(f"    {name:<14} = {info.value.render()[:80]:<40} "
                  f"[{info.value.kind}] atoms={sorted(info.value.atoms())[:6]}")
    if ctx.notes:
        print("  notes:", ctx.notes[:6])


def main() -> int:
    ensure_utf8_stdio()
    show("transaction_commit", "TCommit", "TCommit.cfg")
    show("Paxos", "MCPaxos", "MCPaxos.cfg")
    show("allocator", "SchedulingAllocator", "SchedulingAllocator.cfg")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
