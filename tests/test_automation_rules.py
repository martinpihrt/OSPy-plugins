import importlib.util
import ast
import json
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    'automation_rules_engine',
    ROOT / 'plugins' / 'automation_rules' / 'engine.py',
)
ENGINE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ENGINE)


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
        self.assertGreaterEqual(manifest['ospy']['min_version'], '3.0.348')
        self.assertIn("'enabled': False", source)
        self.assertIn("'test_mode': True", source)
        self.assertNotIn('stations.activate', source)
        self.assertNotIn('stations.deactivate', source)

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
        self.assertIn('Notification.requestPermission()', editor)
        self.assertNotIn('Notification.requestPermission()', home)
        self.assertIn("Notification.permission !== 'granted'", home)

    def test_existing_notification_plugins_expose_delivery_results(self):
        telegram = (ROOT / 'plugins' / 'telegram_bot' / '__init__.py').read_text(encoding='utf-8')
        email = (ROOT / 'plugins' / 'email_notifications' / '__init__.py').read_text(encoding='utf-8')
        ssl = (ROOT / 'plugins' / 'email_notifications_ssl' / '__init__.py').read_text(encoding='utf-8')
        self.assertIn('def send_notification(', telegram)
        self.assertIn('return True', email[email.index('def try_mail('):email.index('def maping(', email.index('def try_mail('))])
        self.assertIn('return False', ssl[ssl.index('def try_mail('):ssl.index('def maping(', ssl.index('def try_mail('))])


if __name__ == '__main__':
    unittest.main()
