#!/usr/bin/env python3
"""Turn the raw run records into the tables the report cites.

Nothing in the report is typed by hand: this script reads only
``results/raw/**`` and ``config/subset.yaml`` and writes

* ``analysis/output/tables/*.md``   (Markdown, for the report and the README)
* ``analysis/output/tables/*.tex``  (LaTeX, for a paper draft)
* ``analysis/output/numbers.json``  (every headline number, consumed by
  ``analysis/make_report.py`` so prose and tables cannot drift apart)

    python analysis/make_tables.py
"""

from __future__ import annotations

import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import yaml  # noqa: E402

from symview.util import ensure_utf8_stdio, write_json, write_text  # noqa: E402

RAW = ROOT / "results" / "raw"
RUNS = RAW / "runs"
ANALYSIS = RAW / "analysis"
MUTANTS = RAW / "mutants"
OUT = ROOT / "analysis" / "output"
TABLES = OUT / "tables"
SUBSET = ROOT / "config" / "subset.yaml"
EXPERIMENT = ROOT / "config" / "experiment.yaml"


# ---------------------------------------------------------------- utilities
def load_json(path: Path, default=None):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def analysis_path(model_id: str) -> Path:
    return ANALYSIS / f"{model_id}.json"


def subset_models() -> list[dict]:
    models: list[dict] = []
    if SUBSET.exists():
        models = yaml.safe_load(SUBSET.read_text(encoding="utf-8"))["models"]
    # The hand-written lab models are part of the study too (they carry the
    # controlled reduction measurements), so they are appended when they have
    # been run.
    truth = ROOT / "benchmarks" / "lab" / "ground_truth.yaml"
    if truth.exists():
        for name, entry in yaml.safe_load(truth.read_text(encoding="utf-8"))["models"].items():
            if (ANALYSIS / f"{name}.json").exists():
                models.append({"model_id": name, "family": "lab",
                               "module": entry["root_module"],
                               "spec_dir": entry["dir"], "config": entry["config"]})
    return models


def experiments() -> dict:
    return yaml.safe_load(EXPERIMENT.read_text(encoding="utf-8"))


def md_table(headers: list[str], rows: list[list], align: list[str] | None = None) -> str:
    align = align or ["---"] * len(headers)
    lines = ["| " + " | ".join(headers) + " |",
             "|" + "|".join(align) + "|"]
    for row in rows:
        lines.append("| " + " | ".join(str(cell) for cell in row) + " |")
    return "\n".join(lines)


def tex_table(caption: str, headers: list[str], rows: list[list], label: str) -> str:
    def esc(value) -> str:
        text = str(value)
        for old, new in (("\\", "\\textbackslash{}"), ("_", "\\_"), ("%", "\\%"),
                         ("&", "\\&"), ("#", "\\#"), ("$", "\\$")):
            text = text.replace(old, new)
        return text

    body = ["\\begin{table}[t]", "\\centering", f"\\caption{{{esc(caption)}}}",
            f"\\label{{{label}}}", "\\small",
            "\\begin{tabular}{" + "l" * len(headers) + "}", "\\toprule",
            " & ".join(esc(h) for h in headers) + " \\\\", "\\midrule"]
    for row in rows:
        body.append(" & ".join(esc(c) for c in row) + " \\\\")
    body += ["\\bottomrule", "\\end{tabular}", "\\end{table}"]
    return "\n".join(body)


def median(values: list[float]) -> float | None:
    values = [v for v in values if isinstance(v, (int, float))]
    return statistics.median(values) if values else None


def pct(value: float | None, digits: int = 1) -> str:
    return "n/a" if value is None else f"{100 * value:.{digits}f}%"


def ratio(a: float | None, b: float | None) -> float | None:
    if not a or not b:
        return None
    return b / a


