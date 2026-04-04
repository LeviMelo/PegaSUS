from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable


_CODE_CLEAN = re.compile(r"[^A-Z0-9]")


@dataclass(frozen=True)
class CodeQuery:
    role: str
    system: str
    node: str
    descendants: bool = True


def normalize_code(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = _CODE_CLEAN.sub("", value.upper())
    return cleaned or None


def normalize_codes(values: Iterable[str | None]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        code = normalize_code(value)
        if code and code not in seen:
            out.append(code)
            seen.add(code)
    return out


def code_matches_query(code: str | None, query: CodeQuery) -> bool:
    norm_code = normalize_code(code)
    if not norm_code:
        return False
    node = normalize_code(query.node)
    if not node:
        return False
    if not query.descendants:
        return norm_code == node
    if "-" in query.node:
        left, right = [normalize_code(part) for part in query.node.split("-", 1)]
        if not left or not right:
            return False
        return left <= norm_code[:len(left)] <= right
    return norm_code.startswith(node)


def any_code_matches(codes: Iterable[str | None], query: CodeQuery) -> bool:
    return any(code_matches_query(code, query) for code in codes)
