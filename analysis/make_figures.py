#!/usr/bin/env python3
"""Figures for the report, generated only from ``results/raw/**``.

    python analysis/make_figures.py

Writes PNG (300 dpi) and SVG into ``analysis/output/figures``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import yaml  # noqa: E402

from symview.util import ensure_utf8_stdio, write_text  # noqa: E402

RAW = ROOT / "results" / "raw"
OUT = ROOT / "analysis" / "output" / "figures"
TABLES = ROOT / "analysis" / "output" / "tables"
SUBSET = ROOT / "config" / "subset.yaml"
COLORS = {"plain": "#4c566a", "symmetry": "#5e81ac", "view": "#a3be8c",
          "both": "#bf616a", "manual": "#b48ead"}
plt.rcParams.update({"figure.dpi": 120, "savefig.dpi": 300, "font.size": 9,
                     "axes.spines.top": False, "axes.spines.right": False})


def load(path: Path, default=None):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def models() -> list[dict]:
    rows: list[dict] = []
    if SUBSET.exists():
        rows = yaml.safe_load(SUBSET.read_text(encoding="utf-8"))["models"]
    truth = ROOT / "benchmarks" / "lab" / "ground_truth.yaml"
    if truth.exists():
        for name, entry in yaml.safe_load(truth.read_text(encoding="utf-8"))["models"].items():
            if (RAW / "analysis" / f"{name}.json").exists():
                rows.append({"model_id": name, "family": "lab"})
    return rows


def arm_series(model_id: str) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for path in sorted((RAW / "runs").glob(f"{model_id}__*__r*.json")):
        payload = load(path, {})
        arm = payload.get("arm") or path.name.split("__")[1]
        out.setdefault(arm, payload.get("run", {}))
    return out


def save(fig, name: str) -> None:
    fig.tight_layout()
    for suffix in ("png", "svg"):
        fig.savefig(OUT / f"{name}.{suffix}", bbox_inches="tight")
    plt.close(fig)
    print(f"  {name}.png / .svg")


def fig_reduction(rows: list[dict]) -> None:
    rows = [r for r in rows if r.get("plain_distinct") and r.get("both_distinct")]
    if not rows:
        return
    rows.sort(key=lambda r: r["both_reduction"])
    labels = [r["model_id"] for r in rows]
    values = [100 * r["both_reduction"] for r in rows]
    fig, ax = plt.subplots(figsize=(6.4, 0.28 * len(rows) + 1.2))
    ax.barh(labels, values, color=COLORS["both"])
    for index, value in enumerate(values):
        ax.text(value + 1, index, f"{value:.0f}%", va="center", fontsize=7)
    ax.set_xlabel("distinct-state reduction with SYMMETRY + VIEW (%)")
    ax.set_xlim(0, max(105, max(values) + 12))
    save(fig, "fig_rq1_reduction")


def fig_cactus(rows: list[dict]) -> None:
    series = {}
    for arm in ("plain", "symmetry", "view", "both"):
        times = sorted(r[f"{arm}_seconds"] for r in rows
                       if r.get(f"{arm}_seconds") is not None)
        if times:
            series[arm] = times
    if not series:
        return
    fig, ax = plt.subplots(figsize=(5.6, 3.4))
    for arm, times in series.items():
        xs = list(range(1, len(times) + 1))
        ax.step(xs, times, where="post", label=arm, color=COLORS[arm], linewidth=1.6)
    ax.set_xlabel("models solved (sorted by time)")
    ax.set_ylabel("wall-clock seconds (median per model)")
    ax.set_yscale("log")
    ax.legend(frameon=False)
    save(fig, "fig_rq1_cactus")


def fig_preservation() -> None:
    records = []
    for path in sorted((RAW / "mutants").glob("*.json")):
        records += load(path, {}).get("mutants", [])
    detected = [m for m in records if m.get("detected")]
    if not detected:
        return
    arms = ["symmetry", "view", "both"]
    found = [sum(1 for m in detected if m.get("arms", {}).get(a, {}).get("verdict") == "violation"
                 and set(m.get("arms", {}).get(a, {}).get("violated", []))
                 >= set(m.get("violated", []))) for a in arms]
    missed = [len(detected) - f for f in found]
    fig, ax = plt.subplots(figsize=(4.6, 3.0))
    x = np.arange(len(arms))
    ax.bar(x, found, color=COLORS["both"], label="violation preserved")
    ax.bar(x, missed, bottom=found, color="#d8dee9", label="missed")
    for index, value in enumerate(found):
        ax.text(index, value / 2, str(value), ha="center", va="center", fontsize=8)
    ax.set_xticks(x, arms)
    ax.set_ylabel(f"mutants detected by baseline (n={len(detected)})")
    ax.legend(frameon=False, fontsize=7)
    save(fig, "fig_rq2_preservation")


def fig_ablation(rows: list[dict]) -> None:
    rows = [r for r in rows if r["plain_distinct"]]
    if not rows:
        return
    rows.sort(key=lambda r: r["model_id"])
    labels = [r["model_id"] for r in rows]
    x = np.arange(len(rows))
    width = 0.26
    fig, ax = plt.subplots(figsize=(max(6.4, 0.45 * len(rows) + 2), 3.2))
    for offset, arm in enumerate(("symmetry", "view", "both")):
        values = [100 * (r[f"{arm}_reduction"] or 0) for r in rows]
        ax.bar(x + (offset - 1) * width, values, width, label=arm, color=COLORS[arm])
    ax.set_xticks(x, labels, rotation=45, ha="right", fontsize=7)
    ax.set_ylabel("reduction (%)")
    ax.legend(frameon=False)
    save(fig, "fig_rq4_ablation")


def fig_coverage() -> None:
    rows = []
    for path in sorted((RAW / "analysis").glob("*.json")):
        rows.append(load(path, {}))
    if not rows:
        return
    accepted = [(r.get("symmetry", {}).get("candidates") or []) for r in rows]
    total = sum(len(c) for c in accepted)
    verdicts = {"sound": 0, "unsound": 0, "unknown": 0, "trivial": 0}
    for candidates in accepted:
        for candidate in candidates:
            verdicts[candidate.get("verdict", "unknown")] = \
                verdicts.get(candidate.get("verdict", "unknown"), 0) + 1
    views = sum(1 for r in rows if r.get("history", {}).get("dropped"))
    fig, (left, right) = plt.subplots(1, 2, figsize=(7.2, 2.9),
                                      gridspec_kw={"width_ratios": [1, 1.2]})
    colors = {"sound": "#a3be8c", "unsound": "#bf616a", "unknown": "#ebcb8b",
              "trivial": "#d8dee9"}
    labels = [k for k, v in verdicts.items() if v]
    left.bar(labels, [verdicts[k] for k in labels], color=[colors[k] for k in labels])
    left.set_title(f"symmetry candidates (n={total})", fontsize=9)
    right.bar(["view proposed", "no view"], [views, len(rows) - views],
              color=[COLORS["view"], "#d8dee9"])
    right.set_title(f"view abstraction (n={len(rows)} models)", fontsize=9)
    save(fig, "fig_rq5_coverage")


def main() -> int:
    ensure_utf8_stdio()
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    numbers = load(ROOT / "analysis" / "output" / "numbers.json", {}) or {}
    for entry in models():
        model_id = entry["model_id"]
        arms = arm_series(model_id)
        row = {"model_id": model_id}
        for arm in ("plain", "symmetry", "view", "both"):
            run = arms.get(arm, {})
            row[f"{arm}_distinct"] = run.get("distinct_states")
            row[f"{arm}_seconds"] = run.get("wall_seconds")
        plain = row["plain_distinct"]
        for arm in ("symmetry", "view", "both"):
            row[f"{arm}_reduction"] = (1 - row[f"{arm}_distinct"] / plain
                                       if plain and row[f"{arm}_distinct"] else None)
        rows.append(row)
    print("figures:")
    fig_reduction(rows)
    fig_cactus(rows)
    fig_preservation()
    fig_ablation(rows)
    fig_coverage()
    write_text(OUT / "README.md",
               "# Figures\n\nGenerated by `analysis/make_figures.py` from "
               "`results/raw/**`. Do not edit by hand.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
