"""Pure Water Meter measurement helpers."""


def decode_bcd_counter(raw_bytes):
    """Decode exactly three PCF8583 BCD counter registers."""
    if len(raw_bytes) != 3:
        raise ValueError('invalid_counter_length')
    digits = []
    for value in raw_bytes:
        byte = int(value)
        low = byte & 0x0F
        high = (byte >> 4) & 0x0F
        if low > 9 or high > 9:
            raise ValueError('invalid_bcd_digit')
        digits.extend((low, high))
    return sum(digit * (10 ** index) for index, digit in enumerate(digits))
