import importlib.util
import sqlite3
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_PATH = ROOT / 'plugins' / 'database_connector' / '__init__.py'


class DatabaseConnectorQueueTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.modules = {}
        self._install_stub('web', seeother=lambda *args: None, input=lambda: {})

        class PluginOptions(dict):
            def __init__(self, _name, defaults):
                super().__init__(defaults)

            def web_update(self, values):
                self.update(values)

        plugins = types.ModuleType('plugins')
        plugins.__path__ = []
        plugins.PluginOptions = PluginOptions
        plugins.plugin_url = lambda page: str(page)
        plugins.plugin_data_dir = lambda: self.temp_dir.name
        self._install_module('plugins', plugins)
        self._install_module('ospy', types.ModuleType('ospy'))
        log_module = types.ModuleType('ospy.log')
        log_module.log = mock.Mock()
        self._install_module('ospy.log', log_module)
        helpers = types.ModuleType('ospy.helpers')
        helpers.datetime_string = lambda *args: ''
        helpers.get_input = lambda data, key, default, _validate: data.get(key, default)
        helpers.verify_csrf = lambda *_args: None
        self._install_module('ospy.helpers', helpers)
        webpages = types.ModuleType('ospy.webpages')
        webpages.ProtectedPage = type('ProtectedPage', (), {})
        self._install_module('ospy.webpages', webpages)
        package = types.ModuleType('plugins.database_connector')
        package.__path__ = [str(PLUGIN_PATH.parent)]
        self._install_module('plugins.database_connector', package)
        self.previous_gettext = getattr(builtins_module := __import__('builtins'), '_', None)
        builtins_module._ = lambda value: value

        spec = importlib.util.spec_from_file_location('plugins.database_connector', PLUGIN_PATH)
        self.module = importlib.util.module_from_spec(spec)
        sys.modules['plugins.database_connector'] = self.module
        spec.loader.exec_module(self.module)
        self.module.plugin_options['use_buffer'] = True

    def tearDown(self):
        if self.previous_gettext is None:
            delattr(__import__('builtins'), '_')
        else:
            __import__('builtins')._ = self.previous_gettext
        for name, original in self.modules.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original
        self.temp_dir.cleanup()

    def _install_module(self, name, module):
        if name not in self.modules:
            self.modules[name] = sys.modules.get(name)
        sys.modules[name] = module

    def _install_stub(self, name, **attributes):
        module = types.ModuleType(name)
        for key, value in attributes.items():
            setattr(module, key, value)
        self._install_module(name, module)

    def test_settings_template_reads_queue_count_from_plugin_options(self):
        source = PLUGIN_PATH.read_text(encoding='utf-8')
        template = (ROOT / 'plugins' / 'database_connector' / 'templates' / 'database_connector.html').read_text(encoding='utf-8')

        self.assertIn("skipped={'sql_name', 'sql_size', 'queue_size', 'queue_bytes'}", source)
        self.assertIn("$plugin_options['queue_size']", template)
        self.assertIn("name='queue_warning_mib'", template)
        self.assertIn("name='queue_max_mib'", template)
        self.assertIn("name='queue_email_alerts'", template)
        self.assertIn("name='queue_email_subject'", template)
        self.assertNotIn('$queue_size', template)

    def test_enqueue_preserves_command_order_and_commit_flag(self):
        self.module.enqueue_db('INSERT INTO sample VALUES (1)', commit=True)
        self.module.enqueue_db('INSERT INTO sample VALUES (2)', commit=False)

        connection = sqlite3.connect(self.module.queue_path())
        try:
            rows = connection.execute('SELECT sql, commit_after FROM pending_queries ORDER BY id').fetchall()
        finally:
            connection.close()

        self.assertEqual(rows, [('INSERT INTO sample VALUES (1)', 1), ('INSERT INTO sample VALUES (2)', 0)])
        self.assertEqual(self.module.db_queue_size(), 2)

    def test_failed_direct_write_is_queued(self):
        self.module.is_installed_ok = True
        self.module.plugin_options['use_buffer'] = True
        self.module.plugin_options['use'] = True
        self.module.db_config = lambda: {}
        connector_error = type('Error', (Exception,), {'__init__': lambda self, message: (Exception.__init__(self, message), setattr(self, 'errno', 2003))[-1]})
        errorcode = types.SimpleNamespace(ER_ACCESS_DENIED_ERROR=1045, ER_BAD_DB_ERROR=1049, ER_TABLE_EXISTS_ERROR=1050)
        errorcode.CR_CONNECTION_ERROR = 2003
        connector = types.SimpleNamespace(
            __version_info__=(1, 0, 0),
            connect=mock.Mock(side_effect=connector_error('offline')),
            Error=connector_error,
        )
        mysql_module = types.ModuleType('mysql')
        mysql_module.connector = connector
        self._install_module('mysql', mysql_module)
        self._install_module('mysql.connector', connector)
        connector.errorcode = errorcode

        result = self.module.execute_db('INSERT INTO sample VALUES (1)', commit=True)

        self.assertEqual(result, -1)
        self.assertEqual(self.module.db_queue_size(), 1)
        connection = sqlite3.connect(self.module.queue_path())
        try:
            self.assertEqual(connection.execute('SELECT sql, commit_after FROM pending_queries').fetchone(), ('INSERT INTO sample VALUES (1)', 1))
        finally:
            connection.close()

    def test_worker_replays_in_order_and_deletes_successful_commands(self):
        self.module.enqueue_db('INSERT INTO sample VALUES (1)', commit=True)
        self.module.enqueue_db('INSERT INTO sample VALUES (2)', commit=False)
        self.module.started = True
        self.module.plugin_options['use_buffer'] = True
        calls = []

        def execute(sql, commit=False, test=False, fetch=False, _from_queue=False, _queue_failure=False, _queued_at=None):
            calls.append((sql, commit, _from_queue, _queued_at))
            return -1

        self.module.execute_db = execute
        self.module.queue_stop_event.clear()
        self.module.process_db_queue(_queue_failure=True)
        self.module.process_db_queue(_queue_failure=True)

        self.assertEqual(
            [call[:3] for call in calls],
            [('INSERT INTO sample VALUES (1)', True, True), ('INSERT INTO sample VALUES (2)', False, True)],
        )
        self.assertTrue(all(call[3] > 0 for call in calls))
        self.assertEqual(self.module.db_queue_size(), 0)

    def test_queue_rejects_a_command_larger_than_the_configured_limit(self):
        self.module.plugin_options['queue_warning_mib'] = 1
        self.module.plugin_options['queue_max_mib'] = 2

        result = self.module.enqueue_db('x' * (3 * 1024 * 1024), commit=True)

        self.assertIsNone(result)
        self.assertEqual(self.module.db_queue_size(), 0)

    def test_queue_limit_form_values_keep_existing_values_when_not_rendered(self):
        self.module.plugin_options['queue_warning_mib'] = 37
        self.module.plugin_options['queue_max_mib'] = 71

        self.assertEqual(self.module.queue_limits_from_input({}), (37, 71))
        with self.assertRaisesRegex(ValueError, 'warning size'):
            self.module.queue_limits_from_input({
                'queue_warning_mib': 100,
                'queue_max_mib': 100,
            })

    def test_replay_sets_the_mysql_session_timestamp_to_the_queued_time(self):
        self.module.is_installed_ok = True
        executed = []

        class Cursor:
            def execute(self, sql):
                executed.append(sql)
                return None

            def close(self):
                pass

        class Connection:
            def is_connected(self):
                return True

            def cursor(self):
                return Cursor()

            def close(self):
                pass

            def commit(self):
                pass

        connector = types.SimpleNamespace(
            connect=lambda **_kwargs: Connection(),
            errorcode=types.SimpleNamespace(),
        )
        mysql_module = types.ModuleType('mysql')
        mysql_module.connector = connector
        self._install_module('mysql', mysql_module)
        self._install_module('mysql.connector', connector)

        result = self.module.execute_db(
            'INSERT INTO sample VALUES (1)',
            commit=True,
            _from_queue=True,
            _queued_at=1760000000.9,
        )

        self.assertEqual(result, -1)
        self.assertEqual(executed[0], 'USE ospy')
        self.assertEqual(executed[1], 'SET timestamp = 1760000000')
        self.assertEqual(executed[2], 'INSERT INTO sample VALUES (1)')

    def test_queue_alert_uses_the_configured_ssl_mail_subject(self):
        sent = []
        email_plugin = types.ModuleType('plugins.email_notifications_ssl')

        def try_mail(body, text, attachment=None, subject=None):
            sent.append((body, text, attachment, subject))
            return True

        email_plugin.try_mail = try_mail
        self._install_module('plugins.email_notifications_ssl', email_plugin)
        self.module.plugin_options['queue_email_alerts'] = True
        self.module.plugin_options['queue_email_subject'] = 'Queue warning'

        self.assertTrue(self.module.send_queue_email('warning', 80 * 1024 * 1024))
        self.assertIn('Queue warning - Database queue is large', sent[0][3])
        self.assertIn('80.0 MiB', sent[0][1])

    def test_clear_queue_removes_all_pending_commands(self):
        self.module.enqueue_db('INSERT INTO sample VALUES (1)')
        self.module.enqueue_db('INSERT INTO sample VALUES (2)')

        self.module.clear_db_queue()

        self.assertEqual(self.module.db_queue_size(), 0)

    def test_failed_replay_keeps_command_queued(self):
        self.module.enqueue_db('INSERT INTO sample VALUES (1)')
        self.module.started = True
        self.module.plugin_options['use_buffer'] = True
        self.module.queue_stop_event.clear()
        self.module.queue_stop_event.wait = mock.Mock(side_effect=lambda _seconds: self.module.queue_stop_event.set())

        def fail_replay(*_args, **_kwargs):
            return None

        self.module.execute_db = fail_replay
        self.module.process_db_queue(_queue_failure=True)

        self.assertEqual(self.module.db_queue_size(), 1)


if __name__ == '__main__':
    unittest.main()
