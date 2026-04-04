from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterator


@dataclass(frozen=True)
class _Tok:
    kind: str
    value: str
    pos: int


def _tokens(text: str) -> Iterator[_Tok]:
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch.isspace():
            i += 1
            continue
        if ch in "()":
            yield _Tok("LP" if ch == "(" else "RP", ch, i)
            i += 1
            continue
        if ch == "~":
            yield _Tok("TILDE", ch, i)
            i += 1
            continue
        if i + 1 < n and text[i:i+2] in {">=", "<=", "==", "!="}:
            yield _Tok("OP", text[i:i+2], i)
            i += 2
            continue
        if ch in "<>=":
            yield _Tok("OP", ch, i)
            i += 1
            continue
        if ch == '"':
            start = i
            i += 1
            buf: list[str] = []
            while i < n and text[i] != '"':
                if text[i] == "\\" and i + 1 < n:
                    i += 1
                buf.append(text[i])
                i += 1
            if i >= n:
                raise SyntaxError(f"Unterminated string starting at {start}")
            i += 1
            yield _Tok("STR", "".join(buf), start)
            continue
        if ch.isalpha() or ch == "_":
            start = i
            i += 1
            while i < n and (text[i].isalnum() or text[i] == "_"):
                i += 1
            word = text[start:i].upper()
            if word in {"AND", "OR", "NOT"}:
                yield _Tok(word, word, start)
            else:
                yield _Tok("ID", word, start)
            continue
        if ch.isdigit():
            start = i
            i += 1
            while i < n and text[i].isdigit():
                i += 1
            yield _Tok("NUM", text[start:i], start)
            continue
        raise SyntaxError(f"Unexpected {ch!r} at {i}")
    yield _Tok("EOF", "", n)


@dataclass(frozen=True)
class _Cmp:
    op: str
    ident: str
    number: int


@dataclass(frozen=True)
class _Contains:
    field: str
    text: str


@dataclass(frozen=True)
class _Not:
    node: Any


@dataclass(frozen=True)
class _And:
    left: Any
    right: Any


@dataclass(frozen=True)
class _Or:
    left: Any
    right: Any


WhereNode = Any


class _Parser:
    def __init__(self, text: str) -> None:
        self._it = iter(_tokens(text))
        self.cur = next(self._it)

    def _eat(self, kind: str) -> _Tok:
        if self.cur.kind != kind:
            raise SyntaxError(f"Expected {kind}, got {self.cur.kind} at {self.cur.pos}")
        tok = self.cur
        if kind != "EOF":
            self.cur = next(self._it)
        return tok

    def parse(self) -> WhereNode:
        node = self._expr()
        self._eat("EOF")
        return node

    def _expr(self) -> WhereNode:
        node = self._and()
        while self.cur.kind == "OR":
            self._eat("OR")
            node = _Or(node, self._and())
        return node

    def _and(self) -> WhereNode:
        node = self._unary()
        while self.cur.kind == "AND":
            self._eat("AND")
            node = _And(node, self._unary())
        return node

    def _unary(self) -> WhereNode:
        if self.cur.kind == "NOT":
            self._eat("NOT")
            return _Not(self._unary())
        return self._primary()

    def _primary(self) -> WhereNode:
        if self.cur.kind == "LP":
            self._eat("LP")
            node = self._expr()
            self._eat("RP")
            return node
        return self._atom()

    def _atom(self) -> WhereNode:
        ident = self._eat("ID").value
        if self.cur.kind == "TILDE":
            self._eat("TILDE")
            text = self._eat("STR").value
            return _Contains(field=ident, text=text)
        if self.cur.kind != "OP":
            return _Cmp(op=">=", ident=ident, number=1)
        op = self._eat("OP").value
        if op == "=":
            op = "=="
        number = int(self._eat("NUM").value)
        return _Cmp(op=op, ident=ident, number=number)


def parse_where_expr(text: str) -> WhereNode:
    return _Parser(text).parse()
