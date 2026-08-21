import importlib.util
import ast
import json
import pathlib
import sys
import types
import unittest
from types import SimpleNamespace
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    'automation_rules_engine',
    ROOT / 'plugins' / 'automation_rules' / 'engine.py',
)
ENGINE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ENGINE)

SENSOR_MODULES = {
    'ospy': types.ModuleType('ospy'),
    'ospy.options': types.ModuleType('ospy.options'),
    'ospy.provider_contracts': types.ModuleType('ospy.provider_contracts'),
    'ospy.sensors': types.ModuleType('ospy.sensors'),
}
SENSOR_MODULES['ospy.options'].options = SimpleNamespace(temp_unit='C')
SENSOR_MODULES['ospy.provider_contracts'].utc_timestamp = lambda value=None: (
    '2026-08-21T12:00:00Z')
SENSOR_MODULES['ospy.sensors'].sensors = SimpleNamespace(get=lambda: [])
with mock.patch.dict(sys.modules, SENSOR_MODULES):
    SENSOR_SPEC = importlib.util.spec_from_file_location(
        'automation_rules_sensor_provider',
        ROOT / 'plugins' / 'automation_rules' / 'sensor_provider.py',
    )
    SENSOR_PROVIDER = importlib.util.module_from_spec(SENSOR_SPEC)
    SENSOR_SPEC.loader.exec_module(SENSOR_PROVIDER)


def snapshot(fill=20, pressure=True):
    return {'providers': {
        'tank_monitor': {
            'status': 'ok', 'resources': [{
                'id': 'tank-1', 'status': 'ok',
                'values': [{'id': 'fill_percent', 'value': fill, 'unit': '%'}],
            }],
        },
        'pressure_monitor': {
            'status': 'ok', 'resources': [{
                'id': 'main', 'status': 'ok',
                'values': [{'id': 'pressure_present', 'value': pressure, 'unit': ''}],
            }],
        },
    }}


def rule(mode='all'):
    return {
        'id': 'low-tank', 'name': 'Low tank', 'enabled': True,
        'mode': mode, 'hold_seconds': 10, 'repeat_seconds': 60,
        'notify_on_clear': True, 'severity': 'warning',
        'channels': ['home', 'browser', 'push', 'email'],
        'conditions': [
            {'id': 'tank-low', 'provider_id': 'tank_monitor',
             'resource_id': 'tank-1', 'value_id': 'fill_percent',
             'operator': 'lte', 'expected': 25},
            {'id': 'pressure-ok', 'provider_id': 'pressure_monitor',
             'resource_id': 'main', 'value_id': 'pressure_present',
             'operator': 'is_true', 'expected': True},
        ],
    }


class AutomationRuleEngineTests(unittest.TestCase):
    def test_all_and_any_conditions(self):
        result = ENGINE.evaluate_rule(rule('all'), snapshot(fill=20, pressure=True))
        self.assertTrue(result['available'])
        self.assertTrue(result['matched'])
        result = ENGINE.evaluate_rule(rule('all'), snapshot(fill=30, pressure=True))
        self.assertFalse(result['matched'])
        result = ENGINE.evaluate_rule(rule('any'), snapshot(fill=30, pressure=True))
        self.assertTrue(result['matched'])

    def test_missing_provider_is_unavailable_and_never_matches(self):
        data = snapshot()
        del data['providers']['pressure_monitor']
        result = ENGINE.evaluate_rule(rule(), data)
        self.assertFalse(result['available'])
        self.assertFalse(result['matched'])
        self.assertEqual(result['conditions'][1]['reason'], 'provider_unavailable')

    def test_hold_trigger_repeat_and_clear_transitions(self):
        definition = rule()
        matched = ENGINE.evaluate_rule(definition, snapshot())
        state, event = ENGINE.transition(definition, matched, now=100)
        self.assertEqual(event, 'none')
        state, event = ENGINE.transition(definition, matched, state, now=109)
        self.assertEqual(event, 'none')
        state, event = ENGINE.transition(definition, matched, state, now=110)
        self.assertEqual(event, 'triggered')
        self.assertTrue(state['active'])
        state, event = ENGINE.transition(definition, matched, state, now=169)
        self.assertEqual(event, 'none')
        state, event = ENGINE.transition(definition, matched, state, now=170)
        self.assertEqual(event, 'repeated')
        clear = ENGINE.evaluate_rule(definition, snapshot(fill=50, pressure=False))
        state, event = ENGINE.transition(definition, clear, state, now=171)
        self.assertEqual(event, 'cleared')
        self.assertFalse(state['active'])

    def test_unavailable_values_do_not_clear_an_active_incident(self):
        definition = rule()
        state = {'active': True, 'matched_since': 10, 'last_trigger': 20}
        unavailable = ENGINE.evaluate_rule(definition, {'providers': {}})
        next_state, event = ENGINE.transition(definition, unavailable, state, now=30)
        self.assertEqual(event, 'unavailable')
        self.assertTrue(next_state['active'])

    def test_validation_rejects_unsafe_or_ambiguous_rules(self):
        invalid = rule()
        invalid['conditions'] = []
        with self.assertRaises(ENGINE.RuleValidationError):
            ENGINE.normalize_rule(invalid)
        invalid = rule()
        invalid['conditions'][0]['expected'] = float('nan')
        with self.assertRaises(ENGINE.RuleValidationError):
            ENGINE.normalize_rule(invalid)
        invalid = rule()
        invalid['conditions'][0]['provider_id'] = '../secret'
        with self.assertRaises(ENGINE.RuleValidationError):
            ENGINE.normalize_rule(invalid)


