import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
PLUGINS_DIR = ROOT / "plugins"
GENERATOR = ROOT / "tools" / "generate_plugin_wiki.py"


class PluginWikiTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.wiki = Path(self.temporary_directory.name)
        result = subprocess.run(
            [sys.executable, str(GENERATOR), str(self.wiki)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_every_manifest_has_a_complete_wiki_page(self):
        manifests = sorted(PLUGINS_DIR.glob("*/plugin.json"))
        self.assertEqual(len(manifests), 64)
        for manifest in manifests:
            data = json.loads(manifest.read_text(encoding="utf-8"))
            page = self.wiki / f"Plugin-{manifest.parent.name.replace('_', '-')}.md"
            with self.subTest(plugin=manifest.parent.name):
                self.assertTrue(page.is_file())
                content = page.read_text(encoding="utf-8")
                self.assertIn(f"# {data['name']}", content)
                self.assertIn("## At a glance", content)
                self.assertIn("## What it is for", content)
                self.assertIn("## How it works and how to configure it", content)
                self.assertIn("## Support", content)
                self.assertNotIn("$def with", content)
                self.assertNotIn("plugin_url(", content)

    def test_generated_wiki_is_current_and_has_navigation(self):
        result = subprocess.run(
            [sys.executable, str(GENERATOR), str(self.wiki), "--check"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Wiki verified: 74 Markdown files", result.stdout)
        for required in (
            "Home.md",
            "Getting-Started.md",
            "Plugin-Catalog.md",
            "Hardware-and-I2C.md",
            "Permissions-and-Security.md",
            "Integrations.md",
            "Troubleshooting.md",
            "Contributing.md",
            "_Sidebar.md",
            "_Footer.md",
        ):
            self.assertTrue((self.wiki / required).is_file(), required)


if __name__ == "__main__":
    unittest.main()
