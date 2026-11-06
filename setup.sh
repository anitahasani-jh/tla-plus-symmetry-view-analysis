#!/usr/bin/env bash
# SymView environment setup.
#
#   bash setup.sh                 install dependencies, verify TLC, smoke test
#   bash setup.sh --offline       no downloads: requirements and jar must exist
#   bash setup.sh --skip-smoke    skip the static-analysis smoke test
#
# The script is idempotent: running it twice leaves the same environment.
# It works on a laptop (Linux/macOS, Git Bash) and on Google Colab.  TLC needs
# Java 8 or newer; if `java` is missing the script warns and still sets up the
# static analysis, so that `symview analyze` can be used immediately.
#
# Pinned artifact
# ---------------
# tools/tla2tools-1.7.1.jar is TLC2 Version 2.16 of 31 December 2020 (MIT).
# Its digest is fixed below.  The jar's manifest declares
#
#     Class-Path: CommunityModules.jar
#
# and the JVM resolves that relative to the jar's own directory.  A newer
# CommunityModules.jar placed next to tla2tools therefore breaks TLC 2.16 with
# NoClassDefFoundError: tlc2/value/impl/KSubsetValue.  This script refuses to
# continue if tools/CommunityModules.jar exists.  The community modules used by
# the corpus are plain .tla files under benchmarks/support/community/.

set -euo pipefail

TLA2TOOLS_URL="https://github.com/tlaplus/tlaplus/releases/download/v1.7.1/tla2tools.jar"
TLA2TOOLS_SHA256="d532ba31aafe17afba1130f92410d9257454ff7393d1eb2fe032f0c07f352da5"
TLA2TOOLS_JAR_NAME="tla2tools-1.7.1.jar"

OFFLINE=0
RUN_SMOKE=1
for arg in "$@"; do
    case "$arg" in
        --offline)    OFFLINE=1 ;;
        --skip-smoke) RUN_SMOKE=0 ;;
        -h|--help)
            cat <<'EOF'
SymView environment setup.

  bash setup.sh                 install dependencies, verify TLC, smoke test
  bash setup.sh --offline       no downloads: requirements and jar must exist
  bash setup.sh --skip-smoke    skip the static-analysis smoke test

Environment:
  PYTHON    interpreter to use (default: python, then python3)
EOF
            exit 0
            ;;
        *)
            printf 'setup.sh: unknown argument: %s\n' "$arg" >&2
            printf 'usage: bash setup.sh [--offline] [--skip-smoke]\n' >&2
            exit 2
            ;;
    esac
done

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

say()  { printf '[setup] %s\n' "$*"; }
warn() { printf '[setup] WARNING: %s\n' "$*" >&2; }
die()  { printf '[setup] ERROR: %s\n' "$*" >&2; exit 1; }

TMP_JAR=""
cleanup() {
    if [ -n "$TMP_JAR" ] && [ -f "$TMP_JAR" ]; then
        rm -f "$TMP_JAR"
    fi
}
trap cleanup EXIT

# --- Python 3.10+ -----------------------------------------------------------
PYTHON="${PYTHON:-}"
if [ -z "$PYTHON" ]; then
    if command -v python >/dev/null 2>&1; then
        PYTHON=python
    elif command -v python3 >/dev/null 2>&1; then
        PYTHON=python3
    else
        die "no python on PATH; install Python 3.10 or newer and re-run"
    fi
fi

if ! "$PYTHON" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)'; then
    die "$PYTHON is older than 3.10; SymView needs Python 3.10 or newer"
fi
PY_VERSION="$("$PYTHON" -c 'import platform; print(platform.python_version())')"
say "python: $PYTHON ($PY_VERSION)"

# --- dependencies -----------------------------------------------------------
# Core dependencies are required by the analysis and the experiments.  Jupyter is
# only needed to open analysis/analysis.ipynb, so a network hiccup while
# installing it must not fail the setup.
OPTIONAL_MODULES="jupyterlab nbformat"

if [ "$OFFLINE" -eq 1 ]; then
    say "offline: checking that the core modules are already installed"
    if ! "$PYTHON" - <<'PYCHECK'
import importlib.util
import sys

required = ["yaml", "pandas", "matplotlib", "scipy", "numpy"]
missing = [name for name in required if importlib.util.find_spec(name) is None]
if missing:
    print("missing modules: " + ", ".join(missing), file=sys.stderr)
    raise SystemExit(1)
print("all core modules are importable")
PYCHECK
    then
        die "offline mode, but some core requirements are missing; install them with 'python -m pip install -r requirements.txt'"
    fi
else
    say "installing core requirements"
    if ! "$PYTHON" -m pip install --disable-pip-version-check pyyaml pandas matplotlib scipy numpy; then
        die "pip install failed; fix the network/proxy and re-run"
    fi
    say "installing optional notebook dependencies (best effort)"
    if ! "$PYTHON" -m pip install --disable-pip-version-check $OPTIONAL_MODULES; then
        warn "could not install the notebook extras ($OPTIONAL_MODULES)."
        warn "everything except opening analysis/analysis.ipynb still works."
    fi
fi

# --- Java (needed by TLC, not by the static analysis) ----------------------
JAVA_OK=0
if command -v java >/dev/null 2>&1; then
    JAVA_OUT="$(java -version 2>&1 || true)"
    JAVA_FIRST="${JAVA_OUT%%$'\n'*}"
    say "java: $JAVA_FIRST"
    JAVA_OK=1
