"""
Minimal source registry placeholders.

The active DATASUS workflow is intentionally black-box first: scan, organize,
profile, and translate before asserting source-specific semantics. These
entries therefore stay generic until accepted translation/mapping artifacts
justify stronger canonical commitments.
"""

SOURCE_REGISTRY = {
    'DATASUS_GENERIC': {
        'source_family': 'datasus',
        'support_role': None,
        'event_type': None,
        'dataset': None,
        'code_roles': [],
        'mapping_status': 'translation_driven',
    },
    'SIDRA': {
        'source_family': 'sidra',
        'support_role': 'aggregate_context',
        'event_type': 'aggregate_context',
        'dataset': None,
        'code_roles': [],
        'mapping_status': 'stable',
    },
}