# ---------------------------------------------------------------- loading
def arm_runs(model_id: str) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = defaultdict(list)
    for path in sorted(RUNS.glob(f"{model_id}__*__r*.json")):
        payload = load_json(path, {})
        arm = payload.get("arm") or path.name.split("__")[1]
        out[arm].append(payload.get("run", {}))
    return out


def summarise_arm(runs: list[dict]) -> dict:
    completed = [r for r in runs if r.get("verdict") in ("ok", "violation", "deadlock")]
    return {
        "runs": len(runs),
        "verdict": runs[0].get("verdict") if runs else None,
        "distinct": runs[0].get("distinct_states") if runs else None,
        "states": runs[0].get("states_generated") if runs else None,
        "median_seconds": median([r.get("wall_seconds") for r in completed]),
        "timeout": any(r.get("verdict") == "timeout" for r in runs),
        "violated": runs[0].get("violated_invariants", []) if runs else [],
    }


# ---------------------------------------------------------------- RQ1 / RQ4
def rq1_rows(models: list[dict]) -> list[dict]:
    rows = []
    for entry in models:
        model_id = entry["model_id"]
        analysis = load_json(ANALYSIS / f"{model_id}.json", {})
        runs = arm_runs(model_id)
        arms = {arm: summarise_arm(runs.get(arm, [])) for arm in
                ("direct", "plain", "symmetry", "view", "both", "manual")}
        plain = arms["plain"]
        row = {
            "model_id": model_id,
            "family": entry.get("family", ""),
            "symmetry_set": ",".join(analysis.get("symmetry", {}).get("selected", [])) or "-",
            "view_dropped": ",".join(analysis.get("history", {}).get("dropped", [])) or "-",
            "plain_distinct": plain["distinct"],
            "plain_seconds": plain["median_seconds"],
            "symmetry_distinct": arms["symmetry"]["distinct"],
            "view_distinct": arms["view"]["distinct"],
            "both_distinct": arms["both"]["distinct"],
            "manual_distinct": arms["manual"]["distinct"],
            "symmetry_seconds": arms["symmetry"]["median_seconds"],
            "view_seconds": arms["view"]["median_seconds"],
            "both_seconds": arms["both"]["median_seconds"],
            "plain_verdict": plain["verdict"],
            "symmetry_verdict": arms["symmetry"]["verdict"],
            "view_verdict": arms["view"]["verdict"],
            "both_verdict": arms["both"]["verdict"],
            "direct_distinct": arms["direct"]["distinct"],
        }
        row["symmetry_reduction"] = (1 - ratio(plain["distinct"], arms["symmetry"]["distinct"])
                                     if arms["symmetry"]["distinct"] and plain["distinct"]
                                     else None)
        row["view_reduction"] = (1 - ratio(plain["distinct"], arms["view"]["distinct"])
                                 if arms["view"]["distinct"] and plain["distinct"] else None)
        row["both_reduction"] = (1 - ratio(plain["distinct"], arms["both"]["distinct"])
                                 if arms["both"]["distinct"] and plain["distinct"] else None)
        row["symmetry_speedup"] = (ratio(arms["symmetry"]["median_seconds"],
                                         plain["median_seconds"]))
        row["view_speedup"] = ratio(arms["view"]["median_seconds"], plain["median_seconds"])
        row["both_speedup"] = ratio(arms["both"]["median_seconds"], plain["median_seconds"])
        available = {arm: arms[arm]["distinct"] for arm in ("symmetry", "view", "both")
                     if arms[arm]["distinct"] and plain["distinct"]}
        row["applicable_arms"] = sorted(available)
        row["best_arm"] = min(available, key=lambda a: available[a]) if available else "-"
        row["best_distinct"] = available.get(row["best_arm"]) if available else None
        row["best_reduction"] = (1 - row["best_distinct"] / plain["distinct"]
                                 if row["best_distinct"] else None)
        row["best_seconds"] = arms[row["best_arm"]]["median_seconds"] \
            if available else None
        row["wrapper_transparent"] = (arms["direct"]["distinct"] == plain["distinct"]
                                      if arms["direct"]["distinct"] is not None else None)
        rows.append(row)
    return rows


