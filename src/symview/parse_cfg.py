"""Parser for TLC configuration (``.cfg``) files.

The configuration is where a TLC model actually lives: which constants get which
values, which invariant and temporal properties are checked, and whether the
user already supplied a ``SYMMETRY`` or ``VIEW``.  SymView reads it to

* learn the concrete values of the constants (needed for the exact
  permutation-invariance test),
* know which properties must survive a reduction,
* detect the *manual* baseline configuration shipped by the spec author,
* keep commented-out directives visible: several public specs disable symmetry
  with a warning comment, which is evidence for the soundness analysis.

The file is tokenised with the TLA+ lexer (the two syntaxes overlap) and then
split into sections by keyword.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .lex import Tok, tokenize

KEYWORDS = {
    "CONSTANT", "CONSTANTS", "VARIABLE", "VARIABLES", "INIT", "NEXT",
    "SPECIFICATION", "SPEC", "INVARIANT", "INVARIANTS", "PROPERTY",
    "PROPERTIES", "THEOREM", "SYMMETRY", "VIEW", "ALIAS", "CONSTRAINT",
    "ACTION_CONSTRAINT", "CHECK_DEADLOCK", "POSTCONDITION", "USER_SPEC",
}
LIST_KEYWORDS = {
    "INVARIANT", "INVARIANTS", "PROPERTY", "PROPERTIES", "CONSTRAINT",
    "ACTION_CONSTRAINT", "THEOREM",
}
SINGLE_KEYWORDS = {
    "INIT", "NEXT", "SPECIFICATION", "SPEC", "SYMMETRY", "VIEW",
    "POSTCONDITION", "USER_SPEC",
}
COMMENT_RE = re.compile(r"\\.*$")


@dataclass
class Assignment:
    """One ``CONSTANTS`` entry, e.g. ``Acceptor <- MCAcceptor``."""

    name: str
    form: str            # "=" | "<-" | "<-[Module]"
    value_text: str      # the raw right hand side, for regeneration
    value_tokens: list[Tok] = field(default_factory=list)
    line: int = 0


@dataclass
class TlaConfig:
    path: str = ""
    constants: dict[str, Assignment] = field(default_factory=dict)
    aliases: dict[str, str] = field(default_factory=dict)
    variables: list[str] = field(default_factory=list)
    init: str | None = None
    next: str | None = None
    specification: str | None = None
    invariants: list[str] = field(default_factory=list)
    properties: list[str] = field(default_factory=list)
    symmetry: str | None = None
    view: str | None = None
    constraints: list[str] = field(default_factory=list)
    action_constraints: list[str] = field(default_factory=list)
    check_deadlock: bool | None = None
    postcondition: str | None = None
    comments: list[str] = field(default_factory=list)
    unknown_keywords: list[str] = field(default_factory=list)
    unknown_tokens: list[str] = field(default_factory=list)
    raw: str = ""

    @property
    def checked_properties(self) -> list[str]:
        return list(self.invariants) + list(self.properties)

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "constants": {k: {"form": v.form, "value_text": v.value_text, "line": v.line}
                          for k, v in self.constants.items()},
            "aliases": self.aliases,
            "variables": self.variables,
            "init": self.init,
            "next": self.next,
            "specification": self.specification,
            "invariants": self.invariants,
            "properties": self.properties,
            "symmetry": self.symmetry,
            "view": self.view,
            "constraints": self.constraints,
            "action_constraints": self.action_constraints,
            "check_deadlock": self.check_deadlock,
            "postcondition": self.postcondition,
            "comments": self.comments,
            "unknown_keywords": self.unknown_keywords,
            "unknown_tokens": self.unknown_tokens,
        }


def _strip_comments(source: str) -> tuple[str, list[str]]:
    """Remove ``\\*`` comments but keep them: they carry author intent."""
    kept: list[str] = []
    out_lines = []
    for line in source.splitlines():
        match = re.search(r"\\\*", line)
        if match:
            comment = line[match.start():].strip()
            kept.append(comment)
            line = line[:match.start()]
        out_lines.append(line)
    return "\n".join(out_lines), kept


def parse_config_source(source: str, path: str = "<string>") -> TlaConfig:
    body, comments = _strip_comments(source)
    lex = tokenize(body)
    tokens = [t for t in lex.tokens if t.kind != "EOF"]
    cfg = TlaConfig(path=path, comments=comments, raw=source)

    i = 0
    n = len(tokens)

    def is_keyword(tok: Tok) -> bool:
        # TLC keywords are upper case.  Matching case-insensitively would eat the
        # extremely common values of `SPECIFICATION Spec`, `INIT Init`,
        # `NEXT Next` and `VIEW View`, and the TLA+ lexer already classifies
        # CONSTANT/VARIABLE/THEOREM as KEY rather than NAME.
        return (tok.kind in ("NAME", "KEY")
                and tok.text == tok.text.upper()
                and tok.text in KEYWORDS)

    while i < n:
        tok = tokens[i]
        if not is_keyword(tok):
            cfg.unknown_tokens.append(tok.text)
            i += 1
            continue
        key = tok.text.upper()
        i += 1
        section: list[Tok] = []
        while i < n and not is_keyword(tokens[i]):
            section.append(tokens[i])
            i += 1

        if key in ("CONSTANT", "CONSTANTS"):
            _parse_constant_section(section, cfg)
        elif key in ("VARIABLE", "VARIABLES"):
            cfg.variables += [t.text for t in section if t.kind == "NAME"]
        elif key == "ALIAS":
            for j in range(len(section) - 2):
                if section[j].kind == "NAME" and section[j + 1].text == "=":
                    cfg.aliases[section[j].text] = section[j + 2].text
        elif key in SINGLE_KEYWORDS:
            names = [t.text for t in section if t.kind in ("NAME", "OP")]
            value = " ".join(names) if names else None
            if key in ("SPECIFICATION", "SPEC"):
                cfg.specification = value
            elif key == "INIT":
                cfg.init = value
            elif key == "NEXT":
                cfg.next = value
            elif key == "SYMMETRY":
                cfg.symmetry = value
            elif key == "VIEW":
                cfg.view = value
            elif key == "POSTCONDITION":
                cfg.postcondition = value
            elif key == "USER_SPEC":
                cfg.unknown_keywords.append("USER_SPEC")
        elif key in LIST_KEYWORDS:
            names = [t.text for t in section if t.kind == "NAME"]
            if key in ("INVARIANT", "INVARIANTS"):
                cfg.invariants += names
            elif key in ("PROPERTY", "PROPERTIES"):
                cfg.properties += names
            elif key == "CONSTRAINT":
                cfg.constraints += names
            elif key == "ACTION_CONSTRAINT":
                cfg.action_constraints += names
            elif key == "THEOREM":
                cfg.invariants += names
        elif key == "CHECK_DEADLOCK":
            text = " ".join(t.text for t in section).upper()
            cfg.check_deadlock = not text.startswith("FALSE")
        else:
            cfg.unknown_keywords.append(key)

    return cfg


def _parse_constant_section(section: list[Tok], cfg: TlaConfig) -> None:
    """Split ``a1=a1 Acceptor <- MCAcceptor Ballot <-[Voting] MCBallot`` apart."""
    marks: list[tuple[int, str]] = []
    for j, tok in enumerate(section):
        if tok.kind == "NAME" and j + 1 < len(section):
            nxt = section[j + 1]
            if nxt.text == "=":
                marks.append((j, "="))
            elif nxt.text == "<-":
                form = "<-"
                if j + 3 < len(section) and section[j + 2].text == "[" \
                        and section[j + 4].text == "]":
                    form = "<-[" + section[j + 3].text + "]"
                marks.append((j, form))
    for k, (start, form) in enumerate(marks):
        end = marks[k + 1][0] if k + 1 < len(marks) else len(section)
        name = section[start].text
        value_tokens = section[start + 2:end] if not form.startswith("<-[") \
            else section[start + 5:end]
        while value_tokens and value_tokens[0].text == ",":
            value_tokens = value_tokens[1:]
        while value_tokens and value_tokens[-1].text == ",":
            value_tokens = value_tokens[:-1]
        text = _render(value_tokens)
        cfg.constants[name] = Assignment(name=name, form=form, value_text=text,
                                         value_tokens=list(value_tokens),
                                         line=section[start].line)


NO_SPACE_BEFORE = {")", "]", "}", ",", "'", ">>", ".", "!", "_", ":"}
NO_SPACE_AFTER = {"(", "[", "{", "<<"}


def _render(tokens: list[Tok]) -> str:
    """Re-render a token run for display and for regenerated configurations.

    Whitespace is not significant in a TLC configuration, so this only has to be
    readable, not byte identical to the original.
    """
    parts: list[str] = []
    prev = ""
    for tok in tokens:
        glue = bool(parts) and (tok.text in NO_SPACE_BEFORE or prev in NO_SPACE_AFTER)
        parts.append(tok.text if glue or not parts else " " + tok.text)
        prev = tok.text
    return "".join(parts)


def parse_config_file(path: Path | str) -> TlaConfig:
    path = Path(path)
    return parse_config_source(path.read_text(encoding="utf-8", errors="replace"),
                               path=str(path))
