try:
    from .ingest import ingest_table, ingest_by_coverage
except ModuleNotFoundError as exc:
    _INGEST_IMPORT_ERROR = exc

    def ingest_table(*args, **kwargs):
        raise ModuleNotFoundError('SIDRA ingestion requires optional runtime dependencies') from _INGEST_IMPORT_ERROR

    def ingest_by_coverage(*args, **kwargs):
        raise ModuleNotFoundError('SIDRA ingestion requires optional runtime dependencies') from _INGEST_IMPORT_ERROR

from .search import search_tables

__all__ = ["ingest_table", "ingest_by_coverage", "search_tables"]
