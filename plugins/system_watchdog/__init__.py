__author__ = u'Martin Pihrt'
# this plugins enable or disable system RPi HW watchdog 
# help: https://www.raspberrypi.org/forums/viewtopic.php?f=29&t=147501
# testing: :(){ :|:&};:

from threading import Thread, Event
import time
import subprocess
import os
import traceback
import shlex

import web
from ospy.helpers import restart, reboot, verify_csrf
from ospy.webpages import ProtectedPage
from ospy.log import log
from plugins import plugin_url


NAME = 'System Watchdog'
MENU =  _(u'Package: System Watchdog')
LINK = 'status_page'
COMMAND_TIMEOUT = 60
STATUS_TIMEOUT = 15
ERROR_LOG_THROTTLE = 300


class StatusChecker(Thread):
    def __init__(self):
        Thread.__init__(self)
        self.daemon = True
        self.started = Event()
        
        self._stop_event = Event()

        self.status = {
            'service_install': False,
            'service_state': False}
        self._last_error_log = 0

        self._sleep_time = 0
        self.start()

    def stop(self):
        self._stop_event.set()

    def update(self):
        self._sleep_time = 0

    def _sleep(self, secs):
        self._sleep_time = secs
        while self._sleep_time > 0 and not self._stop_event.is_set():
            time.sleep(1)
            self._sleep_time -= 1

    def log_problem(self):
        now = time.time()
        if now - self._last_error_log >= ERROR_LOG_THROTTLE:
            log.error(NAME, _('System watchdog plug-in') + ':\n' + traceback.format_exc())
            self._last_error_log = now

    def _is_installed(self):
        """Returns watchdog is instaled."""
        if not os.path.exists("/usr/sbin/watchdog"):       # if watchdog is not installed
           log.info(NAME, _('Watchdog is not installed. For continue press button install watchdog.'))
           self.status['service_install'] = False
        else:
           self.status['service_install'] = True

    def _is_started(self):
        """Returns true if watchdog is started."""
        try: 
            result = subprocess.run(
                shlex.split("systemctl is-active watchdog"),
                stderr=subprocess.STDOUT,
                stdout=subprocess.PIPE,
                timeout=STATUS_TIMEOUT)
            self.status['service_state'] = result.stdout.decode('utf8', errors='replace').strip() == 'active'

        except Exception:
                self.status['service_state'] = False
                self.started.set()
                self.log_problem()
                self._sleep(60)
   
       
    def run(self):
        log.clear(NAME)

        while not self._stop_event.is_set():
            try:
                self._is_installed()
                if self.status['service_install']:
                    self._is_started()
                else:
                    self.status['service_state'] = False
                self.started.set()
                self._sleep(60)

            except Exception:
                self.started.set()
                self.log_problem()
                self._sleep(60)


checker = None


################################################################################
# Helper functions:                                                            #
################################################################################
def start():
    global checker
    if checker is None:
        checker = StatusChecker()


def stop():
    global checker
    if checker is not None:
        checker.stop()
        checker.join(15)
        checker = None

def run_process(cmd, timeout=COMMAND_TIMEOUT):
    try:
        proc = subprocess.run(
            shlex.split(cmd),
            stderr=subprocess.STDOUT, # merge stdout and stderr
            stdout=subprocess.PIPE,
            timeout=timeout)
        output = proc.stdout.decode('utf8', errors='replace')
        log.info(NAME, _('System watchdog plug-in') + ':\n' + output)
        return proc.returncode == 0

    except Exception:
        log.info(NAME, _('System watchdog plug-in') + ':\n' + traceback.format_exc())
        return False

def add_module(module):
    try:
        existing = ''
        if os.path.exists('/etc/modules'):
            with open('/etc/modules', 'r') as module_file:
                existing = module_file.read()
        if module not in existing.splitlines():
            with open('/etc/modules', 'a') as module_file:
                module_file.write(module + '\n')
    except Exception:
        log.info(NAME, _('System watchdog plug-in') + ':\n' + traceback.format_exc())

