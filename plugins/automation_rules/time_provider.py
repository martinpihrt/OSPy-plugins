"""Read-only provider for the current local OSPy date and time."""

import datetime

from ospy.provider_contracts import utc_timestamp


PROVIDER_ID = 'ospy_datetime'


def provider_capabilities():
    return {
        'contract': 'ospy.provider.v1', 'provider_id': PROVIDER_ID,
        'resource_types': ['local_datetime'], 'values': [],
        'events': [], 'alerts': [], 'actions': [],
    }


def provider_snapshot(now=None):
    now = now or datetime.datetime.now()
    observed_at = utc_timestamp()
    values = [
        ('current_date', 'date', now.strftime('%Y-%m-%d'), 'string'),
        ('current_time', 'time', now.strftime('%H:%M'), 'string'),
        ('weekday', 'weekday', now.isoweekday(), 'integer'),
        ('month', 'month', now.month, 'integer'),
        ('day_of_month', 'day', now.day, 'integer'),
    ]
    return {
        'contract': 'ospy.provider.v1', 'provider_id': PROVIDER_ID,
        'status': 'ok', 'observed_at': observed_at,
        'resources': [{
            'id': 'local', 'type': 'local_datetime', 'status': 'ok',
            'values': [{
                'id': identifier, 'quantity': quantity, 'value': value,
                'unit': '', 'value_type': value_type, 'quality': 'derived',
                'observed_at': observed_at,
            } for identifier, quantity, value, value_type in values],
            'alerts': [],
        }],
        'events': [], 'alerts': [],
    }
