import datetime
import importlib.util
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
        switch_css = (PLUGIN / 'static' / 'energy_meter.css').read_text(encoding='utf-8')
        self.assertIn('.switch input {\n    display: none;', switch_css)
        self.assertIn('input:checked + .slider:before', switch_css)
        self.assertIn("$for record in reversed(records[-1000:]):", history)
        self.assertIn('\n</tbody>\n</table>\n</div>\n</div>', history)
        self.assertIn("$if today.get('production_available'):", overview)
        self.assertIn("\n<h3>$_(u'Electricity meters')</h3>", overview)
        self.assertIn('\n</div>\n<section class="energyGraphSection">', overview)

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
        self.assertEqual(state['import_kwh'], [11, 22, 33])

    def test_tariff_supports_midnight_range_and_weekdays(self):
        tariff = {'id': 'night', 'name': 'Night', 'enabled': True, 'start_minute': 22 * 60, 'end_minute': 6 * 60, 'weekdays': [0], 'import_price': 3, 'export_price': 1}
        self.assertEqual(model.tariff_at(datetime.datetime(2026, 8, 10, 23, 0), [tariff], 9, 0)['id'], 'night')
        self.assertEqual(model.tariff_at(datetime.datetime(2026, 8, 11, 23, 0), [tariff], 9, 0)['id'], 'default')

    def test_aggregate_splits_restart_interval_at_period_boundary(self):
        record = {'meter_id': 'grid', 'role': 'grid', 'started': 0, 'ended': 200, 'import_kwh': 10, 'export_kwh': 2, 'cost': 50, 'income': 4}
        self.assertEqual(model.aggregate([record], 100, 200)['import_kwh'], 5)

    def test_solar_summary_never_calls_grid_export_production(self):
        grid = {'meter_id': 'grid', 'role': 'grid', 'started': 0, 'ended': 100, 'import_kwh': 2, 'export_kwh': 4, 'cost': 10, 'income': 8}
        self.assertFalse(model.solar_summary([grid], 0, 100)['production_available'])
        solar = {'meter_id': 'solar', 'role': 'production', 'started': 0, 'ended': 100, 'import_kwh': 10, 'export_kwh': 0, 'cost': 0, 'income': 0}
        result = model.solar_summary([grid, solar], 0, 100)
        self.assertEqual(result['production_kwh'], 10)
        self.assertEqual(result['house_consumption_kwh'], 8)
        self.assertEqual(result['self_consumption_kwh'], 6)
        self.assertEqual(result['solar_savings'], 30)

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
