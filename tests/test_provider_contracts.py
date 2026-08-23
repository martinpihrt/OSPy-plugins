import ast
import copy
import datetime
import json
import pathlib
import re
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
PROVIDERS = (
    'water_meter',
    'pressure_monitor',
    'tank_monitor',
    'current_loop_tanks_monitor',
    'venetian_blind',
    'ospy_backup',
)
IDENTIFIER = re.compile(r'^[a-z][a-z0-9_.-]{0,127}$')


class DummyLock(object):
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False


class DummyWorker(object):
    def __init__(self, status=None, alive=True):
        self.status = status or {}
        self._alive = alive

    def is_alive(self):
        return self._alive


def provider_source(plugin):
    return (ROOT / 'plugins' / plugin / '__init__.py').read_text(encoding='utf-8-sig')


def provider_functions(plugin):
    source = provider_source(plugin)
    tree = ast.parse(source)
    selected = [
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and
        (node.name.startswith('_provider_') or node.name.startswith('provider_'))
    ]
    namespace = {'datetime': datetime}
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(plugin), 'exec'), namespace)
    return namespace


def assert_snapshot(test, snapshot, provider_id):
    json.dumps(snapshot, allow_nan=False)
    test.assertEqual(snapshot['contract'], 'ospy.provider.v1')
    test.assertEqual(snapshot['provider_id'], provider_id)
    test.assertIn(snapshot['status'], ('ok', 'unavailable', 'stale', 'error', 'disabled'))
    test.assertIsInstance(snapshot['resources'], list)
    for resource in snapshot['resources']:
        test.assertRegex(resource['id'], IDENTIFIER)
        test.assertRegex(resource['type'], IDENTIFIER)
        test.assertIn(resource['status'], ('ok', 'unavailable', 'stale', 'error', 'disabled'))
        for value in resource['values']:
            test.assertRegex(value['id'], IDENTIFIER)
            test.assertRegex(value['quantity'], IDENTIFIER)
            test.assertIn(value['value_type'], ('number', 'integer', 'boolean', 'string'))
            test.assertIn(value['quality'], ('measured', 'derived', 'estimated', 'unknown'))
            test.assertIsInstance(value['unit'], str)


