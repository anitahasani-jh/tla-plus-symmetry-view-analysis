#!/usr/bin/env bash
# Reproduce the SymView study with one command.
#
#   bash run_all.sh --quick     tiny probe subset, 1 repeat (pipeline smoke run)
#   bash run_all.sh --full      full subset, 3 repeats (the reported study)
#
# Options
#   --offline        do not fetch the corpus; use benchmarks/public as it is
#   --force          re-run experiment arms whose result files already exist
#   --skip-mutants   skip mutant generation (RQ2 will be empty)
#   -h, --help       show this help
#
# Environment overrides
#   PYTHON           interpreter to use (default: python)
#   QUICK_LIMIT      candidates probed in quick mode (default: 6)
#   QUICK_TIMEOUT    per-model probe timeout in quick mode, seconds (default: 30)
#   QUICK_MUTANTS    mutants per model in quick mode (default: 1)
#   FULL_REPEATS     timing repeats in full mode (default: 3)
#
# Steps (in order): corpus -> parser robustness -> ground-truth tests ->
# subset selection -> experiments -> tables -> figures.  Each step is the
# documented script path, so the log can be mapped one-to-one onto the report.
#
# Quick mode re-runs subset selection with --limit.  The frozen
# config/subset.yaml (if one exists) is backed up before the run and restored on
# exit, so a smoke run never destroys the selection used for the report.  Run
# --full to regenerate that selection deliberately.

set -euo pipefail

MODE="quick"
OFFLINE=0
FORCE=0
SKIP_MUTANTS=0
QUICK_LIMIT="${QUICK_LIMIT:-6}"
QUICK_TIMEOUT="${QUICK_TIMEOUT:-30}"
QUICK_MUTANTS="${QUICK_MUTANTS:-1}"
FULL_REPEATS="${FULL_REPEATS:-3}"

usage() {
    cat <<'EOF'
Reproduce the SymView study with one command.

  bash run_all.sh --quick     tiny probe subset, 1 repeat (pipeline smoke run)
  bash run_all.sh --full      full subset, 3 repeats (the reported study)

Options
  --offline        do not fetch the corpus; use benchmarks/public as it is
  --force          re-run experiment arms whose result files already exist
  --skip-mutants   skip mutant generation (RQ2 will be empty)
  -h, --help       show this help

Environment overrides
  PYTHON           interpreter to use (default: python)
  QUICK_LIMIT      candidates probed in quick mode (default: 6)
  QUICK_TIMEOUT    per-model probe timeout in quick mode, seconds (default: 30)
  QUICK_MUTANTS    mutants per model in quick mode (default: 1)
  FULL_REPEATS     timing repeats in full mode (default: 3)
EOF
}

for arg in "$@"; do
    case "$arg" in
        --quick)        MODE="quick" ;;
        --full)         MODE="full" ;;
        --offline)      OFFLINE=1 ;;
        --force)        FORCE=1 ;;
        --skip-mutants) SKIP_MUTANTS=1 ;;
        -h|--help)      usage; exit 0 ;;
        *)
            printf 'run_all.sh: unknown argument: %s\n' "$arg" >&2
            printf 'usage: bash run_all.sh [--quick|--full] [--offline] [--force] [--skip-mutants]\n' >&2
            exit 2
            ;;
    esac
done

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT/src"

PYTHON="${PYTHON:-python}"
say()  { printf '[run_all] %s\n' "$*"; }
warn() { printf '[run_all] WARNING: %s\n' "$*" >&2; }
die()  { printf '[run_all] ERROR: %s\n' "$*" >&2; exit 1; }

require_file() {
    if [ ! -f "$ROOT/$1" ]; then
        die "missing $1; this script expects the documented path to exist"
    fi
}

STEP=0
TOTAL_STEPS=7
step() {
    STEP=$((STEP + 1))
    printf '\n=== [%d/%d] %s ===\n' "$STEP" "$TOTAL_STEPS" "$*"
}

# A quick run writes a temporary subset; put the frozen selection back on exit.
SUBSET_BACKUP=""
restore_subset() {
    if [ -n "$SUBSET_BACKUP" ] && [ -f "$SUBSET_BACKUP" ]; then
        mv "$SUBSET_BACKUP" "$ROOT/config/subset.yaml"
    fi
}
trap restore_subset EXIT

# --- preconditions ----------------------------------------------------------
if ! command -v "$PYTHON" >/dev/null 2>&1; then
    die "'$PYTHON' is not on PATH; run 'bash setup.sh' or set PYTHON=<interpreter>"
