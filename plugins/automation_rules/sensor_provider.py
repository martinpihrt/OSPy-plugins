"""Read-only ospy.provider.v1 adapter for built-in OSPy sensors."""

import math

from ospy.options import options
from ospy.provider_contracts import utc_timestamp
from ospy.sensors import sensors


PROVIDER_ID = 'ospy_sensors'


def provider_capabilities():
    return {
        'contract': 'ospy.provider.v1',
        'provider_id': PROVIDER_ID,
        'resource_types': ['ospy_sensor'],
        'values': [], 'events': [], 'alerts': [], 'actions': [],
    }


def _nested(source, *indexes):
    value = source
    try:
        for index in indexes:
            value = value[index]
        return value
    except (IndexError, KeyError, TypeError):
        return None


def _number(value):
    if isinstance(value, bool) or value in (None, '', -127, -127.0):
        return None
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError, OverflowError):
        return None


def _value(identifier, quantity, value, unit='', value_type='number',
           quality='measured', observed_at=None):
    if value_type == 'boolean':
        value = None if value in (None, '', -127, -127.0) else bool(value)
    else:
        value = _number(value)
    return {
        'id': identifier, 'quantity': quantity, 'value': value,
        'unit': unit, 'value_type': value_type, 'quality': quality,
        'observed_at': observed_at,
    }


def _pihrt_values(sensor, observed_at):
    values = getattr(sensor, 'last_read_value', [])
    sensor_type = getattr(sensor, 'sens_type', 0)
    multi_type = getattr(sensor, 'multi_type', 0)
    temperature_unit = str(getattr(options, 'temp_unit', 'C'))
    if sensor_type == 1:
        return [_value('contact_state', 'state', _nested(values, 4), '',
                       'number', observed_at=observed_at)]
    if sensor_type == 2:
        return [_value('flow_lps', 'volume_flow_rate', _nested(values, 5),
                       'L/s', observed_at=observed_at)]
    if sensor_type == 3:
        return [_value('moisture_percent', 'relative_humidity',
                       _nested(values, 6), '%', observed_at=observed_at)]
    if sensor_type == 4:
        return [_value('motion', 'state', _nested(values, 7), '', 'boolean',
                       observed_at=observed_at)]
    if sensor_type == 5:
        return [_value('temperature', 'temperature', _nested(values, 0),
                       temperature_unit, observed_at=observed_at)]
    if sensor_type == 7:
        return [
            _value('contact_{}'.format(index + 1), 'state',
                   _nested(values, index), '', 'number',
                   observed_at=observed_at)
            for index in range(7)
        ]
    if sensor_type != 6:
        return []
    if 0 <= multi_type <= 3:
        return [_value('temperature', 'temperature',
                       _nested(values, multi_type), temperature_unit,
                       observed_at=observed_at)]
    if multi_type == 4:
        return [_value('contact_state', 'state', _nested(values, 4), '',
                       'number', observed_at=observed_at)]
    if multi_type == 5:
        return [_value('flow_lps', 'volume_flow_rate', _nested(values, 5),
                       'L/s', observed_at=observed_at)]
    if multi_type == 6:
        return [_value('moisture_percent', 'relative_humidity',
                       _nested(values, 6), '%', observed_at=observed_at)]
    if multi_type == 7:
        return [_value('motion', 'state', _nested(values, 7), '', 'boolean',
                       observed_at=observed_at)]
    if multi_type == 8:
        distance = _number(_nested(values, 8))
        top = _number(getattr(sensor, 'distance_top', None))
        bottom = _number(getattr(sensor, 'distance_bottom', None))
        level = None
        fill = None
        volume = None
        volume_unit = 'L' if bool(getattr(sensor, 'check_liters', False)) else 'm3'
        if distance is not None and distance > 0 and top is not None and \
                bottom is not None and bottom > top:
            level = max(0.0, min(bottom - top, bottom - distance))
            fill = max(0.0, min(100.0, level * 100.0 / (bottom - top)))
            diameter = _number(getattr(sensor, 'diameter', None))
            if diameter is not None and diameter > 0:
                volume_cm3 = math.pi * (diameter / 2.0) ** 2 * level
                volume = volume_cm3 * (0.001 if volume_unit == 'L' else 0.000001)
        return [
            _value('sensor_distance_cm', 'length', distance, 'cm',
                   observed_at=observed_at),
            _value('level_cm', 'length', level, 'cm', 'number', 'derived',
                   observed_at),
            _value('fill_percent', 'ratio', fill, '%', 'number', 'derived',
                   observed_at),
            _value('volume', 'volume', volume, volume_unit, 'number', 'derived',
                   observed_at),
        ]
    if multi_type == 9:
        soil = getattr(sensor, 'soil_last_read_value', [])
        return [
            _value('soil_moisture_{}'.format(index + 1), 'relative_humidity',
                   _nested(soil, index), '%', observed_at=observed_at)
            for index in range(16)
        ]
    return []


