import importlib.util
import json
import pathlib
import unittest


MODULE_PATH = (
    pathlib.Path(__file__).resolve().parents[1]
    / 'plugins'
    / 'wind_monitor'
    / 'methods.py'
)
PLUGIN_ROOT = MODULE_PATH.parent
SPEC = importlib.util.spec_from_file_location('wind_monitor_methods', MODULE_PATH)
methods = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(methods)


class WindMonitorMethodTests(unittest.TestCase):
    def test_decimal_input_accepts_comma_point_and_integer(self):
        self.assertEqual(methods.parse_decimal('2,5', 'pulses'), 2.5)
        self.assertEqual(methods.parse_decimal('2.5', 'pulses'), 2.5)
        self.assertEqual(methods.parse_decimal(2, 'pulses'), 2.0)

    def test_invalid_decimal_reports_field_and_value(self):
        with self.assertRaisesRegex(ValueError, 'pulses:wrong'):
            methods.parse_decimal('wrong', 'pulses')

    def test_bcd_counter_is_decoded_from_three_registers(self):
        self.assertEqual(methods.decode_bcd_counter([0x56, 0x34, 0x12]), 123456)

    def test_invalid_bcd_digit_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'invalid_bcd_digit'):
            methods.decode_bcd_counter([0x1A, 0x00, 0x00])

    def test_speed_uses_actual_elapsed_time(self):
        pulse_rate, speed = methods.calculate_speed(
            raw_pulses=100,
            elapsed_seconds=20,
            pulses_per_rotation=2,
            meters_per_rotation=1.5,
        )
        self.assertEqual(pulse_rate, 5.0)
        self.assertEqual(speed, 3.75)

    def test_zts_modbus_request_matches_documented_frame(self):
        self.assertEqual(
            methods.build_zts_wind_request(1),
            bytes.fromhex('01 03 00 00 00 02 C4 0B'),
        )

    def test_zts_modbus_response_decodes_speed_and_wind_force(self):
        result = methods.parse_zts_wind_response(
            bytes.fromhex('01 03 04 00 24 00 03 FA 39'), 1)
        self.assertEqual(result['speed_mps'], 3.6)
        self.assertEqual(result['wind_force'], 3)
        self.assertEqual(result['raw_speed'], 36)

    def test_zts_modbus_response_rejects_crc_and_address(self):
        with self.assertRaisesRegex(ValueError, 'modbus_crc'):
            methods.parse_zts_wind_response(
                bytes.fromhex('01 03 04 00 24 00 03 FA 38'), 1)
        with self.assertRaisesRegex(ValueError, 'modbus_address_mismatch'):
            methods.parse_zts_wind_response(
                bytes.fromhex('01 03 04 00 24 00 03 FA 39'), 2)

    def test_zts_modbus_address_range_is_validated(self):
        for address in (0, 248):
            with self.assertRaisesRegex(ValueError, 'invalid_modbus_address'):
                methods.build_zts_wind_request(address)

    def test_plausibility_filter_rejects_only_when_enabled(self):
        self.assertEqual(
            methods.validate_measurement(45, True, 40),
            (False, 'maximum_speed'))
        self.assertEqual(methods.validate_measurement(45, False, 40), (True, ''))

    def test_safety_action_requires_consecutive_confirmations(self):
        count, triggered = methods.update_confirmation(0, True, 2)
        self.assertEqual((count, triggered), (1, False))
        count, triggered = methods.update_confirmation(count, True, 2)
        self.assertEqual((count, triggered), (2, True))
        self.assertEqual(methods.update_confirmation(count, False, 2), (0, False))

    def test_trend_detects_rising_falling_and_steady_samples(self):
        rising = [(0, 1.0), (20, 1.1), (40, 2.0), (60, 2.2)]
        falling = [(0, 3.0), (20, 2.8), (40, 1.0), (60, 0.8)]
        steady = [(0, 2.0), (20, 2.1), (40, 2.0), (60, 2.1)]
        self.assertEqual(methods.calculate_trend(rising), 'up')
        self.assertEqual(methods.calculate_trend(falling), 'down')
        self.assertEqual(methods.calculate_trend(steady), 'steady')

    def test_trend_waits_for_a_sufficient_window(self):
        self.assertEqual(
            methods.calculate_trend([(0, 1), (10, 2), (20, 3), (30, 4)]),
            'unknown')


class WindMonitorTemplateTests(unittest.TestCase):
    def test_graph_restores_previous_and_actual_value_tooltip(self):
        template = (
            PLUGIN_ROOT / 'templates' / 'wind_monitor.html'
        ).read_text(encoding='utf-8')
        css = (
            PLUGIN_ROOT / 'static' / 'wind_monitor.css'
        ).read_text(encoding='utf-8')

        self.assertIn('plothover.windMonitor', template)
        self.assertIn("(_('Previous Value')", template)
        self.assertIn("(_('Actual Value')", template)
        self.assertIn('windGraphTexts[item.seriesIndex][item.dataIndex]', template)
        self.assertIn('.windGraphTooltip', css)

    def test_settings_offer_source_specific_pcf_and_rs485_fields(self):
        template = (
            PLUGIN_ROOT / 'templates' / 'wind_monitor_settings.html'
        ).read_text(encoding='utf-8')
        self.assertIn('name="source"', template)
        self.assertIn('value="pcf8583"', template)
        self.assertIn('value="rs485"', template)
        self.assertIn('name="rs485_address"', template)
        self.assertIn('windSourcePcf', template)
        self.assertIn('windSourceRs485', template)

    def test_rs485_and_smbus_dependencies_are_optional(self):
        manifest = json.loads(
            (PLUGIN_ROOT / 'plugin.json').read_text(encoding='utf-8'))
        dependencies = {
            item['id']: item['required']
            for item in manifest['dependencies']
        }
        requirements = {
            item['module']: item['required']
            for item in manifest['requirements']
        }
        self.assertFalse(dependencies['rs485_communication'])
        self.assertFalse(requirements['smbus'])


if __name__ == '__main__':
    unittest.main()
