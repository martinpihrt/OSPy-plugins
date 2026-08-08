import importlib.util
import os
import pathlib
import tempfile
import unittest


MODULE_PATH = (
    pathlib.Path(__file__).resolve().parents[1]
    / 'plugins'
    / 'ospy_backup'
    / 'backup_state.py'
)
SPEC = importlib.util.spec_from_file_location('ospy_backup_state', MODULE_PATH)
backup_state = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(backup_state)


class OSpyBackupStateTests(unittest.TestCase):
    def test_latest_backup_survives_process_state_reset(self):
        with tempfile.TemporaryDirectory() as folder:
            older = pathlib.Path(folder) / '2026.08.06_11-10-22_PluginsBackup.zip'
            newest = pathlib.Path(folder) / '2026.08.07_12-41-03_PluginsBackup.zip'
            older.write_bytes(b'old')
            newest.write_bytes(b'newest')
            os.utime(older, (10, 10))
            os.utime(newest, (20, 20))
            result = backup_state.latest_backup(folder)
            self.assertEqual(result['filename'], newest.name)
            self.assertEqual(result['size'], 6)
            self.assertEqual(result['modified'], 20)

    def test_ignores_unrelated_files(self):
        with tempfile.TemporaryDirectory() as folder:
            pathlib.Path(folder, 'notes.txt').write_text('x', encoding='utf-8')
            pathlib.Path(folder, 'system-backup.zip').write_bytes(b'x')
            self.assertIsNone(backup_state.latest_backup(folder))


if __name__ == '__main__':
    unittest.main()
