import ast
import json
import pathlib
import shlex
import subprocess
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]
PLUGIN_PATH = ROOT / 'plugins' / 'system_update' / '__init__.py'


def load_functions(*names):
    source = PLUGIN_PATH.read_text(encoding='utf-8')
    tree = ast.parse(source)
    functions = [
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in names
    ]
    namespace = {
        'NAME': 'System Update',
        'log': mock.Mock(),
        'shlex': shlex,
        'subprocess': subprocess,
    }
    module = ast.Module(body=functions, type_ignores=[])
    exec(compile(module, str(PLUGIN_PATH), 'exec'), namespace)
    return namespace


class SystemUpdateTests(unittest.TestCase):
    def test_release_metadata_documents_transport_fix(self):
        plugin = PLUGIN_PATH.parent
        manifest = json.loads((plugin / 'plugin.json').read_text(encoding='utf-8'))
        readme = (plugin / 'README.md').read_text(encoding='utf-8')
        changelog = (ROOT / 'CHANGELOG.md').read_text(encoding='utf-8')

        self.assertEqual(manifest['version'], '1.2.8')
        self.assertIn('Version 1.2.8', readme)
        self.assertIn('System Update v1.2.8', changelog)
        self.assertIn('HTTP/1.1', changelog)

    def test_fetch_command_forces_http_1_1(self):
        namespace = load_functions('git_fetch_command')

        command = namespace['git_fetch_command']('--prune', '--tags', 'origin')

        self.assertEqual(command, [
            'git', '-c', 'http.version=HTTP/1.1',
            'fetch', '--prune', '--tags', 'origin'
        ])

    def test_required_command_surfaces_git_error_output(self):
        namespace = load_functions('run_required_command')
        error = subprocess.CalledProcessError(
            128,
            ['git', 'fetch'],
            output=b'error: RPC failed; HTTP 401\nfatal: expected flush'
        )

        with mock.patch.object(subprocess, 'check_output', side_effect=error):
            with self.assertRaisesRegex(RuntimeError, 'HTTP 401') as raised:
                namespace['run_required_command'](['git', 'fetch'])

        self.assertIn('exit code 128', str(raised.exception))
        self.assertIn('fatal: expected flush', str(raised.exception))

    def test_required_command_reports_timeout_and_partial_output(self):
        namespace = load_functions('run_required_command')
        error = subprocess.TimeoutExpired(
            ['git', 'fetch'],
            45,
            output=b'partial response'
        )

        with mock.patch.object(subprocess, 'check_output', side_effect=error):
            with self.assertRaisesRegex(RuntimeError, 'timed out after 45 seconds') as raised:
                namespace['run_required_command'](['git', 'fetch'], timeout=45)

        self.assertIn('partial response', str(raised.exception))


if __name__ == '__main__':
    unittest.main()
