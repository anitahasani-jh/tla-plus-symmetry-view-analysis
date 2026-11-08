"""A pragmatic TLA+ module parser for static analysis.

This is *not* a reimplementation of SANY.  It is an analysis parser: it builds
an AST that records every identifier occurrence together with the operator
context it appears in, and it degrades gracefully.  Anything it cannot
understand becomes an ``unknown`` node that still consumes its tokens, so

* parsing never crashes on a real specification,
* ``symview.astnodes.coverage`` can prove that every token is accounted for,
* the number of ``unknown`` nodes is a measurable robustness statistic that is
  reported per model instead of being hidden.

Operator precedence, associativity and fixity come from
:mod:`symview.operators` (generated from SANY's table).
"""

from __future__ import annotations

from pathlib import Path

from .astnodes import N, coverage, link
from .lex import LexResult, tokenize
from .operators import OPERATORS

UNIT_KEYWORDS = {
    "EXTENDS", "CONSTANT", "CONSTANTS", "VARIABLE", "VARIABLES", "ASSUME",
    "ASSUMPTION", "THEOREM", "PROPOSITION", "LEMMA", "COROLLARY", "INSTANCE",
    "LOCAL", "RECURSIVE", "USE", "DEFINE", "HIDE", "MODULE",
}
SKIP_KEYWORDS = {
    "USE", "DEFINE", "HIDE", "RECALL", "TAKE", "HAVE", "SUFFICES", "PICK",
    "WITNESS", "PROOF", "PROVE", "BY", "OBVIOUS", "OMITTED", "QED", "DEF",
    "ONLY", "ASSERT", "PRINT", "TLASSUME", "NEW", "STEP",
}
THEOREM_KEYWORDS = {"THEOREM", "PROPOSITION", "LEMMA", "COROLLARY"}
BULLETS = {"\\land", "\\lor"}
OPENERS = {"(", "[", "{", "<<"}
CLOSERS = {")": "(", "]": "[", "}": "{", ">>": "<<"}


