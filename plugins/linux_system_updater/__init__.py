# -*- coding: utf-8 -*-
"""Scheduled Debian Linux operating-system updates for OSPy."""

__author__ = "Martin Pihrt"

import datetime as dt
import html
import json
import os
import queue
import selectors
import shutil
import subprocess
import time
import traceback
from threading import Lock, Thread

import web

from ospy.helpers import datetime_string, ospy_web_url, reboot, verify_csrf
from ospy.log import log
from ospy.options import options
from ospy.webpages import ProtectedPage
from plugins import PluginOptions, get_runtime, plugin_data_dir, plugin_url
from plugins.linux_system_updater import model


NAME = "Linux System Updater"
MENU = _("Package: Linux System Updater")
LINK = "settings_page"
STATE_SCHEMA = 1
BUSY_PHASES = {"checking", "simulating", "updating", "rebooting"}

plugin_options = PluginOptions(NAME, {
    "enabled": False,
    "schedule_frequency": "daily",
    "check_time": "03:00",
    "week_day": 0,
    "month_day": 1,
    "automatic_update": False,
    "delay_value": 1,
    "delay_unit": "hours",
    "excluded_packages": "",
    "send_email": False,
    "email_subject": _("Linux system update report from OSPy"),
    "reboot_after_update": False,
    "output_lines": 200,
})

runtime = get_runtime()
state_lock = Lock()
operation_lock = Lock()
worker = None

live_state = {
    "phase": "idle",
    "message": _("Waiting"),
    "last_error": "",
    "last_check": 0,
    "last_update": 0,
    "next_check": 0,
    "operation_started": 0,
    "operation_finished": 0,
    "updates": [],
    "output": [],
    "pending": {},
    "reboot_marker": {},
    "reboot_required": False,
    "last_notified_digest": "",
    "email_error": "",
}


def _state_file():
    return os.path.join(plugin_data_dir(), "state.json")


def _read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as source:
            value = json.load(source)
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_json(path, value):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temporary = path + ".tmp"
    with open(temporary, "w", encoding="utf-8") as target:
        json.dump(value, target, ensure_ascii=False, indent=2, sort_keys=True)
        target.flush()
        os.fsync(target.fileno())
    os.replace(temporary, path)


def _persist_state():
    with state_lock:
        value = {
            "schema_version": STATE_SCHEMA,
            "pending": dict(live_state.get("pending") or {}),
            "reboot_marker": dict(live_state.get("reboot_marker") or {}),
            "last_check": float(live_state.get("last_check") or 0),
            "last_update": float(live_state.get("last_update") or 0),
            "last_notified_digest": str(live_state.get("last_notified_digest") or ""),
        }
    _write_json(_state_file(), value)


def _restore_state():
    value = _read_json(_state_file())
    if value.get("schema_version") != STATE_SCHEMA:
        return
    with state_lock:
        for key in ("pending", "reboot_marker"):
            live_state[key] = dict(value.get(key) or {})
        for key in ("last_check", "last_update"):
            try:
                live_state[key] = float(value.get(key) or 0)
            except (TypeError, ValueError):
                live_state[key] = 0
        live_state["last_notified_digest"] = str(
            value.get("last_notified_digest") or ""
        )


def _boot_id():
    try:
        with open("/proc/sys/kernel/random/boot_id", "r", encoding="ascii") as source:
            return source.read().strip()
    except OSError:
        return ""


def _output_limit():
    try:
        return max(50, min(500, int(plugin_options.get("output_lines", 200))))
    except (TypeError, ValueError):
        return 200


def _append_output(value):
    value = str(value or "").replace("\x00", "").rstrip()
    if not value:
        return
    with state_lock:
        live_state["output"].append(value[:2000])
        del live_state["output"][:-_output_limit()]


def _set_phase(phase, message, error=""):
    with state_lock:
        live_state["phase"] = phase
        live_state["message"] = str(message)
        live_state["last_error"] = str(error)
        if phase in BUSY_PHASES:
            live_state["operation_started"] = time.time()
            live_state["operation_finished"] = 0
        elif live_state.get("operation_started"):
            live_state["operation_finished"] = time.time()


