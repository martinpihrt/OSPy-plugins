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