def table_rq1(rows: list[dict]) -> tuple[str, str]:
    headers = ["model", "family", "symmetry set", "view drops", "plain states",
               "symmetry", "view", "both", "manual", "best arm", "reduction",
               "plain s", "best s"]
    body = []
    for r in rows:
        def states(key: str) -> str:
            value = r[key]
            return str(value) if value is not None else "-"
        body.append([
            r["model_id"], r["family"], r["symmetry_set"], r["view_dropped"],
            states("plain_distinct"), states("symmetry_distinct"),
            states("view_distinct"), states("both_distinct"),
            states("manual_distinct"), r["best_arm"],
            pct(r["best_reduction"]) if r["best_reduction"] is not None else "-",
            f"{r['plain_seconds']:.2f}" if r["plain_seconds"] else "-",
            f"{r['best_seconds']:.2f}" if r["best_seconds"] else "-",
        ])
    return md_table(headers, body), tex_table(
        "State-space reduction per model.  'best arm' is the strongest reduction "
        "certified for that model; dashes mean the arm was not applicable or the "
        "model finished without that reduction.",
        headers, body, "tab:rq1")


def table_rq4(rows: list[dict]) -> tuple[str, str]:
    headers = ["model", "symmetry", "view", "both", "best"]
    body = []
    for r in rows:
        candidates = {"symmetry": r["symmetry_reduction"],
                      "view": r["view_reduction"],
                      "both": r["both_reduction"]}
        available = {k: v for k, v in candidates.items() if v is not None}
        best = max(available, key=available.get) if available else "-"
        body.append([r["model_id"], pct(candidates["symmetry"]),
                     pct(candidates["view"]), pct(candidates["both"]), best])
    return md_table(headers, body), tex_table(
        "Ablation: relative state-space reduction of each reduction alone and combined.",
        headers, body, "tab:rq4")


# ---------------------------------------------------------------- RQ2
def rq2_rows(models: list[dict]) -> list[dict]:
    rows = []
    for entry in models:
        model_id = entry["model_id"]
        payload = load_json(MUTANTS / f"{model_id}.json", {})
        for mutant in payload.get("mutants", []):
            arms = mutant.get("arms", {})
            baseline = arms.get("plain", {})
            detected = mutant.get("detected")
            row = {
                "model_id": model_id,
                "mutant": mutant.get("mutant_id"),
                "operator": mutant.get("operator"),
                "line": mutant.get("line"),
                "baseline": baseline.get("verdict"),
                "baseline_violated": ",".join(baseline.get("violated", []) or []),
                "detected": detected,
            }
            for arm in ("symmetry", "view", "both"):
                run = arms.get(arm, {})
                row[f"{arm}_verdict"] = run.get("verdict")
                row[f"{arm}_violated"] = ",".join(run.get("violated", []) or [])
                if detected and run:
                    row[f"{arm}_preserved"] = (
                        run.get("verdict") == "violation"
                        and set(run.get("violated", []) or []) >= set(baseline.get("violated", []) or []))
                else:
                    row[f"{arm}_preserved"] = None
            rows.append(row)
    return rows


def table_rq2(rows: list[dict]) -> tuple[str, str]:
    headers = ["model", "mutant", "operator", "baseline", "symmetry", "view", "both"]
    body = []
    for r in rows:
        if not r["detected"]:
            continue
        def cell(arm: str) -> str:
            verdict = r.get(f"{arm}_verdict")
            if verdict is None:
                return "n/a"          # the arm was not applicable to this model
            if r.get(f"{arm}_preserved"):
                return "found"
            return f"MISSED ({verdict})"
        body.append([r["model_id"], r["mutant"], r["operator"], r["baseline_violated"] or r["baseline"],
                     cell("symmetry"), cell("view"), cell("both")])
    if not body:
        body = [["(no mutant was detected by the baseline)", "-", "-", "-", "-", "-", "-"]]
    return md_table(headers, body), tex_table(
        "Violation preservation: bugs detected by the unreduced baseline "
        "and re-detected under each reduction.",
        headers, body, "tab:rq2")