def _normalize_settings():
    frequency = str(plugin_options.get("schedule_frequency", "daily"))
    if frequency not in model.VALID_FREQUENCIES:
        frequency = "daily"
    plugin_options["schedule_frequency"] = frequency
    try:
        model.parse_clock(plugin_options.get("check_time", "03:00"))
    except ValueError:
        plugin_options["check_time"] = "03:00"
    try:
        plugin_options["week_day"] = max(
            0, min(6, int(plugin_options.get("week_day", 0)))
        )
    except (TypeError, ValueError):
        plugin_options["week_day"] = 0
    try:
        plugin_options["month_day"] = max(
            1, min(31, int(plugin_options.get("month_day", 1)))
        )
    except (TypeError, ValueError):
        plugin_options["month_day"] = 1
    unit = str(plugin_options.get("delay_unit", "hours"))
    plugin_options["delay_unit"] = unit if unit in model.VALID_DELAY_UNITS else "hours"
    try:
        plugin_options["delay_value"] = max(
            1, min(365, int(plugin_options.get("delay_value", 1)))
        )
    except (TypeError, ValueError):
        plugin_options["delay_value"] = 1
    try:
        plugin_options["output_lines"] = max(
            50, min(500, int(plugin_options.get("output_lines", 200)))
        )
    except (TypeError, ValueError):
        plugin_options["output_lines"] = 200
    plugin_options["excluded_packages"] = "\n".join(
        model.parse_exclusions(plugin_options.get("excluded_packages", ""))
    )


def _next_check_timestamp(now=None):
    now = now or dt.datetime.now()
    return model.next_check(
        now,
        plugin_options.get("schedule_frequency", "daily"),
        plugin_options.get("check_time", "03:00"),
        plugin_options.get("week_day", 0),
        plugin_options.get("month_day", 1),
    ).timestamp()


def _recalculate_next_check(now=None):
    with state_lock:
        live_state["next_check"] = (
            _next_check_timestamp(now) if plugin_options.get("enabled") else 0
        )


def _base_url():
    scheme = "https" if options.use_ssl or options.use_own_ssl else "http"
    return "{}://{}:{}".format(scheme, ospy_web_url(), options.web_port)


def _mail(body, log_text, force=False):
    if not force and not plugin_options.get("send_email"):
        return True
    try:
        from plugins.email_notifications_ssl import try_mail
        sent = bool(try_mail(
            body,
            log_text,
            attachment=None,
            subject=plugin_options.get("email_subject"),
        ))
        with state_lock:
            live_state["email_error"] = "" if sent else _("E-mail delivery failed")
        return sent
    except Exception:
        error = traceback.format_exc().splitlines()[-1]
        with state_lock:
            live_state["email_error"] = error
        log.error(NAME, _("E-mail notification failed") + ":\n" + traceback.format_exc())
        return False


def _package_summary(updates, limit=12):
    names = [item.get("name", "") for item in updates if item.get("name")]
    shown = names[:limit]
    text = ", ".join(shown)
    if len(names) > limit:
        text += " " + _("and {} more").format(len(names) - limit)
    return text or _("None")


def _notify_available(updates, pending=None):
    security = sum(1 for item in updates if item.get("security"))
    body = "<b>{}</b><br>".format(html.escape(_("Linux updates are available.")))
    body += "{}: {}<br>".format(html.escape(_("Number of packages")), len(updates))
    body += "{}: {}<br>".format(html.escape(_("Security updates")), security)
    body += "{}: {}<br>".format(
        html.escape(_("Packages")), html.escape(_package_summary(updates))
    )
    if pending:
        planned = datetime_string(time.localtime(float(pending["execute_at"])))
        body += "<br><b>{}</b> {}<br>".format(
            html.escape(_("Automatic update is scheduled for")), html.escape(planned)
        )
        body += "{}<br>".format(html.escape(
            _("Sign in to OSPy and open Linux System Updater to cancel it before this time.")
        ))
        body += '<a href="{}/plugins/linux_system_updater/settings_page">{}</a>'.format(
            html.escape(_base_url(), quote=True), html.escape(_("Open OSPy"))
        )
    return _mail(body, _("Linux updates are available: {} package(s).").format(len(updates)))


def _notify_before_update(updates):
    body = "<b>{}</b><br>{}: {}".format(
        html.escape(_("The Linux system update will start in a moment.")),
        html.escape(_("Packages")),
        html.escape(_package_summary(updates)),
    )
    return _mail(body, _("The Linux system update is starting."))