class ProviderAdapterContractTests(unittest.TestCase):
    def test_manifests_declare_provider_v1_and_functions_exist(self):
        for plugin in PROVIDERS:
            with self.subTest(plugin=plugin):
                manifest = json.loads((ROOT / 'plugins' / plugin / 'plugin.json').read_text(encoding='utf-8-sig'))
                self.assertEqual(manifest.get('provider'), {'contract': 'ospy.provider.v1'})
                self.assertIn('min', manifest.get('ospy', {}))
                self.assertNotIn('min_version', manifest.get('ospy', {}))
                functions = provider_functions(plugin)
                declaration = functions['provider_capabilities']()
                self.assertEqual(declaration['contract'], 'ospy.provider.v1')
                self.assertEqual(declaration['provider_id'], plugin)
                self.assertTrue(declaration['resource_types'])
                self.assertIsInstance(declaration['values'], list)
                self.assertIsInstance(declaration['events'], list)
                self.assertIsInstance(declaration['alerts'], list)
                self.assertIsInstance(declaration['actions'], list)
                json.dumps(declaration, allow_nan=False)

    def test_water_meter_declares_and_executes_reset_action(self):
        source = provider_source('water_meter')
        tree = ast.parse(source)
        selected = [
            node for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name in (
                'provider_capabilities', '_reset_total_consumption',
                'provider_execute_action')
        ]
        persisted = []
        sender = DummyWorker({
            'total_liters': 12.5, 'minute_liters': 2.0,
            'hour_liters': 7.0,
        })
        sender._persist_total = lambda: persisted.append(True)
        namespace = {
            '_': lambda value: value, 'options': {
                'sum': 12.5, 'log_date_last_reset': 'old'},
            'water_sender': sender,
            'datetime_string': lambda: '2026-08-23 12:00:00',
            'log': type('Log', (), {'info': staticmethod(lambda *args: None)}),
            'NAME': 'Water Meter',
        }
        exec(compile(ast.Module(body=selected, type_ignores=[]),
                     'water_meter', 'exec'), namespace)

        declaration = namespace['provider_capabilities']()
        self.assertEqual(declaration['actions'], [{
            'id': 'reset_total_consumption', 'risk': 'control',
            'parameters': {},
        }])
        result = namespace['provider_execute_action'](
            'reset_total_consumption', resource_id='main', parameters={})
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['data']['previous_total_liters'], 12.5)
        self.assertEqual(sender.status['total_liters'], 0.0)
        self.assertEqual(sender.status['minute_liters'], 0.0)
        self.assertEqual(sender.status['hour_liters'], 0.0)
        self.assertEqual(persisted, [True])

    def test_tank_monitor_executes_reset_extrema_action(self):
        source = provider_source('tank_monitor')
        tree = ast.parse(source)
        selected = [node for node in tree.body
                    if isinstance(node, ast.FunctionDef) and node.name in (
                        'reset_tank_minimum_maximum', 'provider_execute_action')]
        status = {'level': 42, 'minlevel': 10, 'maxlevel': 90}
        settings = {'saved_min': 10, 'saved_max': 90}
        namespace = {
            '_': lambda value: value, 'status': status,
            'tank_options': settings,
            'datetime_string': lambda: '2026-08-23 12:00:00',
            'log': type('Log', (), {
                'info': staticmethod(lambda *args: None)}), 'NAME': 'Tank',
            'stop_tank_regulation': lambda: None,
        }
        exec(compile(ast.Module(body=selected, type_ignores=[]),
                     'tank_monitor', 'exec'), namespace)
        result = namespace['provider_execute_action'](
            'reset_minimum_maximum', 'tank-1', {})
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(status['minlevel'], 42)
        self.assertEqual(status['maxlevel'], 42)
        self.assertEqual(settings['saved_min'], 42)
        self.assertEqual(settings['saved_max'], 42)

    def test_current_loop_tank_action_stops_only_selected_regulation(self):
        source = provider_source('current_loop_tanks_monitor')
        tree = ast.parse(source)
        selected = [node for node in tree.body
                    if isinstance(node, ast.FunctionDef) and node.name in (
                        'stop_tank_regulation', 'provider_execute_action')]
        intervals = [
            {'station': 3, 'program_name': 'Tank B'},
            {'station': 4, 'program_name': 'Other'},
        ]
        finished = []
        deactivated = []
        fake_log = type('Log', (), {
            'active_runs': staticmethod(lambda: list(intervals)),
            'finish_run': staticmethod(lambda item: finished.append(item)),
            'info': staticmethod(lambda *args: None),
        })
        namespace = {
            '_': lambda value: value,
            'plugin_options': {
                'en_tank2': True, 'label2': 'Tank B',
                'reg_out_tank2': 3, 'mini_reg_out_tank2': 4,
            },
            'tanks': {'label': ['A', 'Tank B', 'C', 'D']},
            'log': fake_log, 'NAME': 'Current Loop',
            'stations': type('Stations', (), {
                'deactivate': staticmethod(lambda sid: deactivated.append(sid))}),
        }
        exec(compile(ast.Module(body=selected, type_ignores=[]),
                     'current_loop', 'exec'), namespace)
        result = namespace['provider_execute_action'](
            'stop_regulation', 'tank-2', {})
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['data']['stopped_runs'], 1)
        self.assertEqual(deactivated, [3])
        self.assertEqual(finished, [intervals[0]])

    def test_venetian_blind_provider_action_reuses_mobile_command(self):
        source = provider_source('venetian_blind')
        tree = ast.parse(source)
        selected = [node for node in tree.body
                    if isinstance(node, ast.FunctionDef) and node.name in (
                        '_blind_resource_id', 'provider_execute_action')]
        calls = []
        blinds = [{'uid': 'blind-a', 'enabled': True}]
        namespace = {
            '_': lambda value: value, 'hashlib': __import__('hashlib'),
            'get_blinds': lambda: blinds,
            'mobile_action': lambda action, payload: (
                calls.append((action, payload)) or {'status': 'ok'}),
        }
        exec(compile(ast.Module(body=selected, type_ignores=[]),
                     'venetian_blind', 'exec'), namespace)
        resource_id = namespace['_blind_resource_id']('blind-a')
        result = namespace['provider_execute_action'](
            'tilt_2', resource_id, {})
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(calls, [('tilt2', {'blind_uid': 'blind-a'})])

    def test_ospy_backup_provider_action_uses_existing_backup_path(self):
        source = provider_source('ospy_backup')
        tree = ast.parse(source)
        selected = [node for node in tree.body
                    if isinstance(node, ast.FunctionDef) and
                    node.name == 'provider_execute_action']
        namespace = {
            '_': lambda value: value, 'get_backup': lambda: True,
            'health_lock': DummyLock(),
            'health_state': {'last_file': 'backup.zip', 'last_size': 123},
            'datetime_string': lambda: '2026-08-23 12:00:00',
            'log': type('Log', (), {
                'info': staticmethod(lambda *args: None)}), 'NAME': 'Backup',
        }
        exec(compile(ast.Module(body=selected, type_ignores=[]),
                     'ospy_backup', 'exec'), namespace)
        result = namespace['provider_execute_action'](
            'create_backup', 'main', {})
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['data'], {'filename': 'backup.zip', 'size': 123})

    def test_venetian_blind_snapshot_is_cached_and_valid(self):
        functions = provider_functions('venetian_blind')
        functions.update({
            '_': lambda value: value,
            'plugin_options': {'use_control': True},
            'get_blinds': lambda: [{
                'uid': 'abc', 'enabled': True, 'label': 'Kitchen'}],
            'sender': DummyWorker({
                'details': {0: {'reachable': True, 'position': 55}},
                'bstatus': {0: 'stopped'},
            }),
            'health_lock': DummyLock(),
            'health_state': {'last_status': 100.0},
            '_blind_resource_id': lambda uid: 'blind-' + uid,
        })
        result = functions['provider_snapshot']()
        assert_snapshot(self, result, 'venetian_blind')
        self.assertEqual(result['resources'][0]['id'], 'blind-abc')
        self.assertEqual(result['resources'][0]['values'][0]['value'], 55.0)

    def test_ospy_backup_snapshot_is_cached_and_valid(self):
        functions = provider_functions('ospy_backup')
        functions.update({
            '_': lambda value: value, 'sender': object(),
            'health_lock': DummyLock(),
            'health_state': {
                'running': False, 'last_success': 100.0,
                'last_file': 'backup.zip', 'last_size': 123,
                'last_error': 0, 'last_error_message': '',
            },
        })
        result = functions['provider_snapshot']()
        assert_snapshot(self, result, 'ospy_backup')
        values = {item['id']: item for item in result['resources'][0]['values']}
        self.assertIs(values['in_progress']['value'], False)
        self.assertEqual(values['last_backup_size']['value'], 123)

    def test_snapshot_functions_do_not_call_hardware_or_existing_health(self):
        forbidden = {
            'counter', 'get_check_pressure', 'get_sonic_cm', 'get_data',
            'read_adc', 'health', 'mobile_status', 'mobile_cards',
        }
        for plugin in PROVIDERS:
            with self.subTest(plugin=plugin):
                tree = ast.parse(provider_source(plugin))
                function = next(node for node in tree.body
                                if isinstance(node, ast.FunctionDef) and node.name == 'provider_snapshot')
                calls = {
                    node.func.id for node in ast.walk(function)
                    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                }
                self.assertFalse(calls & forbidden, calls & forbidden)

    def test_water_meter_snapshot_is_cached_and_does_not_mutate_options(self):
        functions = provider_functions('water_meter')
        options = {'enabled': True, 'sum': 15.0}
        state = {'last_reading': 100.0, 'last_error': 0, 'last_error_message': ''}
        status = {
            'meter': 0.2, 'minute_rate': 12.0, 'minute_liters': 4.0,
            'hour_liters': 44.0, 'total_liters': 120.0,
        }
        functions.update({
            'options': options, 'health_state': state, 'health_lock': DummyLock(),
            'water_sender': DummyWorker(status), '_empty_status': lambda: dict(status),
        })
        before = copy.deepcopy((options, state, status))
        result = functions['provider_snapshot']()
        assert_snapshot(self, result, 'water_meter')
        self.assertEqual(before, (options, state, status))

    def test_pressure_snapshot_uses_cached_binary_state(self):
        functions = provider_functions('pressure_monitor')
        options = {'use_press_monitor': True}
        state = {
            'last_cycle': 100.0, 'sensor_active': True, 'last_shutdown': 0,
            'last_error': 0, 'last_error_message': '',
        }
        functions.update({
            'pressure_options': options, 'health_state': state,
            'health_lock': DummyLock(), 'pressure_sender': DummyWorker(), 'master': True,
        })
        before = copy.deepcopy((options, state))
        result = functions['provider_snapshot']()
        assert_snapshot(self, result, 'pressure_monitor')
        self.assertIs(result['resources'][0]['values'][0]['value'], True)
        self.assertEqual(before, (options, state))

    def test_ultrasonic_tank_snapshot_has_stable_volume_units(self):
        functions = provider_functions('tank_monitor')
        options = {'use_sonic': True, 'water_minimum': 30, 'check_liters': False}
        state = {'last_read': 100.0, 'sensor_error': False,
                 'last_error': 0, 'last_error_message': ''}
        status = {'level': 80, 'percent': 50, 'ping': 90, 'volume': 1.5}
        functions.update({
            'tank_options': options, 'health_state': state, 'health_lock': DummyLock(),
            'status': status, 'sender': DummyWorker(),
        })
        before = copy.deepcopy((options, state, status))
        result = functions['provider_snapshot']()
        assert_snapshot(self, result, 'tank_monitor')
        values = {item['id']: item for item in result['resources'][0]['values']}
        self.assertEqual(values['volume_liters']['value'], 1500.0)
        self.assertEqual(values['volume_liters']['unit'], 'L')
        self.assertEqual(values['volume_cubic_meters']['value'], 1.5)
        self.assertEqual(before, (options, state, status))

    def test_current_loop_snapshot_exposes_each_enabled_tank(self):
        functions = provider_functions('current_loop_tanks_monitor')
        options = {
            'en_tank1': True, 'en_tank2': True, 'en_tank3': False, 'en_tank4': False,
            'en_eml_tank1_low': False, 'en_eml_tank2_low': False,
            'eml_tank1_low_lvl': 20, 'eml_tank2_low_lvl': 20,
        }
        state = {'last_success': 100.0, 'last_error': 0, 'last_error_message': ''}
        tanks = {
            'levelCm': [100, 200, 0, 0], 'volumeLiter': [500, 1000, 0, 0],
            'levelPercent': [25, 50, 0, 0], 'voltage': [1.0, 2.0, 0, 0],
            'label': ['A', 'B', 'C', 'D'], 'use': [True, True, False, False],
            'channel_error': [False, False, False, False],
        }
        functions.update({
            'plugin_options': options, 'health_state': state,
            'health_lock': DummyLock(), 'tanks': tanks, 'sender': DummyWorker(),
        })
        before = copy.deepcopy((options, state, tanks))
        result = functions['provider_snapshot']()
        assert_snapshot(self, result, 'current_loop_tanks_monitor')
        self.assertEqual([item['id'] for item in result['resources']], ['tank-1', 'tank-2'])
        self.assertEqual(before, (options, state, tanks))


if __name__ == '__main__':
    unittest.main()
