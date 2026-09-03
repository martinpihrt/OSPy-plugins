# -*- coding: utf-8 -*-
"""Pure configuration and scheduling helpers for the Thermostat plug-in."""

import re


MAX_THERMOSTATS = 20
INVALID_TEMPERATURE = -127
MIN_CHECK_INTERVAL = 5
MAX_CHECK_INTERVAL = 3600
SHELLY_VALUE_TYPES = (
    'temperature',
    'temperature_2',
    'temperature_3',
    'temperature_4',
    'temperature_5',
)
SOURCES = ('air_temp', 'ospy_sensor', 'shelly_cloud')
ACTIONS = ('none', 'start', 'stop')
TIME_PATTERN = re.compile(r'^(?:[01]\d|2[0-3]):[0-5]\d$')


def safe_int(value, default=0):
    try:
        return int(value)
    except Exception:
        return default


def safe_float(value, default=0.0):
    try:
        return float(str(value).replace(',', '.'))
    except Exception:
        return default


def clamp(value, minimum, maximum):
    return max(minimum, min(maximum, value))


def default_zone(name='Thermostat'):
    return {
        'id': '',
        'enabled': False,
        'name': name,
        'source': 'air_temp',
        'channel': 0,
        'value_type': 'temperature',
        'low_temp': 22.4,
        'high_temp': 22.6,
        'low_action': 'start',
        'high_action': 'stop',
        'program': 0,
        'time_limited': False,
        'start_time': '06:00',
        'end_time': '22:00',
    }


def valid_time(value):
    return isinstance(value, str) and TIME_PATTERN.match(value) is not None


def time_minutes(value):
    if not valid_time(value):
        raise ValueError('invalid time')
    hour, minute = value.split(':')
    return int(hour) * 60 + int(minute)


def normalize_zone(value, name, program_count, id_factory):
    zone = default_zone(name)
    if isinstance(value, dict):
        zone.update(value)
    zone['id'] = str(zone.get('id') or id_factory())
    zone['enabled'] = bool(zone.get('enabled', False))
    zone['name'] = str(zone.get('name') or name)
    zone['source'] = str(zone.get('source') or 'air_temp')
    if zone['source'] not in SOURCES:
        zone['source'] = 'air_temp'
    zone['channel'] = max(0, safe_int(zone.get('channel'), 0))
    zone['value_type'] = str(zone.get('value_type') or 'temperature')
    if zone['value_type'] not in SHELLY_VALUE_TYPES:
        zone['value_type'] = 'temperature'
    zone['low_temp'] = clamp(safe_float(zone.get('low_temp'), 22.4), -50, 100)
    zone['high_temp'] = clamp(safe_float(zone.get('high_temp'), 22.6), -50, 100)
    zone['low_action'] = str(zone.get('low_action') or 'start')
    zone['high_action'] = str(zone.get('high_action') or 'stop')
    if zone['low_action'] not in ACTIONS:
        zone['low_action'] = 'start'
    if zone['high_action'] not in ACTIONS:
        zone['high_action'] = 'stop'
    zone['program'] = clamp(safe_int(zone.get('program'), 0), 0, max(0, program_count - 1))
    zone['time_limited'] = bool(zone.get('time_limited', False))
    zone['start_time'] = str(zone.get('start_time') or '06:00')
    zone['end_time'] = str(zone.get('end_time') or '22:00')
    if not valid_time(zone['start_time']):
        zone['start_time'] = '06:00'
    if not valid_time(zone['end_time']):
        zone['end_time'] = '22:00'
    return zone


def normalize_zones(values, program_count, id_factory, name_factory):
    if not isinstance(values, list):
        values = []
    normalized = []
    used_ids = set()
    for index, value in enumerate(values[:MAX_THERMOSTATS]):
        if not isinstance(value, dict):
            continue
        zone = normalize_zone(value, name_factory(index), program_count, id_factory)
        if zone['id'] in used_ids:
            zone['id'] = str(id_factory())
        used_ids.add(zone['id'])
        normalized.append(zone)
    return normalized


def validate_zone(zone):
    if zone['low_temp'] >= zone['high_temp']:
        raise ValueError('invalid temperature limits')
    if zone['time_limited']:
        start = time_minutes(zone['start_time'])
        end = time_minutes(zone['end_time'])
        if start == end:
            raise ValueError('empty time window')


def duplicate_enabled_program(zones, candidate):
    if not candidate.get('enabled'):
        return False
    return any(
        zone.get('enabled')
        and zone.get('id') != candidate.get('id')
        and zone.get('program') == candidate.get('program')
        for zone in zones
    )


def duplicate_enabled_program_ids(zones):
    duplicates = set()
    used = set()
    for zone in zones:
        if not zone.get('enabled'):
            continue
        program = zone.get('program')
        if program in used:
            duplicates.add(program)
        used.add(program)
    return duplicates


def in_time_window(now_minutes, start_minutes, end_minutes):
    if start_minutes == end_minutes:
        return False
    if start_minutes < end_minutes:
        return start_minutes <= now_minutes < end_minutes
    return now_minutes >= start_minutes or now_minutes < end_minutes


def zone_in_time_window(zone, now_minutes):
    if not zone.get('time_limited'):
        return True
    return in_time_window(
        now_minutes,
        time_minutes(zone['start_time']),
        time_minutes(zone['end_time']),
    )


def seconds_until_boundary(now_seconds, zones):
    boundaries = []
    for zone in zones:
        if not zone.get('enabled') or not zone.get('time_limited'):
            continue
        for key in ('start_time', 'end_time'):
            boundary = time_minutes(zone[key]) * 60
            distance = (boundary - now_seconds) % 86400
            boundaries.append(distance if distance else 86400)
    return min(boundaries) if boundaries else None
