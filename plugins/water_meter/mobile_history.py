"""Helpers for bounded Water Meter mobile history responses."""

import datetime
import math


def _boundary(value, fallback):
    if not value:
        return fallback
    parsed = datetime.datetime.fromisoformat(value[:-1] + '+00:00' if value.endswith('Z') else value)
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone().replace(tzinfo=None)
    return parsed


def _downsample(points, maximum):
    if len(points) <= maximum:
        return points
    buckets = max(1, maximum // 2)
    size = int(math.ceil(len(points) / float(buckets)))
    result = []
    for offset in range(0, len(points), size):
        bucket = points[offset:offset + size]
        low = min(bucket, key=lambda point: point[1])
        high = max(bucket, key=lambda point: point[1])
        for point in sorted({low, high}, key=lambda item: item[0]):
            result.append(point)
    return result[:maximum]


def mobile_history(records, from_time=None, to_time=None, max_points=400, source='local'):
    now = datetime.datetime.now()
    start = _boundary(from_time, now.replace(hour=0, minute=0, second=0, microsecond=0))
    end = _boundary(to_time, now)
    maximum = max(20, min(2000, int(max_points or 400)))
    raw = []
    latest = None
    for record in records or []:
        try:
            epoch = int(record.get('timestamp'))
            value = float(record.get('flow_lps'))
        except (AttributeError, TypeError, ValueError, OSError):
            continue
        latest = epoch if latest is None else max(latest, epoch)
        if start.timestamp() <= epoch <= end.timestamp():
            raw.append((epoch, value))
    raw.sort(key=lambda point: point[0])
    points = [{'time': datetime.datetime.fromtimestamp(epoch).isoformat(), 'value': value} for epoch, value in _downsample(raw, maximum)]
    series = [{'id': 'flow', 'label': 'Flow', 'unit': 'l/s', 'points': points}]
    history = {
        'from': start.isoformat(),
        'to': end.isoformat(),
        'max_points': maximum,
        'source': source,
        'last_available': datetime.datetime.fromtimestamp(latest).isoformat() if latest is not None else None,
        'returned_points': len(points),
    }
    return series, history