def _notify_completed(updates, rebooted=False):
    if rebooted:
        title = _("The Linux update completed and the system restarted successfully.")
        detail = _("OSPy started successfully and the updater is running.")
    else:
        title = _("The Linux system update completed successfully.")
        detail = _("A system restart was not requested by the plug-in.")
    body = "<b>{}</b><br>{}<br>{}: {}".format(
        html.escape(title), html.escape(detail), html.escape(_("Packages")),
        html.escape(_package_summary(updates)),
    )
    return _mail(body, title)


def _notify_failed(message):
    body = "<b>{}</b><br>{}".format(
        html.escape(_("The Linux system update failed.")), html.escape(str(message))
    )
    return _mail(body, _("The Linux system update failed: {} ").format(message).strip())


def _prepare_command(command):
    command = list(command)
    if command and command[0] == "apt-get":
        command[1:1] = [
            "-o", "DPkg::Lock::Timeout=60",
            "-o", "Dpkg::Options::=--force-confold",
        ]
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        return command
    if shutil.which("sudo"):
        return [
            "sudo", "-n", "env",
            "DEBIAN_FRONTEND=noninteractive", "LC_ALL=C",
        ] + command
    raise RuntimeError(_("Root privileges are required and passwordless sudo is not available."))


def _run_command(command, timeout=None, privileged=False):
    if privileged:
        command = _prepare_command(command)
    _append_output("$ " + " ".join(command))
    environment = os.environ.copy()
    environment.update({"DEBIAN_FRONTEND": "noninteractive", "LC_ALL": "C"})
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        env=environment,
        close_fds=True,
    )
    started = time.monotonic()
    collected = []
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    try:
        while process.poll() is None:
            for key, _mask in selector.select(0.5):
                line = key.fileobj.readline()
                if line:
                    collected.append(line)
                    _append_output(line)
            if timeout and time.monotonic() - started > timeout:
                process.terminate()
                try:
                    process.wait(10)
                except subprocess.TimeoutExpired:
                    process.kill()
                raise RuntimeError(
                    _("Command timed out after {} seconds.").format(timeout)
                )
        remainder = process.stdout.read() if process.stdout else ""
        if remainder:
            collected.append(remainder)
            for line in remainder.splitlines():
                _append_output(line)
    finally:
        selector.close()
    output = "".join(collected)
    if process.returncode:
        tail = "\n".join(output.splitlines()[-12:])
        raise RuntimeError(
            _("Command failed with exit code {}.").format(process.returncode)
            + (("\n" + tail) if tail else "")
        )
    return output


def _platform_ready():
    if os.name != "posix" or not shutil.which("apt-get") or not shutil.which("apt"):
        raise RuntimeError(_("This plug-in requires a Debian-based Linux system with APT."))


def _available_updates():
    output = _run_command(["apt", "list", "--upgradable"], timeout=120)
    updates = model.parse_upgradable(output)
    excluded = set(model.parse_exclusions(plugin_options.get("excluded_packages", "")))
    for item in updates:
        item["excluded"] = item["name"] in excluded
    return updates


def _reboot_required():
    return os.path.exists("/var/run/reboot-required")


