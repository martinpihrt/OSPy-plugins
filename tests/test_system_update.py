import ast
import json
import pathlib
import shlex
import subprocess
import tempfile
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
        '_': lambda value: value,
        'log': mock.Mock(),
        'os': __import__('os'),
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

        self.assertEqual(manifest['version'], '1.2.9')
        self.assertIn('Version 1.2.9', readme)
        self.assertIn('System Update v1.2.9', changelog)
        self.assertIn('HTTP/1.1', changelog)

    def test_oversized_debug_log_is_reported_only_when_deleting_it_makes_backup_fit(self):
        namespace = load_functions('_format_file_size', 'debug_log_backup_issue')
        detect = namespace['debug_log_backup_issue']
        with tempfile.TemporaryDirectory() as root:
            data = pathlib.Path(root, 'ospy', 'data')
            data.mkdir(parents=True)
            debug_log = data / 'events.log'
            with debug_log.open('wb') as target:
                target.truncate(2 * 1024 * 1024)
            sources = [('ospy/data/events.log', str(debug_log))]
            issue = detect(
                root, max_expanded_size=2 * 1024 * 1024, sources=sources
            )
            self.assertEqual(issue['display_path'], 'ospy/data/events.log')
            self.assertEqual(issue['size'], 2 * 1024 * 1024)
            self.assertEqual(issue['limit_text'], '2.0 MiB')

            other = data / 'other.bin'
            with other.open('wb') as target:
                target.truncate(2 * 1024 * 1024)
            sources.append(('ospy/data/other.bin', str(other)))
            self.assertEqual({}, detect(
                root, max_expanded_size=2 * 1024 * 1024, sources=sources
            ))

    def test_confirmed_cleanup_disables_debug_logging_and_deletes_only_events_log(self):
        namespace = load_functions('delete_debug_log_for_update')
        options = mock.Mock()
        options.debug_log = True
        namespace['options'] = options
        with tempfile.TemporaryDirectory() as root:
            data = pathlib.Path(root, 'ospy', 'data')
            data.mkdir(parents=True)
            debug_log = data / 'events.log'
            debug_log.write_text('debug data', encoding='utf-8')
            keep = data / 'keep.txt'
            keep.write_text('keep', encoding='utf-8')
            namespace['debug_log_backup_issue'] = mock.Mock(return_value={
                'path': namespace['os'].path.abspath(namespace['os'].path.join(
                    root, 'ospy', 'data', 'events.log'
                )),
            })

            self.assertTrue(namespace['delete_debug_log_for_update'](root))

            self.assertFalse(debug_log.exists())
            self.assertTrue(keep.exists())
            self.assertFalse(options.debug_log)
            options.save_now.assert_called_once_with()

    def test_cleanup_rejects_any_path_other_than_events_log(self):
        namespace = load_functions('delete_debug_log_for_update')
        namespace['options'] = mock.Mock()
        with tempfile.TemporaryDirectory() as root:
            data = pathlib.Path(root, 'ospy', 'data')
            data.mkdir(parents=True)
            debug_log = data / 'events.log'
            debug_log.write_text('debug data', encoding='utf-8')
            namespace['debug_log_backup_issue'] = mock.Mock(return_value={
                'path': str(pathlib.Path(root, 'outside.log').resolve()),
            })

            with self.assertRaisesRegex(RuntimeError, 'path is invalid'):
                namespace['delete_debug_log_for_update'](root)

            self.assertTrue(debug_log.exists())

    def test_cleanup_interface_requires_post_and_explicit_confirmation(self):
        plugin = PLUGIN_PATH.parent
        source = PLUGIN_PATH.read_text(encoding='utf-8')
        template = (plugin / 'templates' / 'system_update_debug_log_cleanup.html').read_text(
            encoding='utf-8'
        )
        self.assertIn('class cleanup_update_page(ProtectedPage):', source)
        self.assertIn('def POST(self):', source)
        self.assertIn("verify_csrf(data)", source)
        self.assertIn("delete_debug_log_and_update", source)
        self.assertIn("$plugins.plugin_url('system_update.cleanup_update_page')", template)
        self.assertIn('$:csrf_input()', template)
        self.assertIn("Permanently delete the debug log and continue the update?", template)

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