################################################################################
# Web pages:                                                                   #
################################################################################
class status_page(ProtectedPage):
    """Load an html page."""

    def GET(self):  
        log.clear(NAME)
        cmd = "sudo systemctl status watchdog"
        run_process(cmd, timeout=STATUS_TIMEOUT)
        status = checker.status if checker is not None else {'service_install': False, 'service_state': False}
        return self.plugin_render.system_watchdog(status, log.events(NAME))


class help_page(ProtectedPage):
    """Load an html page for help"""

    def GET(self):
        return self.plugin_render.system_watchdog_help()        


class install_page(ProtectedPage):
    """Instalation watchdog page"""

    def GET(self):
        verify_csrf()
        log.clear(NAME)
        add_module('bcm2708_wdog')
        add_module('bcm2835_wdog')
        add_module('bcm2711_wdt')


        try:
            cmd = "sudo modprobe bcm2708_wdog"
            log.debug(NAME, cmd)
            run_process(cmd)
        except:
            try:
                cmd = "sudo modprobe bcm2835_wdog"
                log.debug(NAME, cmd)
                run_process(cmd)
            except:
                cmd = "sudo modprobe bcm2711_wdog"
                log.debug(NAME, cmd)
                run_process(cmd)

        cmd = "sudo apt-get install -y watchdog chkconfig"
        log.debug(NAME, cmd)
        run_process(cmd, timeout=300)
        cmd = "sudo chkconfig watchdog on"
        log.debug(NAME, cmd)
        run_process(cmd)
        log.debug(NAME, _('Saving config to /etc/watchdog.conf'))

        # http://linux.die.net/man/5/watchdog.conf
        fname = "/etc/watchdog.conf"
        with open(fname, 'wb') as f:
            f.write(b"watchdog-device = /dev/watchdog\n")
            f.write(b"watchdog-timeout = 14\n")
            f.write(b"realtime = yes\n")
            f.write(b"priority = 1\n")
            f.write(b"interval = 4\n")
            f.write(b"max-load-1 = 24\n")

        cmd = "sudo systemctl enable watchdog"
        log.debug(NAME, cmd)
        run_process(cmd)
        cmd = "sudo systemctl daemon-reload"
        log.debug(NAME, cmd)
        run_process(cmd)
        cmd = "sudo systemctl start watchdog"
        log.debug(NAME, cmd)
        run_process(cmd)

        reboot(True) # reboot HW software after instal watchdog
        msg = _('The system (Linux) will now restart (restart started by the user in the Watch-dog plugins), please wait for the page to reload.')
        return self.core_render.notice(plugin_url(status_page), msg)        

class stop_page(ProtectedPage):
    """Stop watchdog service page"""

    def GET(self):
        verify_csrf()
        log.clear(NAME)
        cmd = "sudo systemctl stop watchdog"
        log.debug(NAME, cmd) 
        run_process(cmd)
        cmd = "sudo systemctl disable watchdog"
        log.debug(NAME, cmd)
        run_process(cmd)
        cmd = "sudo systemctl daemon-reload"
        log.debug(NAME, cmd)
        run_process(cmd)
        restart(3) 
        msg = _('The Watchdog service will now stoped, OSPy is now restarted (restart started by the Watch-dog plugins), please wait for the page to reload.')
        return self.core_render.notice(plugin_url(status_page), msg)              
        
class start_page(ProtectedPage):
    """Start watchdog service page"""

    def GET(self):
        verify_csrf()
        log.clear(NAME)
        cmd = "sudo systemctl start watchdog"
        log.debug(NAME, cmd)
        run_process(cmd)
        cmd = "sudo systemctl enable watchdog"
        log.debug(NAME, cmd)
        run_process(cmd)
        cmd = "sudo systemctl daemon-reload"
        log.debug(NAME, cmd)
        run_process(cmd)
        restart(3)
        msg = _('The Watchdog service will now started, OSPy is now restarted (restart started by the Watch-dog plugins), please wait for the page to reload.')
        return self.core_render.notice(plugin_url(status_page), msg) 
        