# ---------------------------------------------------------------- RQ3 / RQ5
def rq3_rows(models: list[dict]) -> list[dict]:
    rows = []
    for entry in models:
        model_id = entry["model_id"]
        analysis = load_json(ANALYSIS / f"{model_id}.json", {})
        symmetry = analysis.get("symmetry", {})
        history = analysis.get("history", {})
        candidates = symmetry.get("candidates", [])
        accepted = [c for c in candidates if c.get("verdict") == "sound"]
        rejected = [c for c in candidates if c.get("verdict") in ("unsound", "unknown")]
        reasons = Counter()
        for candidate in candidates:
            if candidate.get("verdict") == "sound":
                continue          # the positive explanation is not a rejection reason
            for reason in candidate.get("reasons", []):
                if "not invariant" in reason or "distinguished" in reason:
                    key = "distinguished-element"
                elif "non-equivariant" in reason:
                    key = "non-equivariant-operator"
                elif "unclassified" in reason:
                    key = "unclassified-operator"
                elif "resolve" in reason:
                    key = "unresolved-module"
                elif "temporal property" in reason or "fairness" in reason:
                    key = "liveness"
                elif "could not be interpreted" in reason:
                    key = "value-not-interpreted"
                elif "trivial" in reason or "permutation group" in reason:
                    key = "trivial-group"
                else:
                    key = "other"
                reasons[key] += 1
        rows.append({
            "model_id": model_id,
            "candidates": len(candidates),
            "accepted": len(accepted),
            "rejected": len(rejected),
            "reasons": dict(reasons),
            "view_verdict": history.get("verdict"),
            "dropped": len(history.get("dropped", [])),
            "liveness": analysis.get("program", {}).get("liveness"),
            "parser_coverage": analysis.get("context", {}).get("parse_stats", {}).get("cov_coverage"),
        })
    return rows


def table_rq3(rows: list[dict], ground_truth: dict) -> tuple[str, str]:
    headers = ["model", "candidates", "accepted", "rejected", "view", "dropped",
               "liveness warning", "rejection reasons"]
    body = []
    for r in rows:
        body.append([r["model_id"], r["candidates"], r["accepted"], r["rejected"],
                     r["view_verdict"], r["dropped"],
                     "yes" if r["liveness"] else "no",
                     ", ".join(f"{k}:{v}" for k, v in sorted(r["reasons"].items())) or "-"])
    return md_table(headers, body), tex_table(
        "Soundness bookkeeping: candidates proposed, accepted and rejected, with "
        "the reason each rejection fired.",
        headers, body, "tab:rq3")


def table_ground_truth(gt: dict) -> tuple[str, str]:
    rows = []
    for name, entry in gt.get("models", {}).items():
        expected = entry.get("expected_symmetry", {})
        rows.append([name, expected.get("candidate") or "-", expected.get("verdict"),
                     ",".join(entry.get("expected_history") or []) or "-",
                     "yes" if entry.get("expected_liveness_warning") else "no"])
    headers = ["lab model", "expected candidate", "expected verdict",
               "expected droppable", "liveness warning"]
    return md_table(headers, rows), tex_table(
        "Ground truth of the hand-written lab models.", headers, rows, "tab:truth")


