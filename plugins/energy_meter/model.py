"""Pure energy calculations used by the Energy Meter plug-in."""

import datetime
import math


ROLES = ('grid', 'production', 'load', 'auxiliary')


def number(value, default=0.0):
    try:
        result = float(str(value).replace(',', '.'))
        return result if math.isfinite(result) else default
    except (TypeError, ValueError):
        return default


def normalized_reading(reading, invert=False):
    imported = [max(0.0, number(value)) for value in reading.get('import_kwh', [0, 0, 0])][:3]
    exported = [max(0.0, number(value)) for value in reading.get('export_kwh', [0, 0, 0])][:3]
    power = [number(value) for value in reading.get('power_w', [0, 0, 0])][:3]
    while len(imported) < 3:
        imported.append(0.0)
    while len(exported) < 3:
        exported.append(0.0)
    while len(power) < 3:
        power.append(0.0)
    if invert:
        imported, exported = exported, imported
        power = [-value for value in power]
    return {'import_kwh': imported, 'export_kwh': exported, 'power_w': power, 'online': bool(reading.get('online', True)), 'identity': str(reading.get('identity', '')), 'updated': reading.get('updated')}


def counter_delta(current, previous):
    if previous is None:
        return 0.0, False
    current = max(0.0, number(current))
    previous = max(0.0, number(previous))
    if current + 1e-9 < previous:
        return 0.0, True
    return current - previous, False


def tariff_at(moment, tariffs, default_import=0.0, default_export=0.0):
    if not isinstance(moment, datetime.datetime):
        moment = datetime.datetime.fromtimestamp(float(moment))
    fallback_import = number(default_import)
    fallback_export = number(default_export)
    minute = moment.hour * 60 + moment.minute
    weekday = moment.weekday()
    for tariff in tariffs or []:
        if not tariff.get('enabled', True) or weekday not in tariff.get('weekdays', range(7)):
            continue
        start = max(0, min(1440, int(number(tariff.get('start_minute', 0)))))
        end = max(0, min(1440, int(number(tariff.get('end_minute', 1440), 1440))))
        matches = True if start == end else (start <= minute < end if start < end else minute >= start or minute < end)
        if matches:
            return {'id': str(tariff.get('id', 'tariff')), 'name': str(tariff.get('name', 'Tariff')), 'import_price': number(tariff.get('import_price', fallback_import), fallback_import), 'export_price': number(tariff.get('export_price', fallback_export), fallback_export)}
    return {'id': 'default', 'name': 'Default', 'import_price': fallback_import, 'export_price': fallback_export}


def make_interval(meter, reading, previous, started, ended, tariff):
    imported = []
    exported = []
    reset = False
    previous_import = previous.get('import_kwh') if previous else None
    previous_export = previous.get('export_kwh') if previous else None
    for index in range(3):
        delta, was_reset = counter_delta(reading['import_kwh'][index], previous_import[index] if previous_import else None)
        imported.append(delta)
        reset = reset or was_reset
        delta, was_reset = counter_delta(reading['export_kwh'][index], previous_export[index] if previous_export else None)
        exported.append(delta)
        reset = reset or was_reset
    interval = {'meter_id': meter['id'], 'label': meter['label'], 'role': meter['role'], 'started': float(started), 'ended': float(ended), 'datetime': datetime.datetime.fromtimestamp(float(ended)).strftime('%Y-%m-%d %H:%M:%S'), 'import_l1_kwh': imported[0], 'import_l2_kwh': imported[1], 'import_l3_kwh': imported[2], 'import_kwh': sum(imported), 'export_l1_kwh': exported[0], 'export_l2_kwh': exported[1], 'export_l3_kwh': exported[2], 'export_kwh': sum(exported), 'power_l1_w': reading['power_w'][0], 'power_l2_w': reading['power_w'][1], 'power_l3_w': reading['power_w'][2], 'power_w': sum(reading['power_w']), 'tariff_id': tariff['id'], 'tariff_name': tariff['name'], 'import_price': tariff['import_price'], 'export_price': tariff['export_price'], 'cost': sum(imported) * tariff['import_price'], 'income': sum(exported) * tariff['export_price'], 'counter_reset': reset}
    state = {'import_kwh': list(reading['import_kwh']), 'export_kwh': list(reading['export_kwh']), 'timestamp': float(ended), 'identity': reading.get('identity', '')}
    return interval, state


