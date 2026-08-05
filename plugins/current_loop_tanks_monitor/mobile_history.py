"""Helpers for bounded mobile history responses."""

import datetime
import math


def _boundary(value, fallback):
    if not value:
        return fallback
    parsed = datetime.datetime.fromisoformat(
        value[:-1] + "+00:00" if value.endswith("Z") else value)
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone().replace(tzinfo=None)
    return parsed


def _downsample(points, maximum):
    if len(points) <= maximum:
        return points
    size = int(math.ceil(len(points) / float(max(1, maximum // 2))))
    result = []
    for offset in range(0, len(points), size):
        bucket = points[offset:offset + size]
        result.extend(sorted({min(bucket, key=lambda point: point[1]),
                              max(bucket, key=lambda point: point[1])},
                             key=lambda item: item[0]))
    return result[:maximum]


def mobile_history(graph_data, definitions, from_time=None, to_time=None,
                   max_points=400, source="local"):
    now = datetime.datetime.now()
    start = _boundary(from_time, now.replace(hour=0, minute=0, second=0,
                                              microsecond=0))
    end = _boundary(to_time, now)
    maximum = max(20, min(2000, int(max_points or 400)))
    start_epoch, end_epoch = start.timestamp(), end.timestamp()
    latest = None
    series = []
    for index, item in enumerate(graph_data or []):
        if index >= len(definitions) or definitions[index] is None:
            continue
        definition = definitions[index]
        raw = []
        balances = item.get("balances", {}) if isinstance(item, dict) else {}
        for timestamp, value in balances.items():
            try:
                epoch, numeric = int(timestamp), float(value.get("total"))
            except (AttributeError, TypeError, ValueError, OSError):
                continue
            latest = epoch if latest is None else max(latest, epoch)
            if start_epoch <= epoch <= end_epoch:
                raw.append((epoch, numeric))
        raw.sort(key=lambda point: point[0])
        series.append({"id": definition[0],
                       "label": str(item.get("station") or definition[1]),
                       "unit": definition[2],
                       "points": [{"time": datetime.datetime.fromtimestamp(epoch).isoformat(),
                                   "value": value}
                                  for epoch, value in _downsample(raw, maximum)]})
    return series, {"from": start.isoformat(), "to": end.isoformat(),
                    "max_points": maximum, "source": source,
                    "last_available": (datetime.datetime.fromtimestamp(latest).isoformat()
                                       if latest is not None else None),
                    "returned_points": sum(len(item["points"]) for item in series)}