# ---------------------------------------------------------------- main
def main() -> int:
    ensure_utf8_stdio()
    TABLES.mkdir(parents=True, exist_ok=True)
    models = subset_models()
    config = experiments()
    numbers: dict = {"generated_from": "results/raw/**", "models": len(models)}

    rq1 = rq1_rows(models)
    md, tex = table_rq1(rq1)
    write_text(TABLES / "rq1_reduction.md", md)
    write_text(TABLES / "rq1_reduction.tex", tex)

    rq4 = rq1
    md, tex = table_rq4(rq4)
    write_text(TABLES / "rq4_ablation.md", md)
    write_text(TABLES / "rq4_ablation.tex", tex)

    rq2 = rq2_rows(models)
    md, tex = table_rq2(rq2)
    write_text(TABLES / "rq2_violation_preservation.md", md)
    write_text(TABLES / "rq2_violation_preservation.tex", tex)

    rq3 = rq3_rows(models)
    gt_path = ROOT / "benchmarks" / "lab" / "ground_truth.yaml"
    gt = yaml.safe_load(gt_path.read_text(encoding="utf-8")) if gt_path.exists() else {}
    md, tex = table_rq3(rq3, gt)
    write_text(TABLES / "rq3_soundness.md", md)
    write_text(TABLES / "rq3_soundness.tex", tex)
    md, tex = table_ground_truth(gt)
    write_text(TABLES / "ground_truth.md", md)
    write_text(TABLES / "ground_truth.tex", tex)

    # headline numbers
    with_plain = [r for r in rq1 if r["plain_distinct"]]
    best_rows = [r for r in with_plain if r["best_reduction"] is not None]
    best = [r["best_reduction"] for r in best_rows]
    reductions_sym = [r["symmetry_reduction"] for r in with_plain
                      if r["symmetry_reduction"] is not None]
    reductions_view = [r["view_reduction"] for r in with_plain if r["view_reduction"] is not None]
    reductions_both = [r["both_reduction"] for r in with_plain if r["both_reduction"] is not None]
    speedups = [r["best_seconds"] / r["plain_seconds"] for r in best_rows
                if r["best_seconds"] and r["plain_seconds"]]
    detected = [r for r in rq2 if r["detected"]]
    # Empirical soundness guard: an arm must never turn a clean baseline run into a
    # violation.  This is computed from the raw runs, independently of the static
    # analysis, and it is the strongest statement the experiment can make.
    new_violations = []
    compared = 0
    for entry in models:
        model_id = entry["model_id"]
        runs = arm_runs(model_id)
        base = summarise_arm(runs.get("plain", []))
        if base.get("verdict") not in ("ok",):
            continue
        for arm in ("symmetry", "view", "both", "manual"):
            summary = summarise_arm(runs.get(arm, []))
            if not summary.get("runs"):
                continue
            compared += 1
            if summary.get("verdict") == "violation":
                new_violations.append({"model": model_id, "arm": arm,
                                       "violated": summary.get("violated")})
    integrity = load_json(RAW / "integrity_checks.json", {}).get("summary", {})
    preservation = {}
    for arm in ("symmetry", "view", "both"):
        applicable = [r for r in detected if r.get(f"{arm}_verdict") is not None]
        kept = [r for r in applicable if r.get(f"{arm}_preserved")]
        preservation[arm] = {
            "applicable": len(applicable),
            "preserved": len(kept),
            "missed": len(applicable) - len(kept),
            "rate": (len(kept) / len(applicable)) if applicable else None,
            "missed_mutants": [r["mutant"] for r in applicable
                               if not r.get(f"{arm}_preserved")],
        }
    numbers.update({
        "rq1": {
            "models": len(rq1),
            "models_with_baseline": len(with_plain),
            "models_with_reduction": len(best_rows),
            "median_best_reduction": median(best),
            "mean_best_reduction": (statistics.fmean(best) if best else None),
            "max_best_reduction": max(best) if best else None,
            "manual_matches_automatic": {
                r["model_id"]: (r["symmetry_distinct"] == r["manual_distinct"])
                for r in rq1 if r["manual_distinct"] and r["symmetry_distinct"]},
            "models_with_manual": sum(1 for r in rq1 if r["manual_distinct"]),
            "best_reduction_models": {r["model_id"]: r["best_reduction"]
                                      for r in best_rows},
            "median_symmetry_reduction": median(reductions_sym),
            "median_view_reduction": median(reductions_view),
            "median_both_reduction": median(reductions_both),
            "median_best_speedup": median(speedups),
            "wrapper_transparent": all(r["wrapper_transparent"] for r in rq1
                                       if r["wrapper_transparent"] is not None),
            "timeouts_plain": sum(1 for r in rq1 if r["plain_verdict"] == "timeout"),
            "timeouts_symmetry": sum(1 for r in rq1 if r["symmetry_verdict"] == "timeout"),
        },
        "speedups": {
            "examples": [
                {"model": r["model_id"], "plain_s": r["plain_seconds"],
                 "best_s": r["best_seconds"], "arm": r["best_arm"],
                 "reduction": r["best_reduction"],
                 "speedup": (r["plain_seconds"] / r["best_seconds"]
                             if r["best_seconds"] else None)}
                for r in best_rows if r["best_seconds"] and r["plain_seconds"]
            ],
            "median_over_3s": median([
                r["plain_seconds"] / r["best_seconds"] for r in best_rows
                if r["best_seconds"] and r["plain_seconds"] and r["plain_seconds"] >= 3]),
        },
        "rq2": {
            "mutants_generated": len(rq2),
            "mutants_detected_by_baseline": len(detected),
            "preservation": preservation,
            "preserved": {arm: preservation[arm]["preserved"] for arm in preservation},
            "preservation_rate": {arm: preservation[arm]["rate"] for arm in preservation},
        },
        "rq3": {
            "candidates": sum(r["candidates"] for r in rq3),
            "accepted": sum(r["accepted"] for r in rq3),
            "rejected": sum(r["rejected"] for r in rq3),
            "reason_counts": dict(sum((Counter(r["reasons"]) for r in rq3),
                                      Counter())),
            "models_with_accepted_symmetry": sum(1 for r in rq3 if r["accepted"]),
            "models_with_view": sum(1 for r in rq3 if r["dropped"]),
            "models_with_liveness": sum(1 for r in rq3 if r["liveness"]),
            "models_with_symmetry_emitted": sum(
                1 for entry in models
                if (RUNS / f"{entry['model_id']}__symmetry__r0.json").exists()
                or (RUNS / f"{entry['model_id']}__both__r0.json").exists()),
            "empirical_new_violations": new_violations,
            "arm_runs_compared": compared,
            "integrity": integrity,
            "models_with_zero_candidates": sum(1 for r in rq3 if r["candidates"] == 0),
        },
        "rq5": {
            "models": len(rq3),
            "symmetry_coverage": (sum(1 for r in rq3 if r["accepted"]) / len(rq3)
                                  if rq3 else None),
            "view_coverage": (sum(1 for r in rq3 if r["dropped"]) / len(rq3)
                              if rq3 else None),
            "mean_parser_coverage": median([r["parser_coverage"] for r in rq3
                                            if r["parser_coverage"]]),
        },
        "budget": config.get("budget", {}),
        "subset_probe": load_json(RAW / "subset_probe.json", {}).get("results", []) and
                        load_json(RAW / "subset_probe.json", {}).get("results"),
    })
    parser_raw = load_json(RAW / "parser_robustness.json", {})
    if parser_raw:
        numbers["parser"] = parser_raw.get("summary", {})
    write_json(OUT / "numbers.json", numbers)
    print(json.dumps({k: v for k, v in numbers.items() if k in ("rq1", "rq2", "rq3", "rq5")},
                     indent=2, ensure_ascii=False)[:2000])
    print(f"\n[ok] tables in {TABLES.relative_to(ROOT)}")
    print(f"[ok] {OUT.relative_to(ROOT) / 'numbers.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