class AutomationRulePluginTests(unittest.TestCase):
    def test_manifest_requires_provider_core_and_defaults_are_safe(self):
        plugin = ROOT / 'plugins' / 'automation_rules'
        manifest = json.loads((plugin / 'plugin.json').read_text(encoding='utf-8'))
        source = (plugin / '__init__.py').read_text(encoding='utf-8')
        self.assertEqual(manifest['id'], 'automation_rules')
        self.assertEqual(manifest['version'], '1.0.4')
        self.assertGreaterEqual(manifest['ospy']['min_version'], '3.0.348')
        self.assertIn("'enabled': False", source)
        self.assertIn("'test_mode': True", source)
        self.assertNotIn('stations.activate', source)
        self.assertNotIn('stations.deactivate', source)
        self.assertIn("'rule_name': rule['name']", source)

    def test_builtin_ultrasonic_sensor_exposes_derived_tank_values(self):
        sensor = SimpleNamespace(
            index=1, enabled=True, manufacturer=0, name='Barrel level',
            response=True, sens_type=6, multi_type=8,
            last_read_value=[''] * 8 + [22], last_response=100,
            distance_top=10, distance_bottom=95, diameter=100,
            check_liters=True,
        )
        with mock.patch.object(
                SENSOR_PROVIDER.sensors, 'get', return_value=[sensor]):
            snapshot_data = SENSOR_PROVIDER.provider_snapshot()
        resource = snapshot_data['resources'][0]
        values = {item['id']: item for item in resource['values']}
        self.assertEqual(resource['id'], 'sensor-1')
        self.assertEqual(resource['name'], 'Barrel level')
        self.assertEqual(values['sensor_distance_cm']['value'], 22.0)
        self.assertEqual(values['level_cm']['value'], 73.0)
        self.assertAlmostEqual(values['fill_percent']['value'], 85.882, places=3)
        self.assertAlmostEqual(values['volume']['value'], 573.341, places=3)
        self.assertEqual(values['volume']['unit'], 'L')

    def test_builtin_shelly_sensor_exposes_selected_measurement(self):
        sensor = SimpleNamespace(
            index=0, enabled=True, manufacturer=1, name='Pump relay',
            response=True, sens_type=1,
            last_read_value=[[True], [], [], [], [], []], last_response=100,
        )
        with mock.patch.object(
                SENSOR_PROVIDER.sensors, 'get', return_value=[sensor]):
            snapshot_data = SENSOR_PROVIDER.provider_snapshot()
        value = snapshot_data['resources'][0]['values'][0]
        self.assertEqual(value['id'], 'output_1')
        self.assertIs(value['value'], True)
        self.assertEqual(value['value_type'], 'boolean')

    def test_test_mode_dispatch_never_calls_local_or_external_delivery(self):
        path = ROOT / 'plugins' / 'automation_rules' / '__init__.py'
        source = path.read_text(encoding='utf-8')
        tree = ast.parse(source)
        selected = [node for node in tree.body if isinstance(node, ast.FunctionDef)
                    and node.name in ('_event_text', 'dispatch_notifications')]
        calls = []

        def called(name):
            def inner(*args, **kwargs):
                calls.append(name)
                return {'channel': name, 'status': 'sent'}
            return inner

        namespace = {
            '_': lambda value: value,
            '_queue_local_notification': called('local'),
            '_send_email': called('email'), '_send_telegram': called('telegram'),
            '_send_push': called('push'),
        }
        exec(compile(ast.Module(body=selected, type_ignores=[]), str(path), 'exec'), namespace)
        definition = rule()
        definition['channels'] = list(ENGINE.CHANNELS)
        results = namespace['dispatch_notifications'](definition, 'triggered', test_mode=True)
        self.assertEqual(calls, [])
        self.assertEqual({item['status'] for item in results}, {'test'})

    def test_explicit_notification_test_delivers_without_changing_rule_state(self):
        path = ROOT / 'plugins' / 'automation_rules' / '__init__.py'
        source = path.read_text(encoding='utf-8')
        tree = ast.parse(source)
        selected = [node for node in tree.body if isinstance(node, ast.FunctionDef)
                    and node.name in ('_event_text', 'dispatch_notifications',
                                      'send_test_notifications')]
        calls = []
        history = []

        def called(name):
            def inner(*args, **kwargs):
                calls.append(name)
                return {'channel': name, 'status': 'sent'}
            return inner

        namespace = {
            '_': lambda value: value, 'engine': ENGINE,
            '_queue_local_notification': called('local'),
            '_send_email': called('email'), '_send_telegram': called('telegram'),
            '_send_push': called('push'),
            '_history_record': lambda definition, event, evaluation, results, test_mode: {
                'event': event, 'results': results, 'test_mode': test_mode},
            'append_history': history.append,
        }
        exec(compile(ast.Module(body=selected, type_ignores=[]), str(path), 'exec'), namespace)
        definition = rule()
        definition['channels'] = list(ENGINE.CHANNELS)
        results = namespace['send_test_notifications'](definition)
        self.assertEqual(calls, ['local', 'email', 'telegram', 'push'])
        self.assertEqual(len(results), len(ENGINE.CHANNELS))
        self.assertEqual(history[0]['event'], 'notification_test')
        self.assertFalse(history[0]['test_mode'])

    def test_editor_is_row_based_and_browser_permission_is_explicit(self):
        plugin = ROOT / 'plugins' / 'automation_rules'
        template = (plugin / 'templates' / 'automation_rules.html').read_text(encoding='utf-8')
        css = (plugin / 'static' / 'automation_rules.css').read_text(encoding='utf-8')
        editor = (plugin / 'static' / 'editor.js').read_text(encoding='utf-8')
        home = (plugin / 'static' / 'automation_rules.js').read_text(encoding='utf-8')
        self.assertIn('condition-row', template)
        self.assertIn('add-condition', template)
        self.assertIn("value=\"all\"", template)
        self.assertIn("value=\"any\"", template)
        self.assertIn('@media (max-width: 850px)', css)
        self.assertEqual(template.count('type="checkbox"'), template.count('class="slider"'))
        self.assertGreaterEqual(template.count('title=$:{json.dumps(_('), 20)
        self.assertIn('.switch input:checked + .slider', css)
        self.assertIn('automation_rules.css?v=1.0.3', template)
        self.assertIn('value="test_notifications"', template)
        self.assertIn('.settings-grid > label, .settings-grid > .field-row, .switch-field { justify-content: flex-start; }', css)
        self.assertIn('Notification.requestPermission()', editor)
        self.assertNotIn('Notification.requestPermission()', home)
        self.assertIn("Notification.permission !== 'granted'", home)
        self.assertNotIn("if (window.location.pathname !== '/') { return; }", home)
        self.assertIn("if (window.location.pathname === '/') { showHome(item); }", home)

    def test_existing_notification_plugins_expose_delivery_results(self):
        telegram = (ROOT / 'plugins' / 'telegram_bot' / '__init__.py').read_text(encoding='utf-8')
        email = (ROOT / 'plugins' / 'email_notifications' / '__init__.py').read_text(encoding='utf-8')
        ssl = (ROOT / 'plugins' / 'email_notifications_ssl' / '__init__.py').read_text(encoding='utf-8')
        self.assertIn('def send_notification(', telegram)
        self.assertIn('return True', email[email.index('def try_mail('):email.index('def maping(', email.index('def try_mail('))])
        self.assertIn('return False', ssl[ssl.index('def try_mail('):ssl.index('def maping(', ssl.index('def try_mail('))])


if __name__ == '__main__':
    unittest.main()
