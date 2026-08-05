import datetime
import importlib.util
import os
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HELPER = os.path.join(ROOT, "plugins", "air_temp_humi", "mobile_history.py")
SPEC = importlib.util.spec_from_file_location("mobile_history_test", HELPER)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class MobileHistoryTests(unittest.TestCase):
    def graph(self, values):
        return [{
            "station": "Probe",
            "balances": {
                str(epoch): {"total": value} for epoch, value in values
            },
        }]

    def test_filters_requested_interval_and_reports_last_available(self):
        start = datetime.datetime(2026, 8, 5, 10, 0)
        epochs = [int((start + datetime.timedelta(minutes=i)).timestamp())
                  for i in range(4)]
        series, history = MODULE.mobile_history(
            self.graph(list(zip(epochs, [1, 2, 3, 4]))),
            [("probe", "Probe", "C")],
            (start + datetime.timedelta(minutes=1)).isoformat(),
            (start + datetime.timedelta(minutes=2)).isoformat(),
            400,
            "sql",
        )
        self.assertEqual([point["value"] for point in series[0]["points"]],
                         [2.0, 3.0])
        self.assertEqual(history["source"], "sql")
        self.assertEqual(history["returned_points"], 2)
        self.assertEqual(
            history["last_available"],
            datetime.datetime.fromtimestamp(epochs[-1]).isoformat())

    def test_downsampling_retains_bucket_minimum_and_maximum(self):
        start = datetime.datetime(2026, 8, 5, 10, 0)
        values = []
        for index in range(100):
            value = 1000 if index == 50 else (-1000 if index == 51 else index)
            values.append((int((start + datetime.timedelta(seconds=index)).timestamp()),
                           value))
        series, history = MODULE.mobile_history(
            self.graph(values), [("probe", "Probe", "C")],
            start.isoformat(),
            (start + datetime.timedelta(seconds=100)).isoformat(), 20)
        sampled = [point["value"] for point in series[0]["points"]]
        self.assertLessEqual(len(sampled), 20)
        self.assertIn(-1000.0, sampled)
        self.assertIn(1000.0, sampled)
        self.assertEqual(history["returned_points"], len(sampled))


if __name__ == "__main__":
    unittest.main()
