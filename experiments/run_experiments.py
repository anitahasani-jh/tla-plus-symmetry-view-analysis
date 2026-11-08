#!/usr/bin/env python3
"""Run the study: reduction, violation preservation, soundness, ablation, coverage.

Protocol
--------
For every model of the frozen subset (``config/subset.yaml``):

1. analyse the model (constant probe + static analysis) and store the full
   proposal in ``results/raw/analysis/<model>.json``;
2. run every applicable arm ``--repeats`` times under one fixed budget, storing
   one JSON per run (including timeouts and crashes);
3. generate seeded mutants, keep the ones the *unreduced* baseline detects, and
   replay exactly those under the other arms;
4. record whether a symmetry set / view was certified, and if not, why -- that
   is the coverage measurement (RQ5).

Everything is resumable: an existing run file is skipped unless ``--force`` is
given, which matters on Colab where sessions are recycled.

    python experiments/run_experiments.py                 # the frozen subset
    python experiments/run_experiments.py --models TCommit LabLog
    python experiments/run_experiments.py --repeats 3 --mutants 4
"""

from __future__ import annotations

import argparse
import platform
import shutil
import sys
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from symview.analysis.program import SpecProgram  # noqa: E402
from symview.mutate import Mutant, generate_mutants  # noqa: E402
from symview.pipeline import (ModelSpec, analyze_model, arm_plan,  # noqa: E402
                              run_arm)
from symview.tlc import TlcBudget  # noqa: E402
from symview.util import ensure_utf8_stdio, write_json  # noqa: E402

SUBSET = ROOT / "config" / "subset.yaml"
EXPERIMENT = ROOT / "config" / "experiment.yaml"
RAW = ROOT / "results" / "raw"
RUNS = RAW / "runs"
ANALYSIS = RAW / "analysis"
MUTANTS = RAW / "mutants"
JAR = ROOT / "tools" / "tla2tools-1.7.1.jar"
SUPPORT = ROOT / "benchmarks" / "support"
WORK = ROOT.parent / "_scratch_lab" / "runs"


def environment() -> dict:
    import subprocess
    try:
        java = subprocess.run(["java", "-version"], capture_output=True, text=True,
                              timeout=20)
        java_version = (java.stderr or java.stdout).splitlines()[0].strip() \
            if (java.stderr or java.stdout) else "unknown"
    except (OSError, subprocess.SubprocessError):
        java_version = "java not found"
    return {
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "java": java_version,
        "cpu_count": __import__("os").cpu_count(),
        "tla2tools": JAR.name,
        "tla2tools_sha256_note": "see benchmarks/PROVENANCE.json and NOTICE",
        "experiment_config": str(EXPERIMENT.relative_to(ROOT)),
    }


def run_path(model_id: str, arm: str, repeat: int) -> Path:
    return RUNS / f"{model_id}__{arm}__r{repeat}.json"


def load_subset() -> list[dict]:
    data = yaml.safe_load(SUBSET.read_text(encoding="utf-8"))
    return data["models"]


