"""Pure calculation helpers for Weather-based Water Level."""

MULTI_DAY = 'multi_day'
ZIMMERMAN = 'zimmerman'
ETO_FAO56 = 'eto_fao56'
METHODS = (MULTI_DAY, ZIMMERMAN, ETO_FAO56)


def normalize_method(value):
    value = str(value or MULTI_DAY)
    return value if value in METHODS else MULTI_DAY


def clamp(value, minimum, maximum):
    return max(float(minimum), min(float(maximum), float(value)))


def humidity_percent(value):
    """Normalize OSPy humidity (0..1) while accepting legacy percent inputs."""
    value = float(value)
    return value * 100.0 if -1.0 <= value <= 1.0 else value


def mean(values):
    return sum(values) / len(values) if values else None


def apply_limits(raw_adjustment, minimum, maximum):
    final = clamp(raw_adjustment, minimum, maximum)
    return {
        'raw_water_adjustment': round(float(raw_adjustment), 1),
        'water_adjustment': round(final, 1),
        'limited_by_min': raw_adjustment < minimum,
        'limited_by_max': raw_adjustment > maximum,
    }


def calculate_multi_day(days, base_mm_per_day, minimum, maximum):
    used = [day for day in days if day.get('hourly')]
    hourly = [item for day in used for item in day['hourly']]
    if not hourly:
        raise ValueError('missing_weather_data')

    temperature = mean([float(item['temperature']) for item in hourly])
    wind = mean([float(item['windSpeed']) for item in hourly])
    humidity = mean([humidity_percent(item['humidity']) for item in hourly])
    rain = sum(float(day.get('rain_mm', 0.0)) for day in days)
    normal_water = float(base_mm_per_day) * len(used)
    water_needed = normal_water
    water_needed *= 1.0 + (temperature - 20.0) / 15.0
    water_needed *= 1.0 + wind / 100.0
    water_needed *= 1.0 - (humidity - 50.0) / 200.0
    water_needed = max(0.0, water_needed)
    irrigation = max(0.0, min(100.0, water_needed - rain))
    raw = irrigation / normal_water * 100.0
    result = apply_limits(raw, minimum, maximum)
    result.update({
        'days_used': len(used),
        'rain_mm': round(rain, 2),
        'water_needed': round(water_needed, 2),
        'water_left': round(irrigation, 2),
        'average_temperature_c': round(temperature, 2),
        'average_wind_ms': round(wind, 2),
        'average_humidity': round(humidity, 2),
    })
    return result


def calculate_zimmerman(yesterday, today, reference_temp_c, reference_humidity,
                         minimum, maximum):
    hourly = yesterday.get('hourly') or []
    if not hourly:
        raise ValueError('missing_yesterday_weather_data')

    temperature = mean([float(item['temperature']) for item in hourly])
    humidity = mean([humidity_percent(item['humidity']) for item in hourly])
    rain_yesterday = float(yesterday.get('rain_mm', 0.0))
    rain_today = float(today.get('rain_mm', 0.0))
    temperature_factor = (temperature - float(reference_temp_c)) * 7.2
    humidity_factor = float(reference_humidity) - humidity
    rain_factor = (rain_yesterday + rain_today) * -7.8740157
    raw = 100.0 + temperature_factor + humidity_factor + rain_factor
    result = apply_limits(raw, minimum, maximum)
    result.update({
        'days_used': 1,
        'rain_mm': round(rain_yesterday + rain_today, 2),
        'water_needed': 0.0,
        'water_left': 0.0,
        'average_temperature_c': round(temperature, 2),
        'average_humidity': round(humidity, 2),
        'temperature_factor': round(temperature_factor, 2),
        'humidity_factor': round(humidity_factor, 2),
        'rain_factor': round(rain_factor, 2),
        'rain_yesterday': round(rain_yesterday, 2),
        'rain_today': round(rain_today, 2),
    })
    return result


def calculate_eto(days, today_rain, crop_coefficient, base_mm_per_day,
                  irrigation_efficiency, effective_rain, minimum, maximum):
    used = [day for day in days if day.get('eto') is not None]
    if not used:
        raise ValueError('missing_eto_data')

    coefficient = float(crop_coefficient)
    rain_ratio = float(effective_rain) / 100.0
    efficiency_ratio = float(irrigation_efficiency) / 100.0
    if efficiency_ratio <= 0:
        raise ValueError('invalid_irrigation_efficiency')

    rows = []
    total_eto = 0.0
    total_etc = 0.0
    historical_rain = 0.0
    for day in used:
        eto = max(0.0, float(day['eto']))
        etc = eto * coefficient
        rain = max(0.0, float(day.get('rain_mm', 0.0)))
        effective = rain * rain_ratio
        rows.append({
            'date': day['date'],
            'eto': round(eto, 2),
            'etc': round(etc, 2),
            'rain_mm': round(rain, 2),
            'effective_rain_mm': round(effective, 2),
            'deficit_mm': round(max(0.0, etc - effective), 2),
        })
        total_eto += eto
        total_etc += etc
        historical_rain += rain

    total_rain = historical_rain + max(0.0, float(today_rain))
    effective_total_rain = total_rain * rain_ratio
    net = max(0.0, total_etc - effective_total_rain)
    gross = net / efficiency_ratio
    normal_water = float(base_mm_per_day) * len(used)
    raw = gross / normal_water * 100.0
    result = apply_limits(raw, minimum, maximum)
    result.update({
        'days_used': len(used),
        'rain_mm': round(total_rain, 2),
        'water_needed': round(total_etc, 2),
        'water_left': round(gross, 2),
        'total_eto': round(total_eto, 2),
        'total_etc': round(total_etc, 2),
        'effective_rain_mm': round(effective_total_rain, 2),
        'net_irrigation_mm': round(net, 2),
        'gross_irrigation_mm': round(gross, 2),
        'rows': rows,
    })
    return result
