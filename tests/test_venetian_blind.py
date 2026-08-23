import importlib.util
import datetime
import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
PLUGIN = ROOT / 'plugins' / 'venetian_blind'
SPEC = importlib.util.spec_from_file_location('venetian_blind_model', PLUGIN / 'blind_model.py')
model = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(model)


class VenetianBlindModelTests(unittest.TestCase):
    def test_structured_settings_are_loaded_directly(self):
        blind = model.default_blind('stable')
        blind.update({'profile': 'gen2', 'host': '192.168.1.20',
                      'tilt_positions': [15, 35, 65, 85]})
        loaded = model.stored_blinds({'blinds': [blind]}, lambda: 'new')
        self.assertEqual(loaded[0]['profile'], 'gen2')
        self.assertEqual(loaded[0]['tilt_positions'], [15, 35, 65, 85])
        self.assertEqual(model.stored_blinds({}, lambda: 'new'), [])

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

    def test_run_now_deadline_uses_the_last_real_program_interval(self):
        start = datetime.datetime(2026, 8, 23, 10, 0)

        class Program(object):
            stations = [0, 1]

            def __init__(self):
                self.start = start

            def active_intervals(self, _from, _to, station):
                return [{'end': start + datetime.timedelta(minutes=station + 1)}]

        self.assertEqual(
            model.run_now_deadline(Program()),
            start + datetime.timedelta(minutes=2),
        )
        Program.stations = []
        self.assertIsNone(model.run_now_deadline(Program()))

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

    def test_shading_rearms_only_after_all_blinds_transition_to_open(self):
        armed, was_open = model.shading_arm_state(False, False, True)
        self.assertTrue(armed)
        armed = False  # One automatic lowering action consumes the arm.
        armed, was_open = model.shading_arm_state(armed, was_open, True)
        self.assertFalse(armed)
        armed, was_open = model.shading_arm_state(armed, was_open, False)
        self.assertFalse(armed)  # Closed, tilted and intermediate are equivalent.
        armed, was_open = model.shading_arm_state(armed, was_open, False)
        self.assertFalse(armed)
        armed, was_open = model.shading_arm_state(armed, was_open, True)
        self.assertTrue(armed)  # Wind or a manual full opening rearms shading.


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
        self.assertIn('shading_arm_state(', source)
        self.assertIn('worker._shading_armed', source)
        self.assertNotIn('worker._temperature_action_sent', source)
        self.assertIn('sensor_temperature(sensors.get(index))', source)
        self.assertIn('if index < 0:', source)
        self.assertNotIn("getattr(sensor, 'value'", source)
        self.assertIn('log.active_runs()', source)
        self.assertIn('active = programs.run_now_program', source)
        self.assertIn('enabled_indices', source)
        self.assertIn('aggregate_blind_states(details, enabled_indices)', source)
        self.assertIn('_cancel_lowering_actions(worker)', source)
        self.assertIn('worker._program_queue.append(index)', source)
        self.assertIn('active = programs.run_now_program', source)
        self.assertIn('priority=True', source)
        self.assertIn('deadline <= datetime.datetime.now()', source)
        self.assertIn('programs.run_now_program = None', source)

    def test_structured_blinds_persist_and_mobile_cards_are_declared(self):
        source = (PLUGIN / '__init__.py').read_text(encoding='utf-8')
        self.assertIn("'blinds': []", source)
        self.assertNotIn("'blinds_migrated'", source)
        self.assertNotIn("'number_blinds'", source)
        self.assertNotIn('legacy_lists', source)
        self.assertIn('def mobile_status(', source)
        self.assertIn('def mobile_cards(', source)
        self.assertIn('def mobile_action(', source)
        self.assertIn("datetime_string(time.localtime(updated))", source)
        manifest = json.loads((PLUGIN / 'plugin.json').read_text(encoding='utf-8'))
        self.assertEqual(manifest['mobile']['api_version'], 1)
        self.assertEqual(
            set(manifest['mobile']['actions']),
            {'open', 'stop', 'closed', 'tilt1', 'tilt2', 'tilt3', 'tilt4'},
        )

    def test_manifest_version_dependency_and_permissions_are_current(self):
        manifest = json.loads((PLUGIN / 'plugin.json').read_text(encoding='utf-8'))
        self.assertEqual(manifest['version'], '1.2.4')
        self.assertIn('venetian_blind.css?v=1.2.3', (PLUGIN / 'templates' / 'venetian_blind_settings.html').read_text(encoding='utf-8'))
        self.assertIn('venetian_blind.css?v=1.2.3', (PLUGIN / 'templates' / 'venetian_blind_overview.html').read_text(encoding='utf-8'))
        self.assertIn('system', manifest['permissions'])
        self.assertIn('wind_monitor', [item['id'] for item in manifest['dependencies']])


if __name__ == '__main__':
    unittest.main()
