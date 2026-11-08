"""TLA+ operator table extracted mechanically from SANY.

Upstream: tlaplus/tlaplus@309e489a512e8017f1cdc8388fa6a5e8a01cf597
File:     tlatools/org.lamport.tlatools/src/tla2sany/parser/Operators.java
Regenerate with ``python tools/gen_operators.py``.  Do not edit by hand.

Each entry is ``OpSpec(canonical, low, high, assoc, fix)`` where ``low``
and ``high`` are SANY's precedence *range* (an operator binds operands
whose precedence lies in that range), ``assoc`` is one of
left/right/none/nonassoc and ``fix`` is one of prefix/infix/postfix/nfix.
"""

from __future__ import annotations

from dataclasses import dataclass

UPSTREAM_COMMIT = "tlaplus/tlaplus@309e489a512e8017f1cdc8388fa6a5e8a01cf597"
UPSTREAM_FILE = "tlatools/org.lamport.tlatools/src/tla2sany/parser/Operators.java"


@dataclass(frozen=True)
class OpSpec:
    canonical: str
    low: int
    high: int
    assoc: str
    fix: str

    @property
    def prec(self) -> int:
        return self.low


CANONICAL: dict[str, OpSpec] = {
    '[': OpSpec('[', 160, 160, 'left', 'postfix'),
    '.': OpSpec('.', 170, 170, 'left', 'infix'),
    "'": OpSpec("'", 150, 150, 'none', 'postfix'),
    '^': OpSpec('^', 140, 140, 'none', 'infix'),
    '/': OpSpec('/', 130, 130, 'none', 'infix'),
    '*': OpSpec('*', 130, 130, 'left', 'infix'),
    '-': OpSpec('-', 110, 110, 'left', 'infix'),
    '-.': OpSpec('-.', 120, 120, 'none', 'prefix'),
    '+': OpSpec('+', 100, 100, 'left', 'infix'),
    '=': OpSpec('=', 50, 50, 'none', 'infix'),
    '\\lnot': OpSpec('\\lnot', 40, 40, 'left', 'prefix'),
    '\\land': OpSpec('\\land', 30, 30, 'left', 'infix'),
    '\\lor': OpSpec('\\lor', 30, 30, 'left', 'infix'),
    '~>': OpSpec('~>', 20, 20, 'none', 'infix'),
    '=>': OpSpec('=>', 10, 10, 'none', 'infix'),
    '[]': OpSpec('[]', 40, 150, 'none', 'prefix'),
    '<>': OpSpec('<>', 40, 150, 'none', 'prefix'),
    'ENABLED': OpSpec('ENABLED', 40, 150, 'none', 'prefix'),
    'UNCHANGED': OpSpec('UNCHANGED', 40, 150, 'none', 'prefix'),
    'SUBSET': OpSpec('SUBSET', 100, 130, 'none', 'prefix'),
    'UNION': OpSpec('UNION', 100, 130, 'none', 'prefix'),
    'DOMAIN': OpSpec('DOMAIN', 100, 130, 'none', 'prefix'),
    '^+': OpSpec('^+', 150, 150, 'none', 'postfix'),
    '^*': OpSpec('^*', 150, 150, 'none', 'postfix'),
    '^#': OpSpec('^#', 150, 150, 'none', 'postfix'),
    '\\cdot': OpSpec('\\cdot', 50, 140, 'left', 'infix'),
    '\\equiv': OpSpec('\\equiv', 20, 20, 'none', 'infix'),
    '-+->': OpSpec('-+->', 20, 20, 'none', 'infix'),
    '/=': OpSpec('/=', 50, 50, 'none', 'infix'),
    '\\subseteq': OpSpec('\\subseteq', 50, 50, 'none', 'infix'),
    '\\in': OpSpec('\\in', 50, 50, 'none', 'infix'),
    '\\notin': OpSpec('\\notin', 50, 50, 'none', 'infix'),
    '<': OpSpec('<', 50, 50, 'none', 'infix'),
    '\\leq': OpSpec('\\leq', 50, 50, 'none', 'infix'),
    '>': OpSpec('>', 50, 50, 'none', 'infix'),
    '\\geq': OpSpec('\\geq', 50, 50, 'none', 'infix'),
    '\\times': OpSpec('\\times', 100, 130, 'left', 'nfix'),
    '\\': OpSpec('\\', 80, 80, 'none', 'infix'),
    '\\intersect': OpSpec('\\intersect', 80, 80, 'left', 'infix'),
    '\\union': OpSpec('\\union', 80, 80, 'left', 'infix'),
    '...': OpSpec('...', 90, 90, 'none', 'infix'),
    '..': OpSpec('..', 90, 90, 'none', 'infix'),
    '|': OpSpec('|', 100, 110, 'left', 'infix'),
    '||': OpSpec('||', 100, 110, 'left', 'infix'),
    '&&': OpSpec('&&', 130, 130, 'left', 'infix'),
    '&': OpSpec('&', 130, 130, 'left', 'infix'),
    '$$': OpSpec('$$', 90, 130, 'left', 'infix'),
    '$': OpSpec('$', 90, 130, 'left', 'infix'),
    '??': OpSpec('??', 90, 130, 'left', 'infix'),
    '?': OpSpec('?', 90, 130, 'left', 'infix'),
    '%%': OpSpec('%%', 100, 110, 'left', 'infix'),
    '%': OpSpec('%', 100, 110, 'none', 'infix'),
    '##': OpSpec('##', 90, 130, 'left', 'infix'),
    '++': OpSpec('++', 100, 100, 'left', 'infix'),
    '--': OpSpec('--', 110, 110, 'left', 'infix'),
    '**': OpSpec('**', 130, 130, 'left', 'infix'),
    '//': OpSpec('//', 130, 130, 'none', 'infix'),
    '^^': OpSpec('^^', 140, 140, 'none', 'infix'),
    '@@': OpSpec('@@', 60, 60, 'left', 'infix'),
    '!!': OpSpec('!!', 90, 130, 'none', 'infix'),
    '|-': OpSpec('|-', 50, 50, 'none', 'infix'),
    '|=': OpSpec('|=', 50, 50, 'none', 'infix'),
    '-|': OpSpec('-|', 50, 50, 'none', 'infix'),
    '=|': OpSpec('=|', 50, 50, 'none', 'infix'),
    '<:': OpSpec('<:', 70, 70, 'none', 'infix'),
    ':>': OpSpec(':>', 70, 70, 'none', 'infix'),
    ':=': OpSpec(':=', 50, 50, 'none', 'infix'),
    '::=': OpSpec('::=', 50, 50, 'none', 'infix'),
    '\\oplus': OpSpec('\\oplus', 100, 100, 'left', 'infix'),
    '\\ominus': OpSpec('\\ominus', 110, 110, 'left', 'infix'),
    '\\odot': OpSpec('\\odot', 130, 130, 'left', 'infix'),
    '\\oslash': OpSpec('\\oslash', 130, 130, 'none', 'infix'),
    '\\otimes': OpSpec('\\otimes', 130, 130, 'left', 'infix'),
    '\\uplus': OpSpec('\\uplus', 90, 130, 'left', 'infix'),
    '\\sqcap': OpSpec('\\sqcap', 90, 130, 'left', 'infix'),
    '\\sqcup': OpSpec('\\sqcup', 90, 130, 'left', 'infix'),
    '\\div': OpSpec('\\div', 130, 130, 'none', 'infix'),
    '\\wr': OpSpec('\\wr', 90, 140, 'none', 'infix'),
    '\\star': OpSpec('\\star', 130, 130, 'left', 'infix'),
    '\\o': OpSpec('\\o', 130, 130, 'left', 'infix'),
    '\\bigcirc': OpSpec('\\bigcirc', 130, 130, 'left', 'infix'),
    '\\bullet': OpSpec('\\bullet', 130, 130, 'left', 'infix'),
    '\\prec': OpSpec('\\prec', 50, 50, 'none', 'infix'),
    '\\succ': OpSpec('\\succ', 50, 50, 'none', 'infix'),
    '\\preceq': OpSpec('\\preceq', 50, 50, 'none', 'infix'),
    '\\succeq': OpSpec('\\succeq', 50, 50, 'none', 'infix'),
    '\\sim': OpSpec('\\sim', 50, 50, 'none', 'infix'),
    '\\simeq': OpSpec('\\simeq', 50, 50, 'none', 'infix'),
    '\\ll': OpSpec('\\ll', 50, 50, 'none', 'infix'),
    '\\gg': OpSpec('\\gg', 50, 50, 'none', 'infix'),
    '\\asymp': OpSpec('\\asymp', 50, 50, 'none', 'infix'),
    '\\subset': OpSpec('\\subset', 50, 50, 'none', 'infix'),
    '\\supset': OpSpec('\\supset', 50, 50, 'none', 'infix'),
    '\\supseteq': OpSpec('\\supseteq', 50, 50, 'none', 'infix'),
    '\\approx': OpSpec('\\approx', 50, 50, 'none', 'infix'),
    '\\cong': OpSpec('\\cong', 50, 50, 'none', 'infix'),
    '\\sqsubset': OpSpec('\\sqsubset', 50, 50, 'none', 'infix'),
    '\\sqsubseteq': OpSpec('\\sqsubseteq', 50, 50, 'none', 'infix'),
    '\\sqsupset': OpSpec('\\sqsupset', 50, 50, 'none', 'infix'),
    '\\sqsupseteq': OpSpec('\\sqsupseteq', 50, 50, 'none', 'infix'),
    '\\doteq': OpSpec('\\doteq', 50, 50, 'none', 'infix'),
    '\\propto': OpSpec('\\propto', 50, 50, 'none', 'infix'),
}

