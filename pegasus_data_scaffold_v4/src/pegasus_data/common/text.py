from __future__ import annotations

import re
import unicodedata

_WS = re.compile(r"\s+")
_PUNCT = re.compile(r"[^\w\s-]", re.UNICODE)


def normalize_basic(text: str | None) -> str:
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower().replace(" ", " ")
    text = _WS.sub(" ", text).strip()
    text = _PUNCT.sub(" ", text)
    text = _WS.sub(" ", text).strip()
    text = re.sub(r"\s*-\s*", "-", text)
    text = _WS.sub(" ", text).strip()
    return text
