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
