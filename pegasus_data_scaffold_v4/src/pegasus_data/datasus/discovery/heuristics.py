from __future__ import annotations

import datetime as dt
import re
from pathlib import PurePosixPath

DATA_EXTENSIONS = {".dbc", ".dbf", ".xml", ".csv", ".zip", ".gz"}
PDF_KEYWORDS = {"manual", "dicionario", "leia-me", "layout", "estrutura", "dic_dados", "instrucoes"}
AUXILIARY_PATH_KEYWORDS = {"TABELAS", "DOCS", "DOCUMENTOS", "TABWIN", "DOC"}
EXCLUSION_PATH_KEYWORDS = {"/IBGE/"}
STAGING_PATH_KEYWORDS = {"PRELIM", "HOMOL"}
UF_CODES = {
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS",
    "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO"
}
PATTERNS: dict[str, re.Pattern[str]] = {
    "PREFIX_GEO_YYMM": re.compile(r"^([A-Z_]{2,})((?:[A-Z]{2})|(?:BR))(\d{4})$", re.IGNORECASE),
    "PREFIX_GEO_YY": re.compile(r"^([A-Z_]{2,})((?:[A-Z]{2})|(?:BR))(\d{2})$", re.IGNORECASE),
    "PREFIX_GEO_DATE": re.compile(r"^([A-Z_]{2,})((?:[A-Z]{2})|(?:BR))(\d{2,8})$", re.IGNORECASE),
}
MIN_FILES_FOR_PATTERN_VALIDATION = 5
MIN_UF_COUNT_FOR_STATE_VALIDATION = 20
PDF_RELEVANCE_THRESHOLD = 60.0
WEIGHT_PROXIMITY = 0.35
WEIGHT_FUZZY_NAME = 0.25
WEIGHT_FUZZY_PATH = 0.40
KEYWORD_BONUS = 25


def is_excluded_path(path: str) -> bool:
    upper = path.upper()
    return any(token in upper for token in EXCLUSION_PATH_KEYWORDS)


def classify_path_type(path: str) -> str:
    upper = path.upper()
    return "Auxiliary" if any(token in upper for token in AUXILIARY_PATH_KEYWORDS) else "Primary"


def split_path(path: str) -> tuple[str, str, str]:
    p = PurePosixPath(path)
    return str(p.parent), p.name, p.suffix.lower()


def infer_system_guess(directory: str) -> str | None:
    parts = [part for part in directory.split("/") if part]
    if len(parts) >= 3:
        return parts[2]
    return None


def infer_date_format(date_codes: list[str]) -> str:
    four = [value for value in date_codes if len(value) == 4]
    if not four:
        return "YY"
    try:
        valid_month_share = sum(1 <= int(value[2:]) <= 12 for value in four) / len(four)
        if valid_month_share > 0.8:
            return "YYMM"
        if all(19 <= int(value[:2]) <= 20 for value in four):
            return "YYYY"
    except Exception:
        return "YY"
    return "YY"


def normalize_datecode(date_code: str, date_format: str) -> int:
    number = int(date_code)
    if date_format == "YY":
        year = 2000 + number if number < 70 else 1900 + number
        return year * 100
    if date_format == "YYMM":
        year, month = divmod(number, 100)
        year = 2000 + year if year < 70 else 1900 + year
        return year * 100 + month
    if date_format == "YYYY":
        return number * 100
    return 0


def format_normalized_date(value: int) -> str:
    year, month = divmod(value, 100)
    if month == 0:
        return str(year)
    return dt.date(year, month, 1).strftime("%b %Y")


def classify_partition(unique_geo_codes: set[str]) -> str:
    is_state_partitioned = len(unique_geo_codes.intersection(UF_CODES)) >= MIN_UF_COUNT_FOR_STATE_VALIDATION
    is_nationwide = "BR" in unique_geo_codes
    if is_state_partitioned and is_nationwide:
        return "Mixed-Partition"
    if is_state_partitioned:
        return "State-Partitioned"
    if is_nationwide:
        return "Nation-Wide"
    return "Unknown"


def classify_path_semantic(path: str, *, global_max_date: int, path_max_date: int, date_format: str) -> str:
    upper = path.upper()
    if any(token in upper for token in STAGING_PATH_KEYWORDS):
        return "[Staging]"
    if (date_format == "YYMM" and global_max_date - path_max_date > 500) or (date_format == "YY" and global_max_date - path_max_date > 5):
        return "[Legacy Archive]"
    return "[Primary]"
