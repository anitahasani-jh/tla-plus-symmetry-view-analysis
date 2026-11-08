"""Small shared helpers.

Everything here is deliberately dependency-free so that the analysis can run on
a bare Colab VM or on Windows with only the Python standard library.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any


def ensure_utf8_stdio() -> None:
    """Force UTF-8 on stdout/stderr.

    Windows consoles default to a code page such as cp1252, which cannot encode
    TLA+ Unicode operators or Persian report text and would crash the CLI.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(Path(path).read_bytes())


def write_json(path: Path, payload: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=False) + "\n",
                    encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")


def read_text(path: Path) -> str:
    return Path(path).read_text(encoding="utf-8", errors="replace")


def human_seconds(seconds: float | None) -> str:
    if seconds is None:
        return "n/a"
    if seconds < 60:
        return f"{seconds:.2f}s"
    return f"{int(seconds // 60)}m{seconds % 60:04.1f}s"


def repo_root(start: Path | None = None) -> Path:
    """Root of the SymView checkout (the directory holding config/ and src/)."""
    current = Path(start or Path(__file__)).resolve()
    for candidate in [current, *current.parents]:
        if (candidate / "config" / "corpus.yaml").exists():
            return candidate
    return current.parent
