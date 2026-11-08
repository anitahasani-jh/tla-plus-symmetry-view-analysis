#!/usr/bin/env python3
"""Render the Persian technical report from the generated numbers.

The prose lives in ``docs/report_fa.template.md``; every number and every table
is injected here from ``analysis/output/numbers.json`` and
``analysis/output/tables/*.md``, so the report can never disagree with the raw
results.  Run ``make_tables.py`` first.

    python analysis/make_report.py
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from symview.util import ensure_utf8_stdio, write_text  # noqa: E402

NUMBERS = ROOT / "analysis" / "output" / "numbers.json"
TABLES = ROOT / "analysis" / "output" / "tables"
TEMPLATE = ROOT / "docs" / "report_fa.template.md"
TARGET = ROOT / "docs" / "report_fa.md"
RAW = ROOT / "results" / "raw"


def load(path: Path, default=None):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def load_yaml(path: Path, default=None):
    import yaml
    return yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else default


def table(name: str) -> str:
    path = TABLES / f"{name}.md"
    if not path.exists():
        return "_(جدول تولید نشده است)_"
    text = path.read_text(encoding="utf-8").strip()
    # The report embeds the table body without its duplicate heading.
    return text


def pct(value, digits: int = 1) -> str:
    if value is None:
        return "نامشخص"
    return f"{100 * value:.{digits}f}٪"


def number(value, digits: int = 2) -> str:
    if value is None:
        return "نامشخص"
    return f"{value:.{digits}f}"


def _pres(rq2: dict, arm: str) -> tuple[int, int, int]:
    detail = (rq2.get("preservation") or {}).get(arm) or {}
    return (detail.get("preserved", 0), detail.get("applicable", 0),
            detail.get("missed", 0))


def ground_truth_agreement() -> tuple[int, int]:
    """Run the lab ground-truth test and parse its summary line."""
    script = ROOT / "tests" / "test_lab_ground_truth.py"
    if not script.exists():
        return 0, 0
    try:
        proc = subprocess.run([sys.executable, str(script)], cwd=str(ROOT),
                              capture_output=True, text=True, timeout=900)
        text = (proc.stdout or "") + (proc.stderr or "")
        match = re.search(r"models=(\d+) failures=(\d+)", text)
        if match:
            models, failures = int(match.group(1)), int(match.group(2))
            return models - failures, models
    except (OSError, subprocess.SubprocessError):
        pass
    return 0, 0


def lab_log_reduction() -> str:
    plain = load(RAW / "runs" / "LabLog__plain__r0.json")
    both = load(RAW / "runs" / "LabLog__both__r0.json")
    if not plain or not both:
        return "نامشخص"
    a = plain["run"].get("distinct_states")
    b = both["run"].get("distinct_states")
    if not a or not b:
        return "نامشخص"
    return pct(1 - b / a)


def main() -> int:
    ensure_utf8_stdio()
    numbers = load(NUMBERS)
    if not numbers:
        print("[error] analysis/output/numbers.json missing; run make_tables.py first")
        return 1
    subset = (load_yaml(ROOT / "config" / "subset.yaml", {}) or {}).get("models", [])
    survey = (load(RAW / "config_survey.json", {}) or {}).get("summary", {})
    parser = numbers.get("parser", {})
    agree, total = ground_truth_agreement()

    rq1 = numbers.get("rq1", {})
    rq2 = numbers.get("rq2", {})
    rq3 = numbers.get("rq3", {})
    rq5 = numbers.get("rq5", {})
    budget = numbers.get("budget", {})
    experiment = (load_yaml(ROOT / "config" / "experiment.yaml", {}) or {})

    buckets: dict[str, int] = {}
    families = set()
    for model in subset:
        bucket = (model.get("baseline") or {}).get("bucket", "unknown")
        buckets[bucket] = buckets.get(bucket, 0) + 1
        families.add(model.get("family", ""))

    max_model = "-"
    max_value = None
    rq1_table = TABLES / "rq1_reduction.md"
    if rq1_table.exists():
        rows = re.findall(r"^\| (\S+) \|.*?\| (\d+(?:\.\d+)?)% \|", rq1_table.read_text(encoding="utf-8"),
                          re.MULTILINE)
        for name, value in rows:
            if max_value is None or float(value) > max_value:
                max_value, max_model = float(value), name

    values = {
        "VERSION": "1.0.0",
        "DATE": "۶ نوامبر ۲۰۲۶",
        "N_MODELS": str(len(subset)),
        "N_FAMILIES": str(len(families)),
        "N_CHEAP": str(buckets.get("cheap", 0)),
        "N_MEDIUM": str(buckets.get("medium", 0)),
        "N_EXPENSIVE": str(buckets.get("expensive", 0)),
        "MEDIAN_REDUCTION": pct(rq1.get("median_best_reduction")),
        "N_WITH_REDUCTION": str(rq1.get("models_with_reduction", 0)),
        "N_ANALYSED": str(rq1.get("models", 0)),
        "MANUAL_MODELS": str(rq1.get("models_with_manual", 0)),
        "MANUAL_MATCH": str(sum(1 for v in (rq1.get("manual_matches_automatic") or {}).values() if v)),
        "EMITTED_MODELS": str(rq3.get("models_with_symmetry_emitted", 0)),
        "ARM_RUNS_COMPARED": str(rq3.get("arm_runs_compared", 0)),
        "EMPIRICAL_UNSOUND": str(len(rq3.get("empirical_new_violations") or [])),
        "MODELS_WITHOUT_PROPS": str(len((rq3.get("integrity") or {}).get("models_without_properties", []))),
        "VACUOUS": str(len((rq3.get("integrity") or {}).get("models_with_vacuous_literal", []))),
        "UNOBSERVING": str(len((rq3.get("integrity") or {}).get("models_with_unobserving_property", []))),
        "NONDET": str(len((rq3.get("integrity") or {}).get("models_nondeterministic", []))),
        "TRANSPARENCY": str(len((rq3.get("integrity") or {}).get("wrapper_transparency_failures", []))),
        "EMPTY_RUNS": str(len((rq3.get("integrity") or {}).get("models_with_empty_run", []))),
        "MEDIAN_SPEEDUP_OVER_3S": number((numbers.get("speedups") or {}).get("median_over_3s")),
        "MEAN_REDUCTION": pct(rq1.get("mean_both_reduction")),
        "MAX_REDUCTION": f"{max_value:.0f}٪" if max_value is not None else "نامشخص",
        "REDUCTION_MODEL_MAX": max_model,
        "MEDIAN_SPEEDUP": number(rq1.get("median_best_speedup")),
        "WRAPPER_TRANSPARENT": "بله" if rq1.get("wrapper_transparent") else "خیر",
        "MUTANTS_GENERATED": str(rq2.get("mutants_generated", 0)),
        "MUTANTS_DETECTED": str(rq2.get("mutants_detected_by_baseline", 0)),
        "PRESERVED_SYM": str(_pres(rq2, "symmetry")[0]),
        "PRESERVED_VIEW": str(_pres(rq2, "view")[0]),
        "PRESERVED_BOTH": str(_pres(rq2, "both")[0]),
        "PRESERVED_SYM_APPLICABLE": str(_pres(rq2, "symmetry")[1]),
        "PRESERVED_VIEW_APPLICABLE": str(_pres(rq2, "view")[1]),
        "PRESERVED_BOTH_APPLICABLE": str(_pres(rq2, "both")[1]),
        "MISSED_SYM": str(_pres(rq2, "symmetry")[2]),
        "MISSED_VIEW": str(_pres(rq2, "view")[2]),
        "MISSED_BOTH": str(_pres(rq2, "both")[2]),
        "PRESERVATION_RATE_BOTH": pct((rq2.get("preservation_rate") or {}).get("both")),
        "CANDIDATES": str(rq3.get("candidates", 0)),
        "ACCEPTED": str(rq3.get("accepted", 0)),
        "REJECTED": str(rq3.get("rejected", 0)),
        "SYM_COVERAGE": pct(rq5.get("symmetry_coverage")),
        "LIVE_MODELS": str(rq3.get("models_with_liveness", 0)),
        "ZERO_CANDIDATE_MODELS": str(rq3.get("models_with_zero_candidates", 0)),
        "VIEW_COVERAGE": pct(rq5.get("view_coverage")),
        "PARSER_FILES": str(parser.get("files", 0)),
        "PARSER_CRASHES": str(parser.get("files_crashed", 0)),
        "PARSER_COVERAGE": pct(parser.get("token_coverage")),
        "PARSER_PERFECT": str(parser.get("files_perfect_ast", 0)),
        "PARSER_BAD": str(parser.get("bad_tokens_total", 0)),
        "BUDGET_SECONDS": str(budget.get("timeout_s", "-")),
        "WORKERS": str(budget.get("workers", "-")),
        "HEAP_MB": str(budget.get("heap_mb", "-")),
        "MUTANTS_PER_MODEL": str((experiment.get("mutants") or {}).get("per_model", "-")),
        "LAB_AGREEMENT": str(agree),
        "LAB_TOTAL": str(total),
        "LAB_LOG_REDUCTION": lab_log_reduction(),
        "CFG_TOTAL": str(survey.get("configurations", 0)),
        "CFG_SYMMETRY": str(survey.get("with_symmetry", 0)),
        "CFG_VIEW": str(survey.get("with_view", 0)),
        "CFG_PROPS": str(survey.get("with_properties", 0)),
        "CFG_DISABLED": str(survey.get("disabled_reduction_lines", 0)),
        "CFG_DISABLED_WARN": str(survey.get("disabled_with_warning", 0)),
        "TABLE_RQ1": table("rq1_reduction"),
        "TABLE_RQ2": table("rq2_violation_preservation"),
        "TABLE_RQ3": table("rq3_soundness"),
        "TABLE_RQ4": table("rq4_ablation"),
        "TABLE_TRUTH": table("ground_truth"),
    }
    examples = (numbers.get("speedups") or {}).get("examples") or []
    biggest = max(examples, key=lambda e: e.get("plain_s") or 0, default={})
    values.update({
        "ALLOC_MODEL": biggest.get("model", "-"),
        "ALLOC_PLAIN_S": f"{biggest.get('plain_s', 0):.2f}" if biggest else "-",
        "ALLOC_BEST_S": f"{biggest.get('best_s', 0):.2f}" if biggest else "-",
        "ALLOC_SPEEDUP": f"{biggest.get('speedup', 0):.2f}" if biggest else "-",
        "ALLOC_REDUCTION": pct(biggest.get("reduction")),
    })
    git = load(RAW / "git.json", {}) or {}
    values.update({
        "GIT_REPO": git.get("repo", "در حال ثبت"),
        "GIT_BRANCH": git.get("branch", "main"),
        "GIT_COMMIT": git.get("commit", "در حال ثبت"),
        "GIT_DATE": git.get("date", "-"),
    })
    template = TEMPLATE.read_text(encoding="utf-8")
    rendered = template
    missing = set()
    for key, value in values.items():
        placeholder = "{{" + key + "}}"
        if placeholder in rendered:
            rendered = rendered.replace(placeholder, value)
    for leftover in re.findall(r"\{\{([A-Z0-9_]+)\}\}", rendered):
        missing.add(leftover)
    write_text(TARGET, rendered)
    print(f"[ok] {TARGET.relative_to(ROOT)}  ({len(rendered.splitlines())} lines)")
    if missing:
        print(f"[warn] unfilled placeholders: {sorted(missing)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