def _shelly_values(sensor, observed_at):
    sensor_type = getattr(sensor, 'sens_type', -1)
    values = getattr(sensor, 'last_read_value', [])
    if sensor_type == 0:
        return [_value('voltage', 'voltage', getattr(sensor, 'last_voltage', None),
                       'V', observed_at=observed_at)]
    if 1 <= sensor_type <= 4:
        index = sensor_type - 1
        return [_value('output_{}'.format(index + 1), 'state',
                       _nested(values, 0, index), '', 'boolean',
                       observed_at=observed_at)]
    if 5 <= sensor_type <= 9:
        index = sensor_type - 5
        return [_value('temperature_{}'.format(index + 1), 'temperature',
                       _nested(values, 2, index), 'C',
                       observed_at=observed_at)]
    if 10 <= sensor_type <= 13:
        index = sensor_type - 10
        return [_value('power_{}'.format(index + 1), 'power',
                       _nested(values, 1, index), 'W',
                       observed_at=observed_at)]
    if sensor_type == 14:
        return [_value('humidity', 'relative_humidity',
                       _nested(values, 3, 0), '%', observed_at=observed_at)]
    if 15 <= sensor_type <= 17:
        index = sensor_type - 15
        return [_value('pv_power_{}'.format(index + 1), 'power',
                       _nested(values, 4, index), 'W',
                       observed_at=observed_at)]
    if sensor_type == 18:
        return [_value('illuminance', 'illuminance',
                       _nested(values, 5, 0), 'lx', observed_at=observed_at)]
    return []


def _observed_at(sensor):
    value = getattr(sensor, 'last_response', 0)
    try:
        return utc_timestamp(float(value)) if float(value) > 0 else None
    except (TypeError, ValueError, OverflowError):
        return None


def provider_snapshot():
    getter = getattr(sensors, 'get', None)
    configured = list(getter() or []) if callable(getter) else []
    resources = []
    for fallback_index, sensor in enumerate(configured):
        if not bool(getattr(sensor, 'enabled', False)):
            continue
        observed_at = _observed_at(sensor)
        if int(getattr(sensor, 'manufacturer', 0) or 0) == 1:
            values = _shelly_values(sensor, observed_at)
        else:
            values = _pihrt_values(sensor, observed_at)
        index = getattr(sensor, 'index', fallback_index)
        try:
            index = int(index)
        except (TypeError, ValueError):
            index = fallback_index
        connected = bool(getattr(sensor, 'response', False))
        resource_status = 'ok' if connected and any(
            item.get('value') is not None for item in values) else 'unavailable'
        resources.append({
            'id': 'sensor-{}'.format(max(0, index)),
            'type': 'ospy_sensor', 'status': resource_status,
            'name': str(getattr(sensor, 'name', '') or ''),
            'manufacturer': ('shelly' if int(
                getattr(sensor, 'manufacturer', 0) or 0) == 1 else 'pihrt'),
            'values': values, 'alerts': [],
        })
    return {
        'contract': 'ospy.provider.v1', 'provider_id': PROVIDER_ID,
        'status': 'ok', 'observed_at': utc_timestamp(),
        'resources': resources, 'events': [], 'alerts': [],
    }
