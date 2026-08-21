import ast
import importlib.util
import json
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
PLUGIN_ROOT = ROOT / 'plugins' / 'shelly_cloud_integrator'
MODULE_PATH = PLUGIN_ROOT / 'device_config.py'
SPEC = importlib.util.spec_from_file_location('shelly_device_config', MODULE_PATH)
device_config = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(device_config)


class ShellyDeviceConfigTests(unittest.TestCase):
    def test_legacy_parallel_lists_are_preserved_and_receive_stable_uids(self):
        generated = iter(('uid-one', 'uid-two'))
        settings = {
            'number_sensors': 2,
            'use_sensor': [True, False],
            'sensor_label': ['Grid meter', 'Boiler'],
            'sensor_id': ['abc123', 'def456'],
            'sensor_type': [10, 2],
            'gen_type': [1, 1],
            'reading_type': [0, 1],
            'sensor_ip': ['192.168.1.20', ''],
        }
        devices = device_config.normalize_devices(settings, lambda: next(generated))
        self.assertEqual([item['device_uid'] for item in devices], ['uid-one', 'uid-two'])
        self.assertEqual([item['sensor_id'] for item in devices], ['abc123', 'def456'])
        self.assertEqual([item['sensor_label'] for item in devices], ['Grid meter', 'Boiler'])
        self.assertEqual([item['sensor_type'] for item in devices], [10, 2])
        self.assertEqual(devices[0]['sensor_ip'], '192.168.1.20')

    def test_existing_unique_uids_and_order_survive_normalization(self):
        settings = {
            'number_sensors': 2,
            'device_uid': ['stable-a', 'stable-b'],
            'sensor_id': ['first', 'second'],
        }
        devices = device_config.normalize_devices(settings, lambda: 'unused')
        serialized = device_config.serialize_devices(devices)
        self.assertEqual(serialized['device_uid'], ['stable-a', 'stable-b'])
        self.assertEqual(serialized['sensor_id'], ['first', 'second'])
        self.assertEqual(serialized['number_sensors'], 2)

    def test_edit_add_and_delete_touch_only_the_selected_record(self):
        first = device_config.default_device('one')
        first['sensor_id'] = 'first'
        second = device_config.default_device('two')
        second['sensor_id'] = 'second'
        edited = dict(first, sensor_label='Edited')
        devices, created = device_config.upsert_device([first, second], edited)
        self.assertFalse(created)
        self.assertEqual([item['device_uid'] for item in devices], ['one', 'two'])
        self.assertEqual(devices[1]['sensor_id'], 'second')
        third = device_config.default_device('three')
        devices, created = device_config.upsert_device(devices, third)
        self.assertTrue(created)
        devices, deleted = device_config.delete_device(devices, 'two')
        self.assertTrue(deleted)
        self.assertEqual([item['device_uid'] for item in devices], ['one', 'three'])

    def test_cloud_only_devices_cannot_retain_local_reading_mode(self):
        settings = {
            'number_sensors': 2,
            'sensor_type': [0, 9],
            'reading_type': [0, 0],
        }
        devices = device_config.normalize_devices(settings, iter(('a', 'b')).__next__)
        self.assertEqual([item['reading_type'] for item in devices], [1, 1])


class ShellyDeviceManagementTemplateTests(unittest.TestCase):
    def test_active_settings_template_uses_individual_device_actions(self):
        template = (PLUGIN_ROOT / 'templates' / 'shelly_cloud_integration_devices.html').read_text(encoding='utf-8')
        self.assertNotIn('name="number_sensors"', template)
        self.assertIn("$_('Add new Shelly')", template)
        self.assertIn('value="save_device"', template)
        self.assertIn('value="delete_device"', template)
        self.assertIn("$_('Edit')", template)
        self.assertIn("$_('Delete')", template)
        self.assertIn('shellyDeleteForm', template)

    def test_list_and_card_choice_is_saved_server_side(self):
        template = (PLUGIN_ROOT / 'templates' / 'shelly_cloud_integration_devices.html').read_text(encoding='utf-8')
        source = (PLUGIN_ROOT / '__init__.py').read_text(encoding='utf-8')
        self.assertIn('name="device_view" value="list"', template)
        self.assertIn('name="device_view" value="cards"', template)
        self.assertIn("requested_view in ('cards', 'list')", source)
        self.assertIn("'device_view': 'cards'", source)

    def test_mutating_forms_are_csrf_protected_and_use_stable_uid(self):
        template = (PLUGIN_ROOT / 'templates' / 'shelly_cloud_integration_devices.html').read_text(encoding='utf-8')
        source = (PLUGIN_ROOT / '__init__.py').read_text(encoding='utf-8')
        self.assertGreaterEqual(template.count('csrf_input()'), 5)
        self.assertIn('name="device_uid"', template)
        self.assertIn('verify_csrf(qdict)', source)
        self.assertIn("'device_uid': []", source)

    def test_device_previews_are_available_in_editor_list_and_cards(self):
        template = (PLUGIN_ROOT / 'templates' / 'shelly_cloud_integration_devices.html').read_text(encoding='utf-8')
        source = (PLUGIN_ROOT / '__init__.py').read_text(encoding='utf-8')
        for marker in ('devicePreviewImage', 'shellyListPreview', 'shellyCardPreview'):
            self.assertIn(marker, template)
        assignment = next(node for node in ast.parse(source).body if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == 'DEVICE_PREVIEWS' for target in node.targets))
        previews = ast.literal_eval(assignment.value)
        self.assertEqual(set(previews), {str(index) for index in range(12)})
        for choices in previews.values():
            for preview in choices.values():
                self.assertTrue((PLUGIN_ROOT / 'static' / 'images' / preview['image']).is_file())
                self.assertTrue(preview['url'].startswith('https://kb.shelly.cloud/knowledge-base/'))

    def test_public_device_service_exposes_configuration_and_handles_stopped_worker(self):
        source = (PLUGIN_ROOT / '__init__.py').read_text(encoding='utf-8')
        self.assertIn('return list(sender.devices) if sender is not None else []', source)
        self.assertIn("'id': device.get('sensor_id', '')", source)
        self.assertIn("'enabled': bool(device.get('use_sensor', False))", source)

    def test_shelly_25_and_addon_status_use_initialized_network_values(self):
        source = (PLUGIN_ROOT / '__init__.py').read_text(encoding='utf-8')
        shelly_25 = source.split('# typ: 4=Shelly 2.5', 1)[1].split('# typ: 5=Shelly Pro 4PM', 1)[0]
        self.assertNotIn('a_voltage', shelly_25)
        self.assertNotIn('wifi = response_data["sta_ip"]', shelly_25)
        self.assertIn('wifi = response_data["wifi"]', shelly_25)
        self.assertIn('sta_ip = wifi["sta_ip"]', shelly_25)
        self.assertEqual(source.count("RSSI:{} dbm {}\\n').format(name, a_power, round(a_total/1000.0, 2), voltage, sta_ip, rssi, format_timestamp(updated))"), 4)

    def test_manifest_and_active_css_use_version_1_0_8(self):
        manifest = json.loads((PLUGIN_ROOT / 'plugin.json').read_text(encoding='utf-8'))
        template = (PLUGIN_ROOT / 'templates' / 'shelly_cloud_integration_devices.html').read_text(encoding='utf-8')
        self.assertEqual(manifest['version'], '1.0.8')
        self.assertIn('shelly_cloud_integration.css?v=1.0.8', template)
        self.assertTrue((PLUGIN_ROOT / 'static' / 'shelly_cloud_integration.css').is_file())


if __name__ == '__main__':
    unittest.main()
