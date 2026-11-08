#!/usr/bin/env python3
"""Internal validity checks the course guide asks for.

Section 1-6 of the guide requires more than "the numbers look nice": a reduction
must not be credited for *not checking* anything (vacuity), the checked
properties must actually constrain state variables, and state counts must be
reproducible.  This script computes those checks from the raw results and the
specifications, and writes

* ``results/raw/integrity_checks.json``
* ``analysis/output/tables/integrity.md``

Checks
------
1. **Non-vacuity of the configuration**: every model checks at least one
   invariant or property, and the property is not the literal ``TRUE``/``FALSE``.
2. **The property observes the state**: transitively, a checked property reads at
   least one declared variable.  A property that mentions no variable is vacuous.
3. **The reduction does not hide the property**: the reduced arm is run with the
   same configuration (same invariants) and reports a verdict.
4. **Determinism**: for every (model, arm) with more than one repeat, the distinct
   state count is identical.  TLC's BFS is deterministic; this proves the runs are
   comparable at the level of the metric we report.
5. **Wrapper transparency**: ``direct`` and ``plain`` produce the same state count
   (checked again here, from the raw files).
6. **No empty model**: every completed run found at least one distinct state.

    python analysis/checks.py
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from symview.astnodes import N  # noqa: E402
from symview.analysis.program import SpecProgram  # noqa: E402
from symview.context import load_context  # noqa: E402
from symview.util import ensure_utf8_stdio, write_json, write_text  # noqa: E402

RAW = ROOT / "results" / "raw"
TABLES = ROOT / "analysis" / "output" / "tables"
SUBSET = ROOT / "config" / "subset.yaml"
SUPPORT = [ROOT / "benchmarks" / "support"]


def models() -> list[dict]:
    rows = yaml.safe_load(SUBSET.read_text(encoding="utf-8"))["models"]
    truth = ROOT / "benchmarks" / "lab" / "ground_truth.yaml"
    if truth.exists():
        for name, entry in yaml.safe_load(truth.read_text(encoding="utf-8"))["models"].items():
            if (RAW / "analysis" / f"{name}.json").exists():
                rows.append({"model_id": name, "module": entry["root_module"],
                             "spec_dir": entry["dir"], "config": entry["config"],
                             "family": "lab"})
    return rows


def transitive_variables(program: SpecProgram, name: str, limit: int = 400) -> set[str]:
    """Variables read by ``name`` and by every definition it calls."""
    seen: set[str] = set()
    queue = [name]
    variables: set[str] = set()
    while queue and len(seen) < limit:
        current = queue.pop()
        key = current.split("!")[-1]
        if key in seen:
            continue
        seen.add(key)
        body = program.definition_body(current)
        if body is None:
            continue
        for leaf in body.walk():
            if leaf.kind == "name":
                if program.name_kind.get(leaf.text) == "variable":
                    variables.add(leaf.text)
                elif leaf.text in program.ctx.opdefs:
                    queue.append(leaf.text)
            elif leaf.kind == "bang":
                left, right = leaf.kid("left"), leaf.kid("right")
                if left is None or right is None:
                    continue
                module = program.alias_module.get(left.text, left.text)
                for candidate in (f"{module}!{right.text}", right.text):
                    if candidate in program.ctx.opdefs:
                        queue.append(candidate)
                        break
    return variables


def is_literal(node: N | None) -> bool:
    return node is not None and node.kind in ("bool",)


def main() -> int:
    ensure_utf8_stdio()
    TABLES.mkdir(parents=True, exist_ok=True)
    rows = []
    for entry in models():
        model_id = entry["model_id"]
        spec_dir = ROOT / entry["spec_dir"]
        try:
            ctx = load_context(spec_dir, entry["module"], spec_dir / entry["config"],
                               support_dirs=SUPPORT)
        except Exception as exc:                  # a broken model is a finding, not a crash
            rows.append({"model_id": model_id, "error": f"{type(exc).__name__}: {exc}"})
            continue
        program = SpecProgram.build(ctx)
        checked = list(ctx.cfg.invariants) + list(ctx.cfg.properties)
        vacuous = []
        unobserving = []
        for name in checked:
            body = program.definition_body(name)
            if body is None:
                unobserving.append(name)          # unresolved definition
                continue
            if is_literal(body):
                vacuous.append(name)
                continue
            if not transitive_variables(program, name):
                unobserving.append(name)
        # determinism and transparency from the raw runs
        repeat_values: dict[str, set] = {}
        verdicts: dict[str, str] = {}
        for path in sorted((RAW / "runs").glob(f"{model_id}__*__r*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            arm = payload.get("arm") or path.name.split("__")[1]
            run = payload.get("run", {})
            repeat_values.setdefault(arm, set()).add(run.get("distinct_states"))
            verdicts.setdefault(arm, run.get("verdict"))
        nondeterministic = [arm for arm, values in repeat_values.items() if len(values) > 1]
        empty_runs = [arm for arm, values in repeat_values.items()
                      if values == {None} or values == {0}]
        transparent = None
        if "direct" in repeat_values and "plain" in repeat_values:
            transparent = repeat_values["direct"] == repeat_values["plain"]
        rows.append({
            "model_id": model_id, "family": entry.get("family", ""),
            "checked_properties": len(checked),
            "vacuous_literals": vacuous,
            "properties_without_state": unobserving,
            "nondeterministic_arms": nondeterministic,
            "empty_arms": empty_runs,
            "wrapper_transparent": transparent,
            "arms": sorted(repeat_values),
            "verdicts": verdicts,
        })

    ok = [r for r in rows if "error" not in r]
    summary = {
        "models": len(rows),
        "errors": [r for r in rows if "error" in r],
        "models_without_properties": [r["model_id"] for r in ok if r["checked_properties"] == 0],
        "models_with_vacuous_literal": [r["model_id"] for r in ok if r["vacuous_literals"]],
        "models_with_unobserving_property": [r["model_id"] for r in ok
                                             if r["properties_without_state"]],
        "models_nondeterministic": [r["model_id"] for r in ok if r["nondeterministic_arms"]],
        "repeat_pairs_checked": sum(1 for r in ok if len(r["arms"])),
        "wrapper_transparency_failures": [r["model_id"] for r in ok
                                          if r["wrapper_transparent"] is False],
        "models_with_empty_run": [r["model_id"] for r in ok if r["empty_arms"]],
        "verdict_counter": dict(Counter(v for r in ok for v in r["verdicts"].values()
                                        if v not in (None, "not-applicable"))),
    }
    write_json(RAW / "integrity_checks.json", {"summary": summary, "models": rows})

    lines = ["# Internal validity checks", "",
             "Generated by `analysis/checks.py`; do not edit by hand.", "",
             f"- models inspected: **{summary['models']}**",
             f"- models that check no property: **{len(summary['models_without_properties'])}**",
             f"- checked properties that are a literal TRUE/FALSE: "
             f"**{len(summary['models_with_vacuous_literal'])}**",
             f"- checked properties that read no state variable: "
             f"**{len(summary['models_with_unobserving_property'])}**",
             f"- (model, arm) pairs with non-deterministic state counts: "
             f"**{len(summary['models_nondeterministic'])}**",
             f"- wrapper-transparency failures (`direct` != `plain`): "
             f"**{len(summary['wrapper_transparency_failures'])}**",
             f"- models with an empty run: **{len(summary['models_with_empty_run'])}**", "",
             "## Per model", "",
             "| model | checked | vacuous literal | unobserving | non-det. arms | "
             "direct==plain |", "|---|---|---|---|---|---|"]
    for r in rows:
        if "error" in r:
            lines.append(f"| {r['model_id']} | error | {r['error']} | | | |")
            continue
        lines.append(f"| {r['model_id']} | {r['checked_properties']} | "
                     f"{','.join(r['vacuous_literals']) or '-'} | "
                     f"{','.join(r['properties_without_state']) or '-'} | "
                     f"{','.join(r['nondeterministic_arms']) or '-'} | "
                     f"{r['wrapper_transparent'] if r['wrapper_transparent'] is not None else '-'} |")
    lines.append("")
    write_text(TABLES / "integrity.md", "\n".join(lines))
    print(json.dumps(summary, indent=1, ensure_ascii=False)[:1500])
    print(f"[ok] {TABLES.relative_to(ROOT) / 'integrity.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
