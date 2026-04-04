SOURCE_REGISTRY = {
    'SINASC': {
        'source_family': 'datasus',
        'support_role': 'birth_occurrence',
        'event_type': 'birth',
        'dataset': 'DN',
        'code_roles': ['anomaly'],
    },
    'SIM': {
        'source_family': 'datasus',
        'support_role': 'death_occurrence',
        'event_type': 'death',
        'dataset': 'DO',
        'code_roles': ['cause_of_death', 'associated_cause'],
    },
    'SINAN': {
        'source_family': 'datasus',
        'support_role': 'notification_residence',
        'event_type': 'notification',
        'dataset': 'NOTIFIC',
        'code_roles': ['condition'],
    },
    'SIH': {
        'source_family': 'datasus',
        'support_role': 'hospitalization_occurrence',
        'event_type': 'hospitalization',
        'dataset': 'AIH',
        'code_roles': ['diagnosis', 'secondary_diagnosis', 'procedure'],
    },
    'SIDRA': {
        'source_family': 'sidra',
        'support_role': 'aggregate_context',
        'event_type': 'aggregate_context',
        'dataset': None,
        'code_roles': [],
    },
}
