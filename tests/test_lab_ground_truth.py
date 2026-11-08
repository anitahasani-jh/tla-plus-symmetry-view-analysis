#!/usr/bin/env python3
"""Check SymView's verdicts against the authored ground truth of the lab models.

The lab models exist precisely so that the soundness claims are measurable
instead of argued: each one is built to exercise exactly one decision the tool
has to make (a symmetric set, a distinguished element, ordered identifiers, a
non-equivariant ``CHOOSE``, an append-only history variable, a variable that
only looks like history, a liveness property).

    python tests/test_lab_ground_truth.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

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
WORK = ROOT.parent / "_scratch_lab" / "ground_truth"
TRUTH = ROOT / "benchmarks" / "lab" / "ground_truth.yaml"


def evaluate(entry: dict) -> dict:
    spec_dir = ROOT / entry["dir"]
    module = entry["root_module"]
    cfg = entry["config"]
    ctx = load_context(spec_dir, module, spec_dir / cfg, support_dirs=SUPPORT)
    budget = TlcBudget(jar=JAR, community_jar=None, workers=1, heap_mb=2048,
                       timeout_s=90)
    probe = probe_constant_values(ctx, WORK / f"{module}_{Path(cfg).stem}", budget,
                                  support_dirs=SUPPORT)
    program = SpecProgram.build(ctx)
    symmetry = analyze_symmetry(program)
    history = analyze_history(program)
    by_name = {c.constant: c for c in symmetry.candidates}
    return {"ctx": ctx, "program": program, "symmetry": symmetry,
            "history": history, "by_name": by_name, "probe": probe}


def check(name: str, entry: dict, got: dict) -> list[str]:
    failures: list[str] = []
    expected_sym = entry["expected_symmetry"]
    candidate_name = expected_sym["candidate"]
    expected_verdict = expected_sym["verdict"]

    if candidate_name is None:
        if got["by_name"]:
            failures.append(
                f"expected no symmetry candidate, got "
                f"{sorted(got['by_name'])}")
    else:
        candidate = got["by_name"].get(candidate_name)
        if candidate is None:
            failures.append(f"expected a candidate for {candidate_name}, got none "
                            f"(constants: {sorted(got['by_name'])})")
        else:
            actual = candidate.verdict
            if expected_verdict == "sound" and actual not in ("sound",):
                failures.append(f"{candidate_name}: expected verdict sound, got "
                                f"{actual} ({candidate.reasons[:1]})")
            if expected_verdict == "unsound" and actual not in ("unsound", "unknown"):
                failures.append(f"{candidate_name}: expected an unsound/rejected "
                                f"verdict, got {actual}")
            if expected_verdict == "sound" and candidate_name not in got["symmetry"].selected \
                    and not candidate.liveness_warning:
                failures.append(f"{candidate_name} was not selected for generation")

    expected_history = list(entry.get("expected_history") or [])
    if sorted(got["history"].dropped) != sorted(expected_history):
        failures.append(f"history: expected droppable {expected_history}, got "
                        f"{got['history'].dropped} (verdict {got['history'].verdict})")

    expected_warning = bool(entry.get("expected_liveness_warning"))
    actual_warning = got["program"].liveness
    if expected_warning != actual_warning:
        failures.append(f"liveness warning: expected {expected_warning}, got "
                        f"{actual_warning} ({got['program'].liveness_reasons[:1]})")
    return failures


def main() -> int:
    ensure_utf8_stdio()
    truth = yaml.safe_load(TRUTH.read_text(encoding="utf-8"))
    models = truth["models"]
    rows = []
    total_failures = 0
    for name, entry in models.items():
        try:
            got = evaluate(entry)
        except Exception as exc:
            rows.append((name, "ERROR", [f"{type(exc).__name__}: {exc}"], {}))
            total_failures += 1
            continue
        failures = check(name, entry, got)
        total_failures += len(failures)
        summary = {
            "symmetry": ",".join(f"{c.constant}:{c.verdict}"
                                 for c in got["symmetry"].candidates) or "-",
            "selected": ",".join(got["symmetry"].selected) or "-",
            "view": ",".join(got["history"].dropped) or "-",
            "liveness": str(got["program"].liveness),
        }
        rows.append((name, "PASS" if not failures else "FAIL", failures, summary))

    width = max(len(r[0]) for r in rows) + 2
    print(f"{'model'.ljust(width)}{'result':<8}symmetry".ljust(46)
          + "selected        view            liveness")
    for name, status, failures, summary in rows:
        print(f"{name.ljust(width)}{status:<8}"
              f"{summary.get('symmetry', '?'):<24}"
              f"{summary.get('selected', '?'):<16}"
              f"{summary.get('view', '?'):<16}"
              f"{summary.get('liveness', '?')}")
        for failure in failures:
            print(f"{''.ljust(width)}  -> {failure}")
    print()
    print(f"models={len(rows)} failures={total_failures}")
    return 0 if total_failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
