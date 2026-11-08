# SymView -- thin wrappers over the scripts used in the study.
#
#   make setup     one-time environment setup (network, Java warning, jar hash)
#   make all       run the whole pipeline on the frozen subset (assumes setup)
#
# Every target is a one-line wrapper; the logic lives in the Python scripts and
# in setup.sh / run_all.sh so that the command is the same on Colab and locally.

PY ?= python
REPEATS ?= 1
MUTANTS ?= 4
SUBSET_LIMIT ?= 0
export PYTHONPATH=src

.PHONY: setup corpus parser test subset run tables figures all clean help

help:
	@echo "SymView targets:"
	@echo "  make setup    install requirements, verify TLC, smoke test (once)"
	@echo "  make corpus   fetch the pinned public corpus (needs network)"
	@echo "  make parser   measure parser robustness over the corpus"
	@echo "  make test     run the 8 lab ground-truth checks"
	@echo "  make subset   freeze the evaluated subset (SUBSET_LIMIT=0 means all)"
	@echo "  make run      run the arms (REPEATS=1, MUTANTS=4 by default)"
	@echo "  make tables   build analysis/output/tables from results/raw"
	@echo "  make figures  build analysis/output/figures from results/raw"
	@echo "  make all      corpus parser test subset run tables figures"
	@echo "  make clean    remove scratch dirs and caches (never results/ or analysis/output)"
	@echo ""
	@echo "For a quick end-to-end smoke run use: bash run_all.sh --quick"

setup:
	PYTHON=$(PY) bash setup.sh

corpus:
	$(PY) benchmarks/fetch_public_specs.py

parser:
	$(PY) experiments/parser_robustness.py

test:
	$(PY) tests/test_lab_ground_truth.py

subset:
	$(PY) experiments/select_subset.py --limit $(SUBSET_LIMIT)

run:
	$(PY) experiments/run_experiments.py --repeats $(REPEATS) --mutants $(MUTANTS)

tables:
	$(PY) analysis/make_tables.py

figures:
	$(PY) analysis/make_figures.py

all: corpus parser test subset run tables figures

clean:
	rm -rf "$(CURDIR)/../_scratch_lab"
	rm -rf "$(CURDIR)/src/symview/__pycache__"
	rm -rf "$(CURDIR)/src/symview/analysis/__pycache__"
	rm -rf "$(CURDIR)/experiments/__pycache__"
	rm -rf "$(CURDIR)/analysis/__pycache__"
	rm -rf "$(CURDIR)/tests/__pycache__"
	rm -rf "$(CURDIR)/.pytest_cache" "$(CURDIR)/.mypy_cache" "$(CURDIR)/.ruff_cache"
	rm -rf "$(CURDIR)/.ipynb_checkpoints" "$(CURDIR)/notebooks/.ipynb_checkpoints"
	@echo "clean: scratch and caches removed; results/ and analysis/output/ untouched"
