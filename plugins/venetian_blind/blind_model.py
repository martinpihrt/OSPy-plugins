"""Pure configuration, Shelly protocol and automation helpers."""

from urllib.parse import quote


PROFILES = ('custom', 'gen1', 'gen2')
TARGETS = ('closed', 'tilt1', 'tilt2', 'tilt3', 'tilt4', 'open')


def default_blind(uid):
    return {
        'uid': str(uid), 'enabled': True, 'label': '', 'profile': 'gen1', 'host': '',
        'open_url': '', 'stop_url': '', 'close_url': '', 'status_url': '',
        'closed_label': '', 'open_label': '',
        'tilt_positions': [20, 40, 60, 80],
        'tilt_labels': ['', '', '', ''],
        'tilt_urls': ['', '', '', ''],
    }


def _list_value(settings, key, index, default=''):
    values = settings.get(key, [])
    return values[index] if isinstance(values, (list, tuple)) and index < len(values) else default


def _integer(value, default, minimum, maximum):
    try:
        value = int(value)
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def normalize_blind(blind, uid_factory):
    result = default_blind(blind.get('uid') or uid_factory())
    result.update(blind)
    result['uid'] = str(result.get('uid') or uid_factory())
    result['enabled'] = bool(result.get('enabled', True))
    result['profile'] = result.get('profile') if result.get('profile') in PROFILES else 'custom'
    for key in ('label', 'host', 'open_url', 'stop_url', 'close_url', 'status_url', 'closed_label', 'open_label'):
        result[key] = str(result.get(key, '') or '').strip()
    positions = list(result.get('tilt_positions', []))
    labels = list(result.get('tilt_labels', []))
    urls = list(result.get('tilt_urls', []))
    result['tilt_positions'] = [_integer(positions[i] if i < len(positions) else (i + 1) * 20, (i + 1) * 20, 1, 99) for i in range(4)]
    result['tilt_labels'] = [str(labels[i] if i < len(labels) else '') for i in range(4)]
    result['tilt_urls'] = [str(urls[i] if i < len(urls) else '') for i in range(4)]
    return result


def configured_blinds(settings, uid_factory, maximum=100):
    stored = settings.get('blinds')
    if isinstance(stored, list):
        result = [normalize_blind(item, uid_factory) for item in stored[:maximum] if isinstance(item, dict)]
    else:
        count = _integer(settings.get('number_blinds', 1), 1, 0, maximum)
        result = []
        for index in range(count):
            blind = default_blind(uid_factory())
            blind.update({
                'profile': 'custom',
                'label': _list_value(settings, 'label', index),
                'open_url': _list_value(settings, 'open', index),
                'stop_url': _list_value(settings, 'stop', index),
                'close_url': _list_value(settings, 'close', index),
                'status_url': _list_value(settings, 'status', index),
                'closed_label': _list_value(settings, 'label0', index),
                'open_label': _list_value(settings, 'label100', index),
            })
            result.append(normalize_blind(blind, uid_factory))
    seen = set()
    for blind in result:
        if blind['uid'] in seen:
            blind['uid'] = str(uid_factory())
        seen.add(blind['uid'])
    return result


def legacy_lists(blinds):
    return {
        'number_blinds': len(blinds), 'label': [item['label'] for item in blinds],
        'open': [command_url(item, 'open') for item in blinds],
        'stop': [command_url(item, 'stop') for item in blinds],
        'close': [command_url(item, 'closed') for item in blinds],
        'status': [status_url(item) for item in blinds],
        'label0': [item['closed_label'] for item in blinds],
        'label100': [item['open_label'] for item in blinds],
    }


def _base(blind):
    host = str(blind.get('host', '')).strip().rstrip('/')
    return host if host.startswith(('http://', 'https://')) else 'http://' + host


def status_url(blind):
    if blind['profile'] == 'gen1':
        return _base(blind) + '/status'
    if blind['profile'] == 'gen2':
        return _base(blind) + '/rpc/Cover.GetStatus?id=0'
    return blind.get('status_url', '')


