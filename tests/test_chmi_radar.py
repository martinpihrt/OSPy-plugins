import importlib.util
import pathlib
import unittest


MODULE_PATH = (
    pathlib.Path(__file__).resolve().parents[1]
    / 'plugins'
    / 'chmi'
    / 'radar_analysis.py'
)
SPEC = importlib.util.spec_from_file_location('chmi_radar_analysis', MODULE_PATH)
analysis = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(analysis)


class FakeBitmap:
    def __init__(self, pixels):
        self._pixels = pixels
        self.height = len(pixels)
        self.width = len(pixels[0])

    def getpixel(self, coordinates):
        x, y = coordinates
        return self._pixels[y][x]


class ChmiRadarAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.channels = {
            'red_enabled': True,
            'red_threshold': 200,
            'green_enabled': False,
            'green_threshold': 100,
            'blue_enabled': False,
            'blue_threshold': 100,
        }

    def test_exact_location_rgb_is_reported_below_threshold(self):
        bitmap = FakeBitmap([
            [(0, 0, 0), (0, 0, 0), (0, 0, 0)],
            [(0, 0, 0), (120, 40, 80), (0, 0, 0)],
            [(0, 0, 0), (0, 0, 0), (0, 0, 0)],
        ])
        result = analysis.analyze_location_pixels(
            bitmap, 1, 1, 1, 10, self.channels)
        self.assertEqual(
            (result['red'], result['green'], result['blue']),
            (120, 40, 80))
        self.assertFalse(result['rain'])
        self.assertEqual(result['rainy_pixels'], 0)

    def test_area_threshold_is_independent_from_center_rgb(self):
        bitmap = FakeBitmap([
            [(0, 0, 0), (240, 0, 0), (0, 0, 0)],
            [(240, 0, 0), (10, 20, 30), (240, 0, 0)],
            [(0, 0, 0), (240, 0, 0), (0, 0, 0)],
        ])
        result = analysis.analyze_location_pixels(
            bitmap, 1, 1, 1, 50, self.channels)
        self.assertEqual(
            (result['red'], result['green'], result['blue']),
            (10, 20, 30))
        self.assertEqual(result['rainy_pixels'], 4)
        self.assertEqual(result['total_pixels'], 5)
        self.assertEqual(result['rainy_percent'], 80)
        self.assertTrue(result['rain'])

    def test_disabled_channels_do_not_match(self):
        channels = dict(self.channels)
        channels['red_enabled'] = False
        self.assertFalse(
            analysis.pixel_matches_threshold(255, 255, 255, channels))


if __name__ == '__main__':
    unittest.main()
