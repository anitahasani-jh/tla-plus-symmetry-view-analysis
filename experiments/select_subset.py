#!/usr/bin/env python3
"""Select the evaluated subset from the candidate pool, before any SymView run.

The criterion is fixed in ``config/corpus.yaml`` (P1-P5) and uses **only
unreduced baseline information**:

* P1 provenance / files present;
* P2 TLC completes the unreduced baseline within the probe budget;
* P3 family diversity;
* P4 a cost spread (cheap, medium, expensive);
* P5 a fixed size, with deterministic tie-breaking.

The script writes ``config/subset.yaml`` (frozen selection, with the measured
baseline numbers and the reason for every exclusion) and
``results/raw/subset_probe.json`` (the full probe log, including failures).

    python experiments/select_subset.py [--limit N] [--timeout S]
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from symview.codegen import strip_reduction_directives  # noqa: E402
from symview.tlc import TlcBudget, prepare_workdir, run_tlc  # noqa: E402
from symview.util import ensure_utf8_stdio, write_json, write_text  # noqa: E402

CORPUS = ROOT / "config" / "corpus.yaml"
EXPERIMENT = ROOT / "config" / "experiment.yaml"
SUBSET = ROOT / "config" / "subset.yaml"
PROBE_JSON = ROOT / "results" / "raw" / "subset_probe.json"
JAR = ROOT / "tools" / "tla2tools-1.7.1.jar"
SUPPORT = ROOT / "benchmarks" / "support"
WORK = ROOT.parent / "_scratch_lab" / "subset"


def candidates() -> list[dict]:
    corpus = yaml.safe_load(CORPUS.read_text(encoding="utf-8"))
    out: list[dict] = []
    for source in corpus["sources"]:
        for entry in source["dirs"]:
            local = ROOT / "benchmarks" / "public" / _slug(entry["path"], source["repo"])
            for model in entry["models"]:
                cfg = local / f"{model}.cfg"
                tla = local / f"{model}.tla"
                out.append({
                    "model_id": model,
                    "module": model,
                    "spec_dir": str(local.relative_to(ROOT)).replace("\\", "/"),
                    "config": f"{model}.cfg",
                    "family": entry["family"],
                    "source": f"{source['repo']}@{source['commit'][:12]}",
                    "files_present": cfg.exists() and tla.exists(),
                })
    # Two directories can ship a model with the same file name (several are
    # called MC.tla).  The module name must stay untouched for TLA+, but the
    # identifier used for results files has to be unique.
    counts: dict[str, int] = {}
    for candidate in out:
        counts[candidate["module"]] = counts.get(candidate["module"], 0) + 1
    for candidate in out:
        if counts[candidate["module"]] > 1:
            leaf = Path(candidate["spec_dir"]).name
            candidate["model_id"] = f"{leaf}-{candidate['module']}"
    return out


def _slug(dir_path: str, repo: str) -> str:
    cleaned = dir_path.strip("/")
    if cleaned.startswith("specifications/"):
        cleaned = cleaned[len("specifications/"):]
    return cleaned.replace("/", "--").replace(".", "_") if cleaned not in ("", ".") \
        else repo.replace("/", "--").replace(".", "_")


def probe(model: dict, timeout_s: int, workers: int, heap_mb: int) -> dict:
    spec_dir = ROOT / model["spec_dir"]
    cfg_path = spec_dir / model["config"]
    base, removed = strip_reduction_directives(cfg_path.read_text(encoding="utf-8",
                                                                  errors="replace"))
    workdir = WORK / model["model_id"]
    prepare_workdir(spec_dir, workdir, support_dirs=[SUPPORT],
                    extra_files={f"{model['module']}_sv_base.cfg": base})
    budget = TlcBudget(jar=JAR, workers=workers, heap_mb=heap_mb,
                       timeout_s=timeout_s)
    result = run_tlc(workdir, model["module"], f"{model['module']}_sv_base",
                     budget, label=f"probe_{model['model_id']}",
                     log_dir=WORK / "logs")
    return {
        "model_id": model["model_id"],
        "verdict": result.verdict,
        "states": result.states_generated,
        "distinct": result.distinct_states,
        "seconds": result.wall_seconds,
        "violated": result.violated_invariants + result.violated_properties,
        "deadlock": result.deadlock,
        "removed_directives": removed,
        "errors": result.error_lines[:5],
    }


def bucket(seconds: float | None, verdict: str) -> str:
    if verdict in ("timeout", "crash", "parse-error", "error"):
        return "failed"
    if seconds is None:
        return "unknown"
    if seconds < 5:
        return "cheap"
    if seconds < 30:
        return "medium"
    return "expensive"


def main() -> int:
    ensure_utf8_stdio()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=0,
                        help="probe at most N candidates (debugging)")
    parser.add_argument("--timeout", type=int, default=0,
                        help="override the probe timeout from experiment.yaml")
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--heap-mb", type=int, default=2048)
    parser.add_argument("--reuse", type=Path, default=None,
                        help="reuse an existing subset_probe.json instead of re-running "
                             "the baseline (e.g. after a Colab session died)")
    args = parser.parse_args()

    experiment = yaml.safe_load(EXPERIMENT.read_text(encoding="utf-8"))
    corpus = yaml.safe_load(CORPUS.read_text(encoding="utf-8"))
    timeout_s = args.timeout or experiment["budget"]["timeout_s"]
    seed = corpus["seed"]
    size = corpus["subset_size"]

    pool = candidates()
    runnable = [c for c in pool if c["files_present"]]
    missing = [c for c in pool if not c["files_present"]]
    if args.limit:
        runnable = runnable[: args.limit]
    print(f"pool={len(pool)} files_present={len(runnable)} missing={len(missing)} "
          f"timeout={timeout_s}s")

    results = []
    unprobed: list[dict] = []
    if args.reuse and Path(args.reuse).exists():
        payload = json.loads(Path(args.reuse).read_text(encoding="utf-8"))
        by_id = {c["model_id"]: c for c in pool}
        by_module: dict[str, list[dict]] = {}
        for candidate in pool:
            by_module.setdefault(candidate["module"], []).append(candidate)
        ambiguous: list[str] = []
        for record in payload.get("results", []):
            if record["model_id"] not in by_id:
                matches = by_module.get(record["model_id"], [])
                if len(matches) == 1:
                    record["model_id"] = matches[0]["model_id"]
                else:
                    # Several directories ship a model with this file name, so the
                    # probe log cannot be attributed; drop it rather than guess.
                    ambiguous.append(record["model_id"])
                    continue
            meta = by_id.get(record["model_id"], {})
            record["family"] = record.get("family") or meta.get("family", "")
            record["source"] = record.get("source") or meta.get("source", "")
            record["bucket"] = record.get("bucket") or bucket(
                record.get("seconds"), record.get("verdict") or "error")
            results.append(record)
        probed = {r["model_id"] for r in results}
        unprobed = [m for m in runnable if m["model_id"] not in probed]
        print(f"reused {len(results)} probe records from {args.reuse}; "
              f"{len(unprobed)} candidates were not probed"
              + (f"; ambiguous dropped: {sorted(set(ambiguous))}" if ambiguous else ""))
    else:
        for index, model in enumerate(runnable, start=1):
            record = probe(model, timeout_s, args.workers, args.heap_mb)
            record["family"] = model["family"]
            record["source"] = model["source"]
            record["bucket"] = bucket(record["seconds"], record["verdict"])
            results.append(record)
            print(f"  [{index:>3}/{len(runnable)}] {model['model_id']:<28} "
                  f"{record['verdict']:<12} distinct={record['distinct']} "
                  f"t={record['seconds']}s ({record['bucket']})")

    usable = [r for r in results if r["verdict"] in ("ok", "violation", "deadlock")]
    # P3 family diversity: at most two models per (family, bucket) at first pass
    rng = random.Random(seed)
    rng.shuffle(usable)
    selection: list[dict] = []
    per_family: dict[str, int] = {}
    per_bucket: dict[str, int] = {}
    for record in usable:
        if len(selection) >= size:
            break
        family = record["family"]
        if per_family.get(family, 0) >= 2 and len(usable) > size:
            continue
        selection.append(record)
        per_family[family] = per_family.get(family, 0) + 1
        per_bucket[record["bucket"]] = per_bucket.get(record["bucket"], 0) + 1
    # P4 cost spread: make sure the three cost buckets are represented
    for wanted in ("cheap", "medium", "expensive"):
        if per_bucket.get(wanted, 0) == 0:
            for record in usable:
                if record["bucket"] == wanted and record not in selection:
                    if len(selection) >= size:
                        selection[-1] = record
                    else:
                        selection.append(record)
                    per_bucket[wanted] = per_bucket.get(wanted, 0) + 1
                    break
    selection.sort(key=lambda r: (r["family"], r["model_id"]))

    exclusions = []
    for record in results:
        if record not in selection:
            reason = ("baseline failed: " + (record["errors"][0] if record["errors"]
                                             else record["verdict"])) \
                if record["verdict"] not in ("ok", "violation", "deadlock") \
                else "not selected by the diversity/size rule"
            exclusions.append({"model_id": record["model_id"],
                               "family": record["family"], "reason": reason,
                               "verdict": record["verdict"],
                               "seconds": record["seconds"]})
    for model in missing:
        exclusions.append({"model_id": model["model_id"], "family": model["family"],
                           "reason": "files not fetched (P1)", "verdict": None,
                           "seconds": None})
    for model in unprobed:
        exclusions.append({"model_id": model["model_id"], "family": model["family"],
                           "reason": "not probed within the compute budget (P2)",
                           "verdict": None, "seconds": None})

    subset = {
        "generated_by": "experiments/select_subset.py",
        "criterion": corpus["selection_criterion"],
        "seed": seed,
        "subset_size": size,
        "probe_timeout_s": timeout_s,
        "workers": args.workers,
        "heap_mb": args.heap_mb,
        "models": [
            {
                "model_id": r["model_id"],
                "module": r["model_id"],
                "spec_dir": next(c["spec_dir"] for c in pool
                                 if c["model_id"] == r["model_id"]),
                "config": f"{r['model_id']}.cfg",
                "family": r["family"],
                "source": r["source"],
                "baseline": {"verdict": r["verdict"], "distinct_states": r["distinct"],
                             "states": r["states"], "seconds": r["seconds"],
                             "bucket": r["bucket"]},
            }
            for r in selection
        ],
        "excluded": exclusions,
        "probe_summary": {
            "candidates": len(results),
            "runnable": len(usable),
            "failed": len(results) - len(usable),
            "selected": len(selection),
            "buckets": per_bucket,
        },
    }
    SUBSET.write_text(yaml.safe_dump(subset, sort_keys=False, allow_unicode=True),
                      encoding="utf-8")
    write_json(PROBE_JSON, {"results": results, "missing": missing})
    print(f"\nselected {len(selection)} models from {len(usable)} runnable "
          f"({len(results) - len(usable)} failed) -> {SUBSET.relative_to(ROOT)}")
    print("buckets:", per_bucket)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
