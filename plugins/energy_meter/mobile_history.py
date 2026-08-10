"""Bounded native mobile history for Energy Meter."""

import datetime
import math


def boundary(value, fallback):
    if not value:
        return fallback
    if isinstance(value, (int, float)):
        return datetime.datetime.fromtimestamp(value)
    parsed = datetime.datetime.fromisoformat(value[:-1] + '+00:00' if str(value).endswith('Z') else str(value))
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone().replace(tzinfo=None)
    return parsed


def downsample(points, maximum):
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


def mobile_history(records, configured_meters, from_time=None, to_time=None, max_points=400, source='local'):
    now = datetime.datetime.now()
    start = boundary(from_time, now.replace(hour=0, minute=0, second=0, microsecond=0))
    end = boundary(to_time, now)
    maximum = max(20, min(2000, int(max_points or 400)))
    grouped = {meter['id']: [] for meter in configured_meters if meter.get('enabled', True)}
    latest = None
    for record in records or []:
        try:
            epoch = float(record.get('ended'))
            power = float(record.get('power_w'))
            meter_id = str(record.get('meter_id'))
        except (AttributeError, TypeError, ValueError, OSError):
            continue
        latest = epoch if latest is None else max(latest, epoch)
        if meter_id in grouped and start.timestamp() <= epoch <= end.timestamp():
            grouped[meter_id].append((epoch, power))
    series = []
    for meter in configured_meters:
        if meter['id'] not in grouped:
            continue
        raw = sorted(grouped[meter['id']], key=lambda point: point[0])
        points = [{'time': datetime.datetime.fromtimestamp(epoch).isoformat(), 'value': value} for epoch, value in downsample(raw, maximum)]
        if points:
            series.append({'id': 'power_' + meter['id'], 'label': meter['label'], 'unit': 'W', 'points': points})
    returned = sum(len(item['points']) for item in series)
    history = {'from': start.isoformat(), 'to': end.isoformat(), 'max_points': maximum, 'source': source, 'last_available': datetime.datetime.fromtimestamp(latest).isoformat() if latest is not None else None, 'returned_points': returned}
    return series, history
