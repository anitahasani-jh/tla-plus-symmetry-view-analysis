#!/usr/bin/env python3
"""Rebuild ``results/raw/subset_probe.json`` from the per-model TLC logs.

The feasibility probe writes one log per candidate.  Parsing those logs is
useful on its own: a Colab session that dies mid-probe can be resumed without
re-running the models that already finished, and the probe table stays auditable.

    python experiments/probe_logs_to_json.py [--logs DIR]

Verdicts follow the same rules as :mod:`symview.tlc` so the output is drop-in
compatible with ``experiments/select_subset.py --reuse``.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from symview.util import ensure_utf8_stdio, write_json  # noqa: E402

DEFAULT_LOGS = ROOT.parent / "_scratch_lab" / "subset" / "logs"
OUT = ROOT / "results" / "raw" / "subset_probe.json"
RE_STATES = re.compile(r"(\d+) states generated, (\d+) distinct states found")
RE_SECONDS = re.compile(r"Finished in (\d+)s at")
RE_KILLED = re.compile(r"killed after (\d+)s")
RE_INV = re.compile(r"Error: Invariant (\S+) is violated")
RE_PROP = re.compile(r"Error: (?:Temporal property|Property) (\S+) is violated")


def corpus_index() -> dict[str, dict]:
    data = yaml.safe_load((ROOT / "config" / "corpus.yaml").read_text(encoding="utf-8"))
    index = {}
    for source in data["sources"]:
        for entry in source["dirs"]:
            for model in entry["models"]:
                index.setdefault(model, {
                    "family": entry["family"],
                    "source": f"{source['repo']}@{source['commit'][:12]}",
                })
    return index


def verdict_of(text: str) -> str:
    if "No error has been found" in text:
        return "ok"
    if RE_INV.search(text) or RE_PROP.search(text) or "Temporal properties were violated" in text:
        return "violation"
    if "Deadlock reached" in text:
        return "deadlock"
    if RE_KILLED.search(text):
        return "timeout"
    if "Parsing or semantic analysis failed" in text:
        return "parse-error"
    if "TLC threw an unexpected exception" in text:
        return "crash"
    return "error"


def main() -> int:
    ensure_utf8_stdio()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--logs", type=Path, default=DEFAULT_LOGS)
    args = parser.parse_args()
    index = corpus_index()
    results = []
    for path in sorted(args.logs.glob("probe_*.log")):
        model_id = path.stem[len("probe_"):]
        text = path.read_text(encoding="utf-8", errors="replace")
        verdict = verdict_of(text)
        states = RE_STATES.search(text)
        seconds = RE_SECONDS.search(text)
        killed = RE_KILLED.search(text)
        seconds_value = int(seconds.group(1)) if seconds else \
            (int(killed.group(1)) if killed else None)
        meta = index.get(model_id, {})
        results.append({
            "model_id": model_id,
            "verdict": verdict,
            "states": int(states.group(1)) if states else None,
            "distinct": int(states.group(2)) if states else None,
            "seconds": seconds_value,
            "violated": sorted(set(RE_INV.findall(text)) | set(RE_PROP.findall(text))),
            "deadlock": "Deadlock reached" in text,
            "removed_directives": [],
            "errors": [line.strip() for line in text.splitlines()
                       if line.startswith("Error")][:5],
            "family": meta.get("family", "unclassified"),
            "source": meta.get("source", ""),
            "bucket": _bucket(seconds_value, verdict),
        })
    write_json(OUT, {"results": results, "missing": [],
                     "note": "rebuilt from TLC logs by probe_logs_to_json.py"})
    print(f"[ok] {len(results)} probe records -> {OUT.relative_to(ROOT)}")
    counts: dict[str, int] = {}
    for record in results:
        counts[record["verdict"]] = counts.get(record["verdict"], 0) + 1
    print("verdicts:", counts)
    return 0


def _bucket(seconds: int | None, verdict: str) -> str:
    if verdict in ("timeout", "crash", "parse-error", "error"):
        return "failed"
    if seconds is None:
        return "unknown"
    if seconds < 5:
        return "cheap"
    if seconds < 30:
        return "medium"
    return "expensive"


if __name__ == "__main__":
    raise SystemExit(main())