def main() -> int:
    ensure_utf8_stdio()
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--models", nargs="*", default=None)
    parser.add_argument("--repeats", type=int, default=None)
    parser.add_argument("--mutants", type=int, default=None)
    parser.add_argument("--timeout", type=int, default=None)
    parser.add_argument("--workers", type=int, default=None)
    parser.add_argument("--heap-mb", type=int, default=None)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--skip-mutants", action="store_true")
    parser.add_argument("--prune", action="store_true",
                        help="delete stored runs for arms the current analysis no "
                             "longer certifies, so tables never mix tool versions")
    parser.add_argument("--mutant-timeout", type=int, default=None)
    args = parser.parse_args()

    experiment = yaml.safe_load(EXPERIMENT.read_text(encoding="utf-8"))
    budget_cfg = experiment["budget"]
    budget = TlcBudget(
        jar=JAR, workers=args.workers or budget_cfg["workers"],
        heap_mb=args.heap_mb or budget_cfg["heap_mb"],
        timeout_s=args.timeout or budget_cfg["timeout_s"])
    repeats = args.repeats or budget_cfg["repeats"]
    mutant_count = args.mutants if args.mutants is not None \
        else experiment["mutants"]["per_model"]
    mutant_timeout = args.mutant_timeout or budget.timeout_s

    for directory in (RUNS, ANALYSIS, MUTANTS):
        directory.mkdir(parents=True, exist_ok=True)
    write_json(RAW / "environment.json", environment())

    models = load_subset()
    if args.models:
        wanted = set(args.models)
        models = [m for m in models if m["model_id"] in wanted]
    print(f"models={len(models)} repeats={repeats} timeout={budget.timeout_s}s "
          f"mutants={mutant_count}")

    summary = []
    for index, entry in enumerate(models, start=1):
        model = ModelSpec.from_dict(entry, ROOT)
        print(f"\n[{index}/{len(models)}] {model.model_id} ({model.family})")
        analysis_path = ANALYSIS / f"{model.model_id}.json"
        started = time.perf_counter()
        try:
            result = analyze_model(model, budget, [SUPPORT], WORK / model.model_id,
                                   allow_liveness=False)
        except Exception as exc:  # one broken model must not stop the study
            import traceback
            print(f"  ANALYSIS FAILED: {type(exc).__name__}: {exc}")
            traceback.print_exc(limit=4)
            summary.append({"model_id": model.model_id, "family": model.family,
                            "error": f"{type(exc).__name__}: {exc}"})
            continue
        write_json(analysis_path, result.to_dict())
        selected = result.symmetry["selected"]
        dropped = result.history["dropped"]
        print(f"  analysis {result.analysis_seconds}s  symmetry={selected or '-'} "
              f"view_drops={dropped or '-'}")
        for note in result.artifacts.notes[:3]:
            print(f"    note: {note}")

        plan = arm_plan(model, result.artifacts)
        if args.prune:
            for stale in RUNS.glob(f"{model.model_id}__*__r*.json"):
                arm_name = stale.name.split("__")[1]
                if arm_name not in plan:
                    stale.unlink()
                    print(f"    pruned stale arm {arm_name}")
        for arm in experiment["arms"]["run"]:
            if arm not in plan:
                continue
            for repeat in range(repeats):
                target = run_path(model.model_id, arm, repeat)
                if target.exists() and not args.force:
                    continue
                try:
                    run = run_arm(model, arm, result.artifacts, budget, [SUPPORT],
                                  WORK / model.model_id,
                                  log_dir=WORK / model.model_id / "logs")
                except Exception as exc:
                    print(f"    {arm} r{repeat} FAILED: {type(exc).__name__}: {exc}")
                    continue
                write_json(target, {"run": run.to_dict(), "model": model.to_dict(),
                                    "arm": arm, "repeat": repeat,
                                    "budget": budget.to_dict()})
            print(f"    {arm:<9} " + ", ".join(
                f"{run_path(model.model_id, arm, r).exists() and 'saved' or 'missing'}"
                for r in range(repeats)))

        if not args.skip_mutants and mutant_count:
            try:
                mutant_records = run_mutants(model, result, mutant_count,
                                             mutant_timeout, budget, args.force)
                write_json(MUTANTS / f"{model.model_id}.json", mutant_records)
                kept = [m for m in mutant_records["mutants"] if m["detected"]]
                print(f"  mutants: generated={len(mutant_records['mutants'])} "
                      f"detected_by_baseline={len(kept)}")
            except Exception as exc:
                print(f"  MUTANTS FAILED: {type(exc).__name__}: {exc}")

        summary.append({
            "model_id": model.model_id, "family": model.family,
            "symmetry": selected, "view_dropped": dropped,
            "analysis_seconds": result.analysis_seconds,
            "liveness": result.program["liveness"],
            "arms_applicable": [k for k, v in result.artifacts.applicable.items() if v],
            "wall_seconds": round(time.perf_counter() - started, 1),
        })
    write_json(RAW / "run_summary.json", {"models": summary,
                                          "repeats": repeats,
                                          "budget": budget.to_dict()})
    print(f"\ndone: {len(summary)} models -> {RAW.relative_to(ROOT)}")
    return 0


def _apply_mutant(result, mutant: Mutant) -> None:
    """Overlay the mutated module in every generated artifact set."""
    result.artifacts.files[mutant.file] = mutant.content


def run_mutants(model: ModelSpec, result, count: int, timeout_s: int,
                budget: TlcBudget, force: bool) -> dict:
    program = result.program_obj
    if program is None:
        return {"model_id": model.model_id, "seed": 20261106,
                "generated": 0, "mutants": [], "note": "analysis produced no program"}
    mutants = generate_mutants(program, model.model_id, count=count, seed=20261106)
    records = []
    arms = ["plain", "symmetry", "view", "both"]
    for mutant in mutants:
        entry = mutant.to_dict()
        entry["arms"] = {}
        overlay = {mutant.file: mutant.content}
        for arm in arms:
            if arm not in arm_plan(model, result.artifacts):
                continue
            run = run_arm(model, arm, result.artifacts, budget, [SUPPORT],
                          WORK / model.model_id, timeout_s=timeout_s,
                          overlay=overlay, tag=f"__m_{mutant.mutant_id}")
            entry["arms"][arm] = {"verdict": run.verdict,
                                  "states": run.states_generated,
                                  "distinct": run.distinct_states,
                                  "seconds": run.wall_seconds,
                                  "violated": run.violated_invariants
                                              + run.violated_properties}
            if arm == "plain":
                entry["detected"] = run.verdict == "violation"
                entry["baseline_verdict"] = run.verdict
                entry["violated"] = entry["arms"][arm]["violated"]
        records.append(entry)
    return {"model_id": model.model_id, "seed": 20261106,
            "generated": len(mutants), "mutants": records}


if __name__ == "__main__":
    raise SystemExit(main())
