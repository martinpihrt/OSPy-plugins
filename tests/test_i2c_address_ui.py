import json
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class SelectableI2cAddressUiTests(unittest.TestCase):
    def test_conflicts_render_inline_alerts_in_both_plugins(self):
        definitions = (
            ('wind_monitor', 'wind_monitor_settings'),
            ('water_meter', 'water_meter_settings'),
        )
        for plugin, template_name in definitions:
            with self.subTest(plugin=plugin):
                source = (ROOT / 'plugins' / plugin / '__init__.py').read_text(
                    encoding='utf-8-sig'
                )
                template = (
                    ROOT / 'plugins' / plugin / 'templates' /
                    '{}.html'.format(template_name)
                ).read_text(encoding='utf-8-sig')
                self.assertNotIn('raise web.badrequest(address_error)', source)
                self.assertIn('address_error', source)
                self.assertIn('validation_error=None', template)
                self.assertIn('class="alert" role="alert"', template)
                self.assertIn('$validation_error', template)

    def test_inline_alert_release_versions_are_incremented(self):
        expected = {
            'wind_monitor': '1.2.3',
            'water_meter': '1.2.1',
        }
        for plugin, version in expected.items():
            with self.subTest(plugin=plugin):
                manifest = json.loads(
                    (ROOT / 'plugins' / plugin / 'plugin.json').read_text(
                        encoding='utf-8-sig'
                    )
                )
                self.assertEqual(manifest['version'], version)


if __name__ == '__main__':
    unittest.main()