class UpdateWorker(Thread):
    def __init__(self):
        Thread.__init__(self, name="LinuxSystemUpdater")
        self.daemon = True
        self._stop_event = runtime.stop_event
        self._queue = queue.Queue(maxsize=8)
        self._post_boot_retry = 0
        self.start()
        runtime.register_thread(self)

    def submit(self, action, package=""):
        with state_lock:
            if live_state.get("phase") in BUSY_PHASES:
                return False
        try:
            self._queue.put_nowait((str(action), str(package or "")))
            return True
        except queue.Full:
            return False

    def stop(self):
        self._stop_event.set()

    def _post_boot_notification(self):
        with state_lock:
            marker = dict(live_state.get("reboot_marker") or {})
        if not marker:
            return
        current_boot = _boot_id()
        if not model.boot_changed(marker.get("boot_id"), current_boot):
            return
        if time.time() < self._post_boot_retry:
            return
        updates = list(marker.get("updates") or [])
        if _notify_completed(updates, rebooted=True):
            with state_lock:
                live_state["reboot_marker"] = {}
                live_state["phase"] = "idle"
                live_state["message"] = _("OSPy started successfully after the system update.")
            _persist_state()
        else:
            self._post_boot_retry = time.time() + 60

    def _schedule_pending(self, updates):
        digest = model.package_digest(updates)
        with state_lock:
            current = dict(live_state.get("pending") or {})
        if current and current.get("digest") == digest:
            return current, False
        pending = {
            "created": time.time(),
            "execute_at": time.time() + model.delay_seconds(
                plugin_options.get("delay_value", 1),
                plugin_options.get("delay_unit", "hours"),
            ),
            "digest": digest,
            "packages": [item["name"] for item in updates if not item.get("excluded")],
        }
        with state_lock:
            live_state["pending"] = pending
        _persist_state()
        return pending, True

    def _check(self, scheduled=False):
        _platform_ready()
        _set_phase("checking", _("Refreshing the APT package index"))
        with state_lock:
            live_state["output"] = []
        _run_command(["apt-get", "update"], timeout=1800, privileged=True)
        updates = _available_updates()
        digest = model.package_digest(updates)
        with state_lock:
            live_state["updates"] = updates
            live_state["last_check"] = time.time()
            live_state["reboot_required"] = _reboot_required()
            previous_digest = live_state.get("last_notified_digest", "")
        _recalculate_next_check()

        pending = None
        newly_pending = False
        allowed_updates = [item for item in updates if not item.get("excluded")]
        if allowed_updates and plugin_options.get("automatic_update"):
            pending, newly_pending = self._schedule_pending(updates)
        elif not updates:
            with state_lock:
                live_state["pending"] = {}

        if updates and (digest != previous_digest or newly_pending):
            if _notify_available(updates, pending):
                with state_lock:
                    live_state["last_notified_digest"] = digest
        elif not updates:
            with state_lock:
                live_state["last_notified_digest"] = ""

        with state_lock:
            if updates:
                live_state["phase"] = "waiting" if pending else "idle"
                live_state["message"] = _("{} update(s) are available.").format(len(updates))
            else:
                live_state["phase"] = "idle"
                live_state["message"] = _("The Linux system is up to date.")
            live_state["operation_finished"] = time.time()
        _persist_state()
        log.info(NAME, live_state["message"])

    def _update(self, selected=""):
        _platform_ready()
        with operation_lock:
            _set_phase("checking", _("Refreshing package information before installation"))
            _run_command(["apt-get", "update"], timeout=1800, privileged=True)
            refreshed = _available_updates()
            with state_lock:
                live_state["updates"] = refreshed
                updates = [dict(item) for item in refreshed]
                live_state["pending"] = {}
            available = [item["name"] for item in updates]
            exclusions = plugin_options.get("excluded_packages", "")
            try:
                simulation = model.build_upgrade_command(
                    available, exclusions=exclusions,
                    selected=selected or None, simulate=True,
                )
                actual = model.build_upgrade_command(
                    available, exclusions=exclusions,
                    selected=selected or None, simulate=False,
                )
            except ValueError as exception:
                raise RuntimeError(_("No allowed package update is currently available.")) from exception
            chosen = [
                item for item in updates
                if (not selected or item["name"] == selected) and not item.get("excluded")
            ]
            _notify_before_update(chosen)
            _set_phase("simulating", _("Checking the planned APT transaction"))
            simulated_output = _run_command(simulation, timeout=300, privileged=True)
            simulated = set(model.parse_simulated_packages(simulated_output))
            excluded = set(model.parse_exclusions(exclusions))
            forbidden = sorted(simulated & excluded)
            if forbidden:
                raise RuntimeError(
                    _("The transaction would update excluded packages: {}.").format(
                        ", ".join(forbidden)
                    )
                )
            _set_phase("updating", _("Installing Linux package updates"))
            _run_command(actual, timeout=None, privileged=True)
            remaining = _available_updates()
            with state_lock:
                live_state["updates"] = remaining
                live_state["last_update"] = time.time()
                live_state["reboot_required"] = _reboot_required()
                live_state["last_notified_digest"] = model.package_digest(remaining)
            _persist_state()

            if plugin_options.get("reboot_after_update"):
                marker = {
                    "created": time.time(),
                    "boot_id": _boot_id(),
                    "updates": chosen,
                }
                with state_lock:
                    live_state["reboot_marker"] = marker
                _persist_state()
                _set_phase("rebooting", _("The Linux system is restarting"))
                log.info(NAME, _("Linux package updates completed; restarting the system."))
                reboot(wait=3)
            else:
                _notify_completed(chosen, rebooted=False)
                _set_phase("idle", _("Linux package updates completed successfully"))
                log.info(NAME, _("Linux package updates completed successfully."))

    def _handle(self, action, package):
        try:
            if action == "check":
                self._check(scheduled=False)
            elif action == "scheduled_check":
                self._check(scheduled=True)
            elif action == "update_all":
                self._update("")
            elif action == "update_package":
                self._update(model.normalize_package(package))
        except Exception:
            message = traceback.format_exc().splitlines()[-1]
            _set_phase("error", _("Linux update operation failed"), message)
            _append_output(message)
            log.error(NAME, _("Linux System Updater") + ":\n" + traceback.format_exc())
            _notify_failed(message)
            _persist_state()

    def run(self):
        _restore_state()
        _normalize_settings()
        _recalculate_next_check()
        while not self._stop_event.is_set():
            try:
                self._post_boot_notification()
                now = time.time()
                with state_lock:
                    pending = dict(live_state.get("pending") or {})
                    next_check = float(live_state.get("next_check") or 0)
                if pending and plugin_options.get("automatic_update"):
                    if model.pending_due(pending, now):
                        self._handle("update_all", "")
                        continue
                if plugin_options.get("enabled") and next_check and now >= next_check:
                    _recalculate_next_check(dt.datetime.now() + dt.timedelta(seconds=1))
                    self._handle("scheduled_check", "")
                    continue
                try:
                    action, package = self._queue.get(timeout=1)
                    self._handle(action, package)
                except queue.Empty:
                    pass
            except Exception:
                message = traceback.format_exc().splitlines()[-1]
                _set_phase("error", _("Linux updater worker failed"), message)
                log.error(NAME, _("Linux System Updater") + ":\n" + traceback.format_exc())
                self._stop_event.wait(30)


