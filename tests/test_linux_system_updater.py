import datetime as dt
import importlib.util
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "linux_system_updater"

spec = importlib.util.spec_from_file_location("linux_system_updater_model", PLUGIN / "model.py")
model = importlib.util.module_from_spec(spec)
spec.loader.exec_module(model)


class LinuxSystemUpdaterModelTests(unittest.TestCase):
    def test_daily_weekly_and_monthly_schedules_are_future_local_times(self):
        now = dt.datetime(2026, 11, 16, 10, 30)  # Monday
        self.assertEqual(
            model.next_check(now, "daily", "11:00"),
            dt.datetime(2026, 11, 16, 11, 0),
        )
        self.assertEqual(
            model.next_check(now, "weekly", "09:00", weekday=0),
            dt.datetime(2026, 11, 23, 9, 0),
        )
        self.assertEqual(
            model.next_check(now, "monthly", "04:15", month_day=20),
            dt.datetime(2026, 11, 20, 4, 15),
        )

    def test_monthly_schedule_uses_last_day_of_short_month(self):
        now = dt.datetime(2027, 2, 1, 0, 0)
        self.assertEqual(
            model.next_check(now, "monthly", "03:00", month_day=31),
            dt.datetime(2027, 2, 28, 3, 0),
        )

    def test_delay_is_bounded_and_unit_is_validated(self):
        self.assertEqual(model.delay_seconds(2, "minutes"), 120)
        self.assertEqual(model.delay_seconds(2, "hours"), 7200)
        self.assertEqual(model.delay_seconds(2, "days"), 172800)
        self.assertEqual(model.delay_seconds(0, "invalid"), 3600)

    def test_upgradable_parser_returns_only_compact_package_metadata(self):
        output = """Listing... Done
curl/bookworm-security 7.88.1-10+deb12u9 arm64 [upgradable from: 7.88.1-10+deb12u8]
python3/bookworm 3.11.2-1+b2 arm64 [upgradable from: 3.11.2-1+b1]
warning text that must be ignored
"""
        updates = model.parse_upgradable(output)
        self.assertEqual([item["name"] for item in updates], ["curl", "python3"])
        self.assertTrue(updates[0]["security"])
        self.assertFalse(updates[1]["security"])
        self.assertEqual(updates[0]["installed"], "7.88.1-10+deb12u8")

    def test_exclusions_accept_only_exact_debian_package_names(self):
        self.assertEqual(
            model.parse_exclusions("linux-image, docker-ce\nlibc6:arm64; $(reboot)"),
            ["linux-image", "docker-ce", "libc6:arm64"],
        )

    def test_all_package_command_uses_upgrade_without_exclusions(self):
        self.assertEqual(
            model.build_upgrade_command(["curl", "git"], simulate=True),
            ["apt-get", "-s", "upgrade"],
        )
        self.assertEqual(
            model.build_upgrade_command(["curl", "git"]),
            ["apt-get", "upgrade", "-y"],
        )

    def test_exclusions_and_single_package_use_only_upgrade_with_allowlist(self):
        self.assertEqual(
            model.build_upgrade_command(
                ["curl", "git", "linux-image"],
                exclusions="linux-image",
            ),
            ["apt-get", "install", "--only-upgrade", "-y", "curl", "git"],
        )
        self.assertEqual(
            model.build_upgrade_command(["curl", "git"], selected="curl"),
            ["apt-get", "install", "--only-upgrade", "-y", "curl"],
        )
        with self.assertRaises(ValueError):
            model.build_upgrade_command(["curl"], selected="curl;reboot")

    def test_simulated_transaction_parser_supports_dependency_guard(self):
        output = """Inst curl [1] (2 Debian:12 [arm64])
Inst libcurl4 [1] (2 Debian:12 [arm64])
Conf curl (2 Debian:12 [arm64])
"""
        self.assertEqual(
            model.parse_simulated_packages(output), ["curl", "libcurl4"]
        )

    def test_reboot_confirmation_requires_a_changed_nonempty_boot_id(self):
        self.assertTrue(model.boot_changed("old-boot", "new-boot"))
        self.assertFalse(model.boot_changed("same", "same"))
        self.assertFalse(model.boot_changed("", "new-boot"))

    def test_pending_deadline_survives_serialized_numeric_values(self):
        self.assertTrue(model.pending_due({"execute_at": "100"}, 100.0))
        self.assertFalse(model.pending_due({"execute_at": 101}, 100.0))
        self.assertFalse(model.pending_due({}, 100.0))


class LinuxSystemUpdaterIntegrationContractTests(unittest.TestCase):
    def test_manifest_and_documentation_describe_the_new_plugin(self):
        manifest = json.loads((PLUGIN / "plugin.json").read_text(encoding="utf-8"))
        readme = (PLUGIN / "README.md").read_text(encoding="utf-8")
        self.assertEqual(manifest["id"], "linux_system_updater")
        self.assertEqual(manifest["version"], "1.0.0")
        self.assertEqual(manifest["ospy"], {"min": "3.0.354"})
        self.assertEqual(
            set(manifest["permissions"]),
            {"email", "files", "network", "subprocess", "system"},
        )
        self.assertIn("apt-get upgrade -y", readme)
        self.assertIn("recipients remain exclusively", readme)

    def test_runtime_uses_csrf_admin_checks_fixed_subprocesses_and_ospy_reboot(self):
        source = (PLUGIN / "__init__.py").read_text(encoding="utf-8")
        self.assertIn("verify_csrf(qdict)", source)
        self.assertIn('server.session.get("category") != "admin"', source)
        self.assertIn("subprocess.Popen(", source)
        self.assertNotIn("shell=True", source)
        self.assertIn("reboot(wait=3)", source)
        self.assertIn("from plugins.email_notifications_ssl import try_mail", source)
        self.assertNotIn("emladr", source)

    def test_plugin_contains_settings_help_style_and_translatable_user_interface(self):
        settings = (PLUGIN / "templates" / "linux_system_updater.html").read_text(encoding="utf-8")
        help_page = (PLUGIN / "templates" / "linux_system_updater_help.html").read_text(encoding="utf-8")
        css = (PLUGIN / "static" / "linux_system_updater.css").read_text(encoding="utf-8")
        self.assertIn("status_json", settings)
        self.assertIn("setTimeout(load", settings)
        self.assertIn("csrf_input()", settings)
        self.assertIn("E-mail Notifications SSL", help_page)
        self.assertIn("linuxUpdaterDashboard", css)


if __name__ == "__main__":
    unittest.main()
