from __future__ import annotations

import datetime as dt
import re
from pathlib import PurePosixPath
from typing import Any

STRUCTURED_DATA_EXTENSIONS = {".dbc", ".dbf", ".xml", ".csv", ".json", ".parquet"}
WRAPPER_EXTENSIONS = {".zip", ".gz"}
DATA_EXTENSIONS = STRUCTURED_DATA_EXTENSIONS | WRAPPER_EXTENSIONS
PDF_KEYWORDS = {"manual", "dicionario", "leia-me", "layout", "estrutura", "dic_dados", "instrucoes"}
AUXILIARY_PATH_KEYWORDS = {"TABELAS", "DOCS", "DOCUMENTOS", "TABWIN", "DOC", "AUXILIAR", "AUXILIARES"}
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
    return str(p.parent), p.name, infer_extension_chain(path)


def suffix_chain(path: str) -> list[str]:
    return [suffix.lower() for suffix in PurePosixPath(path).suffixes]


def infer_extension_chain(path: str) -> str:
    suffixes = suffix_chain(path)
    return ''.join(suffixes) if suffixes else ''


def strip_all_suffixes(name: str) -> str:
    pure = PurePosixPath(name)
    base = pure.name
    for suffix in reversed(pure.suffixes):
        if base.lower().endswith(suffix.lower()):
            base = base[: -len(suffix)]
    return base


def infer_primary_extension(path: str) -> str | None:
    suffixes = suffix_chain(path)
    for suffix in reversed(suffixes):
        if suffix in STRUCTURED_DATA_EXTENSIONS:
            return suffix
    upper_path = path.upper()
    if '/JSON/' in upper_path:
        return '.json'
    if '/XML/' in upper_path:
        return '.xml'
    if '/CSV/' in upper_path:
        return '.csv'
    if '/PARQUET/' in upper_path:
        return '.parquet'
    if suffixes:
        return suffixes[-1]
    return None


def infer_format_family(path: str) -> str:
    primary = infer_primary_extension(path)
    if primary in {'.dbf', '.dbc'}:
        return 'dbase'
    if primary == '.json':
        return 'json'
    if primary == '.xml':
        return 'xml'
    if primary == '.csv':
        return 'csv'
    if primary == '.parquet':
        return 'parquet'
    if any(suffix in WRAPPER_EXTENSIONS for suffix in suffix_chain(path)):
        return 'archive'
    return 'unknown'


def is_probably_structured_data(path: str) -> bool:
    primary = infer_primary_extension(path)
    return primary in STRUCTURED_DATA_EXTENSIONS or infer_format_family(path) == 'archive'


def infer_inner_candidate_name(path: str) -> str:
    return strip_all_suffixes(PurePosixPath(path).name)


def infer_pattern_components(path: str) -> dict[str, Any]:
    filename = PurePosixPath(path).name
    stem = infer_inner_candidate_name(filename)
    extension = infer_extension_chain(path)
    primary_extension = infer_primary_extension(path)
    format_family = infer_format_family(path)
    pattern_name = None
    series_prefix = None
    geo_code = None
    date_code = None
    for candidate_name, pattern in PATTERNS.items():
        match = pattern.match(stem)
        if match:
            pattern_name = candidate_name
            series_prefix = match.group(1).upper()
            geo_code = match.group(2).upper()
            date_code = match.group(3)
            break
    return {
        'filename': filename,
        'stem': stem,
        'extension': extension,
        'primary_extension': primary_extension,
        'format_family': format_family,
        'pattern_name': pattern_name,
        'series_prefix': series_prefix,
        'geo_code': geo_code,
        'date_code': date_code,
    }


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
        if not 1 <= month <= 12:
            return 0
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
