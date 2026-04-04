from .normalize import SidraValueRow, normalize_value_payload
from .canonical import sidra_row_to_canonical

try:
    from .loader import fetch_values_sharded, fetch_and_normalize_values_sharded
except ModuleNotFoundError as exc:
    _LOADER_IMPORT_ERROR = exc

    def fetch_values_sharded(*args, **kwargs):
        raise ModuleNotFoundError('SIDRA network loading requires optional runtime dependencies') from _LOADER_IMPORT_ERROR

    def fetch_and_normalize_values_sharded(*args, **kwargs):
        raise ModuleNotFoundError('SIDRA network loading requires optional runtime dependencies') from _LOADER_IMPORT_ERROR

__all__ = [
    'fetch_values_sharded',
    'fetch_and_normalize_values_sharded',
    'SidraValueRow',
    'normalize_value_payload',
    'sidra_row_to_canonical',
]
