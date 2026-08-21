import importlib.util
import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
PLUGIN = ROOT / 'plugins' / 'venetian_blind'
SPEC = importlib.util.spec_from_file_location('venetian_blind_model', PLUGIN / 'blind_model.py')
model = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(model)


class VenetianBlindModelTests(unittest.TestCase):
    def test_legacy_settings_migrate_without_changing_urls_or_labels(self):
        settings = {'number_blinds': 1, 'label': ['South'], 'open': ['http://a/open'], 'stop': ['http://a/stop'], 'close': ['http://a/close'], 'status': ['http://a/status'], 'label0': ['Closed'], 'label100': ['Open']}
        blinds = model.configured_blinds(settings, lambda: 'stable')
        self.assertEqual(blinds[0]['profile'], 'custom')
        self.assertEqual(blinds[0]['label'], 'South')
        self.assertEqual(model.command_url(blinds[0], 'open'), 'http://a/open')
        self.assertEqual(model.status_url(blinds[0]), 'http://a/status')

    def test_legacy_shelly_gen1_urls_restore_the_gen1_profile_and_host(self):
        settings = {
            'number_blinds': 1,
            'label': ['South'],
            'open': ['http://192.168.1.20/roller/0?go=open'],
            'stop': ['http://192.168.1.20/roller/0?go=stop'],
            'close': ['http://192.168.1.20/roller/0?go=close'],
            'status': ['http://192.168.1.20/status'],
        }
        blind = model.configured_blinds(settings, lambda: 'stable')[0]
        self.assertEqual(blind['profile'], 'gen1')
        self.assertEqual(blind['host'], 'http://192.168.1.20')

    def test_already_migrated_gen1_urls_are_repaired_without_touching_custom_sets(self):
        migrated = model.default_blind('stable')
        migrated.update({
            'profile': 'custom',
            'host': '',
            'open_url': 'http://192.168.1.20/roller/0?go=open',
            'stop_url': 'http://192.168.1.20/roller/0?go=stop',
            'close_url': 'http://192.168.1.20/roller/0?go=close',
            'status_url': 'http://192.168.1.20/status',
        })
        repaired = model.configured_blinds({'blinds': [migrated]}, lambda: 'new')[0]
        self.assertEqual(repaired['profile'], 'gen1')
        self.assertEqual(repaired['host'], 'http://192.168.1.20')
        migrated['stop_url'] = 'http://192.168.1.20/custom-stop'
        custom = model.configured_blinds({'blinds': [migrated]}, lambda: 'new')[0]
        self.assertEqual(custom['profile'], 'custom')

    def test_gen1_and_gen2_commands_use_the_correct_api(self):
        blind = model.default_blind('a')
        blind['host'] = '192.168.1.20'
        self.assertEqual(model.status_url(blind), 'http://192.168.1.20/status')
        self.assertIn('go=to_pos&roller_pos=20', model.command_url(blind, 'tilt1'))
        blind['profile'] = 'gen2'
        self.assertIn('Cover.GetStatus?id=0', model.status_url(blind))
        self.assertIn('Cover.GoToPosition?id=0&pos=80', model.command_url(blind, 'tilt4'))

    def test_status_parser_supports_gen1_gen2_and_custom_gen1_payloads(self):
        gen1 = {'rollers': [{'state': 'stop', 'current_pos': 40, 'power': 0}]}
        gen2 = {'state': 'stopped', 'current_pos': 80, 'apower': 0}
        self.assertEqual(model.parse_status(gen1, 'gen1')['position'], 40)
        self.assertEqual(model.parse_status(gen1, 'custom')['position'], 40)
        self.assertEqual(model.parse_status(gen2, 'gen2')['position'], 80)

    def test_four_tilt_positions_are_classified_with_tolerance(self):
        positions = [20, 40, 60, 80]
        self.assertEqual(model.position_state(0, positions), 'closed')
        self.assertEqual(model.position_state(22, positions), 'tilt1')
        self.assertEqual(model.position_state(79, positions), 'tilt4')
        self.assertEqual(model.position_state(100, positions), 'open')
        self.assertEqual(model.position_state(51, positions), 'position')

    def test_time_window_supports_daytime_overnight_and_full_day(self):
        self.assertTrue(model.in_time_window(9 * 60, 8 * 60, 20 * 60))
        self.assertFalse(model.in_time_window(21 * 60, 8 * 60, 20 * 60))
        self.assertTrue(model.in_time_window(23 * 60, 20 * 60, 8 * 60))
        self.assertTrue(model.in_time_window(12 * 60, 0, 0))

    def test_temperature_uses_the_real_ospy_sensor_channel(self):
        class Sensor(object):
            manufacturer = 0
            sens_type = 5
            multi_type = 0
            last_read_value = [28.4, '', '', '', '', '', '', '', '']

        self.assertEqual(model.sensor_temperature(Sensor()), 28.4)
        Sensor.last_read_value[0] = -127
        self.assertIsNone(model.sensor_temperature(Sensor()))
        Sensor.sens_type = 6
        Sensor.multi_type = 2
        Sensor.last_read_value[2] = 31.2
        self.assertEqual(model.sensor_temperature(Sensor()), 31.2)
        Sensor.manufacturer = 1
        Sensor.last_read_value[2] = [29.7]
        self.assertEqual(model.sensor_temperature(Sensor()), 29.7)

    def test_wind_confirmation_counts_unique_samples_inside_the_interval(self):
        state = model.wind_window_state([(100, 11), (200, 4), (250, 12)], 260, 10, 2, 2, 300)
        self.assertTrue(state['strong'])
        self.assertEqual(state['exceedances'], 2)
        self.assertFalse(state['safe'])
        state = model.wind_window_state([(240, 4), (250, 5)], 260, 10, 2, 2, 60)
        self.assertTrue(state['safe'])
        self.assertFalse(state['strong'])
        stale = model.wind_window_state([(100, 4), (110, 5)], 260, 10, 2, 2, 300)
        self.assertFalse(stale['safe'])

    def test_mixed_or_unreachable_blinds_never_count_as_all_open_or_closed(self):
        details = {index: {'reachable': True, 'state': 'closed'} for index in range(9)}
        details[8]['state'] = 'open'
        mixed = model.aggregate_blind_states(details, range(9))
        self.assertFalse(mixed['all_open'])
        self.assertFalse(mixed['all_closed'])
        details = {index: {'reachable': True, 'state': 'open'} for index in range(9)}
        details[8] = {'reachable': False, 'state': 'unknown'}
        unreachable = model.aggregate_blind_states(details, range(9))
        self.assertFalse(unreachable['all_open'])
        self.assertEqual(unreachable['known_count'], 8)
        details[8] = {'reachable': True, 'state': 'open'}
        self.assertTrue(model.aggregate_blind_states(details, range(9))['all_open'])


