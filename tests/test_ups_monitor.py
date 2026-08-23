import ast
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / 'plugins' / 'ups_adj'
SOURCE_PATH = PLUGIN / '__init__.py'


def _source_tree():
    return ast.parse(SOURCE_PATH.read_text(encoding='utf-8'))


def _function(tree, name):
    return next(
        node for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
    )


def _call_name(call):
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return ''


class UPSMonitorTests(unittest.TestCase):
    def test_shutdown_setting_is_backward_compatible_and_exposed_as_switch(self):
        tree = _source_tree()
        helper = _function(tree, 'automatic_shutdown_enabled')
        module = ast.Module(body=[helper], type_ignores=[])
        ast.fix_missing_locations(module)
        namespace = {}
        exec(compile(module, str(SOURCE_PATH), 'exec'), namespace)

        enabled = namespace['automatic_shutdown_enabled']
        self.assertIs(enabled({}), True)
        self.assertIs(enabled({'shutdown_enabled': True}), True)
        self.assertIs(enabled({'shutdown_enabled': False}), False)

        template = (PLUGIN / 'templates' / 'ups_adj.html').read_text(encoding='utf-8')
        self.assertIn("name='shutdown_enabled' type='checkbox'", template)
        self.assertIn("plugin_options.get('shutdown_enabled', True)", template)

    def test_system_and_ups_shutdown_are_guarded_by_the_new_setting(self):
        tree = _source_tree()
        run = _function(tree, 'run')
        shutdown_calls = [
            node for node in ast.walk(run)
            if isinstance(node, ast.Call) and _call_name(node) == '_perform_shutdown'
        ]
        self.assertEqual(len(shutdown_calls), 1)

        guarded = [
            node for node in ast.walk(run)
            if isinstance(node, ast.If)
            and isinstance(node.test, ast.Name)
            and node.test.id == 'shutdown_enabled'
            and any(call is shutdown_calls[0] for call in ast.walk(node))
        ]
        self.assertEqual(len(guarded), 1)

        shutdown = _function(tree, '_perform_shutdown')
        calls = [_call_name(node) for node in ast.walk(shutdown) if isinstance(node, ast.Call)]
        self.assertIn('poweroff', calls)
        self.assertIn('output', calls)

    def test_monitor_only_mode_has_accurate_status_and_documentation(self):
        source = SOURCE_PATH.read_text(encoding='utf-8')
        self.assertIn('automatic system shutdown is disabled and monitoring continues', source)
        self.assertIn("_('Automatic system shutdown')", source)

        help_text = (PLUGIN / 'templates' / 'ups_adj_help.html').read_text(encoding='utf-8')
        readme = (PLUGIN / 'README.md').read_text(encoding='utf-8')
        self.assertIn('without shutting down OSPy', help_text)
        self.assertIn('without shutting down OSPy', readme)

        manifest = json.loads((PLUGIN / 'plugin.json').read_text(encoding='utf-8'))
        self.assertEqual(manifest['version'], '1.0.5')


if __name__ == '__main__':
    unittest.main()
