import importlib.util
import json
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
PLUGIN = ROOT / 'plugins' / 'irrigation_safety'
SPEC = importlib.util.spec_from_file_location(
    'irrigation_safety_model', PLUGIN / 'model.py')
model = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(model)


class IrrigationSafetyModelTests(unittest.TestCase):
    def test_profiles_follow_enabled_non_master_stations(self):
        stored = [{
            'station_id': 2, 'enabled': True,
            'minimum_flow_lpm': '3,5', 'maximum_flow_lpm': '8.5',
        }]
        profiles = model.normalize_profiles(stored, [(2, 'Beds'), (5, 'Trees')])
        self.assertEqual([item['station_id'] for item in profiles], [2, 5])
        self.assertEqual(profiles[0]['name'], 'Beds')
        self.assertEqual(profiles[0]['minimum_flow_lpm'], 3.5)
        self.assertTrue(profiles[0]['enabled'])
        self.assertFalse(profiles[1]['enabled'])

    def test_combined_range_requires_every_active_station(self):
        first = model.default_profile(1, 'First')
        first.update({'enabled': True, 'minimum_flow_lpm': 2,
                      'maximum_flow_lpm': 5, 'startup_delay': 10,
                      'confirm_seconds': 5})
        second = model.default_profile(2, 'Second')
        second.update({'enabled': True, 'minimum_flow_lpm': 3,
                       'maximum_flow_lpm': 8, 'startup_delay': 20,
                       'confirm_seconds': 8})
        expected = model.expected_range([1, 2], [first, second])
        self.assertEqual(expected['minimum'], 5)
        self.assertEqual(expected['maximum'], 13)
        self.assertEqual(expected['startup_delay'], 20)
        self.assertEqual(expected['confirm_seconds'], 8)
        second['enabled'] = False
        self.assertIsNone(model.expected_range([1, 2], [first, second]))

    def test_flow_faults_distinguish_missing_low_and_high(self):
        expected = {'minimum': 5, 'maximum': 10}
        self.assertEqual(model.flow_fault(None, expected), 'flow_unavailable')
        self.assertEqual(model.flow_fault(0, expected), 'no_flow')
        self.assertEqual(model.flow_fault(4.9, expected), 'low_flow')
        self.assertIsNone(model.flow_fault(7, expected))
        self.assertEqual(model.flow_fault(10.1, expected), 'high_flow')

    def test_learning_uses_robust_percentiles_and_margin(self):
        samples = [10.0] * 28 + [1.0, 100.0]
        learned = model.learned_range(samples, 20, 0.5)
        self.assertEqual(learned['median'], 10.0)
        self.assertEqual(learned['minimum'], 8.0)
        self.assertEqual(learned['maximum'], 12.0)
        self.assertEqual(learned['samples'], 30)

    def test_learning_rejects_too_few_or_non_positive_samples(self):
        with self.assertRaises(ValueError):
            model.learned_range([0, -1, 2, 3])

    def test_profile_validation_rejects_overlapping_limits(self):
        profile = model.default_profile(0, 'Station')
        profile['minimum_flow_lpm'] = 5
        profile['maximum_flow_lpm'] = 5
        with self.assertRaises(ValueError):
            model.validate_profile(profile)

    def test_confirmation_is_inclusive_at_boundary(self):
        self.assertFalse(model.confirmed(None, 20, 10))
        self.assertFalse(model.confirmed(10, 19.99, 10))
        self.assertTrue(model.confirmed(10, 20, 10))


class IrrigationSafetyInterfaceTests(unittest.TestCase):
    def test_manifest_declares_dependencies_provider_and_mobile(self):
        manifest = json.loads((PLUGIN / 'plugin.json').read_text(encoding='utf-8'))
        self.assertEqual(manifest['id'], 'irrigation_safety')
        self.assertEqual(manifest['version'], '1.0.0')
        self.assertEqual(manifest['ospy']['min'], '3.0.354')
        self.assertEqual(manifest['provider']['contract'], 'ospy.provider.v1')
        dependencies = {item['id']: item['required']
                        for item in manifest['dependencies']}
        self.assertTrue(dependencies['water_meter'])
        self.assertFalse(dependencies['pressure_monitor'])
        self.assertEqual(manifest['mobile']['api_version'], 1)

    def test_page_uses_slider_switches_cards_and_background_polling(self):
        template = (PLUGIN / 'templates' / 'irrigation_safety.html').read_text(
            encoding='utf-8')
        script = (PLUGIN / 'static' / 'irrigation_safety.js').read_text(
            encoding='utf-8')
        source = (PLUGIN / '__init__.py').read_text(encoding='utf-8')
        self.assertIn('class="safetySlider"', template)
        self.assertIn('class="safetyCard"', template)
        self.assertIn("('monitor', _('Monitor only'))", source)
        self.assertIn("('protect', _('Active protection'))", source)
        self.assertIn('start_learning', template)
        self.assertIn('acknowledge', template)
        self.assertIn('status_json', template)
        self.assertIn('window.setInterval(poll, 2000)', script)
        self.assertIn('textContent', script)
        self.assertNotIn('innerHTML', script)
        self.assertNotIn('<style>', template)

    def test_safety_action_precedes_notification_submission(self):
        source = (PLUGIN / '__init__.py').read_text(encoding='utf-8')
        reconcile = source[source.index('def _reconcile_incidents'):
                           source.index('def _enforce_lock')]
        self.assertLess(reconcile.index('_execute_safety_actions()'),
                        reconcile.index("notification_worker.submit('triggered'"))
        self.assertIn("'mode': 'off'", source)
        self.assertIn("if _mode() != 'protect'", source)

    def test_all_plugin_text_uses_gettext_without_catalog_files(self):
        help_template = (PLUGIN / 'templates' / 'irrigation_safety_help.html').read_text(
            encoding='utf-8')
        readme = (PLUGIN / 'README.md').read_text(encoding='utf-8')
        self.assertIn("$_('Purpose')", help_template)
        self.assertIn('All user-visible source strings use OSPy gettext', readme)
        self.assertEqual(list(PLUGIN.rglob('*.po')), [])
        self.assertEqual(list(PLUGIN.rglob('*.mo')), [])
        self.assertEqual(list(PLUGIN.rglob('*.pot')), [])


if __name__ == '__main__':
    unittest.main()
