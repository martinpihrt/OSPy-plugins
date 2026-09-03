import importlib.util
import json
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
PLUGIN = ROOT / 'plugins' / 'thermostat'
SPEC = importlib.util.spec_from_file_location(
    'thermostat_model', PLUGIN / 'model.py')
model = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(model)


class ThermostatModelTests(unittest.TestCase):
    def test_legacy_zones_gain_stable_fields_without_fixed_padding(self):
        legacy = [{
            'enabled': True,
            'name': 'Boiler room',
            'source': 'air_temp',
            'channel': 2,
            'low_temp': 20.1,
            'high_temp': 20.5,
            'low_action': 'start',
            'high_action': 'stop',
            'program': 1,
        }]
        ids = iter(('stable-id',))
        zones = model.normalize_zones(
            legacy, 3, lambda: next(ids),
            lambda index: 'Thermostat {}'.format(index + 1))
        self.assertEqual(len(zones), 1)
        self.assertEqual(zones[0]['id'], 'stable-id')
        self.assertFalse(zones[0]['time_limited'])
        self.assertEqual(zones[0]['start_time'], '06:00')
        self.assertEqual(zones[0]['end_time'], '22:00')
        self.assertEqual(zones[0]['channel'], 2)

    def test_normalization_limits_cards_and_repairs_duplicate_ids(self):
        stored = []
        for index in range(25):
            zone = model.default_zone('Thermostat {}'.format(index + 1))
            zone['id'] = 'duplicate'
            stored.append(zone)
        counter = iter('id-{}'.format(index) for index in range(30))
        zones = model.normalize_zones(
            stored, 30, lambda: next(counter),
            lambda index: 'Thermostat {}'.format(index + 1))
        self.assertEqual(len(zones), model.MAX_THERMOSTATS)
        self.assertEqual(len({zone['id'] for zone in zones}), model.MAX_THERMOSTATS)

    def test_time_window_supports_daytime_and_overnight_boundaries(self):
        self.assertTrue(model.in_time_window(8 * 60, 8 * 60, 20 * 60))
        self.assertTrue(model.in_time_window(19 * 60 + 59, 8 * 60, 20 * 60))
        self.assertFalse(model.in_time_window(20 * 60, 8 * 60, 20 * 60))
        self.assertTrue(model.in_time_window(22 * 60, 22 * 60, 6 * 60))
        self.assertTrue(model.in_time_window(5 * 60 + 59, 22 * 60, 6 * 60))
        self.assertFalse(model.in_time_window(6 * 60, 22 * 60, 6 * 60))
        self.assertFalse(model.in_time_window(12 * 60, 12 * 60, 12 * 60))

    def test_continuous_zone_ignores_operating_times(self):
        zone = model.default_zone('Continuous')
        zone['start_time'] = '10:00'
        zone['end_time'] = '11:00'
        self.assertTrue(model.zone_in_time_window(zone, 23 * 60))

    def test_equal_or_invalid_limited_times_are_rejected(self):
        zone = model.default_zone('Limited')
        zone['time_limited'] = True
        zone['start_time'] = '06:00'
        zone['end_time'] = '06:00'
        with self.assertRaises(ValueError):
            model.validate_zone(zone)
        self.assertFalse(model.valid_time('24:00'))
        self.assertFalse(model.valid_time('8:00'))

    def test_next_boundary_is_independent_of_check_interval(self):
        zone = model.default_zone('Day')
        zone.update({
            'enabled': True,
            'time_limited': True,
            'start_time': '08:00',
            'end_time': '20:00',
        })
        self.assertEqual(
            model.seconds_until_boundary(19 * 3600 + 59 * 60 + 30, [zone]),
            30,
        )
        self.assertEqual(
            model.seconds_until_boundary(20 * 3600, [zone]),
            12 * 3600,
        )
        zone['time_limited'] = False
        self.assertIsNone(model.seconds_until_boundary(0, [zone]))

    def test_only_enabled_thermostats_must_use_distinct_programs(self):
        first = model.default_zone('First')
        first.update({'id': 'first', 'enabled': True, 'program': 2})
        second = model.default_zone('Second')
        second.update({'id': 'second', 'enabled': True, 'program': 2})
        self.assertTrue(model.duplicate_enabled_program([first], second))
        self.assertEqual(model.duplicate_enabled_program_ids([first, second]), {2})
        second['enabled'] = False
        self.assertFalse(model.duplicate_enabled_program([first], second))
        self.assertEqual(model.duplicate_enabled_program_ids([first, second]), set())

    def test_invalid_temperature_hysteresis_is_rejected(self):
        zone = model.default_zone('Invalid')
        zone['low_temp'] = 22.6
        zone['high_temp'] = 22.4
        with self.assertRaises(ValueError):
            model.validate_zone(zone)


class ThermostatInterfaceTests(unittest.TestCase):
    def test_settings_use_crud_cards_time_inputs_and_slider_switches(self):
        template = (PLUGIN / 'templates' / 'thermostat.html').read_text(
            encoding='utf-8')
        self.assertIn('value="save_zone"', template)
        self.assertIn('value="delete_zone"', template)
        self.assertIn("_('Add thermostat')", template)
        self.assertIn("_('Edit')", template)
        self.assertIn('name="time_limited" type="checkbox"', template)
        self.assertIn('name="start_time" type="time"', template)
        self.assertIn('name="end_time" type="time"', template)
        self.assertIn('class="thermostatSlider"', template)
        self.assertIn('/plugins/thermostat/static/thermostat.css?v=1.1.1', template)
        self.assertIn('class="thermostatCardTitle"', template)
        self.assertIn('thermostatCardEnabled', template)
        self.assertIn('thermostatCardDisabled', template)
        self.assertIn('thermostatCardButton', template)
        self.assertNotIn('<style>', template)
        self.assertNotIn('enabled${i}', template)

    def test_limit_version_and_documentation_are_updated(self):
        manifest = json.loads((PLUGIN / 'plugin.json').read_text(encoding='utf-8'))
        readme = (PLUGIN / 'README.md').read_text(encoding='utf-8')
        help_template = (PLUGIN / 'templates' / 'thermostat_help.html').read_text(
            encoding='utf-8')
        self.assertEqual(model.MAX_THERMOSTATS, 20)
        self.assertEqual(manifest['version'], '1.1.1')
        self.assertIn('Up to 20 thermostats', readme)
        self.assertIn('Overnight windows', readme)
        self.assertIn("$_('Create, edit or delete up to 20 thermostat cards.", help_template)

    def test_translation_catalog_files_are_not_part_of_the_plugin_change(self):
        self.assertEqual(list(PLUGIN.rglob('*.po')), [])
        self.assertEqual(list(PLUGIN.rglob('*.mo')), [])
        self.assertEqual(list(PLUGIN.rglob('*.pot')), [])


if __name__ == '__main__':
    unittest.main()
