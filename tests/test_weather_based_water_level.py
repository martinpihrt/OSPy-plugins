import importlib.util
import pathlib
import unittest


MODULE_PATH = (
    pathlib.Path(__file__).resolve().parents[1]
    / 'plugins'
    / 'weather_based_water_level'
    / 'methods.py'
)
SPEC = importlib.util.spec_from_file_location('weather_water_methods', MODULE_PATH)
methods = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(methods)


def hourly(temp=20.0, humidity=0.5, wind=0.0):
    return [{'temperature': temp, 'humidity': humidity, 'windSpeed': wind}]


class WeatherBasedWaterLevelMethodTests(unittest.TestCase):
    def test_missing_or_invalid_legacy_method_uses_multi_day(self):
        self.assertEqual(methods.normalize_method(None), methods.MULTI_DAY)
        self.assertEqual(methods.normalize_method('unknown'), methods.MULTI_DAY)
        self.assertEqual(methods.normalize_method(methods.ETO_FAO56), methods.ETO_FAO56)

    def test_humidity_normalizes_ospy_fraction_and_accepts_percent(self):
        self.assertEqual(methods.humidity_percent(0.65), 65.0)
        self.assertEqual(methods.humidity_percent(65), 65.0)

    def test_multi_day_neutral_weather_returns_100_percent(self):
        result = methods.calculate_multi_day(
            [{'hourly': hourly(), 'rain_mm': 0.0}],
            base_mm_per_day=4.0,
            minimum=0,
            maximum=200,
        )
        self.assertEqual(result['water_adjustment'], 100.0)
        self.assertEqual(result['average_humidity'], 50.0)

    def test_multi_day_applies_rain_and_limits(self):
        result = methods.calculate_multi_day(
            [{'hourly': hourly(), 'rain_mm': 4.0}],
            base_mm_per_day=4.0,
            minimum=20,
            maximum=200,
        )
        self.assertEqual(result['raw_water_adjustment'], 0.0)
        self.assertEqual(result['water_adjustment'], 20.0)
        self.assertTrue(result['limited_by_min'])

    def test_multi_day_requires_weather(self):
        with self.assertRaisesRegex(ValueError, 'missing_weather_data'):
            methods.calculate_multi_day(
                [{'hourly': [], 'rain_mm': 0.0}], 4.0, 0, 200)

    def test_zimmerman_reference_weather_returns_100_percent(self):
        result = methods.calculate_zimmerman(
            {'hourly': hourly(temp=21.1, humidity=0.3), 'rain_mm': 0.0},
            {'hourly': hourly(), 'rain_mm': 0.0},
            reference_temp_c=21.1,
            reference_humidity=30.0,
            minimum=0,
            maximum=200,
        )
        self.assertEqual(result['water_adjustment'], 100.0)

    def test_zimmerman_factors_match_classic_coefficients(self):
        result = methods.calculate_zimmerman(
            {'hourly': hourly(temp=22.1, humidity=0.4), 'rain_mm': 1.0},
            {'hourly': hourly(), 'rain_mm': 1.0},
            reference_temp_c=21.1,
            reference_humidity=30.0,
            minimum=0,
            maximum=200,
        )
        self.assertEqual(result['temperature_factor'], 7.2)
        self.assertEqual(result['humidity_factor'], -10.0)
        self.assertAlmostEqual(result['rain_factor'], -15.75, places=2)
        self.assertEqual(result['water_adjustment'], 81.5)

    def test_zimmerman_requires_yesterday_weather(self):
        with self.assertRaisesRegex(ValueError, 'missing_yesterday_weather_data'):
            methods.calculate_zimmerman(
                {'hourly': [], 'rain_mm': 0.0},
                {'hourly': [], 'rain_mm': 0.0},
                21.1, 30.0, 0, 200)

    def test_eto_calculates_crop_rain_and_efficiency(self):
        result = methods.calculate_eto(
            [
                {'date': '2026-07-24', 'eto': 4.0, 'rain_mm': 1.0},
                {'date': '2026-07-25', 'eto': 6.0, 'rain_mm': 1.0},
            ],
            today_rain=2.0,
            crop_coefficient=1.0,
            base_mm_per_day=4.0,
            irrigation_efficiency=80.0,
            effective_rain=50.0,
            minimum=0,
            maximum=200,
        )
        self.assertEqual(result['total_etc'], 10.0)
        self.assertEqual(result['effective_rain_mm'], 2.0)
        self.assertEqual(result['net_irrigation_mm'], 8.0)
        self.assertEqual(result['gross_irrigation_mm'], 10.0)
        self.assertEqual(result['water_adjustment'], 125.0)

    def test_eto_requires_at_least_one_complete_day(self):
        with self.assertRaisesRegex(ValueError, 'missing_eto_data'):
            methods.calculate_eto(
                [{'date': '2026-07-25', 'eto': None, 'rain_mm': 0.0}],
                0.0, 1.0, 4.0, 100.0, 100.0, 0, 200)

    def test_all_methods_use_common_clamp(self):
        result = methods.apply_limits(250.0, 10, 180)
        self.assertEqual(result['water_adjustment'], 180.0)
        self.assertTrue(result['limited_by_max'])


if __name__ == '__main__':
    unittest.main()