def _public_state():
    with state_lock:
        value = {
            key: (list(data) if isinstance(data, list) else dict(data) if isinstance(data, dict) else data)
            for key, data in live_state.items()
        }
    value["worker_running"] = worker is not None and worker.is_alive()
    value["automatic_update"] = bool(plugin_options.get("automatic_update"))
    value["enabled"] = bool(plugin_options.get("enabled"))
    value["excluded_packages"] = model.parse_exclusions(
        plugin_options.get("excluded_packages", "")
    )
    value["now"] = time.time()
    return value


def cancel_pending():
    with state_lock:
        existed = bool(live_state.get("pending"))
        live_state["pending"] = {}
        if live_state.get("phase") == "waiting":
            live_state["phase"] = "idle"
            live_state["message"] = _("The automatic update was cancelled.")
    _persist_state()
    if existed:
        log.info(NAME, _("The pending automatic Linux update was cancelled."))
    return existed


def start():
    global worker
    if worker is None:
        worker = UpdateWorker()


def stop():
    global worker
    if worker is not None:
        worker.stop()
        worker.join(15)
        if worker.is_alive():
            log.error(NAME, _("The updater is still completing a system command."))
        else:
            worker = None


def health():
    state = _public_state()
    details = {
        _("Worker thread"): _("Running") if state["worker_running"] else _("Stopped"),
        _("Current phase"): state["phase"],
        _("Available updates"): len(state["updates"]),
        _("Automatic update pending"): _("Yes") if state["pending"] else _("No"),
        _("Reboot confirmation pending"): _("Yes") if state["reboot_marker"] else _("No"),
    }
    if state["last_error"]:
        details[_("Last error")] = state["last_error"]
    if not state["worker_running"]:
        return {"status": "error", "summary": _("Linux updater worker is not running."), "details": details}
    if state["phase"] == "error":
        return {"status": "error", "summary": state["last_error"] or state["message"], "details": details}
    if os.name != "posix":
        return {"status": "unknown", "summary": _("APT is available only on Linux."), "details": details}
    return {"status": "ok", "summary": state["message"], "details": details}


