import ast
import datetime
import importlib.util
import json
import pathlib
import threading
import unittest


MODULE_PATH = (
    pathlib.Path(__file__).resolve().parents[1]
    / 'plugins'
    / 'chmi'
    / 'radar_analysis.py'
)
PLUGIN_PATH = MODULE_PATH.parent
PLUGIN_SOURCE_PATH = PLUGIN_PATH / '__init__.py'
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


class ChmiRainDelayControlTests(unittest.TestCase):
    @staticmethod
    def control_namespace():
        tree = ast.parse(PLUGIN_SOURCE_PATH.read_text(encoding='utf-8'))
        names = (
            'rain_delay_suppressed', '_set_rain_delay_suppressed',
            'remove_chmi_rain_delay', 'apply_chmi_rain_delay',
            'reset_rain_delay_suppression_after_dry_sample',
        )
        functions = [
            node for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name in names
        ]
        module = ast.Module(body=functions, type_ignores=[])
        ast.fix_missing_locations(module)
        namespace = {
            'datetime': datetime,
            'NAME': 'CHMI',
            'plugin_options': {'RAIN_DELAY_SUPPRESSED': False},
            'rain_blocks': {},
            'rain_delay_lock': threading.Lock(),
        }
        exec(compile(module, str(PLUGIN_SOURCE_PATH), 'exec'), namespace)
        return namespace

    def test_manual_removal_suppresses_only_chmi_until_dry_sample(self):
        control = self.control_namespace()
        other_end = datetime.datetime.now() + datetime.timedelta(hours=2)
        control['rain_blocks'].update({
            'CHMI': datetime.datetime.now() + datetime.timedelta(hours=1),
            'Other plug-in': other_end,
        })

        self.assertTrue(control['remove_chmi_rain_delay'](True))
        self.assertTrue(control['rain_delay_suppressed']())
        self.assertNotIn('CHMI', control['rain_blocks'])
        self.assertEqual(control['rain_blocks']['Other plug-in'], other_end)
        self.assertFalse(control['apply_chmi_rain_delay'](1))
        self.assertNotIn('CHMI', control['rain_blocks'])

        self.assertTrue(control['reset_rain_delay_suppression_after_dry_sample']())
        self.assertFalse(control['rain_delay_suppressed']())
        self.assertTrue(control['apply_chmi_rain_delay'](1))
        self.assertIn('CHMI', control['rain_blocks'])

    def test_disabling_control_removes_chmi_without_suppressing_future_rain(self):
        control = self.control_namespace()
        control['rain_blocks']['CHMI'] = (
            datetime.datetime.now() + datetime.timedelta(hours=1)
        )
        self.assertTrue(control['remove_chmi_rain_delay'](False))
        self.assertFalse(control['rain_delay_suppressed']())
        self.assertNotIn('CHMI', control['rain_blocks'])

        source = PLUGIN_SOURCE_PATH.read_text(encoding='utf-8')
        self.assertIn(
            "plugin_options.web_update(qdict, skipped=['RAIN_DELAY_SUPPRESSED'])",
            source,
        )
        self.assertIn("if not plugin_options['USE_RAIN_DELAY']:", source)

    def test_release_and_interface_document_override_behaviour(self):
        manifest = json.loads(
            (PLUGIN_PATH / 'plugin.json').read_text(encoding='utf-8')
        )
        template = (PLUGIN_PATH / 'templates' / 'chmi.html').read_text(
            encoding='utf-8'
        )
        help_text = (PLUGIN_PATH / 'templates' / 'chmi_help.html').read_text(
            encoding='utf-8'
        )
        self.assertEqual(manifest['version'], '1.0.7')
        self.assertIn('Remove CHMI Rain Delay', template)
        self.assertIn("RAIN_DELAY_SUPPRESSED", template)
        self.assertIn('current rainy period', help_text)


if __name__ == '__main__':
    unittest.main()
