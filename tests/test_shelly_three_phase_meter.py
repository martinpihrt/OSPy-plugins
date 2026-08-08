import importlib.util
import pathlib
import unittest


MODULE_PATH = pathlib.Path(__file__).resolve().parents[1] / 'plugins' / 'shelly_cloud_integrator' / 'three_phase_meter.py'
SPEC = importlib.util.spec_from_file_location('shelly_three_phase_meter', MODULE_PATH)
three_phase_meter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(three_phase_meter)


class ShellyThreePhaseMeterTests(unittest.TestCase):
    def setUp(self):
        self.status = {
            'em:0': {
                'a_act_power': 100.5, 'b_act_power': -20.0, 'c_act_power': 300.0,
                'a_voltage': 230.1, 'b_voltage': 231.2, 'c_voltage': 229.8,
                'a_current': 0.5, 'b_current': 0.2, 'c_current': 1.4,
                'a_pf': 0.98, 'b_pf': -0.90, 'c_pf': 0.99,
                'total_act_power': 380.5,
            },
            'emdata:0': {
                'a_total_act_energy': 1000, 'b_total_act_energy': 2500, 'c_total_act_energy': 500,
            },
            'wifi': {'sta_ip': '192.168.1.20', 'rssi': -55},
        }

    def test_parses_shelly_3em_gen3_without_temperature_component(self):
        meter = three_phase_meter.parse_three_phase_meter(self.status)
        self.assertEqual(meter['powers'], [100.5, -20.0, 300.0])
        self.assertEqual(meter['reverse_powers'], [0, 20.0, 0])
        self.assertEqual(meter['voltages'], [230.1, 231.2, 229.8])
        self.assertEqual(meter['energy_kwh'], [1.0, 2.5, 0.5])
        self.assertEqual(meter['total_energy'], 4.0)
        self.assertIsNone(meter['temperature'])

    def test_parses_cloud_status_wrapper(self):
        cloud = {'isok': True, 'data': {'online': True, 'device_status': self.status}}
        meter = three_phase_meter.parse_three_phase_meter(cloud, cloud=True)
        self.assertTrue(meter['online'])
        self.assertEqual(meter['ip'], '192.168.1.20')
        self.assertEqual(meter['rssi'], -55)

    def test_rejects_status_without_energy_meter_component(self):
        with self.assertRaises(ValueError):
            three_phase_meter.parse_three_phase_meter({'wifi': {}})


if __name__ == '__main__':
    unittest.main()