class VenetianBlindInterfaceTests(unittest.TestCase):
    def test_settings_use_crud_profiles_and_no_blind_count_input(self):
        template = (PLUGIN / 'templates' / 'venetian_blind_settings.html').read_text(encoding='utf-8')
        self.assertNotIn('name="number_blinds"', template)
        for value in ('save_blind', 'delete_blind', 'gen1', 'gen2', 'custom'):
            self.assertIn(value, template)
        self.assertIn("$_('Add blind')", template)
        self.assertIn("$_('Edit')", template)
        self.assertIn("$_('Delete')", template)
        self.assertNotIn('name="temperature_hysteresis"', template)
        self.assertIn('name="strong_wind_interval"', template)

    def test_command_returns_to_the_same_blind_editor(self):
        source = (PLUGIN / '__init__.py').read_text(encoding='utf-8')
        self.assertIn("if action == 'test_command' and requested:", source)
        self.assertIn("'&action=edit&blind=' + quote_plus(requested)", source)

    def test_all_visible_checkboxes_use_sliding_switches(self):
        template = (PLUGIN / 'templates' / 'venetian_blind_settings.html').read_text(encoding='utf-8')
        css = (PLUGIN / 'static' / 'venetian_blind.css').read_text(encoding='utf-8')
        self.assertEqual(template.count('type="checkbox"'), 5)
        self.assertEqual(template.count('class="blindSwitch"'), 5)
        self.assertEqual(template.count('class="blindSlider"'), 5)
        self.assertIn('.blindSwitch input:checked+.blindSlider', css)

    def test_overview_has_four_tilt_controls_and_csrf_post_commands(self):
        template = (PLUGIN / 'templates' / 'venetian_blind_overview.html').read_text(encoding='utf-8')
        self.assertIn('range(4)', template)
        self.assertIn('method="post"', template)
        self.assertIn('csrf_input()', template)
        self.assertIn("plugin_options['view_mode']=='list'", template)

    def test_automation_uses_unique_wind_samples_and_authoritative_positions(self):
        source = (PLUGIN / '__init__.py').read_text(encoding='utf-8')
        self.assertIn('measurement_key != worker._last_wind_measurement', source)
        self.assertIn('wind_window_state(', source)
        self.assertIn("worker._wind_action_sent", source)
        self.assertIn("worker._temperature_action_sent", source)
        self.assertIn('sensor_temperature(sensors.get(index))', source)
        self.assertIn('if index < 0:', source)
        self.assertNotIn("getattr(sensor, 'value'", source)
        self.assertIn('log.active_runs()', source)
        self.assertIn('run_now = programs.run_now_program', source)
        self.assertIn('enabled_indices', source)
        self.assertIn('aggregate_blind_states(details, enabled_indices)', source)
        self.assertIn('_cancel_lowering_actions(worker)', source)
        self.assertIn('worker._program_queue.append(index)', source)
        self.assertIn('programs.run_now_program is not None', source)
        self.assertIn('priority=True', source)

    def test_manifest_version_dependency_and_permissions_are_current(self):
        manifest = json.loads((PLUGIN / 'plugin.json').read_text(encoding='utf-8'))
        self.assertEqual(manifest['version'], '1.2.1')
        self.assertIn('venetian_blind.css?v=1.2.1', (PLUGIN / 'templates' / 'venetian_blind_settings.html').read_text(encoding='utf-8'))
        self.assertIn('venetian_blind.css?v=1.2.1', (PLUGIN / 'templates' / 'venetian_blind_overview.html').read_text(encoding='utf-8'))
        self.assertIn('system', manifest['permissions'])
        self.assertIn('wind_monitor', [item['id'] for item in manifest['dependencies']])


if __name__ == '__main__':
    unittest.main()
