"""Regression test: a model whose checked property cannot be resolved must not
receive a SYMMETRY proposal.

The bug this locks down was found by the experiment itself: on
``AllocatorRefinement`` the configuration says ``PROPERTIES SimpleAllocator``
while the module only contains ``Simple == INSTANCE SimpleAllocator``.  The first
version of the liveness detector could not resolve that name, concluded "no
temporal operator", emitted ``SYMMETRY`` -- and TLC then reported

    Error: Temporal properties were violated.

for the reduced run while the unreduced run was clean.  The detector now treats
an unresolvable checked property as a liveness risk.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from symview.analysis.program import SpecProgram  # noqa: E402
from symview.analysis.symmetry import analyze_symmetry  # noqa: E402
from symview.context import load_context  # noqa: E402
from symview.util import ensure_utf8_stdio  # noqa: E402


def main() -> int:
    ensure_utf8_stdio()
    spec_dir = ROOT / "benchmarks" / "public" / "allocator"
    ctx = load_context(spec_dir, "AllocatorRefinement",
                       spec_dir / "AllocatorRefinement.cfg",
                       support_dirs=[ROOT / "benchmarks" / "support"])
    program = SpecProgram.build(ctx)
    proposal = analyze_symmetry(program)
    failures = []
    if not program.liveness:
        failures.append("liveness risk was not detected for AllocatorRefinement")
    if proposal.selected:
        failures.append(f"SYMMETRY would still be emitted for {proposal.selected}")
    for reason in program.liveness_reasons:
        print("  reason:", reason)
    print("liveness:", program.liveness, "| selected:", proposal.selected or "-")
    print("RESULT:", "PASS" if not failures else "FAIL")
    for failure in failures:
        print("  ->", failure)
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
