"""Read-only provider for current OSPy operating and update states."""

from ospy.inputs import inputs
from ospy.options import options, rain_blocks
from ospy.provider_contracts import utc_timestamp


PROVIDER_ID = 'ospy_system'


def provider_capabilities():
    values = [
        ('scheduler_enabled', 'state', '', 'boolean'),
        ('manual_mode', 'state', '', 'boolean'),
        ('scheduled_mode', 'state', '', 'boolean'),
        ('water_level_percent', 'ratio', '%', 'number'),
        ('rain_delay_seconds', 'duration', 's', 'number'),
        ('rain_sensor_enabled', 'state', '', 'boolean'),
        ('rain_sensor_active', 'state', '', 'boolean'),
        ('ospy_update_available', 'state', '', 'boolean'),
        ('plugin_update_available', 'state', '', 'boolean'),
        ('plugin_update_count', 'count', '', 'integer'),
        ('any_update_available', 'state', '', 'boolean'),
    ]
    return {
        'contract': 'ospy.provider.v1', 'provider_id': PROVIDER_ID,
        'resource_types': ['ospy_system'],
        'values': [{
            'id': identifier, 'quantity': quantity, 'unit': unit,
            'value_type': value_type,
        } for identifier, quantity, unit, value_type in values],
        'events': [], 'alerts': [], 'actions': [],
    }


def _plugin_update_count():
    """Return updates already known by the plug-in checker without refreshing."""
    try:
        import plugins

        repository_info = plugins.checker.cached_available_versions()
        current_info = getattr(options, 'plugin_status', {})
        count = 0
        for plugin in plugins.available():
            available_info = repository_info.get(plugin)
            if not isinstance(available_info, dict):
                continue
            installed = current_info.get(plugin)
            installed_hash = (installed.get('hash')
                              if isinstance(installed, dict) else None)
            if installed_hash != available_info.get('hash'):
                count += 1
        return count
    except Exception:
        return 0


def _ospy_update_available():
    """Read the cached System Update result without starting a new check."""
    try:
        import plugins

        if 'system_update' not in plugins.running():
            return False
        values = plugins.get('system_update').get_all_values()
        return bool(values and values[0] == 2)
    except Exception:
        return False


def _value(identifier, quantity, value, unit, value_type, observed_at):
    return {
        'id': identifier, 'quantity': quantity, 'value': value,
        'unit': unit, 'value_type': value_type, 'quality': 'derived',
        'observed_at': observed_at,
    }


def provider_snapshot():
    observed_at = utc_timestamp()
    manual_mode = bool(getattr(options, 'manual_mode', False))
    plugin_update_count = _plugin_update_count()
    ospy_update_available = _ospy_update_available()
    values = [
        ('scheduler_enabled', 'state',
         bool(getattr(options, 'scheduler_enabled', False)), '', 'boolean'),
        ('manual_mode', 'state', manual_mode, '', 'boolean'),
        ('scheduled_mode', 'state', not manual_mode, '', 'boolean'),
        ('water_level_percent', 'ratio',
         float(getattr(options, 'level_adjustment', 1.0)) * 100.0,
         '%', 'number'),
        ('rain_delay_seconds', 'duration',
         float(rain_blocks.seconds_left()), 's', 'number'),
        ('rain_sensor_enabled', 'state',
         bool(getattr(options, 'rain_sensor_enabled', False)), '', 'boolean'),
        ('rain_sensor_active', 'state', bool(inputs.rain_sensed()), '', 'boolean'),
        ('ospy_update_available', 'state', ospy_update_available, '', 'boolean'),
        ('plugin_update_available', 'state', plugin_update_count > 0, '', 'boolean'),
        ('plugin_update_count', 'count', plugin_update_count, '', 'integer'),
        ('any_update_available', 'state',
         ospy_update_available or plugin_update_count > 0, '', 'boolean'),
    ]
    return {
        'contract': 'ospy.provider.v1', 'provider_id': PROVIDER_ID,
        'status': 'ok', 'observed_at': observed_at,
        'resources': [{
            'id': 'system', 'type': 'ospy_system', 'status': 'ok',
            'values': [
                _value(identifier, quantity, value, unit, value_type, observed_at)
                for identifier, quantity, value, unit, value_type in values
            ],
            'alerts': [],
        }],
        'events': [], 'alerts': [],
    }
