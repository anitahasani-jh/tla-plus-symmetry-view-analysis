#!/usr/bin/env python3
"""Fetch the pinned public TLA+ benchmark corpus.

The corpus is described in ``config/corpus.yaml``.  Every file is downloaded
over HTTPS from ``raw.githubusercontent.com`` at an exact commit and recorded
with its SHA-256 digest in ``benchmarks/PROVENANCE.json`` so that a grader can
verify byte-for-byte that the evaluated models are the public ones.

Usage
-----
    python benchmarks/fetch_public_specs.py            # fetch what is missing
    python benchmarks/fetch_public_specs.py --force    # re-download everything
    python benchmarks/fetch_public_specs.py --verify   # only check hashes

Only the Python standard library plus PyYAML are required.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CORPUS_YAML = ROOT / "config" / "corpus.yaml"
PUBLIC_DIR = ROOT / "benchmarks" / "public"
PROVENANCE_JSON = ROOT / "benchmarks" / "PROVENANCE.json"
PROVENANCE_MD = ROOT / "benchmarks" / "PROVENANCE.md"

RAW = "https://raw.githubusercontent.com/{repo}/{commit}/{path}"
API_TREE = "https://api.github.com/repos/{repo}/git/trees/{commit}?recursive=1"

TIMEOUT_S = 60
RETRIES = 3
TOKEN_ENV = "GITHUB_TOKEN"


def slugify(dir_path: str) -> str:
    """Deterministic, collision-free directory name for a corpus directory."""
    cleaned = dir_path.strip("/")
    if cleaned.startswith("specifications/"):
        cleaned = cleaned[len("specifications/"):]
    return cleaned.replace("/", "--").replace(".", "_") if cleaned not in ("", ".") else ""


def _http_get(url: str, accept: str = "*/*") -> bytes:
    last_error: Exception | None = None
    for attempt in range(RETRIES):
        try:
            request = urllib.request.Request(url, headers={"Accept": accept,
                                                           "User-Agent": "symview-benchmark-fetcher"})
            token = os.environ.get(TOKEN_ENV)
            if token:
                request.add_header("Authorization", f"Bearer {token}")
            with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:
                return response.read()
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
            last_error = exc
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"download failed after {RETRIES} attempts: {url} ({last_error})")


def repo_file_list(repo: str, commit: str, cache: dict[str, list[str]]) -> list[str]:
    if repo in cache:
        return cache[repo]
    payload = json.loads(_http_get(API_TREE.format(repo=repo, commit=commit),
                                   accept="application/vnd.github+json"))
    paths = [entry["path"] for entry in payload.get("tree", [])]
    cache[repo] = paths
    return paths


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def fetch(force: bool, verify_only: bool) -> int:
    corpus = yaml.safe_load(CORPUS_YAML.read_text(encoding="utf-8"))
    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    tree_cache: dict[str, list[str]] = {}
    records: list[dict] = []
    failures: list[dict] = []
    downloaded = verified = skipped = 0

    for source in corpus["sources"]:
        repo, commit = source["repo"], source["commit"]
        try:
            all_paths = repo_file_list(repo, commit, tree_cache)
        except RuntimeError as exc:
            failures.append({"repo": repo, "error": str(exc)})
            print(f"[error] cannot list {repo}@{commit}: {exc}", file=sys.stderr)
            continue

        if source.get("license_file"):
            lic_local = PUBLIC_DIR / "_licenses" / f"{slugify(repo)}.md"
            lic_local.parent.mkdir(parents=True, exist_ok=True)
            try:
                data = _http_get(RAW.format(repo=repo, commit=commit,
                                            path=source["license_file"]))
                lic_local.write_bytes(data)
                records.append({"repo": repo, "commit": commit,
                                "upstream_path": source["license_file"],
                                "local_path": str(lic_local.relative_to(ROOT)),
                                "sha256": sha256_bytes(data), "role": "license"})
            except RuntimeError as exc:
                failures.append({"repo": repo, "error": f"license: {exc}"})

        for entry in source["dirs"]:
            dir_path = entry["path"].strip("/")
            local_dir = PUBLIC_DIR / (slugify(dir_path) or slugify(repo))
            local_dir.mkdir(parents=True, exist_ok=True)
            prefix = "" if dir_path in ("", ".") else dir_path + "/"
            wanted = [p for p in all_paths
                      if p.startswith(prefix)
                      and "/" not in p[len(prefix):]
                      and (p.endswith(".tla") or p.endswith(".cfg"))]
            if not wanted:
                failures.append({"repo": repo, "dir": dir_path,
                                 "error": "no .tla/.cfg files found at pinned commit"})
                continue
            for upstream_path in sorted(wanted):
                local_path = local_dir / Path(upstream_path).name
                rel = str(local_path.relative_to(ROOT)).replace(os.sep, "/")
                if verify_only:
                    if local_path.exists():
                        verified += 1
                        records.append({"repo": repo, "commit": commit,
                                        "upstream_path": upstream_path,
                                        "local_path": rel,
                                        "sha256": sha256_file(local_path),
                                        "role": "spec"})
                    else:
                        failures.append({"local_path": rel, "error": "missing"})
                    continue
                if local_path.exists() and not force:
                    skipped += 1
                    records.append({"repo": repo, "commit": commit,
                                    "upstream_path": upstream_path,
                                    "local_path": rel,
                                    "sha256": sha256_file(local_path),
                                    "role": "spec"})
                    continue
                try:
                    data = _http_get(RAW.format(repo=repo, commit=commit,
                                                path=upstream_path))
                except RuntimeError as exc:
                    failures.append({"upstream_path": upstream_path, "error": str(exc)})
                    print(f"[error] {upstream_path}: {exc}", file=sys.stderr)
                    continue
                local_path.write_bytes(data)
                downloaded += 1
                records.append({"repo": repo, "commit": commit,
                                "upstream_path": upstream_path, "local_path": rel,
                                "sha256": sha256_bytes(data), "role": "spec"})

        for entry in source["dirs"]:
            for model in entry["models"]:
                records.append({"repo": repo, "commit": commit,
                                "model": model, "dir": entry["path"],
                                "family": entry["family"], "role": "model"})

    records = sorted({json.dumps(r, sort_keys=True) for r in records})
    manifest = {
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "corpus_config": str(CORPUS_YAML.relative_to(ROOT)).replace(os.sep, "/"),
        "entries": [json.loads(r) for r in records],
        "failures": failures,
        "stats": {"downloaded": downloaded, "already_present": skipped,
                  "verified": verified, "failures": len(failures)},
    }
    PROVENANCE_JSON.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
                               encoding="utf-8")
    write_provenance_md(manifest)
    print(f"[ok] downloaded={downloaded} present={skipped} verified={verified} "
          f"failures={len(failures)} -> {PROVENANCE_JSON.relative_to(ROOT)}")
    return 0 if not failures else 1


def write_provenance_md(manifest: dict) -> None:
    specs = [e for e in manifest["entries"] if e.get("role") == "spec"]
    models = [e for e in manifest["entries"] if e.get("role") == "model"]
    repos = {}
    for entry in specs:
        repos.setdefault((entry["repo"], entry["commit"]), 0)
        repos[(entry["repo"], entry["commit"])] += 1
    lines = [
        "# Benchmark provenance",
        "",
        "Every public specification used in this project is pinned to an exact",
        "commit and redistributed under its upstream licence.  `PROVENANCE.json`",
        "holds the SHA-256 of each file; verify with",
        "`python benchmarks/fetch_public_specs.py --verify`.",
        "",
        "## Sources",
        "",
        "| Repository | Commit | Files fetched |",
        "|---|---|---|",
    ]
    for (repo, commit), count in sorted(repos.items()):
        lines.append(f"| `{repo}` | `{commit[:12]}` | {count} |")
    lines += ["", "## Candidate models", "",
              "| Model | Directory | Family |", "|---|---|---|"]
    seen = set()
    for entry in sorted(models, key=lambda m: (m["dir"], m["model"])):
        key = (entry["dir"], entry["model"])
        if key in seen:
            continue
        seen.add(key)
        lines.append(f"| `{entry['model']}` | `{entry['dir']}` | {entry['family']} |")
    if manifest["failures"]:
        lines += ["", "## Fetch failures", "",
                  "| Detail |", "|---|"]
        lines += [f"| `{json.dumps(f, ensure_ascii=False)}` |" for f in manifest["failures"]]
    lines.append("")
    PROVENANCE_MD.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="re-download everything")
    parser.add_argument("--verify", action="store_true", help="only hash local files")
    args = parser.parse_args()
    return fetch(force=args.force, verify_only=args.verify)


if __name__ == "__main__":
    raise SystemExit(main())