def price_interval(interval, tariffs, default_import=0.0, default_export=0.0):
    """Apply time-weighted historical prices without creating artificial power samples."""
    result = dict(interval)
    started = number(result.get('started'))
    ended = number(result.get('ended'))
    duration = ended - started
    if duration <= 0:
        applied = tariff_at(datetime.datetime.fromtimestamp(ended), tariffs, default_import, default_export)
        segments = [(1.0, applied)]
        duration = 1.0
    else:
        boundaries = {started, ended}
        first_day = datetime.datetime.fromtimestamp(started).date()
        last_day = datetime.datetime.fromtimestamp(ended).date()
        day = first_day
        while day <= last_day:
            midnight = datetime.datetime.combine(day, datetime.time.min)
            midnight_value = midnight.timestamp()
            if started < midnight_value < ended:
                boundaries.add(midnight_value)
            for tariff in tariffs or []:
                for key, default in (('start_minute', 0), ('end_minute', 1440)):
                    minute = max(0, min(1440, int(number(tariff.get(key, default), default))))
                    boundary = (midnight + datetime.timedelta(minutes=minute)).timestamp()
                    if started < boundary < ended:
                        boundaries.add(boundary)
            day += datetime.timedelta(days=1)
        ordered = sorted(boundaries)
        segments = []
        for index in range(len(ordered) - 1):
            segment_start = ordered[index]
            segment_end = ordered[index + 1]
            midpoint = segment_start + (segment_end - segment_start) / 2.0
            segments.append((segment_end - segment_start, tariff_at(datetime.datetime.fromtimestamp(midpoint), tariffs, default_import, default_export)))
    import_price = sum(segment_duration * tariff['import_price'] for segment_duration, tariff in segments) / duration
    export_price = sum(segment_duration * tariff['export_price'] for segment_duration, tariff in segments) / duration
    tariff_ids = []
    tariff_names = []
    for unused_duration, tariff in segments:
        if tariff['id'] not in tariff_ids:
            tariff_ids.append(tariff['id'])
        if tariff['name'] not in tariff_names:
            tariff_names.append(tariff['name'])
    result.update({'tariff_id': ' / '.join(tariff_ids), 'tariff_name': ' / '.join(tariff_names), 'import_price': import_price, 'export_price': export_price, 'cost': number(result.get('import_kwh')) * import_price, 'income': number(result.get('export_kwh')) * export_price})
    return result


def period_bounds(now=None):
    now = now or datetime.datetime.now()
    today = datetime.datetime(now.year, now.month, now.day)
    return {'today': today.timestamp(), 'yesterday': (today - datetime.timedelta(days=1)).timestamp(), 'month': datetime.datetime(now.year, now.month, 1).timestamp(), 'year': datetime.datetime(now.year, 1, 1).timestamp(), 'now': now.timestamp()}


def selected_day_bounds(value=None, now=None):
    """Return one local calendar day, clamping invalid and future values to today."""
    now = now or datetime.datetime.now()
    selected = now.date()
    if isinstance(value, datetime.datetime):
        selected = value.date()
    elif isinstance(value, datetime.date):
        selected = value
    elif value:
        try:
            selected = datetime.datetime.strptime(str(value).strip(), '%Y-%m-%d').date()
        except (TypeError, ValueError):
            selected = now.date()
    if selected > now.date():
        selected = now.date()
    start = datetime.datetime.combine(selected, datetime.time.min)
    next_day = start + datetime.timedelta(days=1)
    end = now if selected == now.date() else next_day
    return {'start': start.timestamp(), 'end': end.timestamp(), 'date': selected.isoformat(), 'current_date': now.date().isoformat(), 'is_today': selected == now.date()}


def aggregate(records, start, end, meter_id=None, role=None, currency=None):
    result = {'import_kwh': 0.0, 'export_kwh': 0.0, 'cost': 0.0, 'income': 0.0}
    for record in records:
        if meter_id and record.get('meter_id') != meter_id:
            continue
        if role and record.get('role') != role:
            continue
        record_start = number(record.get('started'))
        record_end = number(record.get('ended'))
        overlap = max(0.0, min(end, record_end) - max(start, record_start))
        duration = max(1.0, record_end - record_start)
        factor = min(1.0, overlap / duration)
        if factor:
            for key in result:
                if key in ('cost', 'income') and currency is not None and record.get('currency') not in (None, '', currency):
                    continue
                result[key] += number(record.get(key)) * factor
    return {key: round(value, 6) for key, value in result.items()}


def solar_summary(records, start, end, currency=None):
    grid = aggregate(records, start, end, role='grid', currency=currency)
    production = aggregate(records, start, end, role='production', currency=currency)
    has_production = any(record.get('role') == 'production' and number(record.get('ended')) >= start for record in records)
    result = {'grid_import_kwh': grid['import_kwh'], 'grid_export_kwh': grid['export_kwh'], 'production_kwh': production['import_kwh'], 'cost': grid['cost'], 'feed_in_income': grid['income'], 'production_available': has_production}
    if has_production:
        house = max(0.0, production['import_kwh'] + grid['import_kwh'] - grid['export_kwh'])
        self_consumption = max(0.0, production['import_kwh'] - grid['export_kwh'])
        average_import_price = grid['cost'] / grid['import_kwh'] if grid['import_kwh'] else 0.0
        result.update({'house_consumption_kwh': round(house, 6), 'self_consumption_kwh': round(self_consumption, 6), 'self_consumption_ratio': round(self_consumption / production['import_kwh'] * 100.0, 2) if production['import_kwh'] else 0.0, 'independence_ratio': round(self_consumption / house * 100.0, 2) if house else 0.0, 'solar_savings': round(self_consumption * average_import_price, 6)})
    return result
