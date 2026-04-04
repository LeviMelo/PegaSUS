from __future__ import annotations

from ...pegasus.canonical.schema import CanonicalRecord
from .normalize import SidraValueRow


def sidra_row_to_canonical(row: SidraValueRow) -> CanonicalRecord:
    year = None
    month = None
    if row.period_id and row.period_id.isdigit():
        if len(row.period_id) >= 4:
            year = int(row.period_id[:4])
        if len(row.period_id) >= 6:
            month = int(row.period_id[4:6])
    return CanonicalRecord(
        support={
            'municipality': row.locality_id if row.locality_id and len(row.locality_id) == 7 else None,
            'year': year,
            'month': month,
            'date': None,
        },
        support_role='aggregate_context',
        source={'system': 'SIDRA', 'dataset': str(row.aggregate_id), 'file': None},
        event_type='aggregate_context',
        code_roles={},
        subgroups={},
        continuous={'value': row.value},
        annotations={'dimensions': row.dimensions},
        weight=1.0,
        quality={'included': row.value is not None, 'flags': []},
        provenance={'aggregate_id': row.aggregate_id, 'variable_id': row.variable_id},
    )
