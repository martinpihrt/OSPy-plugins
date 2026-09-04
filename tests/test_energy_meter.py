import datetime
import importlib.util
import json
import pathlib
import sys
import tempfile
import types
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
PLUGIN = ROOT / 'plugins' / 'energy_meter'
PACKAGE = types.ModuleType('energy_meter_test_package')
PACKAGE.__path__ = [str(PLUGIN)]
sys.modules[PACKAGE.__name__] = PACKAGE


def load(name):
    spec = importlib.util.spec_from_file_location('{}.{}'.format(PACKAGE.__name__, name), PLUGIN / '{}.py'.format(name))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


model = load('model')
storage = load('storage')
sources = load('sources')
mobile_history = load('mobile_history')


class EnergyMeterTests(unittest.TestCase):
    def test_empty_templates_keep_settings_history_and_overview_structure(self):
        settings = (PLUGIN / 'templates' / 'energy_meter_settings.html').read_text(encoding='utf-8')
        history = (PLUGIN / 'templates' / 'energy_meter_log.html').read_text(encoding='utf-8')
        overview = (PLUGIN / 'templates' / 'energy_meter.html').read_text(encoding='utf-8')
        self.assertIn("$if validation_error:\n    <div class=\"alert\">$validation_error</div>\n<div class=\"energyToolbar\">", settings)
        self.assertIn('\n<form id="pluginForm"', settings)
        self.assertIn('<label class="switch"><input name="enabled"', settings)
        self.assertEqual(settings.count("<th>$_(u'Enabled')</th>"), 2)
        self.assertNotIn("<th>$_(u'On')</th>", settings)
        self.assertIn("var dayLabels = [$:{json.dumps(_('Mon')", settings)
        self.assertIn("r.find('.energyDay.on')", settings)
        self.assertNotIn('class="t-days"', settings)
        self.assertIn('class="m-metering"', settings)
        self.assertIn("metering_mode:r.find('.m-metering').val()", settings)
        self.assertIn("m.metering_mode||'phase'", settings)
        self.assertIn('Net / vector sum accounting compensates phase import and export inside each sampling interval', settings)
        switch_css = (PLUGIN / 'static' / 'energy_meter.css').read_text(encoding='utf-8')
        self.assertIn('.switch input {\n    display: none;', switch_css)
        self.assertIn('input:checked + .slider:before', switch_css)
        self.assertIn("$for record in reversed(records[-1000:]):", history)
        self.assertIn("energy_meter.clear_history_page", history)
        self.assertIn("record.get('power_l1_w', 0)", history)
        self.assertIn("record.get('import_price', 0)", history)
        self.assertIn("record.get('export_price', 0)", history)
        self.assertIn("record['metering_mode_label']", history)
        self.assertIn('\n</tbody>\n</table>\n</div>\n</div>', history)
        self.assertIn("$if selected.get('production_available'):", overview)
        self.assertIn("\n<h3>$_(u'Electricity meters')</h3>", overview)
        self.assertIn('\n</div>\n<section class="energyGraphSection">', overview)
        self.assertIn("Import and export energy by phase and accounted total", overview)
        self.assertIn("Power by phase", overview)
        self.assertIn("#energy-power-graph", overview)
        self.assertIn("import_l1_kwh", overview)
        self.assertIn("export_l3_kwh", overview)
        self.assertIn('id="energy-selected-date"', overview)
        self.assertIn("summary['periods']['selected']", overview)
        self.assertEqual(overview.count("$_(u'Cost')"), 4)
        self.assertEqual(overview.count("$_(u'Income')"), 4)

    def test_counter_delta_rebaselines_after_meter_reset(self):
        self.assertEqual(model.counter_delta(12.5, 10.0), (2.5, False))
        self.assertEqual(model.counter_delta(1.0, 99.0), (0.0, True))

    def test_interval_keeps_phase_import_export_and_applied_prices(self):
        meter = {'id': 'grid', 'label': 'Grid', 'role': 'grid'}
        reading = model.normalized_reading({'import_kwh': [11, 22, 33], 'export_kwh': [1.5, 2.5, 3.5], 'power_w': [100, -50, 25]})
        previous = {'import_kwh': [10, 20, 30], 'export_kwh': [1, 2, 3]}
        interval, state = model.make_interval(meter, reading, previous, 100, 200, {'id': 'low', 'name': 'Low', 'import_price': 5, 'export_price': 2})
        self.assertEqual(interval['import_kwh'], 6)
        self.assertEqual(interval['export_kwh'], 1.5)
        self.assertEqual(interval['cost'], 30)
        self.assertEqual(interval['income'], 3)
        self.assertEqual(interval['power_w'], 75)
        self.assertEqual(interval['metering_mode'], 'phase')
        self.assertEqual(state['import_kwh'], [11, 22, 33])

    def test_net_metering_compensates_phases_inside_each_interval(self):
        meter = {'id': 'grid', 'label': 'Grid', 'role': 'grid', 'metering_mode': 'net'}
        reading = model.normalized_reading({'import_kwh': [10.0, 16.23, 30.0], 'export_kwh': [4.0, 5.0, 10.049], 'power_w': [-530, 1031, -470]})
        previous = {'import_kwh': [10.0, 10.0, 30.0], 'export_kwh': [4.0, 5.0, 4.0]}
        interval, unused_state = model.make_interval(meter, reading, previous, 100, 200, {'id': 'default', 'name': 'Default', 'import_price': 5, 'export_price': 2})
        self.assertAlmostEqual(interval['import_kwh'], 0.181)
        self.assertEqual(interval['export_kwh'], 0)
        self.assertAlmostEqual(interval['cost'], 0.905)
        self.assertEqual(interval['income'], 0)
        self.assertEqual(interval['power_w'], 31)
        self.assertAlmostEqual(interval['import_l2_kwh'], 6.23)
        self.assertAlmostEqual(interval['export_l3_kwh'], 6.049)
        self.assertEqual(interval['metering_mode'], 'net')

    def test_net_metering_records_only_export_for_negative_interval_balance(self):
        imported, exported = model.metered_totals([0.1, 0.0, 0.2], [0.0, 0.5, 0.0], 'net')
        self.assertEqual(imported, 0)
        self.assertAlmostEqual(exported, 0.2)

    def test_unknown_metering_mode_keeps_legacy_phase_accounting(self):
        self.assertEqual(model.metered_totals([1, 2, 3], [0.5, 0.5, 0.5], 'unknown'), (6, 1.5))

    def test_tariff_supports_midnight_range_and_weekdays(self):
        tariff = {'id': 'night', 'name': 'Night', 'enabled': True, 'start_minute': 22 * 60, 'end_minute': 6 * 60, 'weekdays': [0], 'import_price': 3, 'export_price': 1}
        self.assertEqual(model.tariff_at(datetime.datetime(2026, 8, 10, 23, 0), [tariff], 9, 0)['id'], 'night')
        self.assertEqual(model.tariff_at(datetime.datetime(2026, 8, 11, 23, 0), [tariff], 9, 0)['id'], 'default')

    def test_equal_tariff_times_cover_the_complete_selected_day(self):
        tariff = {'id': 'all-day', 'name': 'All day', 'enabled': True, 'start_minute': 0, 'end_minute': 0, 'weekdays': [3], 'import_price': '0,25', 'export_price': '0,10'}
        applied = model.tariff_at(datetime.datetime(2026, 8, 20, 14, 30), [tariff], 9, 0)
        self.assertEqual(applied['id'], 'all-day')
        self.assertEqual(applied['import_price'], 0.25)

    def test_invalid_tariff_price_uses_normalized_default(self):
        tariff = {'id': 'invalid', 'name': 'Invalid', 'enabled': True, 'start_minute': 0, 'end_minute': 0, 'weekdays': list(range(7)), 'import_price': 'not-a-price', 'export_price': 'nan'}
        applied = model.tariff_at(datetime.datetime(2026, 8, 20, 14, 30), [tariff], '0,31', '0,12')
        self.assertEqual(applied['import_price'], 0.31)
        self.assertEqual(applied['export_price'], 0.12)

    def test_interval_price_is_weighted_across_tariff_boundary(self):
        started = datetime.datetime(2026, 8, 20, 21, 59).timestamp()
        ended = datetime.datetime(2026, 8, 20, 22, 1).timestamp()
        interval = {'started': started, 'ended': ended, 'import_kwh': 2.0, 'export_kwh': 1.0}
        peak = {'id': 'peak', 'name': 'Peak', 'enabled': True, 'start_minute': 22 * 60, 'end_minute': 23 * 60, 'weekdays': list(range(7)), 'import_price': 10, 'export_price': 4}
        priced = model.price_interval(interval, [peak], 2, 1)
        self.assertEqual(priced['tariff_name'], 'Default / Peak')
        self.assertEqual(priced['import_price'], 6)
        self.assertEqual(priced['export_price'], 2.5)
        self.assertEqual(priced['cost'], 12)
        self.assertEqual(priced['income'], 2.5)

    def test_stored_history_preserves_applied_prices_and_totals(self):
        with tempfile.TemporaryDirectory() as directory:
            store = storage.JsonStore(directory)
            record = {'ended': 1, 'tariff_name': 'Night', 'currency': 'EUR', 'import_price': 0.2345, 'export_price': 0.1234, 'cost': 1.234567, 'income': 0.456789}
            store.append([record])
            loaded = storage.JsonStore(directory).history()[0]
            self.assertEqual(loaded, record)

    def test_aggregate_splits_restart_interval_at_period_boundary(self):
        record = {'meter_id': 'grid', 'role': 'grid', 'started': 0, 'ended': 200, 'import_kwh': 10, 'export_kwh': 2, 'cost': 50, 'income': 4}
        self.assertEqual(model.aggregate([record], 100, 200)['import_kwh'], 5)

    def test_selected_day_uses_local_midnight_and_clamps_future_values(self):
        now = datetime.datetime(2026, 8, 20, 7, 30)
        selected = model.selected_day_bounds('2026-08-13', now)
        self.assertEqual(datetime.datetime.fromtimestamp(selected['start']), datetime.datetime(2026, 8, 13, 0, 0))
        self.assertEqual(datetime.datetime.fromtimestamp(selected['end']), datetime.datetime(2026, 8, 14, 0, 0))
        self.assertEqual(selected['date'], '2026-08-13')
        self.assertFalse(selected['is_today'])

        today = model.selected_day_bounds('2099-01-01', now)
        self.assertEqual(today['date'], '2026-08-20')
        self.assertEqual(today['end'], now.timestamp())
        self.assertTrue(today['is_today'])

    def test_solar_summary_never_calls_grid_export_production(self):
        grid = {'meter_id': 'grid', 'role': 'grid', 'started': 0, 'ended': 100, 'import_kwh': 2, 'export_kwh': 4, 'cost': 10, 'income': 8}
        self.assertFalse(model.solar_summary([grid], 0, 100)['production_available'])
        solar = {'meter_id': 'solar', 'role': 'production', 'started': 0, 'ended': 100, 'import_kwh': 10, 'export_kwh': 0, 'cost': 0, 'income': 0}
        result = model.solar_summary([grid, solar], 0, 100)
        self.assertEqual(result['production_kwh'], 10)
        self.assertEqual(result['house_consumption_kwh'], 8)
        self.assertEqual(result['self_consumption_kwh'], 6)
        self.assertEqual(result['solar_savings'], 30)

    def test_summary_keeps_energy_but_does_not_mix_currencies(self):
        records = [
            {'role': 'grid', 'started': 0, 'ended': 100, 'import_kwh': 2, 'export_kwh': 0, 'cost': 10, 'income': 0, 'currency': 'EUR'},
            {'role': 'grid', 'started': 0, 'ended': 100, 'import_kwh': 3, 'export_kwh': 0, 'cost': 90, 'income': 0, 'currency': 'CZK'},
        ]
        result = model.solar_summary(records, 0, 100, 'EUR')
        self.assertEqual(result['grid_import_kwh'], 5)
        self.assertEqual(result['cost'], 10)

    def test_host_accepts_dns_ipv4_ipv6_and_port_but_not_path(self):
        self.assertEqual(sources.normalized_host('http://meter.local:8080/'), 'meter.local:8080')
        self.assertEqual(sources.normalized_host('192.168.1.20'), '192.168.1.20')
        self.assertEqual(sources.normalized_host('fe80::1'), '[fe80::1]')
        with self.assertRaises(ValueError):
            sources.normalized_host('meter.local/rpc/Other')

    def test_parse_shelly_import_and_returned_energy(self):
        data = {'em:0': {'a_act_power': 10, 'b_act_power': -20, 'c_act_power': 30}, 'emdata:0': {'a_total_act_energy': 1000, 'b_total_act_energy': 2000, 'c_total_act_energy': 3000, 'a_total_act_ret_energy': 400, 'b_total_act_ret_energy': 500, 'c_total_act_ret_energy': 600}, 'sys': {'mac': 'abc'}}
        result = sources.parse_status(data)
        self.assertEqual(result['import_kwh'], [1, 2, 3])
        self.assertEqual(result['export_kwh'], [0.4, 0.5, 0.6])
        self.assertEqual(result['power_w'], [10, -20, 30])

    def test_integrator_selection_distinguishes_cached_pending_disabled_and_missing(self):
        cached = [{'id': 'D885AC0CAD5C', 'label': 'Meter', 'online': True, 'energy': [1, 2, 3]}]
        self.assertIs(sources.select_integrator_device(cached, [], 'd885ac0cad5c'), cached[0])
        configured = [{'id': 'd885ac0cad5c', 'label': 'Meter', 'enabled': True}]
        with self.assertRaises(sources.IntegratorReadingPending):
            sources.select_integrator_device([], configured, 'd885ac0cad5c')
        configured[0]['enabled'] = False
        with self.assertRaises(sources.IntegratorMeterDisabled):
            sources.select_integrator_device([], configured, 'd885ac0cad5c')
        with self.assertRaises(sources.IntegratorMeterUnavailable):
            sources.select_integrator_device([], configured, 'missing')

    def test_older_integrator_parallel_lists_are_available_during_warm_up(self):
        configured = sources.legacy_integrator_configuration({'number_sensors': 2, 'sensor_id': ['first', 'second'], 'sensor_label': ['One', 'Two'], 'use_sensor': [True, False], 'sensor_type': [10, 2]})
        self.assertEqual(configured[0], {'id': 'first', 'label': 'One', 'enabled': True, 'type': 10})
        self.assertFalse(configured[1]['enabled'])

    def test_integrator_warm_up_retries_only_pending_meters(self):
        source = (PLUGIN / '__init__.py').read_text(encoding='utf-8')
        self.assertIn('retry_only = set(self.pending_integrator_meters)', source)
        self.assertIn("if retry_only and meter['id'] not in retry_only:", source)
        self.assertIn('wait_seconds = 5 if pending_integrator_meters else', source)
        self.assertIn('except IntegratorReadingPending:', source)
        self.assertIn("value.get('pending')", source)

    def test_manifest_and_cache_keys_use_version_1_0_7(self):
        manifest = json.loads((PLUGIN / 'plugin.json').read_text(encoding='utf-8'))
        self.assertEqual(manifest['version'], '1.0.7')
        for template_name in ('energy_meter.html', 'energy_meter_settings.html', 'energy_meter_help.html', 'energy_meter_log.html'):
            template = (PLUGIN / 'templates' / template_name).read_text(encoding='utf-8')
            self.assertIn('energy_meter.css?v=1.0.7', template)

    def test_state_and_history_survive_new_store_instance(self):
        with tempfile.TemporaryDirectory() as directory:
            first = storage.JsonStore(directory, max_records=2)
            first.save_state({'grid': {'import_kwh': [1, 2, 3]}})
            first.append([{'ended': 1}, {'ended': 2}, {'ended': 3}])
            second = storage.JsonStore(directory, max_records=2)
            self.assertEqual(second.states()['grid']['import_kwh'], [1, 2, 3])
            self.assertEqual([record['ended'] for record in second.history()], [2, 3])
            second.reset_meter('grid')
            self.assertEqual(second.states(), {})

    def test_history_journal_appends_and_clear_preserves_state(self):
        with tempfile.TemporaryDirectory() as directory:
            store = storage.JsonStore(directory, max_records=0)
            store.save_state({'grid': {'import_kwh': [1, 2, 3]}})
            store.append([{'ended': 1}])
            store.append([{'ended': 2}])
            journal = pathlib.Path(directory, 'history.jsonl')

            self.assertEqual([record['ended'] for record in store.history()], [1, 2])
            self.assertEqual(len(journal.read_text(encoding='utf-8').splitlines()), 2)

            store.clear_history()
            self.assertEqual(store.history(), [])
            self.assertEqual(store.states()['grid']['import_kwh'], [1, 2, 3])

    def test_history_journal_compacts_only_after_retention_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            store = storage.JsonStore(directory, max_records=3)
            store.append([{'ended': 1}, {'ended': 2}, {'ended': 3}])
            store.append([{'ended': 4}])

            self.assertEqual([record['ended'] for record in store.history()], [2, 3, 4])

    def test_mobile_history_filters_iso_range_and_keeps_extremes(self):
        start = datetime.datetime(2026, 8, 9, 10, 0)
        records = []
        for index in range(100):
            value = 5000 if index == 50 else (-4000 if index == 51 else index)
            records.append({'meter_id': 'grid', 'ended': (start + datetime.timedelta(seconds=index)).timestamp(), 'power_w': value})
        series, history = mobile_history.mobile_history(records, [{'id': 'grid', 'label': 'Grid', 'enabled': True}], start.isoformat(), (start + datetime.timedelta(seconds=100)).isoformat(), 20, 'local')
        values = [point['value'] for point in series[0]['points']]
        self.assertIn(5000, values)
        self.assertIn(-4000, values)
        self.assertLessEqual(len(values), 20)
        self.assertEqual(history['returned_points'], len(values))


if __name__ == '__main__':
    unittest.main()
