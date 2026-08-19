"""Pure validation and calculation helpers for Wind Speed Monitor."""


def parse_decimal(value, field_name):
    text = str(value).strip().replace(',', '.')
    try:
        return float(text)
    except (TypeError, ValueError):
        raise ValueError('{}:{}'.format(field_name, value))


def decode_bcd_counter(raw_bytes):
    if raw_bytes is None or len(raw_bytes) < 3:
        raise ValueError('counter_read_length')
    digits = []
    for byte in raw_bytes[:3]:
        value = int(byte)
        low = value & 0x0F
        high = (value >> 4) & 0x0F
        if low > 9 or high > 9:
            raise ValueError('invalid_bcd_digit')
        digits.extend((low, high))
    return (
        digits[5] * 100000
        + digits[4] * 10000
        + digits[3] * 1000
        + digits[2] * 100
        + digits[1] * 10
        + digits[0]
    )


def modbus_crc16(data):
    """Return the Modbus RTU CRC-16 for a bytes-like frame."""
    crc = 0xFFFF
    for byte in bytes(bytearray(data)):
        crc ^= byte
        for _unused in range(8):
            if crc & 0x0001:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc


def build_zts_wind_request(address):
    """Build a ZTS-3000-FSJT Modbus request for speed and wind force."""
    device_address = int(address)
    if device_address < 1 or device_address > 247:
        raise ValueError('invalid_modbus_address')
    frame = bytearray((device_address, 0x03, 0x00, 0x00, 0x00, 0x02))
    crc = modbus_crc16(frame)
    frame.extend((crc & 0xFF, (crc >> 8) & 0xFF))
    return bytes(frame)


def parse_zts_wind_response(response, address):
    """Validate a ZTS-3000-FSJT response and return speed in m/s."""
    frame = bytes(bytearray(response or b''))
    if len(frame) < 5:
        raise ValueError('modbus_response_length')
    expected_address = int(address)
    if frame[0] != expected_address:
        raise ValueError('modbus_address_mismatch')
    expected_crc = modbus_crc16(frame[:-2])
    received_crc = frame[-2] | (frame[-1] << 8)
    if received_crc != expected_crc:
        raise ValueError('modbus_crc')
    if frame[1] & 0x80:
        raise ValueError('modbus_exception_{}'.format(frame[2]))
    if len(frame) != 9 or frame[1] != 0x03 or frame[2] != 0x04:
        raise ValueError('modbus_response_format')
    raw_speed = (frame[3] << 8) | frame[4]
    wind_force = (frame[5] << 8) | frame[6]
    return {
        'speed_mps': raw_speed / 10.0,
        'wind_force': wind_force,
        'raw_speed': raw_speed,
    }


def calculate_speed(raw_pulses, elapsed_seconds, pulses_per_rotation,
                    meters_per_rotation):
    elapsed = float(elapsed_seconds)
    pulses = float(pulses_per_rotation)
    if elapsed <= 0:
        raise ValueError('invalid_measurement_interval')
    if pulses <= 0:
        raise ValueError('invalid_pulses_per_rotation')
    pulse_rate = float(raw_pulses) / elapsed
    speed_mps = pulse_rate / pulses * float(meters_per_rotation)
    return pulse_rate, speed_mps


def validate_measurement(speed_mps, filter_enabled, maximum_speed_mps):
    if speed_mps < 0:
        return False, 'negative_speed'
    if filter_enabled and speed_mps > float(maximum_speed_mps):
        return False, 'maximum_speed'
    return True, ''


def update_confirmation(current_count, exceeded, required_count):
    required = max(1, int(required_count))
    if not exceeded:
        return 0, False
    count = min(max(0, int(current_count)) + 1, required)
    return count, count >= required


def calculate_trend(samples, minimum_span=40.0):
    """Return up/down/steady/unknown from a roughly one-minute sample window."""
    if len(samples) < 4:
        return 'unknown'
    ordered = sorted(samples, key=lambda item: item[0])
    span = float(ordered[-1][0]) - float(ordered[0][0])
    if span < minimum_span:
        return 'unknown'
    midpoint = float(ordered[-1][0]) - min(60.0, span) / 2.0
    older = [float(value) for stamp, value in ordered if stamp <= midpoint]
    newer = [float(value) for stamp, value in ordered if stamp > midpoint]
    if not older or not newer:
        return 'unknown'
    old_mean = sum(older) / len(older)
    new_mean = sum(newer) / len(newer)
    deadband = max(0.2, old_mean * 0.1)
    if new_mean - old_mean > deadband:
        return 'up'
    if old_mean - new_mean > deadband:
        return 'down'
    return 'steady'