fi
if [ ! -f "$ROOT/tools/tla2tools-1.7.1.jar" ]; then
    die "tools/tla2tools-1.7.1.jar is missing; run 'bash setup.sh' once with network access"
fi
if ! command -v java >/dev/null 2>&1; then
    die "java is not on PATH; TLC needs Java 8 or newer (run 'bash setup.sh' for the install command)"
fi

require_file benchmarks/fetch_public_specs.py
require_file experiments/parser_robustness.py
require_file tests/test_lab_ground_truth.py
require_file experiments/select_subset.py
require_file experiments/run_experiments.py
require_file analysis/make_tables.py
require_file analysis/make_figures.py

if [ "$MODE" = "quick" ]; then
    say "mode=quick (limit=$QUICK_LIMIT candidates, timeout=${QUICK_TIMEOUT}s, 1 repeat)"
else
    say "mode=full (frozen subset, repeats=$FULL_REPEATS)"
fi

# --- 1. corpus --------------------------------------------------------------
step "corpus"
if [ "$OFFLINE" -eq 1 ]; then
    if [ ! -d "$ROOT/benchmarks/public" ]; then
        die "offline mode, but benchmarks/public does not exist; run without --offline once"
    fi
    TLA_COUNT="$(find "$ROOT/benchmarks/public" -type f -name '*.tla' | wc -l | tr -d ' ')"
    if [ "$TLA_COUNT" -eq 0 ]; then
        die "offline mode, but benchmarks/public contains no .tla files"
    fi
    say "offline: using the existing corpus ($TLA_COUNT .tla files); no download"
else
    "$PYTHON" benchmarks/fetch_public_specs.py
fi

# --- 2. parser robustness ---------------------------------------------------
step "parser robustness"
"$PYTHON" experiments/parser_robustness.py

# --- 3. ground-truth tests --------------------------------------------------
step "lab ground truth (8 hand-written models)"
"$PYTHON" tests/test_lab_ground_truth.py

# --- 4. subset selection ----------------------------------------------------
step "subset selection"
if [ "$MODE" = "quick" ] && [ -f "$ROOT/config/subset.yaml" ]; then
    backup="$(mktemp "${TMPDIR:-/tmp}/symview-subset.XXXXXX")"
    if ! cp "$ROOT/config/subset.yaml" "$backup"; then
        rm -f "$backup"
        die "could not back up config/subset.yaml; refusing to overwrite it"
    fi
    SUBSET_BACKUP="$backup"
    say "quick mode: saved config/subset.yaml; the frozen file is restored on exit"
fi
if [ "$MODE" = "quick" ]; then
    "$PYTHON" experiments/select_subset.py --limit "$QUICK_LIMIT" --timeout "$QUICK_TIMEOUT"
else
    "$PYTHON" experiments/select_subset.py
fi

SUBSET_COUNT="$("$PYTHON" - <<'PY'
import yaml

with open("config/subset.yaml", encoding="utf-8") as handle:
    data = yaml.safe_load(handle) or {}
print(len(data.get("models", [])))
PY
)"
if [ "$SUBSET_COUNT" -eq 0 ]; then
    die "subset selection produced no runnable models; re-run with a larger QUICK_LIMIT or check the TLC/Java setup"
fi
say "subset: $SUBSET_COUNT model(s) frozen in config/subset.yaml"

# --- 5. experiments ---------------------------------------------------------
step "experiments"
if [ "$MODE" = "quick" ]; then
    set -- --repeats 1 --mutants "$QUICK_MUTANTS"
else
    set -- --repeats "$FULL_REPEATS"
fi
if [ "$SKIP_MUTANTS" -eq 1 ]; then
    set -- "$@" --skip-mutants
fi
if [ "$FORCE" -eq 1 ]; then
    set -- "$@" --force
fi
"$PYTHON" experiments/run_experiments.py "$@"

# --- 6. tables --------------------------------------------------------------
step "tables"
"$PYTHON" analysis/make_tables.py

# --- 7. figures -------------------------------------------------------------
step "figures"
"$PYTHON" analysis/make_figures.py

# --- summary ----------------------------------------------------------------
printf '\n'
say "done."
say "raw runs : results/raw/"
say "tables   : analysis/output/tables/"
say "figures  : analysis/output/figures/"
if [ "$MODE" = "quick" ]; then
    if [ -n "$SUBSET_BACKUP" ]; then
        warn "quick mode used a temporary subset; the previous config/subset.yaml was restored on exit"
    else
        warn "quick mode wrote a reduced subset to config/subset.yaml (there was no previous file)"
    fi
fi
