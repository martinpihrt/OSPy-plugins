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

    def test_fault_email_is_sent_once_then_only_after_reminder_interval(self):
        self.assertTrue(methods.fault_email_due(False, 0, 100, 6))
        self.assertFalse(methods.fault_email_due(True, 100, 100 + 5 * 3600, 6))
        self.assertTrue(methods.fault_email_due(True, 100, 100 + 6 * 3600, 6))
        self.assertFalse(methods.fault_email_due(True, 100, 100 + 3599, 0))
        self.assertTrue(methods.fault_email_due(True, 100, 100 + 3600, 0))

    def test_fault_program_runs_once_after_required_failures_until_reset(self):
        self.assertFalse(methods.fault_program_due(1, 3, False))
        self.assertFalse(methods.fault_program_due(2, 3, False))
        self.assertTrue(methods.fault_program_due(3, 3, False))
        self.assertFalse(methods.fault_program_due(4, 3, True))
        self.assertTrue(methods.fault_program_due(1, 0, False))

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

    def test_settings_have_separate_bounded_error_email_controls(self):
        template = (
            PLUGIN_ROOT / 'templates' / 'wind_monitor_settings.html'
        ).read_text(encoding='utf-8')
        email_section = template.index("<legend>$_(u'E-mail')</legend>")
        self.assertIn('name="send_error_email"', template[email_section:])
        self.assertIn('name="error_email_reminder_hours"', template[email_section:])
        self.assertIn('min="1" max="168"', template[email_section:])
        self.assertIn('name="emlsubject"', template[email_section:])
        self.assertIn('name="eplug"', template[email_section:])
        self.assertNotIn('name="emlsubject"', template[:email_section])
        self.assertNotIn('name="eplug"', template[:email_section])

    def test_settings_have_independent_sensor_failure_program_controls(self):
        template = (
            PLUGIN_ROOT / 'templates' / 'wind_monitor_settings.html'
        ).read_text(encoding='utf-8')
        section = template.index("<legend>$_(u'Sensor failure program')</legend>")
        failure_section = template[section:]
        self.assertIn('class="switch"', failure_section)
        self.assertIn('name="use_fault_program"', failure_section)
        self.assertIn('name="fault_program_failures"', failure_section)
        self.assertIn('min="1" max="100"', failure_section)
        self.assertIn('name="fault_program"', failure_section)
        source = (PLUGIN_ROOT / '__init__.py').read_text(encoding='utf-8')
        self.assertIn("_('Select a program to run when wind measurement fails.')", source)

    def test_worker_reports_both_sensor_sources_and_suppresses_fault_spam(self):
        source = (PLUGIN_ROOT / '__init__.py').read_text(encoding='utf-8')
        self.assertIn('fault_email_due(', source)
        self.assertIn("_('PCF8583 setup over I2C failed: {}')", source)
        self.assertIn("_('Reading the PCF8583 counter over I2C failed: {}')", source)
        self.assertIn("_('RS485 wind sensor read failed: {}')", source)
        self.assertIn("diagnostic_event('rs485_measurement_paused_for_bus_scan')", source)
        self.assertIn('self._clear_fault()', source)
        self.assertIn('self._run_fault_program_if_due()', source)
        self.assertIn("health_state['fault_program_triggered'] = True", source)
        self.assertIn("health_state['fault_program_triggered'] = False", source)
        activate_start = source.index('    def _activate_fault(')
        activate = source[
            activate_start:
            source.index('    def _send_fault_email(', activate_start)
        ]
        self.assertLess(
            activate.index('self._run_fault_program_if_due()'),
            activate.index('self._send_fault_email(clean_message)'))
        self.assertIn("getattr(running, 'index', -1) != program_index", source)

    def test_disabled_rs485_dependency_is_handled_without_internal_error(self):
        source = (PLUGIN_ROOT / '__init__.py').read_text(encoding='utf-8')
        dependency_check = source[
            source.index('def rs485_dependency_error():'):
            source.index('\ndef send_wind_email(', source.index('def rs485_dependency_error():'))
        ]
        self.assertIn('except Exception:', dependency_check)

    def test_manifest_and_template_assets_use_current_version(self):
        manifest = json.loads(
            (PLUGIN_ROOT / 'plugin.json').read_text(encoding='utf-8'))
        self.assertEqual(manifest['version'], '1.2.3')
        for template_path in (PLUGIN_ROOT / 'templates').glob('*.html'):
            template = template_path.read_text(encoding='utf-8')
            if 'wind_monitor.css?' in template:
                self.assertIn('wind_monitor.css?v=1.2.3', template)

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
