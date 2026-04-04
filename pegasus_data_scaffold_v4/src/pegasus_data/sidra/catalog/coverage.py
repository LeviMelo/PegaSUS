from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class _Cmp:
    op: str
    ident: str
    number: int


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


class _Parser:
    def __init__(self, text: str) -> None:
        self.tokens = self._tokenize(text)
        self.index = 0

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        spaced = text.replace("(", " ( ").replace(")", " ) ")
        return [token for token in spaced.split() if token]

    def _peek(self) -> str:
        return self.tokens[self.index] if self.index < len(self.tokens) else "EOF"

    def _eat(self, value: str | None = None) -> str:
        token = self._peek()
        if value is not None and token != value:
            raise SyntaxError(f"Expected {value}, got {token}")
        self.index += 1
        return token

    def parse(self) -> Any:
        node = self._expr()
        if self._peek() != "EOF":
            raise SyntaxError(f"Unexpected token {self._peek()}")
        return node

    def _expr(self) -> Any:
        node = self._and()
        while self._peek().upper() == "OR":
            self._eat()
            node = _Or(node, self._and())
        return node

    def _and(self) -> Any:
        node = self._unary()
        while self._peek().upper() == "AND":
            self._eat()
            node = _And(node, self._unary())
        return node

    def _unary(self) -> Any:
        if self._peek().upper() == "NOT":
            self._eat()
            return _Not(self._unary())
        return self._primary()

    def _primary(self) -> Any:
        if self._peek() == "(":
            self._eat("(")
            node = self._expr()
            self._eat(")")
            return node
        return self._cmp()

    def _cmp(self) -> Any:
        ident = self._eat().upper()
        token = self._peek()
        if token == "EOF" or token in {"AND", "OR", ")"}:
            return _Cmp(">=", ident, 1)
        op = self._eat()
        number = int(self._eat())
        if op == "=":
            op = "=="
        return _Cmp(op, ident, number)


def parse_coverage_expr(text: str) -> Any:
    return _Parser(text).parse()


def extract_levels(node: Any) -> set[str]:
    levels: set[str] = set()
    def walk(cur: Any) -> None:
        if isinstance(cur, _Cmp):
            levels.add(cur.ident)
        elif isinstance(cur, _Not):
            walk(cur.node)
        elif isinstance(cur, (_And, _Or)):
            walk(cur.left)
            walk(cur.right)
    walk(node)
    return levels


def eval_coverage(node: Any, counts: dict[str, int]) -> bool:
    def cmp(op: str, left: int, right: int) -> bool:
        return {">=": left >= right, ">": left > right, "<=": left <= right, "<": left < right, "==": left == right, "!=": left != right}[op]
    def walk(cur: Any) -> bool:
        if isinstance(cur, _Cmp):
            return cmp(cur.op, int(counts.get(cur.ident, 0)), cur.number)
        if isinstance(cur, _Not):
            return not walk(cur.node)
        if isinstance(cur, _And):
            return walk(cur.left) and walk(cur.right)
        if isinstance(cur, _Or):
            return walk(cur.left) or walk(cur.right)
        raise TypeError(cur)
    return walk(node)