ALIASES: dict[str, str] = {
    '#': '/=',
    '(+)': '\\oplus',
    '(-)': '\\ominus',
    '(.)': '\\odot',
    '(/)': '\\oslash',
    '(\\X)': '\\otimes',
    '/\\': '\\land',
    '<=': '\\leq',
    '<=>': '\\equiv',
    '=<': '\\leq',
    '>=': '\\geq',
    '\\/': '\\lor',
    '\\X': '\\times',
    '\\cap': '\\intersect',
    '\\circ': '\\o',
    '\\cup': '\\union',
    '\\neg': '\\lnot',
    'mod': '%',
    '~': '\\lnot',
    '¬': '\\lnot',
    '×': '\\times',
    '÷': '\\div',
    '‖': '||',
    '‥': '..',
    '…': '...',
    '‼': '!!',
    '⁇': '??',
    '⁺': '^+',
    '↝': '~>',
    '⇒': '=>',
    '⇔': '\\equiv',
    '⇸': '-+->',
    '∈': '\\in',
    '∉': '\\notin',
    '∘': '\\o',
    '∝': '\\propto',
    '∧': '\\land',
    '∨': '\\lor',
    '∩': '\\intersect',
    '∪': '\\union',
    '∼': '\\sim',
    '≀': '\\wr',
    '≃': '\\simeq',
    '≅': '\\cong',
    '≈': '\\approx',
    '≍': '\\asymp',
    '≐': '\\doteq',
    '≔': ':=',
    '≠': '/=',
    '≡': '\\equiv',
    '≤': '\\leq',
    '≥': '\\geq',
    '≪': '\\ll',
    '≫': '\\gg',
    '≺': '\\prec',
    '≻': '\\succ',
    '⊂': '\\subset',
    '⊃': '\\supset',
    '⊆': '\\subseteq',
    '⊇': '\\supseteq',
    '⊎': '\\uplus',
    '⊏': '\\sqsubset',
    '⊐': '\\sqsupset',
    '⊑': '\\sqsubseteq',
    '⊒': '\\sqsupseteq',
    '⊓': '\\sqcap',
    '⊔': '\\sqcup',
    '⊕': '\\oplus',
    '⊖': '\\ominus',
    '⊗': '\\otimes',
    '⊘': '\\oslash',
    '⊙': '\\odot',
    '⊢': '|-',
    '⊣': '-|',
    '⊨': '|=',
    '⋅': '\\cdot',
    '⋆': '\\star',
    '□': '[]',
    '◇': '<>',
    '●': '\\bullet',
    '◯': '\\bigcirc',
    '⩴': '::=',
    '⪯': '\\preceq',
    '⪰': '\\succeq',
    '⫤': '=|',
}

OPERATORS: dict[str, OpSpec] = {}
for _spec in CANONICAL.values():
    OPERATORS[_spec.canonical] = _spec
for _alt, _canon in ALIASES.items():
    OPERATORS[_alt] = CANONICAL[_canon]


def spec_of(text: str) -> OpSpec | None:
    """Return the SANY operator spec for a lexed operator token, if any."""
    return OPERATORS.get(text)


def is_operator(text: str) -> bool:
    return text in OPERATORS


def all_spellings() -> list[str]:
    """Every accepted spelling, longest first (needed by the lexer)."""
    return sorted(OPERATORS, key=lambda s: (-len(s), s))