class Parser:
    def __init__(self, tokens: list) -> None:
        self.toks = tokens
        self.pos = 0
        self.unknowns: list[N] = []
        self.proof_tokens_skipped = 0
        self.notes: list[str] = []
        self.saw_footer = False
        self.trailing_tokens = 0
        self.preamble_tokens = 0

    # -- token helpers -------------------------------------------------------
    def peek(self, k: int = 0):
        i = self.pos + k
        return self.toks[i] if i < len(self.toks) else self.toks[-1]

    def advance(self):
        tok = self.peek()
        if self.pos < len(self.toks) - 1:
            self.pos += 1
        return tok

    def at(self, kind: str | None = None, text: str | None = None) -> bool:
        tok = self.peek()
        if tok.kind == "EOF":
            return False
        if kind is not None and tok.kind != kind:
            return False
        if text is not None and tok.text != text:
            return False
        return True

    def eat(self, kind: str | None = None, text: str | None = None):
        if self.at(kind, text):
            return self.advance()
        return None

    def expect(self, kind: str | None = None, text: str | None = None):
        tok = self.eat(kind, text)
        if tok is None:
            got = self.peek()
            self.notes.append(f"expected {kind or ''}{text or ''} at "
                              f"{got.line}:{got.col}, found {got.kind}:{got.text!r}")
        return tok

    def here(self) -> tuple[int, int, int]:
        tok = self.peek()
        return tok.line, tok.col, self.pos

    def node(self, kind: str, text: str = "", t0: int | None = None) -> N:
        tok = self.toks[max(0, (self.pos if t0 is None else t0))]
        return N(kind=kind, text=text, line=tok.line, col=tok.col)

    def unknown(self, reason: str) -> N:
        tok = self.advance()
        node = N(kind="unknown", text=reason, line=tok.line, col=tok.col,
                 t0=tok.idx, t1=tok.idx + 1, note=tok.text)
        self.unknowns.append(node)
        return node

    def finish(self, node: N, t0: int) -> N:
        node.t0 = t0
        node.t1 = self.pos
        return node

    # -- lookahead -----------------------------------------------------------
    def at_unit_start(self, reliable_only: bool = False) -> bool:
        tok = self.peek()
        if tok.kind in ("EOF", "FOOTER", "BANNER"):
            return True
        if tok.kind == "KEY" and tok.text in UNIT_KEYWORDS:
            return True
        if not reliable_only and tok.kind == "KEY" and tok.text in SKIP_KEYWORDS:
            return True
        if tok.kind in ("NAME", "OP", "PUNCT") and self.at_def_start():
            return True
        return False

    def looks_like_proof_step(self) -> bool:
        """``<1>``, ``<1>2.``, ``<12>.`` -- TLAPS proof step markers."""
        t1, t2 = self.peek(1), self.peek(2)
        return t1.kind == "NUM" and t2.kind == "OP" and t2.text == ">"

    def skip_proof_step(self) -> N:
        """Consume one TLAPS proof step, up to the next step or real unit.

        Proof syntax is out of scope for a model-checking reduction tool, but
        skipping it cleanly keeps the analysis of proof-carrying modules honest
        instead of drowning it in fallback nodes.
        """
        line, col, t0 = self.here()
        node = N(kind="proofstep", line=line, col=col)
        self.advance()
        self.advance()
        self.expect("OP", ">")
        if self.at("NUM"):
            self.advance()
        self.eat("OP", ".")
        guard = 0
        while self.peek().kind != "EOF" and guard < 100000:
            if self.at("OP", "<") and self.looks_like_proof_step():
                break
            if self.at_unit_start(reliable_only=True):
                break
            self.advance()
            guard += 1
        node.note = f"{self.pos - t0} tokens"
        return self.finish(node, t0)

    def at_def_start(self) -> bool:
        """True if the cursor sits on the head of an operator definition.

        Deliberately local (it inspects at most the parameter region) because a
        long-range scan for ``==`` mis-fires inside ``CONSTANT`` lists, where the
        next definition may be dozens of tokens away.
        """
        t0, t1, t2, t3 = self.peek(0), self.peek(1), self.peek(2), self.peek(3)
        if t0.kind == "PUNCT" and t0.text == "_":
            return t1.kind == "OP" and t2.kind == "PUNCT" and t2.text == "=="
        if t0.kind not in ("NAME", "OP"):
            return False
        if t1.kind == "PUNCT" and t1.text == "==":
            return True
        if t1.kind == "PUNCT" and t1.text in ("(", "["):
            return self.params_then_eq(1)
        if t1.kind == "OP" and t2.kind in ("NAME", "OP", "PUNCT") and \
                t3.kind == "PUNCT" and t3.text == "==":
            return True
        if t1.kind in ("NAME", "PUNCT") and t2.kind == "PUNCT" and t2.text == "==":
            return t0.kind == "OP"
        return False

    def params_then_eq(self, offset: int) -> bool:
        opener = self.peek(offset)
        depth = 0
        j = self.pos + offset
        while j < len(self.toks):
            tok = self.toks[j]
            if tok.kind == "EOF":
                return False
            if tok.kind == "PUNCT":
                if tok.text in OPENERS:
                    depth += 1
                elif tok.text in CLOSERS:
                    depth -= 1
                    if depth == 0:
                        nxt = self.toks[j + 1] if j + 1 < len(self.toks) else None
                        return bool(nxt and nxt.kind == "PUNCT" and nxt.text == "==")
            j += 1
        return False

    def classify_bracket(self) -> str:
        first = self.toks[self.pos + 1] if self.pos + 1 < len(self.toks) else None
        second = self.toks[self.pos + 2] if self.pos + 2 < len(self.toks) else None
        if (first is not None and second is not None and first.kind == "NAME"
                and second.kind == "PUNCT" and second.text == ":"):
            # ``[field : Set, field2 : Set2]`` -- the set of records, which uses
            # ``:`` where a record value uses ``|->``.
            return "recordset"
        depth = 0
        seen_binder = False
        j = self.pos
        while j < len(self.toks):
            tok = self.toks[j]
            if tok.kind == "EOF":
                break
            if tok.kind == "PUNCT":
                if tok.text in OPENERS:
                    depth += 1
                elif tok.text in CLOSERS:
                    depth -= 1
                    if depth == 0 and tok.text == "]":
                        nxt = self.toks[j + 1] if j + 1 < len(self.toks) else None
                        if nxt is not None and ((nxt.kind == "PUNCT" and nxt.text == "_")
                                                or (nxt.kind == "NAME"
                                                    and nxt.text.startswith("_"))):
                            return "stutter"
                        return "badbracket"
                elif depth == 1:
                    if tok.text == "|->":
                        # ``[a |-> b]`` is a record, ``[x \in S |-> e]`` is a
                        # function constructor; the binder is what tells them apart.
                        return "funcc" if seen_binder else "record"
                    if tok.text == "|_":
                        return "funcc"
                    if tok.text == "->":
                        return "funcset"
            elif tok.kind == "OP" and depth == 1 and tok.text in ("\\in", "\\subseteq"):
                seen_binder = True
            elif tok.kind == "KEY" and tok.text == "EXCEPT" and depth == 1:
                return "except"
            j += 1
        return "unknown"

    def classify_brace(self) -> str:
        if self.at("PUNCT", "}") or self.peek(1).kind == "EOF":
            return "empty"
        j = self.pos + 1
        if self.toks[j].kind == "PUNCT" and self.toks[j].text == "}":
            return "empty"
        # {x \in S, y \in T : P}  ->  filter
        k = j
        while k < len(self.toks) and self.toks[k].kind == "NAME":
            k += 1
            if self.toks[k].kind == "PUNCT" and self.toks[k].text == ",":
                k += 1
                continue
            break
        if k < len(self.toks) and self.toks[k].kind == "OP" and self.toks[k].text == "\\in":
            return "filter"
        depth = 1
        m = j
        while m < len(self.toks):
            tok = self.toks[m]
            if tok.kind == "EOF":
                break
            if tok.kind == "PUNCT":
                if tok.text in OPENERS:
                    depth += 1
                elif tok.text in CLOSERS:
                    depth -= 1
                    if depth == 0:
                        return "enum"
                elif tok.text == ":" and depth == 1:
                    return "map"
            m += 1
        return "enum"

    # -- file / module -------------------------------------------------------
    def parse_file(self) -> N:
        modules: list[N] = []
        root = N(kind="file", text="", line=1, col=1, t0=0, t1=self.pos)

        has_banner = any(tok.kind == "BANNER" for tok in self.toks)
        if has_banner and self.peek().kind != "BANNER":
            # SANY ignores prose that precedes the module banner (some public
            # specs start with a plain-English problem statement).
            start = self.pos
            while self.peek().kind not in ("EOF", "BANNER"):
                self.advance()
            first = self.toks[start]
            root.add(N(kind="ignored", text="before-module-banner",
                       line=first.line, col=first.col, t0=start, t1=self.pos), "preamble")
            self.preamble_tokens = self.pos - start

        while self.peek().kind != "EOF":
            if self.peek().kind == "FOOTER":
                self.advance()
                self.saw_footer = True
                break
            modules.append(self.parse_module())
            if self.saw_footer or self.peek().kind == "EOF":
                break
        for mod in modules:
            root.add(mod, "module")
        if self.peek().kind != "EOF":
            # SANY stops at the closing rule of the module; whatever follows it
            # (revision notes, ASCII state diagrams, ...) is not specification
            # text, so it is recorded but not parsed.
            last = len(self.toks) - 1
            trailer = N(kind="ignored", text="after-module-footer",
                        line=self.peek().line, col=self.peek().col, t0=self.pos, t1=last)
            root.add(trailer, "trailing")
            self.trailing_tokens = max(0, last - self.pos)
            self.pos = last
        root.t1 = self.pos
        return link(root)

    def parse_module(self) -> N:
        line, col, t0 = self.here()
        name = ""
        banner = self.eat("BANNER")
        if banner is not None:
            name = banner.text
        mod = N(kind="module", text=name, line=line, col=col)
        guard = 0
        while self.peek().kind not in ("EOF",):
            if self.peek().kind == "FOOTER":
                self.advance()
                self.saw_footer = True
                break
            if self.peek().kind == "BANNER":
                break
            before = self.pos
            unit = self.parse_unit()
            if unit is not None:
                mod.add(unit, "unit")
            if self.pos == before:
                mod.add(self.unknown("no-progress-in-module"), "unit")
            guard += 1
            if guard > 20000:
                self.notes.append("module parse guard tripped")
                break
        return self.finish(mod, t0)

    def parse_unit(self) -> N | None:
        tok = self.peek()
        line, col, t0 = self.here()

        if tok.kind == "KEY" and tok.text == "EXTENDS":
            self.advance()
            node = N(kind="extends", line=line, col=col)
            while True:
                name = self.eat("NAME")
                if name is None:
                    break
                node.add(N(kind="name", text=name.text, line=name.line, col=name.col), "module")
                if not self.eat("PUNCT", ","):
                    break
            return self.finish(node, t0)

        if tok.kind == "KEY" and tok.text in ("CONSTANT", "CONSTANTS"):
            self.advance()
            return self.finish(self.parse_declarations("constant-decl"), t0)

        if tok.kind == "KEY" and tok.text in ("VARIABLE", "VARIABLES"):
            self.advance()
            return self.finish(self.parse_declarations("variable-decl"), t0)

        if tok.kind == "KEY" and tok.text in ("ASSUME", "ASSUMPTION"):
            self.advance()
            node = N(kind="assume", line=line, col=col)
            if self.at("NAME") and self.peek(1).kind == "PUNCT" and self.peek(1).text == "==":
                label = self.advance()
                node.text = label.text
                self.advance()
            node.add(self.parse_expr(), "body")
            return self.finish(node, t0)

        if tok.kind == "KEY" and tok.text in THEOREM_KEYWORDS:
            self.advance()
            node = N(kind="theorem", text=tok.text, line=line, col=col)
            if self.at("NAME") and self.peek(1).kind == "PUNCT" and self.peek(1).text == "==":
                label = self.advance()
                node.note = label.text
                self.advance()
            elif self.at("NAME") and self.peek(1).kind == "PUNCT" and self.peek(1).text == "::=":
                label = self.advance()
                node.note = label.text
                self.advance()
            node.add(self.parse_expr(), "body")
            self.skip_proof()
            return self.finish(node, t0)

        if tok.kind == "KEY" and tok.text == "LOCAL":
            self.advance()
            inner = self.parse_unit()
            node = N(kind="local", line=line, col=col)
            if inner is not None:
                node.add(inner, "unit")
            return self.finish(node, t0)

        if tok.kind == "KEY" and tok.text == "RECURSIVE":
            self.advance()
            node = N(kind="recursive", line=line, col=col)
            while True:
                name = self.eat("NAME")
                if name is None:
                    break
                item = N(kind="name", text=name.text, line=name.line, col=name.col)
                if self.at("PUNCT", "("):
                    self.advance()
                    depth = 1
                    while depth and self.peek().kind != "EOF":
                        t = self.advance()
                        if t.kind == "PUNCT" and t.text == "(":
                            depth += 1
                        elif t.kind == "PUNCT" and t.text == ")":
                            depth -= 1
                    item.note = "operator"
                node.add(item, "name")
                if not self.eat("PUNCT", ","):
                    break
            return self.finish(node, t0)

        if tok.kind == "KEY" and tok.text == "INSTANCE":
            return self.finish(self.parse_instance(""), t0)

        if tok.kind == "OP" and tok.text == "<" and self.looks_like_proof_step():
            return self.finish(self.skip_proof_step(), t0)

        if tok.kind == "KEY" and tok.text in SKIP_KEYWORDS:
            self.advance()
            node = N(kind="directive", text=tok.text, line=line, col=col)
            while not self.at_unit_start() and self.peek().kind != "EOF":
                self.advance()
            return self.finish(node, t0)

        if self.at_def_start():
            return self.finish(self.parse_definition(), t0)

        return self.unknown("unexpected-unit-start")

    def parse_declarations(self, kind: str) -> N:
        line, col, t0 = self.here()
        node = N(kind=kind, line=line, col=col)
        while True:
            if self.at_unit_start() or self.peek().kind == "EOF":
                break
            if self.at("NAME"):
                name = self.advance()
                item = N(kind="name", text=name.text, line=name.line, col=name.col)
                if self.at("PUNCT", "(") or self.at("PUNCT", "["):
                    open_tok = self.advance()
                    close = ")" if open_tok.text == "(" else "]"
                    depth = 1
                    arity = 0
                    while depth and self.peek().kind != "EOF":
                        t = self.advance()
                        if t.kind == "PUNCT" and t.text == open_tok.text:
                            depth += 1
                        elif t.kind == "PUNCT" and t.text == close:
                            depth -= 1
                        elif t.kind == "PUNCT" and t.text == "_" and depth == 1:
                            arity += 1
                    item.note = f"operator-arity-{arity}"
                node.add(item, "name")
            elif self.at("OP"):
                op = self.advance()
                node.add(N(kind="name", text=op.text, line=op.line, col=op.col,
                           note="operator-symbol"), "name")
            else:
                node.add(self.unknown("declaration-item"), "name")
                continue
            if not self.eat("PUNCT", ","):
                if self.at_unit_start() or self.peek().kind == "EOF":
                    break
                if self.at("NAME") or self.at("OP"):
                    continue
                break
        return node

    def parse_definition(self) -> N:
        line, col, t0 = self.here()
        node = N(kind="opdef", line=line, col=col)
        first = self.advance()
        node.text = first.text

        if self.at("PUNCT", "(") or self.at("PUNCT", "["):
            open_tok = self.advance()
            depth = 1
            param_tokens: list = []
            while depth and self.peek().kind != "EOF":
                tok = self.advance()
                if tok.kind == "PUNCT" and tok.text in OPENERS:
                    depth += 1
                elif tok.kind == "PUNCT" and tok.text in CLOSERS:
                    depth -= 1
                    if depth == 0:
                        break
                param_tokens.append(tok)
            node.add(self.parse_param_list(param_tokens, node), "params")
            if open_tok.text == "[":
                node.note = "higher-order"
        elif self.at("OP"):
            op_tok = self.advance()
            right = self.advance()
            node.text = op_tok.text
            node.note = "infix-operator-definition"
            node.add(N(kind="name", text=first.text, line=first.line, col=first.col), "param")
            node.add(N(kind="name", text=right.text, line=right.line, col=right.col), "param")
        elif first.kind == "OP" and (self.at("NAME") or self.at("PUNCT", "_")):
            param = self.advance()
            node.note = "prefix-operator-definition"
            node.add(N(kind="name", text=param.text, line=param.line, col=param.col), "param")
        elif first.kind == "PUNCT":
            node.note = "placeholder-definition"

        self.expect("PUNCT", "==")
        node.add(self.parse_expr(), "body")
        return node

    def parse_param_list(self, tokens: list, owner: N) -> N:
        """Parse the parameter region of a definition.

        Parameters can be plain names, typed names (``x \\in S``), tuple
        patterns (``<<a, b>>``) or higher-order holes (``f(_)``).  For the
        analysis only the bound names matter, so the region is parsed as a
        comma separated expression list and every NAME in it becomes a binder.
        """
        node = N(kind="params", line=owner.line, col=owner.col)
        sub = Parser(tokens + [self.toks[-1]])
        while sub.peek().kind != "EOF":
            before = sub.pos
            expr = sub.parse_expr()
            node.add(expr, "param")
            sub.eat("PUNCT", ",")
            if sub.pos == before:
                node.add(sub.unknown("param"), "param")
        self.unknowns.extend(sub.unknowns)
        self.notes.extend(sub.notes)
        return node

    def parse_instance(self, label: str) -> N:
        line, col, t0 = self.here()
        self.expect("KEY", "INSTANCE")
        node = N(kind="instance", line=line, col=col)
        name = self.eat("NAME")
        if name is not None:
            node.text = name.text
        while self.eat("PUNCT", "!"):
            extra = self.eat("NAME")
            if extra is not None:
                node.text += "!" + extra.text
        if self.eat("KEY", "WITH"):
            while True:
                before = self.pos
                lhs = self.eat("NAME")
                if lhs is None:
                    break
                if self.eat("PUNCT", "<-") or self.eat("OP", "<-"):
                    node.add(N(kind="name", text=lhs.text, line=lhs.line, col=lhs.col), "target")
                    node.add(self.parse_expr(), "value")
                elif self.eat("PUNCT", "="):
                    node.add(N(kind="name", text=lhs.text, line=lhs.line, col=lhs.col), "target")
                    node.add(self.parse_expr(), "value")
                else:
                    self.pos = before
                    break
                if not self.eat("PUNCT", ","):
                    break
        if self.at("PUNCT", "("):
            self.advance()
            depth = 1
            while depth and self.peek().kind != "EOF":
                t = self.advance()
                if t.kind == "PUNCT" and t.text == "(":
                    depth += 1
                elif t.kind == "PUNCT" and t.text == ")":
                    depth -= 1
            node.note = "positional-instance"
        return node

    def skip_proof(self) -> None:
        tok = self.peek()
        starts_proof = (tok.kind == "KEY" and tok.text in SKIP_KEYWORDS) or \
                       (tok.kind == "OP" and tok.text == "<")
        if not starts_proof:
            return
        skipped = 0
        while not self.at_unit_start(reliable_only=True) and self.peek().kind != "EOF":
            self.advance()
            skipped += 1
        self.proof_tokens_skipped += skipped

    # -- expressions ---------------------------------------------------------
    def parse_expr(self, min_prec: int = 0) -> N:
        line, col, t0 = self.here()
        left = self.parse_postfix(self.parse_prefix())
        while True:
            tok = self.peek()
            if tok.kind != "OP":
                break
            if tok.text == "<" and self.looks_like_proof_step():
                # ``<1>2.`` is a TLAPS step marker, not a comparison with 1.
                break
            spec = OPERATORS.get(tok.text)
            if spec is None or spec.fix not in ("infix", "nfix"):
                break
            if spec.low < min_prec:
                break
            self.advance()
            next_min = spec.low if spec.assoc == "right" else spec.low + 1
            right = self.parse_postfix(self.parse_expr(next_min))
            node = N(kind="infix", text=spec.canonical, line=tok.line, col=tok.col)
            node.add(left, "lhs")
            node.add(right, "rhs")
            node.t0, node.t1 = t0, self.pos
            left = node
        return left

    def parse_prefix(self) -> N:
        tok = self.peek()
        line, col, t0 = self.here()

        if tok.kind == "OP":
            spec = OPERATORS.get(tok.text)
            if spec is not None and spec.fix == "prefix":
                self.advance()
                operand = self.parse_postfix(self.parse_expr(spec.low))
                node = N(kind="prefix", text=spec.canonical, line=line, col=col)
                node.add(operand, "operand")
                return self.finish(node, t0)
            if spec is not None and spec.canonical in BULLETS:
                self.advance()
                return self.parse_postfix(self.parse_prefix())
            if tok.text == "-":
                self.advance()
                operand = self.parse_postfix(self.parse_expr(120))
                node = N(kind="prefix", text="-.", line=line, col=col)
                node.add(operand, "operand")
                return self.finish(node, t0)
            if spec is not None:
                # An infix operator sitting in operand position is an operator
                # symbol passed as a value, e.g. `TotallyOrderedUnder(<, Keys)`.
                self.advance()
                return self.finish(N(kind="opref", text=spec.canonical,
                                     line=line, col=col), t0)

        if tok.kind == "KEY":
            if tok.text in ("TRUE", "FALSE"):
                self.advance()
                return self.finish(N(kind="bool", text=tok.text, line=line, col=col), t0)
            if tok.text == "BOOLEAN":
                self.advance()
                return self.finish(N(kind="name", text="BOOLEAN", line=line, col=col), t0)
            if tok.text == "LAMBDA":
                return self.parse_lambda()
            if tok.text in ("\\A", "\\E", "\u2200", "\u2203"):
                return self.parse_quantifier()
            if tok.text == "CHOOSE":
                return self.parse_choose()
            if tok.text == "IF":
                return self.parse_if()
            if tok.text == "LET":
                return self.parse_let()
            if tok.text == "CASE":
                return self.parse_case()
            if tok.text == "INSTANCE":
                return self.parse_instance("")
            if tok.text == "EXCEPT":
                return self.unknown("stray-EXCEPT")

        if tok.kind == "NAME":
            if tok.text in ("TRUE", "FALSE"):
                self.advance()
                return self.finish(N(kind="bool", text=tok.text, line=line, col=col), t0)
            if tok.text.startswith(("WF_", "SF_")) or tok.text in ("WF", "SF"):
                return self.parse_fairness()
            self.advance()
            return self.finish(N(kind="name", text=tok.text, line=line, col=col), t0)

        if tok.kind == "NUM":
            self.advance()
            return self.finish(N(kind="num", text=tok.text, line=line, col=col), t0)

        if tok.kind == "STR":
            self.advance()
            return self.finish(N(kind="str", text=tok.text, line=line, col=col), t0)

        if tok.kind == "PUNCT":
            if tok.text == "@":
                self.advance()
                return self.finish(N(kind="name", text="@", line=line, col=col), t0)
            if tok.text == "(":
                self.advance()
                inner = self.parse_expr()
                self.expect("PUNCT", ")")
                return self.finish(inner, t0)
            if tok.text == "<<":
                tup = self.parse_tuple()
                sub = self.eat_subscript()
                if sub is None:
                    return tup
                node = N(kind="stutter", text="<>", line=line, col=col)
                node.add(tup, "action")
                node.add(sub, "subscript")
                return self.finish(node, t0)
            if tok.text == "{":
                return self.parse_brace()
            if tok.text == "[":
                return self.parse_bracket()

        return self.unknown("unexpected-token-in-expression")

    def parse_postfix(self, node: N) -> N:
        while True:
            tok = self.peek()
            t0 = node.t0 if node.t0 >= 0 else self.pos
            if tok.kind == "OP" and tok.text in ("'", "^+", "^*", "^#"):
                self.advance()
                wrap = N(kind="postfix", text=tok.text, line=tok.line, col=tok.col)
                wrap.add(node, "operand")
                node = self.finish(wrap, t0)
                continue
            if tok.kind == "PUNCT" and tok.text == "(":
                self.advance()
                call = N(kind="apply", text="(", line=tok.line, col=tok.col)
                call.add(node, "head")
                while True:
                    if self.at("PUNCT", ")"):
                        break
                    call.add(self.parse_expr(), "arg")
                    if not self.eat("PUNCT", ","):
                        break
                self.expect("PUNCT", ")")
                node = self.finish(call, t0)
                continue
            if tok.kind == "PUNCT" and tok.text == "[":
                self.advance()
                call = N(kind="apply", text="[", line=tok.line, col=tok.col)
                call.add(node, "head")
                while True:
                    if self.at("PUNCT", "]"):
                        break
                    call.add(self.parse_expr(), "arg")
                    if not self.eat("PUNCT", ","):
                        break
                self.expect("PUNCT", "]")
                node = self.finish(call, t0)
                continue
            if tok.kind == "PUNCT" and tok.text == "!":
                self.advance()
                bang = N(kind="bang", text="!", line=tok.line, col=tok.col)
                bang.add(node, "left")
                if self.at("NAME") or self.at("NUM"):
                    right = self.advance()
                    bang.add(N(kind="name" if right.kind == "NAME" else "num",
                               text=right.text, line=right.line, col=right.col), "right")
                else:
                    bang.add(self.unknown("bang-target"), "right")
                node = self.finish(bang, t0)
                continue
            if tok.kind == "OP" and tok.text == "." and node.kind in ("name", "apply", "bang"):
                self.advance()
                if self.at("NAME"):
                    field = self.advance()
                    dot = N(kind="infix", text=".", line=tok.line, col=tok.col)
                    dot.add(node, "lhs")
                    dot.add(N(kind="name", text=field.text, line=field.line, col=field.col), "rhs")
                    node = self.finish(dot, t0)
                    continue
            break
        return node

    def parse_tuple(self) -> N:
        line, col, t0 = self.here()
        self.expect("PUNCT", "<<")
        node = N(kind="tuple", line=line, col=col)
        while not self.at("PUNCT", ">>") and self.peek().kind != "EOF":
            before = self.pos
            node.add(self.parse_expr(), "item")
            if self.pos == before:
                node.add(self.unknown("tuple-item"), "item")
            if not self.eat("PUNCT", ","):
                break
        self.expect("PUNCT", ">>")
        return self.finish(node, t0)

    def parse_brace(self) -> N:
        line, col, t0 = self.here()
        form = self.classify_brace()
        self.expect("PUNCT", "{")
        if form == "empty":
            self.expect("PUNCT", "}")
            return self.finish(N(kind="set", line=line, col=col), t0)
        if form == "filter":
            node = N(kind="setfilter", line=line, col=col)
            for binder in self.parse_binders():
                node.add(binder, "binder")
            self.expect("PUNCT", ":")
            node.add(self.parse_expr(), "pred")
            self.expect("PUNCT", "}")
            return self.finish(node, t0)
        if form == "map":
            node = N(kind="setmap", line=line, col=col)
            node.add(self.parse_expr(), "body")
            self.expect("PUNCT", ":")
            for binder in self.parse_binders():
                node.add(binder, "binder")
            self.expect("PUNCT", "}")
            return self.finish(node, t0)
        node = N(kind="set", line=line, col=col)
        while not self.at("PUNCT", "}") and self.peek().kind != "EOF":
            before = self.pos
            node.add(self.parse_expr(), "item")
            if self.pos == before:
                node.add(self.unknown("set-item"), "item")
            if not self.eat("PUNCT", ","):
                break
        self.expect("PUNCT", "}")
        return self.finish(node, t0)

    def parse_binders(self) -> list[N]:
        """``x, y \\in S, z \\in T`` binder groups used by quantifiers and filters."""
        binders: list[N] = []
        while True:
            line, col, t0 = self.here()
            binder = N(kind="binder", line=line, col=col)
            names = 0
            while self.at("NAME"):
                name = self.advance()
                binder.add(N(kind="name", text=name.text, line=name.line, col=name.col), "var")
                names += 1
                if names > 1 and not self.eat("PUNCT", ","):
                    break
                if self.at("NAME") and self.peek(1).kind == "PUNCT" and self.peek(1).text == ",":
                    continue
                if self.at("NAME"):
                    continue
                break
            if names == 0:
                binder.add(self.parse_expr(), "var")
            if self.at("OP", "\\in"):
                self.advance()
                binder.add(self.parse_expr(51), "domain")
                binder.note = "in"
            elif self.at("OP", "\\subseteq"):
                self.advance()
                binder.add(self.parse_expr(51), "domain")
                binder.note = "subseteq"
            binders.append(self.finish(binder, t0))
            if self.at("PUNCT", ",") and self.peek(1).kind == "NAME":
                self.advance()
                continue
            break
        return binders

    def eat_subscript(self) -> N | None:
        """Consume ``_v`` after ``[A]`` or ``<<A>>``.

        The lexer keeps ``_vars`` as one identifier, so both spellings are
        accepted; the leading underscore is stripped from the recorded name.
        """
        if self.eat("PUNCT", "_"):
            return self.parse_postfix(self.parse_expr(150))
        if self.at("NAME") and self.peek().text.startswith("_"):
            tok = self.advance()
            return N(kind="name", text=tok.text[1:], line=tok.line, col=tok.col)
        return None

    def parse_bracket(self) -> N:
        line, col, t0 = self.here()
        form = self.classify_bracket()
        if form == "stutter":
            self.expect("PUNCT", "[")
            action = self.parse_expr()
            self.expect("PUNCT", "]")
            node = N(kind="stutter", text="[]", line=line, col=col)
            node.add(action, "action")
            sub = self.eat_subscript()
            node.add(sub if sub is not None else self.unknown("stutter-subscript"), "subscript")
            return self.finish(node, t0)
        self.expect("PUNCT", "[")
        if form == "funcset":
            node = N(kind="funcset", line=line, col=col)
            node.add(self.parse_expr(), "domain")
            self.expect("PUNCT", "->")
            node.add(self.parse_expr(), "codomain")
            self.expect("PUNCT", "]")
            return self.finish(node, t0)
        if form == "recordset":
            node = N(kind="recordset", line=line, col=col)
            while True:
                field_tok = self.peek()
                if field_tok.kind == "NAME":
                    self.advance()
                    field_node = N(kind="recordfield", text=field_tok.text,
                                   line=field_tok.line, col=field_tok.col)
                else:
                    field_node = N(kind="recordfield", text="?", line=line, col=col)
                    field_node.add(self.unknown("recordset-field"), "name")
                self.expect("PUNCT", ":")
                field_node.add(self.parse_expr(), "value")
                node.add(field_node, "field")
                if not self.eat("PUNCT", ","):
                    break
            self.expect("PUNCT", "]")
            return self.finish(node, t0)
        if form == "record":
            node = N(kind="record", line=line, col=col)
            while True:
                field_tok = self.peek()
                if field_tok.kind == "NAME":
                    self.advance()
                    field_node = N(kind="recordfield", text=field_tok.text,
                                   line=field_tok.line, col=field_tok.col)
                else:
                    field_node = N(kind="recordfield", text="?", line=line, col=col)
                    field_node.add(self.unknown("record-field"), "name")
                self.expect("PUNCT", "|->")
                field_node.add(self.parse_expr(), "value")
                node.add(field_node, "field")
                if not self.eat("PUNCT", ","):
                    break
            self.expect("PUNCT", "]")
            return self.finish(node, t0)
        if form == "funcc":
            node = N(kind="funcc", line=line, col=col)
            for binder in self.parse_binders():
                node.add(binder, "binder")
            if not self.eat("PUNCT", "|_"):
                self.expect("PUNCT", "|->")
            node.add(self.parse_expr(), "body")
            self.expect("PUNCT", "]")
            return self.finish(node, t0)
        if form == "except":
            node = N(kind="except", line=line, col=col)
            node.add(self.parse_expr(), "target")
            self.expect("KEY", "EXCEPT")
            while True:
                arm_line, arm_col, arm_t0 = self.here()
                arm = N(kind="exceptarm", line=arm_line, col=arm_col)
                self.expect("PUNCT", "!")
                while True:
                    if self.at("PUNCT", "["):
                        self.advance()
                        while True:
                            arm.add(self.parse_expr(), "index")
                            if not self.eat("PUNCT", ","):
                                break
                        self.expect("PUNCT", "]")
                    elif self.at("OP", "."):
                        self.advance()
                        if self.at("NAME"):
                            field = self.advance()
                            arm.add(N(kind="name", text=field.text, line=field.line,
                                      col=field.col), "field")
                    else:
                        break
                if self.eat("PUNCT", "=") or self.eat("OP", "="):
                    arm.add(self.parse_expr(), "value")
                node.add(self.finish(arm, arm_t0), "arm")
                if not self.eat("PUNCT", ","):
                    break
            self.expect("PUNCT", "]")
            return self.finish(node, t0)
        node = N(kind="paren", line=line, col=col)
        inner = self.parse_expr()
        node.add(inner, "body")
        self.expect("PUNCT", "]")
        node.note = "bracketed-expression"
        return self.finish(node, t0)

    def parse_lambda(self) -> N:
        line, col, t0 = self.here()
        self.expect("KEY", "LAMBDA")
        node = N(kind="lambda", text="LAMBDA", line=line, col=col)
        while self.at("NAME") or self.at("PUNCT", "_"):
            param = self.advance()
            node.add(N(kind="name", text=param.text, line=param.line, col=param.col), "param")
            if not self.eat("PUNCT", ","):
                break
        self.expect("PUNCT", ":")
        node.add(self.parse_expr(), "body")
        return self.finish(node, t0)

    def parse_quantifier(self) -> N:
        line, col, t0 = self.here()
        tok = self.advance()
        kind = {"\\A": "\\A", "\\E": "\\E", "\u2200": "\\A", "\u2203": "\\E"}[tok.text]
        node = N(kind="quant", text=kind, line=line, col=col)
        for binder in self.parse_binders():
            node.add(binder, "binder")
        self.expect("PUNCT", ":")
        node.add(self.parse_expr(), "body")
        return self.finish(node, t0)

    def parse_choose(self) -> N:
        line, col, t0 = self.here()
        self.expect("KEY", "CHOOSE")
        node = N(kind="choose", text="CHOOSE", line=line, col=col)
        nxt = self.peek()
        binder_like = (nxt.kind == "NAME" and self.peek(1).kind == "OP"
                       and self.peek(1).text in ("\\in", "\\subseteq"))
        tuple_like = nxt.kind == "PUNCT" and nxt.text == "<<"
        if binder_like or tuple_like:
            for binder in self.parse_binders():
                node.add(binder, "binder")
            self.expect("PUNCT", ":")
            node.add(self.parse_expr(), "body")
            node.note = "bounded"
        elif nxt.kind == "NAME" and self.peek(1).kind == "PUNCT" and self.peek(1).text == ":":
            for binder in self.parse_binders():
                node.add(binder, "binder")
            self.expect("PUNCT", ":")
            node.add(self.parse_expr(), "body")
            node.note = "unbounded"
        else:
            node.add(self.parse_expr(), "body")
            node.note = "expression-form"
        return self.finish(node, t0)

    def parse_if(self) -> N:
        line, col, t0 = self.here()
        self.expect("KEY", "IF")
        node = N(kind="if", line=line, col=col)
        node.add(self.parse_expr(), "cond")
        self.expect("KEY", "THEN")
        node.add(self.parse_expr(), "then")
        self.expect("KEY", "ELSE")
        node.add(self.parse_expr(), "else")
        return self.finish(node, t0)

    def parse_case(self) -> N:
        line, col, t0 = self.here()
        self.expect("KEY", "CASE")
        node = N(kind="case", line=line, col=col)
        while True:
            if self.at("KEY", "OTHER"):
                self.advance()
                self.expect("PUNCT", "->")
                node.add(self.parse_expr(), "other")
                break
            arm_line, arm_col, arm_t0 = self.here()
            arm = N(kind="casearm", line=arm_line, col=arm_col)
            arm.add(self.parse_expr(), "cond")
            self.expect("PUNCT", "->")
            arm.add(self.parse_expr(), "body")
            node.add(self.finish(arm, arm_t0), "arm")
            if self.at("OP", "[]"):
                self.advance()
                continue
            break
        return self.finish(node, t0)

    def parse_let(self) -> N:
        line, col, t0 = self.here()
        self.expect("KEY", "LET")
        node = N(kind="let", line=line, col=col)
        guard = 0
        while not self.at("KEY", "IN") and self.peek().kind != "EOF":
            before = self.pos
            if self.at("KEY", "INSTANCE"):
                node.add(self.parse_instance(""), "def")
            elif self.at_def_start():
                node.add(self.parse_definition(), "def")
            else:
                node.add(self.unknown("let-item"), "def")
            if self.pos == before:
                break
            guard += 1
            if guard > 500:
                break
        self.expect("KEY", "IN")
        node.add(self.parse_expr(), "body")
        return self.finish(node, t0)

    def parse_fairness(self) -> N:
        line, col, t0 = self.here()
        tok = self.advance()
        if tok.text in ("WF", "SF"):
            op = tok.text
            self.expect("PUNCT", "_")
            subscript = self.parse_postfix(self.parse_expr(150))
        else:
            op, _, sub = tok.text.partition("_")
            subscript = N(kind="name", text=sub, line=line, col=col)
        node = N(kind="fair", text=op, line=line, col=col)
        node.add(subscript, "subscript")
        if self.at("PUNCT", "("):
            self.advance()
            node.add(self.parse_expr(), "action")
            self.expect("PUNCT", ")")
        else:
            node.add(self.unknown("fairness-action"), "action")
        return self.finish(node, t0)


def parse_source(source: str, name: str = "<string>") -> tuple[N, LexResult, dict]:
    """Parse one TLA+ file.  Returns ``(ast, lex_result, stats)``."""
    lex = tokenize(source)
    parser = Parser(lex.tokens)
    ast = parser.parse_file()
    stats = {
        "file": name,
        "module": lex.module_name,
        "bad_tokens": len(lex.bad_tokens),
        "unknown_nodes": len(parser.unknowns),
        "proof_tokens_skipped": parser.proof_tokens_skipped,
        "parser_notes": len(parser.notes),
        "note_samples": parser.notes[:5],
        "trailing_tokens_ignored": parser.trailing_tokens,
        "preamble_tokens_ignored": parser.preamble_tokens,
    }
    # The trailing EOF sentinel is not part of the source, so it is excluded
    # from the coverage denominator.
    total = max(0, len(lex.tokens) - 1)
    stats.update({f"cov_{k}": v for k, v in coverage(ast, total).items()})
    return ast, lex, stats


def parse_file(path: Path | str) -> tuple[N, LexResult, dict]:
    path = Path(path)
    source = path.read_text(encoding="utf-8", errors="replace")
    return parse_source(source, name=str(path))
