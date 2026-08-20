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


class VenetianBlindInterfaceTests(unittest.TestCase):
    def test_settings_use_crud_profiles_and_no_blind_count_input(self):
        template = (PLUGIN / 'templates' / 'venetian_blind_settings.html').read_text(encoding='utf-8')
        self.assertNotIn('name="number_blinds"', template)
        for value in ('save_blind', 'delete_blind', 'gen1', 'gen2', 'custom'):
            self.assertIn(value, template)
        self.assertIn("$_('Add blind')", template)
        self.assertIn("$_('Edit')", template)
        self.assertIn("$_('Delete')", template)

    def test_overview_has_four_tilt_controls_and_csrf_post_commands(self):
        template = (PLUGIN / 'templates' / 'venetian_blind_overview.html').read_text(encoding='utf-8')
        self.assertIn('range(4)', template)
        self.assertIn('method="post"', template)
        self.assertIn('csrf_input()', template)
        self.assertIn("plugin_options['view_mode']=='list'", template)

    def test_automation_requires_safe_samples_and_latches_actions(self):
        source = (PLUGIN / '__init__.py').read_text(encoding='utf-8')
        self.assertIn("all(value < plugin_options['wind_limit']", source)
        self.assertIn("all(value >= plugin_options['wind_limit']", source)
        self.assertIn("worker._automation_latch != 'open'", source)
        self.assertIn("worker._automation_latch != 'closed'", source)
        self.assertIn('log.active_runs()', source)
        self.assertIn('run_now = programs.run_now_program', source)
        self.assertIn('enabled_indices', source)
        self.assertIn('worker._program_queue.append(index)', source)
        self.assertIn('programs.run_now_program is not None', source)
        self.assertIn('priority=True', source)

    def test_manifest_version_dependency_and_permissions_are_current(self):
        manifest = json.loads((PLUGIN / 'plugin.json').read_text(encoding='utf-8'))
        self.assertEqual(manifest['version'], '1.1.0')
        self.assertIn('system', manifest['permissions'])
        self.assertIn('wind_monitor', [item['id'] for item in manifest['dependencies']])


if __name__ == '__main__':
    unittest.main()
