"""SymView -- automatic symmetry detection and view abstraction for TLC.

Public API::

    from symview.context import load_context, probe_constant_values
    from symview.analysis.program import SpecProgram
    from symview.analysis.symmetry import analyze_symmetry
    from symview.analysis.history import analyze_history
    from symview.codegen import generate_artifacts
    from symview.tlc import TlcBudget, run_tlc

The command line entry point is ``python -m symview`` (see :mod:`symview.cli`).
"""

from __future__ import annotations

__version__ = "1.0.0"

__all__ = ["__version__"]
