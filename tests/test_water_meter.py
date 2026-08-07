import pathlib
import importlib.util
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
PLUGIN = ROOT / 'plugins' / 'water_meter'
METHOD_SPEC = importlib.util.spec_from_file_location('water_meter_methods', PLUGIN / 'methods.py')
METHODS = importlib.util.module_from_spec(METHOD_SPEC)
METHOD_SPEC.loader.exec_module(METHODS)


class WaterMeterRegressionTests(unittest.TestCase):
    def test_measurement_has_no_extra_active_loop_sleep(self):
        source = (PLUGIN / '__init__.py').read_text(encoding='utf-8-sig')
        counter_start = source.index('def counter(')
        counter_end = source.index('\ndef get_all_values', counter_start)
        counter_source = source[counter_start:counter_end]
        self.assertIn('stop_event.wait(1.0)', counter_source)
        self.assertIn('elapsed = time.monotonic() - started', counter_source)
        self.assertIn("read_i2c_block_data(_address(), 0x01, 3)", counter_source)
        self.assertIn('decode_bcd_counter(raw)', counter_source)

    def test_three_counter_registers_are_decoded_as_bcd(self):
        self.assertEqual(METHODS.decode_bcd_counter([0x56, 0x34, 0x12]), 123456)
        with self.assertRaisesRegex(ValueError, 'invalid_counter_length'):
            METHODS.decode_bcd_counter([0x56, 0x34])
        with self.assertRaisesRegex(ValueError, 'invalid_bcd_digit'):
            METHODS.decode_bcd_counter([0x1A, 0x00, 0x00])

    def test_existing_total_is_preserved_across_numeric_storage_types(self):
        source = (PLUGIN / '__init__.py').read_text(encoding='utf-8-sig')
        self.assertIn("if 'sum' in stored_options", source)
        self.assertIn("options['sum'] = float", source)

    def test_overview_refreshes_each_second_and_has_graph(self):
        template = (PLUGIN / 'templates' / 'water_meter.html').read_text(encoding='utf-8-sig')
        self.assertIn('setInterval(updateWaterStatus, 1000)', template)
        self.assertIn('/plugins/water_meter/graph_json', template)
        self.assertIn('water-minute-rate', template)
        source = (PLUGIN / '__init__.py').read_text(encoding='utf-8-sig')
        self.assertIn("data['sec_water'] = status['meter']", source)

    def test_settings_expose_logging_and_home_controls(self):
        template = (PLUGIN / 'templates' / 'water_meter_settings.html').read_text(encoding='utf-8-sig')
        for option in ('use_footer', 'enable_log', 'en_sql_log', 'type_log', 'log_interval', 'log_records', 'log_only_flow'):
            self.assertIn('name="{}"'.format(option), template)

    def test_footer_contains_current_and_minute_rates_and_is_cleaned_up(self):
        source = (PLUGIN / '__init__.py').read_text(encoding='utf-8-sig')
        self.assertIn("label=_('Water flow')", source)
        self.assertIn("_('l/s')", source)
        self.assertIn("_('l/min')", source)
        self.assertIn("clear_plugin_runtime_data('water_meter')", source)

    def test_failed_counter_initialization_retries_and_is_visible(self):
        source = (PLUGIN / '__init__.py').read_text(encoding='utf-8-sig')
        template = (PLUGIN / 'templates' / 'water_meter.html').read_text(encoding='utf-8-sig')
        self.assertIn("raise IOError(_('Could not initialize PCF8583.'))", source)
        self.assertIn("self.status['measurement_error']", source)
        self.assertIn("data['status'] = _('I2C error')", source)
        self.assertIn('id="water-error"', template)

    def test_sql_dependency_is_optional(self):
        import json
        manifest = json.loads((PLUGIN / 'plugin.json').read_text(encoding='utf-8-sig'))
        self.assertIn({'id': 'database_connector', 'required': False}, manifest['dependencies'])

    def test_mobile_api_is_declared_and_implemented(self):
        import json
        manifest = json.loads((PLUGIN / 'plugin.json').read_text(encoding='utf-8-sig'))
        source = (PLUGIN / '__init__.py').read_text(encoding='utf-8-sig')
        self.assertEqual(manifest['mobile']['api_version'], 1)
        self.assertIn('def mobile_status(', source)
        self.assertIn('def mobile_cards(', source)

    def test_mobile_history_filters_and_bounds_points(self):
        helper_path = PLUGIN / 'mobile_history.py'
        spec = importlib.util.spec_from_file_location('water_meter_mobile_history', helper_path)
        helper = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(helper)
        import datetime
        start = datetime.datetime(2026, 8, 7, 10, 0)
        records = [{'timestamp': int((start + datetime.timedelta(seconds=index)).timestamp()), 'flow_lps': index / 10.0} for index in range(100)]
        series, history = helper.mobile_history(records, start.isoformat(), (start + datetime.timedelta(seconds=100)).isoformat(), 20, 'local')
        self.assertLessEqual(len(series[0]['points']), 20)
        self.assertEqual(history['source'], 'local')
        self.assertEqual(history['returned_points'], len(series[0]['points']))


if __name__ == '__main__':
    unittest.main()
