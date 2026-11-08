#!/usr/bin/env python3
"""Run every arm on the hand-written lab models.

The lab models are tiny (a few hundred states), so they are the cheapest place to
show the whole pipeline end to end -- including the view reduction, which the
public corpus rarely exercises.  Their ground truth is in
``benchmarks/lab/ground_truth.yaml``.

    python experiments/run_lab_models.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from symview.pipeline import ModelSpec, analyze_model, arm_plan, run_arm  # noqa: E402
from symview.tlc import TlcBudget  # noqa: E402
from symview.util import ensure_utf8_stdio, write_json  # noqa: E402

TRUTH = ROOT / "benchmarks" / "lab" / "ground_truth.yaml"
RUNS = ROOT / "results" / "raw" / "runs"
ANALYSIS = ROOT / "results" / "raw" / "analysis"
JAR = ROOT / "tools" / "tla2tools-1.7.1.jar"
SUPPORT = ROOT / "benchmarks" / "support"
WORK = ROOT.parent / "_scratch_lab" / "lab"
ARMS = ["direct", "plain", "symmetry", "view", "both"]


def main() -> int:
    ensure_utf8_stdio()
    truth = yaml.safe_load(TRUTH.read_text(encoding="utf-8"))
    budget = TlcBudget(jar=JAR, workers=2, heap_mb=1024, timeout_s=120)
    RUNS.mkdir(parents=True, exist_ok=True)
    ANALYSIS.mkdir(parents=True, exist_ok=True)
    rows = []
    for model_id, entry in truth["models"].items():
        spec_dir = ROOT / entry["dir"]
        model = ModelSpec(model_id=model_id, spec_dir=spec_dir,
                          module=entry["root_module"],
                          config=spec_dir / entry["config"],
                          family="lab", source="authored")
        result = analyze_model(model, budget, [SUPPORT], WORK / model_id,
                               skip_probe=False)
        write_json(ANALYSIS / f"{model_id}.json", result.to_dict())
        plan = arm_plan(model, result.artifacts)
        selected = ",".join(result.symmetry["selected"]) or "-"
        dropped = ",".join(result.history["dropped"]) or "-"
        line = [f"{model_id:<14} symmetry={selected:<10} view={dropped}"]
        for arm in ARMS:
            if arm not in plan:
                continue
            run = run_arm(model, arm, result.artifacts, budget, [SUPPORT],
                          WORK / model_id, log_dir=WORK / model_id / "logs")
            write_json(RUNS / f"{model_id}__{arm}__r0.json",
                       {"run": run.to_dict(), "model": model.to_dict(),
                        "arm": arm, "repeat": 0, "budget": budget.to_dict()})
            line.append(f"{arm}:{run.distinct_states}")
        rows.append((model_id, line))
        print("  " + "  ".join(line))
    print(f"\n{len(rows)} lab models x {len(ARMS)} arms -> "
          f"{RUNS.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
