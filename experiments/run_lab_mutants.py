#!/usr/bin/env python3
"""Mutation testing on the lab models.

The public subset is dominated by models without a certified reduction, so most
of its mutants cannot say anything about violation preservation.  The lab models
all have a certified symmetry set (and one has a view), which makes them the
right place for RQ2: a dropped guard there must be found by *every* arm.

    python experiments/run_lab_mutants.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments"))

from run_experiments import run_mutants  # noqa: E402
from symview.pipeline import ModelSpec, analyze_model  # noqa: E402
from symview.tlc import TlcBudget  # noqa: E402
from symview.util import ensure_utf8_stdio, write_json  # noqa: E402

TRUTH = ROOT / "benchmarks" / "lab" / "ground_truth.yaml"
MUTANTS = ROOT / "results" / "raw" / "mutants"
JAR = ROOT / "tools" / "tla2tools-1.7.1.jar"
SUPPORT = ROOT / "benchmarks" / "support"
WORK = ROOT.parent / "_scratch_lab" / "labmutants"


def main() -> int:
    ensure_utf8_stdio()
    truth = yaml.safe_load(TRUTH.read_text(encoding="utf-8"))
    budget = TlcBudget(jar=JAR, workers=2, heap_mb=1024, timeout_s=120)
    MUTANTS.mkdir(parents=True, exist_ok=True)
    total = kept = 0
    for model_id, entry in truth["models"].items():
        spec_dir = ROOT / entry["dir"]
        model = ModelSpec(model_id=model_id, spec_dir=spec_dir,
                          module=entry["root_module"],
                          config=spec_dir / entry["config"], family="lab")
        result = analyze_model(model, budget, [SUPPORT], WORK / model_id,
                               skip_probe=False)
        records = run_mutants(model, result, count=3, timeout_s=90,
                              budget=budget, force=True)
        write_json(MUTANTS / f"{model_id}.json", records)
        detected = [m for m in records["mutants"] if m.get("detected")]
        total += len(records["mutants"])
        kept += len(detected)
        arms = sorted({a for m in detected for a in m.get("arms", {})})
        print(f"  {model_id:<14} generated={len(records['mutants'])} "
              f"detected={len(detected)} arms={arms}")
    print(f"\ngenerated={total} detected_by_baseline={kept}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