class settings_page(ProtectedPage):
    def GET(self):
        _normalize_settings()
        return self.plugin_render.linux_system_updater(
            plugin_options, _public_state(), ""
        )

    def POST(self):
        from ospy import server

        qdict = web.input()
        verify_csrf(qdict)
        error = ""
        try:
            if server.session.get("category") != "admin":
                raise ValueError(_("Only an administrator can manage Linux updates."))
            action = str(qdict.get("action", "save"))
            if action == "save_general":
                frequency = str(qdict.get("schedule_frequency", "daily"))
                if frequency not in model.VALID_FREQUENCIES:
                    raise ValueError(_("Invalid schedule frequency."))
                model.parse_clock(qdict.get("check_time", "03:00"))
                delay_unit = str(qdict.get("delay_unit", "hours"))
                if delay_unit not in model.VALID_DELAY_UNITS:
                    raise ValueError(_("Invalid automatic update delay unit."))
                plugin_options["enabled"] = qdict.get("enabled") == "on"
                plugin_options["schedule_frequency"] = frequency
                plugin_options["check_time"] = str(qdict.get("check_time", "03:00"))
                plugin_options["week_day"] = max(0, min(6, int(qdict.get("week_day", 0))))
                plugin_options["month_day"] = max(1, min(31, int(qdict.get("month_day", 1))))
                plugin_options["automatic_update"] = qdict.get("automatic_update") == "on"
                plugin_options["delay_value"] = max(1, min(365, int(qdict.get("delay_value", 1))))
                plugin_options["delay_unit"] = delay_unit
                plugin_options["excluded_packages"] = "\n".join(
                    model.parse_exclusions(qdict.get("excluded_packages", ""))
                )
                plugin_options["reboot_after_update"] = qdict.get("reboot_after_update") == "on"
                plugin_options["output_lines"] = max(50, min(500, int(qdict.get("output_lines", 200))))
                _normalize_settings()
                _recalculate_next_check()
                if not plugin_options["automatic_update"]:
                    cancel_pending()
            elif action == "save_email":
                subject = str(qdict.get("email_subject", "")).strip()[:200]
                if not subject:
                    raise ValueError(_("E-mail subject cannot be empty."))
                was_enabled = bool(plugin_options.get("send_email"))
                plugin_options["send_email"] = qdict.get("send_email") == "on"
                plugin_options["email_subject"] = subject
                if plugin_options["send_email"] and not was_enabled:
                    with state_lock:
                        live_state["last_notified_digest"] = ""
                    _persist_state()
            elif action == "check_now":
                if worker is None or not worker.submit("check"):
                    raise ValueError(_("Another Linux update operation is already running."))
            elif action == "cancel_pending":
                cancel_pending()
            elif action == "update_all":
                if plugin_options.get("automatic_update"):
                    raise ValueError(_("Cancel or disable automatic updating before a manual update."))
                if worker is None or not worker.submit("update_all"):
                    raise ValueError(_("Another Linux update operation is already running."))
            elif action == "update_package":
                if plugin_options.get("automatic_update"):
                    raise ValueError(_("Cancel or disable automatic updating before a manual update."))
                package = model.normalize_package(qdict.get("package", ""))
                current = {item["name"] for item in _public_state()["updates"] if not item.get("excluded")}
                if not package or package not in current:
                    raise ValueError(_("The selected package is no longer available for update."))
                if worker is None or not worker.submit("update_package", package):
                    raise ValueError(_("Another Linux update operation is already running."))
            elif action == "test_email":
                if not _mail(
                    "<b>{}</b>".format(html.escape(_("Linux System Updater test message"))),
                    _("Linux System Updater test message"), force=True,
                ):
                    raise ValueError(_("The test e-mail could not be sent."))
        except (TypeError, ValueError) as exception:
            error = str(exception)
        if not error:
            raise web.seeother(plugin_url(settings_page), True)
        return self.plugin_render.linux_system_updater(
            plugin_options, _public_state(), error
        )


class status_json(ProtectedPage):
    def GET(self):
        web.header("Content-Type", "application/json; charset=utf-8")
        return json.dumps(_public_state(), ensure_ascii=False, allow_nan=False)


class help_page(ProtectedPage):
    def GET(self):
        return self.plugin_render.linux_system_updater_help()
