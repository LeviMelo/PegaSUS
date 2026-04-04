from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any


@dataclass(frozen=True)
class SupportPoint:
    municipality: str | None
    year: int | None
    month: int | None
    day: str | None


def normalize_municipality_code(value: Any) -> str | None:
    if value in (None, ""):
        return None
    digits = "".join(ch for ch in str(value).strip() if ch.isdigit())
    if len(digits) == 6:
        return digits + "0"
    if len(digits) == 7:
        return digits
    return None


def parse_datasus_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%Y%m%d", "%d%m%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def support_from_date_and_municipality(*, municipality: Any, date_value: Any) -> SupportPoint:
    dt = parse_datasus_date(date_value)
    return SupportPoint(
        municipality=normalize_municipality_code(municipality),
        year=dt.year if dt else None,
        month=dt.month if dt else None,
        day=dt.isoformat() if dt else None,
    )