def command_url(blind, target):
    profile = blind['profile']
    if profile == 'custom':
        if target == 'open': return blind.get('open_url', '')
        if target == 'closed': return blind.get('close_url', '')
        if target == 'stop': return blind.get('stop_url', '')
        if target.startswith('tilt'):
            return blind.get('tilt_urls', [''] * 4)[int(target[-1]) - 1]
        return ''
    if profile == 'gen1':
        base = _base(blind) + '/roller/0?go='
        if target == 'open': return base + 'open'
        if target == 'closed': return base + 'close'
        if target == 'stop': return base + 'stop'
        position = blind['tilt_positions'][int(target[-1]) - 1]
        return base + 'to_pos&roller_pos={}'.format(position)
    method = {'open': 'Cover.Open', 'closed': 'Cover.Close', 'stop': 'Cover.Stop'}.get(target)
    base = _base(blind) + '/rpc/'
    if method:
        return '{}{}?id=0'.format(base, method)
    position = blind['tilt_positions'][int(target[-1]) - 1]
    return '{}Cover.GoToPosition?id=0&pos={}'.format(base, quote(str(position)))


def parse_status(payload, profile):
    data = payload
    if profile == 'gen1' or 'rollers' in payload:
        data = payload['rollers'][0]
    elif 'cover:0' in payload:
        data = payload['cover:0']
    state = str(data.get('state', 'unknown')).lower()
    position = data.get('current_pos', data.get('pos'))
    try:
        position = float(position)
    except (TypeError, ValueError):
        position = None
    return {'state': state, 'position': position, 'power': data.get('power', data.get('apower'))}


def position_state(position, tilt_positions, tolerance=4):
    if position is None:
        return 'unknown'
    targets = [('closed', 0)] + [('tilt{}'.format(i + 1), value) for i, value in enumerate(tilt_positions)] + [('open', 100)]
    name, distance = min(((name, abs(float(position) - float(value))) for name, value in targets), key=lambda item: item[1])
    return name if distance <= tolerance else 'position'


def aggregate_blind_states(details, enabled_indices):
    """Return aggregate positions; an unreachable enabled blind is unconfirmed."""
    enabled = list(enabled_indices)
    known = [details[index].get('state') for index in enabled if details.get(index, {}).get('reachable')]
    complete = bool(enabled) and len(known) == len(enabled)
    return {
        'known_count': len(known),
        'all_open': complete and all(state == 'open' for state in known),
        'all_closed': complete and all(state == 'closed' for state in known),
    }


def in_time_window(now_minutes, start_minutes, end_minutes):
    if start_minutes == end_minutes:
        return True
    if start_minutes < end_minutes:
        return start_minutes <= now_minutes < end_minutes
    return now_minutes >= start_minutes or now_minutes < end_minutes


def sensor_temperature(sensor):
    """Return the temperature channel used by each OSPy sensor type."""
    values = getattr(sensor, 'last_read_value', [])
    if int(getattr(sensor, 'manufacturer', 0)) == 1:
        candidates = values[2] if len(values) > 2 else []
        candidates = candidates if isinstance(candidates, (list, tuple)) else [candidates]
        for candidate in candidates:
            value = _temperature_number(candidate)
            if value is not None:
                return value
        return None
    sensor_type = int(getattr(sensor, 'sens_type', -1))
    if sensor_type == 5:
        channel = 0
    elif sensor_type == 6 and 0 <= int(getattr(sensor, 'multi_type', -1)) <= 3:
        channel = int(sensor.multi_type)
    else:
        return None
    if channel < 0 or channel >= len(values):
        return None
    return _temperature_number(values[channel])


def _temperature_number(raw_value):
    try:
        value = float(raw_value)
    except (TypeError, ValueError):
        return None
    return value if value == value and value not in (-127.0, float('inf'), float('-inf')) else None


def wind_window_state(samples, now, limit, safe_required, strong_required,
                      interval_seconds, freshness_seconds=30):
    """Evaluate unique accepted wind measurements for shading and protection."""
    ordered = sorted(
        (float(timestamp), float(value)) for timestamp, value in samples
        if float(timestamp) <= float(now)
    )
    cutoff = float(now) - max(1.0, float(interval_seconds))
    window = [(timestamp, value) for timestamp, value in ordered if timestamp >= cutoff]
    exceedances = sum(1 for _timestamp, value in window if value >= float(limit))
    strong = exceedances >= max(1, int(strong_required))
    required = max(1, int(safe_required))
    fresh = bool(ordered) and float(now) - ordered[-1][0] <= max(1.0, float(freshness_seconds))
    safe_count = 0
    if fresh:
        for _timestamp, value in reversed(ordered):
            if value >= float(limit):
                break
            safe_count += 1
    safe = safe_count >= required
    return {
        'safe': safe,
        'strong': strong,
        'safe_count': safe_count,
        'exceedances': exceedances,
        'last_timestamp': ordered[-1][0] if ordered else 0,
    }
