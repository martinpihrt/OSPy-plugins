import ast
import json
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


def function_source(path, name):
    source = path.read_text(encoding='utf-8')
    tree = ast.parse(source)
    function = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == name)
    return ast.get_source_segment(source, function)


class MobileVisualInterfaceTests(unittest.TestCase):
    def test_ospy_backup_declares_mobile_create_and_download(self):
        plugin = ROOT / 'plugins' / 'ospy_backup'
        manifest = json.loads((plugin / 'plugin.json').read_text(encoding='utf-8'))
        cards = function_source(plugin / '__init__.py', 'mobile_cards')
        download = function_source(plugin / '__init__.py', 'mobile_download')

        self.assertIn('create_backup', manifest['mobile']['actions'])
        self.assertIn('latest_backup', manifest['mobile']['downloads'])
        self.assertIn("'actions':", cards)
        self.assertIn("card['downloads']", cards)
        self.assertIn("os.path.commonpath", download)

    def test_system_update_mobile_metrics_use_stable_ids(self):
        plugin = ROOT / 'plugins' / 'system_update'
        cards = function_source(plugin / '__init__.py', 'mobile_cards')

        self.assertIn("('current_commit', 'current_commit')", cards)
        self.assertIn("('target_commit', 'target_commit')", cards)
        self.assertIn("('update_available', 'update_available')", cards)

    def test_venetian_blind_cards_include_each_blind_actions(self):
        plugin = ROOT / 'plugins' / 'venetian_blind'
        cards = function_source(plugin / '__init__.py', 'mobile_cards')

        self.assertIn("'payload': {'blind_uid': blind['uid']}", cards)
        self.assertIn("blind.get('tilt_labels'", cards)

    def test_weather_dashboard_declares_native_gauge_contract(self):
        plugin = ROOT / 'plugins' / 'weather_dashboard'
        manifest = json.loads((plugin / 'plugin.json').read_text(encoding='utf-8'))
        cards = function_source(plugin / '__init__.py', 'mobile_cards')

        self.assertEqual(manifest['mobile']['api_version'], 1)
        self.assertIn("'kind': 'gauge_dashboard'", cards)
        self.assertIn("'mode': plugin_options.get('dashboard_mode'", cards)
        self.assertIn("'ticks': gauge_ticks", cards)
        self.assertIn("'ranges': [", cards)

    def test_astro_uses_fixed_timeline_instead_of_history(self):
        plugin = ROOT / 'plugins' / 'sunrise_and_sunset'
        cards = function_source(plugin / '__init__.py', 'mobile_cards')

        self.assertIn("'kind': 'daylight_timeline'", cards)
        self.assertIn("'timeline': {", cards)
        self.assertNotIn("'history':", cards)
        self.assertNotIn("'series':", cards)


if __name__ == '__main__':
    unittest.main()