else
    warn "java was not found on PATH. TLC needs Java 8 or newer; run/report"
    warn "and the experiment arms will fail until it is installed."
    cat >&2 <<'EOF'
[setup]   Debian/Ubuntu/Colab: sudo apt-get update && sudo apt-get install -y openjdk-17-jre-headless
[setup]   macOS (Homebrew)  : brew install openjdk@17
[setup]   Then re-run: bash setup.sh
EOF
    warn "continuing with the Python-only setup; 'symview analyze' still works"
fi

# --- pinned TLC jar ---------------------------------------------------------
mkdir -p "$ROOT/tools"
JAR="$ROOT/tools/$TLA2TOOLS_JAR_NAME"

sha256_of() {
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$1" | awk '{print $1}'
    elif command -v shasum >/dev/null 2>&1; then
        shasum -a 256 "$1" | awk '{print $1}'
    else
        "$PYTHON" - "$1" <<'PY'
import hashlib
import sys

digest = hashlib.sha256()
with open(sys.argv[1], "rb") as handle:
    for chunk in iter(lambda: handle.read(1 << 20), b""):
        digest.update(chunk)
print(digest.hexdigest())
PY
    fi
}

verify_jar() {
    actual="$(sha256_of "$JAR")"
    if [ "$actual" != "$TLA2TOOLS_SHA256" ]; then
        die "SHA-256 mismatch for tools/$TLA2TOOLS_JAR_NAME: expected $TLA2TOOLS_SHA256, got $actual. Delete the file and re-run setup.sh to download the pinned jar."
    fi
}

if [ -f "$JAR" ]; then
    say "verifying tools/$TLA2TOOLS_JAR_NAME"
    verify_jar
elif [ "$OFFLINE" -eq 1 ]; then
    die "offline mode, but tools/$TLA2TOOLS_JAR_NAME is missing; run 'bash setup.sh' once with network access"
else
    TMP_JAR="$JAR.download"
    rm -f "$TMP_JAR"
    say "downloading $TLA2TOOLS_JAR_NAME from the pinned release"
    if command -v curl >/dev/null 2>&1; then
        if ! curl -fL --retry 3 --connect-timeout 20 --max-time 300 \
                -o "$TMP_JAR" "$TLA2TOOLS_URL"; then
            die "download failed: $TLA2TOOLS_URL"
        fi
    elif command -v wget >/dev/null 2>&1; then
        if ! wget -O "$TMP_JAR" "$TLA2TOOLS_URL"; then
            die "download failed: $TLA2TOOLS_URL"
        fi
    else
        die "neither curl nor wget is available; cannot download the TLC jar"
    fi
    actual="$(sha256_of "$TMP_JAR")"
    if [ "$actual" != "$TLA2TOOLS_SHA256" ]; then
        die "downloaded jar has SHA-256 $actual, expected $TLA2TOOLS_SHA256; refusing to install it"
    fi
    mv "$TMP_JAR" "$JAR"
    TMP_JAR=""
    say "downloaded and verified tools/$TLA2TOOLS_JAR_NAME"
fi
say "tlc jar: tools/$TLA2TOOLS_JAR_NAME (sha256 verified)"

# The manifest Class-Path trap: never keep a community jar next to tla2tools.
if [ -e "$ROOT/tools/CommunityModules.jar" ]; then
    die "tools/CommunityModules.jar must not sit next to tla2tools: TLC's manifest loads it and TLC 2.16 then dies with NoClassDefFoundError: tlc2/value/impl/KSubsetValue. Move it to tools/community-disabled/ (the project already ships the .tla sources under benchmarks/support/community/)."
fi
for other in "$ROOT"/tools/*.jar; do
    if [ ! -e "$other" ]; then
        continue
    fi
    if [ "$other" = "$JAR" ]; then
        continue
    fi
    warn "another jar is present in tools/: $(basename "$other"); keep only $TLA2TOOLS_JAR_NAME next to TLC"
done

# --- output directories -----------------------------------------------------
mkdir -p "$ROOT/results/raw" \
         "$ROOT/analysis/output/tables" \
         "$ROOT/analysis/output/figures"
say "created results/raw, analysis/output/tables, analysis/output/figures"

# --- smoke test -------------------------------------------------------------
if [ "$RUN_SMOKE" -eq 1 ]; then
    say "smoke test: static analysis of benchmarks/lab/LabLock (no TLC probe)"
    SMOKE_CMD=(env PYTHONPATH=src "$PYTHON" -m symview analyze
               --spec-dir benchmarks/lab/LabLock --module LabLock
               --config LabLock.cfg --no-probe)
    if ! "${SMOKE_CMD[@]}" >/dev/null; then
        printf '[setup] smoke command was: %s\n' "${SMOKE_CMD[*]}" >&2
        die "smoke test failed; run the command above to see the traceback"
    fi
    say "smoke test passed"
fi

if [ "$JAVA_OK" -eq 0 ]; then
    warn "setup is complete for the static analysis, but TLC cannot run without Java"
fi
printf '\nsetup OK\n'
printf 'Next: bash run_all.sh --quick     # end-to-end smoke run\n'
printf '      bash run_all.sh --full      # full study\n'
