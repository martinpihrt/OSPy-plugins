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
    'ospy.inputs': types.ModuleType('ospy.inputs'),
    'ospy.options': types.ModuleType('ospy.options'),
    'ospy.provider_contracts': types.ModuleType('ospy.provider_contracts'),
    'ospy.sensors': types.ModuleType('ospy.sensors'),
}
SENSOR_MODULES['ospy.inputs'].inputs = SimpleNamespace(rain_sensed=lambda: False)
SENSOR_MODULES['ospy.options'].options = SimpleNamespace(
    temp_unit='C', scheduler_enabled=True, manual_mode=False,
    level_adjustment=0.85, rain_sensor_enabled=True, plugin_status={})
SENSOR_MODULES['ospy.options'].rain_blocks = SimpleNamespace(
    seconds_left=lambda: 7200)
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
    TIME_SPEC = importlib.util.spec_from_file_location(
        'automation_rules_time_provider',
        ROOT / 'plugins' / 'automation_rules' / 'time_provider.py',
    )
    TIME_PROVIDER = importlib.util.module_from_spec(TIME_SPEC)
    TIME_SPEC.loader.exec_module(TIME_PROVIDER)
    SYSTEM_SPEC = importlib.util.spec_from_file_location(
        'automation_rules_system_provider',
        ROOT / 'plugins' / 'automation_rules' / 'system_provider.py',
    )
    SYSTEM_PROVIDER = importlib.util.module_from_spec(SYSTEM_SPEC)
    SYSTEM_SPEC.loader.exec_module(SYSTEM_PROVIDER)


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

    def test_date_and_time_ranges_include_overnight_windows(self):
        definition = rule()
        definition['conditions'] = [{
            'id': 'time-window', 'provider_id': 'ospy_datetime',
            'resource_id': 'local', 'value_id': 'current_time',
            'operator': 'between', 'expected': '22:00..06:00',
        }]
        data = {'providers': {'ospy_datetime': {
            'status': 'ok', 'resources': [{
                'id': 'local', 'status': 'ok', 'values': [{
                    'id': 'current_time', 'value': '23:15', 'unit': '',
                }],
            }],
        }}}
        self.assertTrue(ENGINE.evaluate_rule(definition, data)['matched'])
        data['providers']['ospy_datetime']['resources'][0]['values'][0][
            'value'] = '12:00'
        self.assertFalse(ENGINE.evaluate_rule(definition, data)['matched'])
        definition['conditions'][0]['operator'] = 'not_between'
        self.assertTrue(ENGINE.evaluate_rule(definition, data)['matched'])

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

    def test_latched_incident_stays_active_until_explicit_unlock(self):
        definition = rule()
        definition['hold_seconds'] = 0
        definition['latch_incident'] = True
        matched = ENGINE.evaluate_rule(definition, snapshot())
        state, event = ENGINE.transition(definition, matched, now=100)
        self.assertEqual(event, 'triggered')
        self.assertTrue(state['latched'])
        clear = ENGINE.evaluate_rule(definition, snapshot(fill=50, pressure=False))
        state, event = ENGINE.transition(definition, clear, state, now=101)
        self.assertEqual(event, 'none')
        self.assertTrue(state['active'])
        self.assertTrue(state['latched'])

    def test_control_actions_are_normalized_with_safe_limits(self):
        definition = rule()
        definition['actions'] = [{
            'id': 'start-pump', 'type': 'output_on', 'target': '2',
            'value': '60',
        }, {
            'id': 'set-level', 'type': 'set_water_level', 'value': '85.5',
        }]
        normalized = ENGINE.normalize_rule(definition)
        self.assertEqual(normalized['actions'][0]['value'], 60)
        self.assertEqual(normalized['actions'][1]['value'], 85.5)
        definition['actions'][0]['value'] = 0
        with self.assertRaises(ENGINE.RuleValidationError):
            ENGINE.normalize_rule(definition)

    def test_cyclic_output_action_requires_bounded_safe_timing(self):
        definition = rule()
        definition['actions'] = [{
            'id': 'cycle-pump', 'type': 'output_on', 'target': '2',
            'value': '100', 'cycle_mode': 'cycle',
            'pause_seconds': '300', 'cycle_total_seconds': '3600',
        }]
        action = ENGINE.normalize_rule(definition)['actions'][0]
        self.assertEqual(action['cycle_mode'], 'cycle')
        self.assertEqual(action['value'], 100)
        self.assertEqual(action['pause_seconds'], 300)
        self.assertEqual(action['cycle_total_seconds'], 3600)
        definition['actions'][0]['pause_seconds'] = 0
        with self.assertRaises(ENGINE.RuleValidationError):
            ENGINE.normalize_rule(definition)
        definition['actions'][0]['pause_seconds'] = 300
        definition['actions'][0]['cycle_total_seconds'] = 99
        with self.assertRaises(ENGINE.RuleValidationError):
            ENGINE.normalize_rule(definition)

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
        self.assertEqual(manifest['version'], '1.1.1')
        self.assertEqual(manifest['mobile']['api_version'], 1)
        self.assertEqual(manifest['mobile']['actions'], [])
        self.assertEqual(manifest['ospy'], {'min': '3.0.354'})
        self.assertEqual(manifest['python'], {'min': '3.8'})
        self.assertIn("'enabled': False", source)
        self.assertIn("'test_mode': True", source)
        self.assertIn("'control_enabled': False", source)
        self.assertIn('def execute_control_actions(', source)
        self.assertIn("if not plugin_options.get('control_enabled', False)", source)
        self.assertIn("if test_mode:", source)
        self.assertIn("'rule_name': rule['name']", source)
        self.assertIn('def mobile_status(', source)
        self.assertIn('def mobile_cards(', source)
        self.assertIn('def _advance_rule_cycles(', source)
        self.assertIn("_stop_all_cycles(_('plug-in stopped'))", source)

    def test_control_actions_are_simulated_or_blocked_before_execution(self):
        path = ROOT / 'plugins' / 'automation_rules' / '__init__.py'
        tree = ast.parse(path.read_text(encoding='utf-8'))
        selected = [node for node in tree.body if isinstance(node, ast.FunctionDef)
                    and node.name in ('_action_label', 'execute_control_actions')]
        calls = []
        definition = rule()
        definition['actions'] = [{
            'id': 'stop-pump', 'type': 'stop_station', 'target': '0',
        }]
        namespace = {
            '_': lambda value: value,
            '_execute_control_action': lambda action: calls.append(action),
            'plugin_options': {'control_enabled': False},
            'health_lock': mock.MagicMock(),
            'health_state': {'control_actions': 0, 'control_errors': 0},
            'time': SimpleNamespace(time=lambda: 1),
            'traceback': SimpleNamespace(format_exc=lambda: ''),
            'log': SimpleNamespace(error=lambda *args: None), 'NAME': 'test',
        }
        exec(compile(ast.Module(body=selected, type_ignores=[]), str(path), 'exec'), namespace)
        simulated = namespace['execute_control_actions'](definition, test_mode=True)
        blocked = namespace['execute_control_actions'](definition, test_mode=False)
        self.assertEqual(calls, [])
        self.assertEqual(simulated[0]['status'], 'simulated')
        self.assertEqual(blocked[0]['status'], 'blocked')

    def test_output_cycle_stops_when_conditions_clear_and_advances_without_sleep(self):
        import threading
        path = ROOT / 'plugins' / 'automation_rules' / '__init__.py'
        tree = ast.parse(path.read_text(encoding='utf-8'))
        names = ('_cycle_key', '_cycle_conflict', '_drop_cycle',
                 '_register_output_cycle', '_advance_rule_cycles')
        selected = [node for node in tree.body if isinstance(node, ast.FunctionDef)
                    and node.name in names]
        stopped = []
        executed = []
        namespace = {
            '_': lambda value: value, 'cycle_lock': threading.RLock(),
            'cycle_runtime': {}, '_finish_station_runs': lambda ids: stopped.extend(ids),
            'health_lock': mock.MagicMock(),
            'health_state': {'cycle_starts': 0, 'cycle_stops': 0,
                             'control_actions': 0, 'control_errors': 0,
                             'last_error': 0, 'last_error_message': ''},
            'log': SimpleNamespace(info=lambda *args: None, error=lambda *args: None),
            'NAME': 'test', '_action_label': lambda action: action['type'],
            'time': SimpleNamespace(time=lambda: 100),
            'traceback': SimpleNamespace(format_exc=lambda: ''),
            '_execute_control_action': lambda action: executed.append(dict(action)),
            'plugin_options': {'enabled': True, 'test_mode': False,
                               'control_enabled': True},
        }
        exec(compile(ast.Module(body=selected, type_ignores=[]), str(path), 'exec'), namespace)
        definition = rule()
        action = ENGINE.normalize_action({
            'id': 'cycle-pump', 'type': 'output_on', 'target': '2',
            'value': 100, 'cycle_mode': 'cycle', 'pause_seconds': 300,
            'cycle_total_seconds': 3600,
        })
        definition['actions'] = [action]
        option_modules = {
            'ospy': types.ModuleType('ospy'),
            'ospy.options': types.ModuleType('ospy.options'),
        }
        option_modules['ospy.options'].options = SimpleNamespace(manual_mode=True)
        with mock.patch.dict(sys.modules, option_modules):
            namespace['_register_output_cycle'](definition, action, now=100)
            namespace['_advance_rule_cycles'](
                definition, {'available': True, 'matched': True}, 200)
            self.assertEqual(stopped, [2])
            cycle = next(iter(namespace['cycle_runtime'].values()))
            self.assertEqual(cycle['phase'], 'pause')
            namespace['_advance_rule_cycles'](
                definition, {'available': True, 'matched': True}, 500)
            self.assertEqual(len(executed), 1)
            self.assertEqual(executed[0]['value'], 100)
            namespace['_advance_rule_cycles'](
                definition, {'available': True, 'matched': False}, 550)
        self.assertFalse(namespace['cycle_runtime'])
        self.assertEqual(stopped, [2, 2])

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
            '_condition_summary': lambda definition, evaluation: '',
            '_automation_snapshots': lambda: snapshot(),
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
            '_condition_summary': lambda definition, evaluation: '',
            '_automation_snapshots': lambda: snapshot(),
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

    def test_notification_summary_contains_actual_value_operator_and_limit(self):
        path = ROOT / 'plugins' / 'automation_rules' / '__init__.py'
        tree = ast.parse(path.read_text(encoding='utf-8'))
        selected = [node for node in tree.body if isinstance(node, ast.FunctionDef)
                    and node.name in ('_display_value', '_condition_summary')]
        namespace = {
            '_': lambda value: value,
            '_provider_catalog': lambda: [{
                'provider_id': 'tank_monitor', 'resource_id': 'tank-1',
                'value_id': 'fill_percent', 'resource_label': 'Barrel',
                'value_label': 'Tank fill',
            }],
        }
        exec(compile(ast.Module(body=selected, type_ignores=[]), str(path), 'exec'), namespace)
        definition = rule()
        definition['conditions'] = definition['conditions'][:1]
        evaluation = ENGINE.evaluate_rule(definition, snapshot(fill=20))
        summary = namespace['_condition_summary'](definition, evaluation)
        self.assertIn('Barrel', summary)
        self.assertIn('20 % <= 25 %', summary)

    def test_rule_header_summary_describes_conditions_and_notifications(self):
        path = ROOT / 'plugins' / 'automation_rules' / '__init__.py'
        tree = ast.parse(path.read_text(encoding='utf-8'))
        selected = [node for node in tree.body if isinstance(node, ast.FunctionDef)
                    and node.name in (
                        '_display_value', '_condition_definitions',
                        '_configured_condition_text', '_rule_header_summary')]
        namespace = {'_': lambda value: value}
        exec(compile(ast.Module(body=selected, type_ignores=[]), str(path), 'exec'), namespace)
        catalog = [{
            'provider_id': 'tank_monitor', 'resource_id': 'tank-1',
            'value_id': 'fill_percent', 'resource_label': 'Barrel',
            'value_label': 'Tank fill', 'unit': '%',
        }, {
            'provider_id': 'pressure_monitor', 'resource_id': 'main',
            'value_id': 'pressure_present', 'resource_label': 'Main pump',
            'value_label': 'Pressure', 'unit': '',
        }]

        summary = namespace['_rule_header_summary'](rule(), catalog)

        self.assertIn('Barrel – Tank fill <= 25 %', summary)
        self.assertIn('AND', summary)
        self.assertIn('Main pump – Pressure is active', summary)
        self.assertIn('notify via OSPy Home window', summary)
        self.assertIn('Push notification', summary)

    def test_mobile_rule_card_reports_rule_and_condition_states(self):
        path = ROOT / 'plugins' / 'automation_rules' / '__init__.py'
        tree = ast.parse(path.read_text(encoding='utf-8'))
        names = ('_display_value', '_condition_definitions',
                 '_configured_condition_text', '_mobile_rule_card')
        selected = [node for node in tree.body if isinstance(node, ast.FunctionDef)
                    and node.name in names]
        namespace = {
            '_': lambda value: value,
            'datetime_string': lambda *_args: '2026-08-22 11:00',
            'time': SimpleNamespace(localtime=lambda value: value),
            'cycle_lock': mock.MagicMock(), 'cycle_runtime': {},
        }
        exec(compile(ast.Module(body=selected, type_ignores=[]), str(path), 'exec'), namespace)
        definition = rule()
        catalog = [{
            'provider_id': 'tank_monitor', 'resource_id': 'tank-1',
            'value_id': 'fill_percent', 'resource_label': 'Barrel',
            'value_label': 'Tank fill', 'unit': '%',
        }, {
            'provider_id': 'pressure_monitor', 'resource_id': 'main',
            'value_id': 'pressure_present', 'resource_label': 'Main pump',
            'value_label': 'Pressure', 'unit': '',
        }]
        evaluation = {
            'available': True, 'matched': True,
            'conditions': [
                {'id': 'tank-low', 'available': True, 'matched': True},
                {'id': 'pressure-ok', 'available': True, 'matched': False},
            ],
        }

        card = namespace['_mobile_rule_card'](
            definition, evaluation, {'active': True}, catalog)
        metrics = {item['id']: item['value'] for item in card['metrics']}

        self.assertEqual(card['summary'], 'Triggered')
        self.assertEqual(card['status'], 'warning')
        self.assertEqual(metrics['enabled'], 'Yes')
        self.assertEqual(metrics['condition_1'], 'Active')
        self.assertEqual(metrics['condition_2'], 'Inactive')

        disabled = namespace['_mobile_rule_card'](
            definition, None, {}, catalog, automation_enabled=False)
        disabled_metrics = {
            item['id']: item['value'] for item in disabled['metrics']}
        self.assertEqual(disabled['summary'], 'Automation disabled')
        self.assertEqual(disabled_metrics['condition_1'], 'Not evaluated')

    def test_local_date_time_provider_uses_comparable_iso_values(self):
        import datetime
        data = TIME_PROVIDER.provider_snapshot(datetime.datetime(2026, 8, 21, 16, 5))
        values = {item['id']: item['value']
                  for item in data['resources'][0]['values']}
        self.assertEqual(values['current_date'], '2026-08-21')
        self.assertEqual(values['current_time'], '16:05')
        self.assertEqual(values['weekday'], 5)

    def test_builtin_ospy_status_provider_exposes_operating_states(self):
        with mock.patch.object(SYSTEM_PROVIDER, '_plugin_update_count',
                               return_value=2), mock.patch.object(
                                   SYSTEM_PROVIDER, '_ospy_update_available',
                                   return_value=True):
            data = SYSTEM_PROVIDER.provider_snapshot()
        values = {item['id']: item
                  for item in data['resources'][0]['values']}
        self.assertIs(values['scheduler_enabled']['value'], True)
        self.assertIs(values['manual_mode']['value'], False)
        self.assertIs(values['scheduled_mode']['value'], True)
        self.assertEqual(values['water_level_percent']['value'], 85.0)
        self.assertEqual(values['rain_delay_seconds']['value'], 7200.0)
        self.assertIs(values['rain_sensor_enabled']['value'], True)
        self.assertIs(values['rain_sensor_active']['value'], False)
        self.assertIs(values['ospy_update_available']['value'], True)
        self.assertIs(values['plugin_update_available']['value'], True)
        self.assertEqual(values['plugin_update_count']['value'], 2)
        self.assertIs(values['any_update_available']['value'], True)

    def test_editor_is_row_based_and_browser_permission_is_explicit(self):
        plugin = ROOT / 'plugins' / 'automation_rules'
        template = (plugin / 'templates' / 'automation_rules.html').read_text(encoding='utf-8')
        css = (plugin / 'static' / 'automation_rules.css').read_text(encoding='utf-8')
        editor = (plugin / 'static' / 'editor.js').read_text(encoding='utf-8')
        home = (plugin / 'static' / 'automation_rules.js').read_text(encoding='utf-8')
        self.assertIn('condition-row', template)
        self.assertIn('add-condition', template)
        self.assertIn('add-action', template)
        self.assertIn('latch_incident', template)
        self.assertIn('unlock_incident', template)
        self.assertIn("value=\"all\"", template)
        self.assertIn("value=\"any\"", template)
        self.assertIn('@media (max-width: 850px)', css)
        self.assertEqual(template.count('type="checkbox"'), template.count('class="slider"'))
        self.assertGreaterEqual(template.count('title=$:{json.dumps(_('), 20)
        self.assertIn('.switch input:checked + .slider', css)
        self.assertIn('automation_rules.css?v=1.1.1', template)
        self.assertIn('<details class="automation-card rule-card', template)
        self.assertIn("rule['id'] == open_rule", template)
        self.assertNotIn("' open' if is_new", template)
        self.assertIn('rule-summary-description', template)
        self.assertIn("'?open_rule={}'", (plugin / '__init__.py').read_text(encoding='utf-8'))
        self.assertIn('rule-state active', template)
        self.assertIn("not rule.get('enabled')", template)
        self.assertIn('value="between"', template)
        self.assertIn('value="test_notifications"', template)
        self.assertIn('.settings-grid > label, .settings-grid > .field-row, .switch-field { justify-content: flex-start; }', css)
        self.assertIn('Notification.requestPermission()', editor)
        self.assertNotIn('Notification.requestPermission()', home)
        self.assertIn("Notification.permission !== 'granted'", home)
        self.assertIn('serviceWorkerNotification', home)
        self.assertIn('browser_sw.js?v=1.1.1', home)
        self.assertIn('action-cycle-mode', template)
        self.assertIn('action-pause-seconds', template)
        self.assertIn('action-cycle-total-seconds', template)
        self.assertIn('updateCycleFields', editor)
        self.assertLess(home.index('serviceWorkerNotification(title'),
                        home.index('new Notification(title'))
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
