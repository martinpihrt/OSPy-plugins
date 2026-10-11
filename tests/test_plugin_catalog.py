import json
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
PLUGINS_DIR = ROOT / "plugins"
GENERATOR = ROOT / "tools" / "generate_plugin_table.py"


class PluginCatalogTests(unittest.TestCase):
    def test_every_manifest_has_catalog_metadata(self):
        manifests = sorted(PLUGINS_DIR.glob("*/plugin.json"))
        self.assertTrue(manifests)
        names = set()
        for manifest in manifests:
            data = json.loads(manifest.read_text(encoding="utf-8"))
            for field in ("name", "version", "description"):
                with self.subTest(plugin=manifest.parent.name, field=field):
                    self.assertIsInstance(data.get(field), str)
                    self.assertTrue(data[field].strip())
            self.assertNotIn(data["name"], names)
            names.add(data["name"])

    def test_readme_plugin_table_is_current(self):
        result = subprocess.run(
            [sys.executable, str(GENERATOR), "--check"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
