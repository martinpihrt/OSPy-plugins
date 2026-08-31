# -*- coding: utf-8 -*-
"""Pure configuration, evaluation and learning helpers for Irrigation Safety."""

import math
import statistics


MODES = ('off', 'monitor', 'protect')
MAX_HISTORY = 5000
MIN_CHECK_INTERVAL = 1
MAX_CHECK_INTERVAL = 60
MIN_LEARNING_SAMPLES = 10
MAX_LEARNING_SAMPLES = 600


def safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return default


def safe_float(value, default=0.0):
    try:
        result = float(str(value).replace(',', '.'))
        return result if math.isfinite(result) else default
    except (TypeError, ValueError, OverflowError):
        return default


def clamp(value, minimum, maximum):
    return max(minimum, min(maximum, value))


def default_profile(station_id, station_name):
    return {
        'station_id': int(station_id),
        'name': str(station_name),
        'enabled': False,
        'minimum_flow_lpm': 0.1,
        'maximum_flow_lpm': 100.0,
        'startup_delay': 15,
        'confirm_seconds': 10,
        'learning': False,
        'learning_samples': 30,
        'learning_tolerance_percent': 20.0,
        'learning_minimum_margin_lpm': 0.5,
    }


def normalize_profile(value, station_id, station_name):
    profile = default_profile(station_id, station_name)
    if isinstance(value, dict):
        profile.update(value)
    profile['station_id'] = int(station_id)
    profile['name'] = str(station_name)
    profile['enabled'] = bool(profile.get('enabled', False))
    profile['minimum_flow_lpm'] = clamp(
        safe_float(profile.get('minimum_flow_lpm'), 0.1), 0.0, 1000000.0)
    profile['maximum_flow_lpm'] = clamp(
        safe_float(profile.get('maximum_flow_lpm'), 100.0), 0.0, 1000000.0)
    profile['startup_delay'] = clamp(
        safe_int(profile.get('startup_delay'), 15), 0, 3600)
    profile['confirm_seconds'] = clamp(
        safe_int(profile.get('confirm_seconds'), 10), 1, 3600)
    profile['learning'] = bool(profile.get('learning', False))
    profile['learning_samples'] = clamp(
        safe_int(profile.get('learning_samples'), 30),
        MIN_LEARNING_SAMPLES, MAX_LEARNING_SAMPLES)
    profile['learning_tolerance_percent'] = clamp(
        safe_float(profile.get('learning_tolerance_percent'), 20.0), 1.0, 100.0)
    profile['learning_minimum_margin_lpm'] = clamp(
        safe_float(profile.get('learning_minimum_margin_lpm'), 0.5),
        0.0, 1000000.0)
    return profile


def normalize_profiles(values, stations):
    """Return one profile for every enabled non-master OSPy station."""
    stored = {}
    for value in values if isinstance(values, list) else []:
        if isinstance(value, dict):
            stored[safe_int(value.get('station_id'), -1)] = value
    return [
        normalize_profile(stored.get(int(station_id)), station_id, station_name)
        for station_id, station_name in stations
    ]


def validate_profile(profile):
    if profile['minimum_flow_lpm'] >= profile['maximum_flow_lpm']:
        raise ValueError('minimum flow must be lower than maximum flow')


def expected_range(active_station_ids, profiles):
    """Combine configured limits when every active station has a safety profile."""
    active_ids = set(int(value) for value in active_station_ids)
    selected = [
        profile for profile in profiles
        if profile.get('enabled') and int(profile['station_id']) in active_ids
    ]
    if not active_ids or len(selected) != len(active_ids):
        return None
    return {
        'minimum': sum(profile['minimum_flow_lpm'] for profile in selected),
        'maximum': sum(profile['maximum_flow_lpm'] for profile in selected),
        'confirm_seconds': max(profile['confirm_seconds'] for profile in selected),
        'startup_delay': max(profile['startup_delay'] for profile in selected),
    }


def flow_fault(flow_lpm, expected):
    if expected is None:
        return None
    value = safe_float(flow_lpm, None)
    if value is None:
        return 'flow_unavailable'
    if value <= 0.0:
        return 'no_flow'
    if value < expected['minimum']:
        return 'low_flow'
    if value > expected['maximum']:
        return 'high_flow'
    return None


def percentile(values, fraction):
    ordered = sorted(float(value) for value in values)
    if not ordered:
        raise ValueError('no values')
    position = (len(ordered) - 1) * fraction
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def learned_range(samples, tolerance_percent=20.0, minimum_margin_lpm=0.5):
    """Build a robust range from positive finite samples using P10/P90."""
    values = [safe_float(value, -1.0) for value in samples]
    values = [value for value in values if value > 0.0 and math.isfinite(value)]
    if len(values) < MIN_LEARNING_SAMPLES:
        raise ValueError('not enough learning samples')
    center = statistics.median(values)
    low = percentile(values, 0.10)
    high = percentile(values, 0.90)
    margin = max(
        safe_float(minimum_margin_lpm, 0.5),
        center * safe_float(tolerance_percent, 20.0) / 100.0,
    )
    minimum = max(0.01, low - margin)
    maximum = max(minimum + 0.01, high + margin)
    return {
        'minimum': round(minimum, 3),
        'maximum': round(maximum, 3),
        'median': round(center, 3),
        'samples': len(values),
    }


def confirmed(active_since, now, confirm_seconds):
    return active_since is not None and now - active_since >= confirm_seconds
