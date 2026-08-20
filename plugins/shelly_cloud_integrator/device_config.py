"""Pure helpers for backward-compatible Shelly device configuration."""


DEVICE_FIELDS = (
    'device_uid',
    'use_sensor',
    'sensor_label',
    'sensor_id',
    'sensor_type',
    'gen_type',
    'addons_labels_1',
    'addons_labels_2',
    'addons_labels_3',
    'addons_labels_4',
    'addons_labels_5',
    'reading_type',
    'sensor_ip',
)

DEFAULTS = {
    'device_uid': '',
    'use_sensor': False,
    'sensor_label': '',
    'sensor_id': '',
    'sensor_type': 0,
    'gen_type': 1,
    'addons_labels_1': 'A',
    'addons_labels_2': 'B',
    'addons_labels_3': 'C',
    'addons_labels_4': 'D',
    'addons_labels_5': 'E',
    'reading_type': 1,
    'sensor_ip': '',
}


def _integer(value, default, minimum, maximum):
    try:
        result = int(value)
    except (TypeError, ValueError):
        result = default
    return max(minimum, min(maximum, result))


def default_device(uid):
    result = dict(DEFAULTS)
    result['device_uid'] = str(uid)
    return result


def normalize_devices(settings, uid_factory, maximum=500):
    """Convert legacy parallel lists into validated device records."""
    count = _integer(settings.get('number_sensors', 0), 0, 0, maximum)
    records = []
    used_uids = set()
    for index in range(count):
        record = {}
        for field in DEVICE_FIELDS:
            values = settings.get(field, [])
            value = values[index] if isinstance(values, (list, tuple)) and index < len(values) else DEFAULTS[field]
            record[field] = value
        uid = str(record.get('device_uid') or '').strip()
        if not uid or uid in used_uids:
            uid = str(uid_factory())
        used_uids.add(uid)
        record['device_uid'] = uid
        record['use_sensor'] = bool(record.get('use_sensor', False))
        record['sensor_type'] = _integer(record.get('sensor_type'), 0, 0, 11)
        record['gen_type'] = _integer(record.get('gen_type'), 1, 0, 1)
        record['reading_type'] = _integer(record.get('reading_type'), 1, 0, 1)
        if record['sensor_type'] in (0, 9):
            record['reading_type'] = 1
        for field in DEVICE_FIELDS:
            if field not in ('use_sensor', 'sensor_type', 'gen_type', 'reading_type'):
                record[field] = str(record.get(field, '') or '').strip()
        records.append(record)
    return records


def serialize_devices(devices):
    result = {field: [] for field in DEVICE_FIELDS}
    for device in devices:
        for field in DEVICE_FIELDS:
            result[field].append(device.get(field, DEFAULTS[field]))
    result['number_sensors'] = len(devices)
    return result


def upsert_device(devices, device, maximum=500):
    result = [dict(item) for item in devices]
    uid = str(device.get('device_uid', '') or '')
    for index, current in enumerate(result):
        if current.get('device_uid') == uid:
            result[index] = dict(device)
            return result, False
    if len(result) >= maximum:
        raise ValueError('maximum_devices')
    result.append(dict(device))
    return result, True


def delete_device(devices, uid):
    target = str(uid or '')
    result = [dict(item) for item in devices if item.get('device_uid') != target]
    return result, len(result) != len(devices)
