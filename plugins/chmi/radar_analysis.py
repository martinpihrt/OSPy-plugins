"""Pure radar-pixel analysis helpers used by the CHMI plug-in."""


def pixel_matches_threshold(red, green, blue, channel_settings):
    checks = []
    for enabled, value, threshold in (
        (channel_settings['red_enabled'], red, channel_settings['red_threshold']),
        (channel_settings['green_enabled'], green, channel_settings['green_threshold']),
        (channel_settings['blue_enabled'], blue, channel_settings['blue_threshold']),
    ):
        if enabled:
            checks.append(int(value) > int(threshold))
    return any(checks)


def analyze_location_pixels(bitmap, x, y, radius, minimum_percent,
                            channel_settings):
    """Return exact-location RGB and threshold statistics for a circular area."""
    radius = max(0, int(radius))
    minimum_percent = max(0, min(100, int(minimum_percent)))
    x = int(x)
    y = int(y)
    if x < 0 or y < 0 or x >= bitmap.width or y >= bitmap.height:
        raise ValueError('location_outside_radar')

    center_red, center_green, center_blue = bitmap.getpixel((x, y))
    rainy_pixels = 0
    total_pixels = 0

    for dx in range(-radius, radius + 1):
        for dy in range(-radius, radius + 1):
            if dx * dx + dy * dy > radius * radius:
                continue
            px = x + dx
            py = y + dy
            if px < 0 or py < 0 or px >= bitmap.width or py >= bitmap.height:
                continue

            red, green, blue = bitmap.getpixel((px, py))
            total_pixels += 1
            if pixel_matches_threshold(
                    red, green, blue, channel_settings):
                rainy_pixels += 1

    rainy_percent = (
        int(round((rainy_pixels * 100.0) / total_pixels))
        if total_pixels else 0
    )
    return {
        'rain': rainy_percent >= minimum_percent,
        'red': int(center_red),
        'green': int(center_green),
        'blue': int(center_blue),
        'rainy_pixels': rainy_pixels,
        'total_pixels': total_pixels,
        'rainy_percent': rainy_percent,
        'radius': radius,
        'min_percent': minimum_percent,
    }
