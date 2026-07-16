# -*- coding: utf-8 -*-

import time
from threading import Thread, Lock
import datetime
import traceback

import web
from ospy.log import log
from ospy.options import level_adjustments
from ospy.webpages import ProtectedPage
from plugins import PluginOptions, plugin_url, get_runtime
from ospy.helpers import datetime_string, verify_csrf


NAME = 'Monthly Water Level'
MENU =  _('Package: Monthly Water Level')
LINK = 'settings_page'

plugin_options = PluginOptions(
    NAME,
    {
        key: 100 for key in range(12)
    })
runtime = get_runtime()
health_lock = Lock()
health_state = {
    'last_success': 0,
    'last_error': 0,
    'last_error_message': '',
    'month': -1,
    'percent': 0,
}


def _sleep_time():
    """Calculates how long to sleep until just after midnight."""
    now = datetime.datetime.now()
    return 5 + 3600 * 24 - (now.second + now.minute * 60 + now.hour * 3600)


class MonthChecker(Thread):
    def __init__(self):
        Thread.__init__(self)
        self.daemon = True
        self._stop_event = runtime.stop_event

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

    def run(self):
        while not self._stop_event.is_set():
            try:
                month = time.localtime().tm_mon - 1  # Current month.
                level_adjustments[NAME] = plugin_options[month] / 100.0  # Set the water level% (levels list is zero based).
                record_adjustment_success(month, plugin_options[month])
                log.debug(NAME, _('Monthly Adjust: Setting water level to') + '%d%%' % plugin_options[month])

                self._sleep(_sleep_time())
            except:
                record_adjustment_error(traceback.format_exc())
                log.error(NAME, _('Monthly water level plug-in') + ':\n' + traceback.format_exc())

checker = None


def start():
    global checker
    if checker is None:
        checker = MonthChecker()
        runtime.register_thread(checker)


def stop():
    global checker
    worker = checker
    if worker is not None:
        worker.stop()
        worker.join(5)
        if checker is worker and not worker.is_alive():
            checker = None
    if NAME in level_adjustments:
        del level_adjustments[NAME]


def record_adjustment_success(month, percent):
    with health_lock:
        health_state['last_success'] = time.time()
        health_state['last_error_message'] = ''
        health_state['month'] = int(month)
        health_state['percent'] = int(percent)


def record_adjustment_error(message):
    with health_lock:
        health_state['last_error'] = time.time()
        health_state['last_error_message'] = str(message).splitlines()[-1]


def health():
    """Return worker and current monthly scheduler adjustment state."""
    with health_lock:
        state = dict(health_state)
    worker_alive = checker is not None and checker.is_alive()
    current_month = time.localtime().tm_mon - 1
    percent = int(plugin_options[current_month])
    details = {
        _('Worker thread'): _('Running') if worker_alive else _('Stopped'),
        _('Current month'): current_month + 1,
        _('Configured adjustment'): '{}%'.format(percent),
        _('Applied water level factor'): (
            level_adjustments.get(NAME, _('Not available'))
        ),
        _('Last successful adjustment'): (
            datetime_string(time.localtime(state['last_success']))
            if state['last_success'] else _('Not available')
        ),
    }
    if state['last_error_message']:
        details[_('Last error')] = state['last_error_message']
    if not worker_alive:
        return {
            'status': 'error',
            'summary': _('Monthly Water Level worker is stopped.'),
            'details': details,
        }
    if state['last_error'] and state['last_error'] >= state['last_success']:
        return {
            'status': 'error',
            'summary': state['last_error_message'],
            'details': details,
        }
    if NAME not in level_adjustments or not state['last_success']:
        return {
            'status': 'warning',
            'summary': _('Waiting for the monthly water level adjustment.'),
            'details': details,
        }
    return {
        'status': 'ok',
        'summary': _('Monthly water level adjustment is applied.'),
        'details': details,
    }


class settings_page(ProtectedPage):
    """Load an html page for entering monthly irrigation time adjustments"""

    def GET(self):
        try:
            return self.plugin_render.monthly_water_level(plugin_options)
        except:
            log.error(NAME, _('Monthly water level plug-in') + ':\n' + traceback.format_exc())
            msg = _('An internal error was found in the system, see the error log for more information. The error is in part:') + ' '
            msg += _('monthly_water_level -> settings_page GET')
            return self.core_render.notice('/', msg)

    def POST(self):
        try:
            qdict = web.input()
            verify_csrf(qdict)
            months = ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec']
            vals = {}
            for index, month in enumerate(months):
                vals[index] = max(0, min(10000, int(float(qdict[month]))))
            plugin_options.web_update(vals)
            if checker is not None:
                checker.update()
            raise web.seeother(plugin_url(settings_page), True)
        except:
            log.error(NAME, _('Monthly water level plug-in') + ':\n' + traceback.format_exc())
            msg = _('An internal error was found in the system, see the error log for more information. The error is in part:') + ' '
            msg += _('monthly_water_level -> settings_page POST')
            return self.core_render.notice('/', msg)


class help_page(ProtectedPage):
    """Load an html page for help"""

    def GET(self):
        try:
            return self.plugin_render.monthly_water_level_help()
        except:
            log.error(NAME, _('Monthly water level plug-in') + ':\n' + traceback.format_exc())
            msg = _('An internal error was found in the system, see the error log for more information. The error is in part:') + ' '
            msg += _('monthly_water_level -> help_page GET')
            return self.core_render.notice('/', msg)
