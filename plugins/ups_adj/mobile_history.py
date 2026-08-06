"""Bounded mobile history for the UPS power-line state."""

import datetime


def _parse(value, fallback):
    if not value:
        return fallback
    parsed = datetime.datetime.fromisoformat(value[:-1] + '+00:00' if value.endswith('Z') else value)
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone().replace(tzinfo=None)
    return parsed


def build(graph_data, from_time=None, to_time=None, max_points=400, source='local', live_value=None,
          label='Power line'):
    now = datetime.datetime.now()
    start = _parse(from_time, now.replace(hour=0, minute=0, second=0, microsecond=0))
    end = _parse(to_time, now)
    maximum = max(20, min(2000, int(max_points or 400)))
    points = []
    latest = None
    items = graph_data or []
    balances = items[0].get('balances', {}) if items and isinstance(items[0], dict) else {}
    for timestamp, value in balances.items():
        try:
            epoch = int(timestamp)
            numeric = float(value.get('total'))
        except (AttributeError, TypeError, ValueError):
            continue
        latest = epoch if latest is None else max(latest, epoch)
        if start.timestamp() <= epoch <= end.timestamp():
            points.append((epoch, numeric))
    if live_value is not None:
        epoch = int(now.timestamp())
        if start.timestamp() <= epoch <= end.timestamp():
            points.append((epoch, float(live_value)))
        latest = epoch if latest is None else max(latest, epoch)
    points.sort(key=lambda item: item[0])
    if len(points) > maximum:
        # Preserve state transitions so a short outage is not lost when a long
        # interval is reduced for the mobile client.
        transitions = [points[0]]
        for previous, current in zip(points, points[1:]):
            if current[1] != previous[1]:
                transitions.extend((previous, current))
        transitions.append(points[-1])
        transitions = sorted(set(transitions), key=lambda item: item[0])
        if len(transitions) <= maximum:
            remaining = [point for point in points if point not in set(transitions)]
            slots = maximum - len(transitions)
            if slots and remaining:
                step = max(1, len(remaining) // slots)
                transitions.extend(remaining[::step][:slots])
                transitions.sort(key=lambda item: item[0])
            points = transitions
        else:
            step = max(1, len(transitions) // maximum)
            points = transitions[::step][:maximum]
    result = [{'time': datetime.datetime.fromtimestamp(epoch).isoformat(), 'value': value}
              for epoch, value in points]
    return [{'id': 'power_line', 'label': label, 'unit': '', 'points': result}], {
        'from': start.isoformat(), 'to': end.isoformat(), 'max_points': maximum,
        'source': source, 'returned_points': len(result),
        'last_available': datetime.datetime.fromtimestamp(latest).isoformat() if latest else None,
    }
