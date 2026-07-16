# -*- coding: utf-8 -*-
__author__ = 'Martin Pihrt'
# This plugin pulses a selected circuit with a 1 Hz signal with adjusted time. (For discover the location of a valve).

import json
import web
import traceback

from threading import Thread, Event

from ospy import helpers
from ospy.stations import stations
from ospy.webpages import ProtectedPage
from plugins import PluginOptions, plugin_url, get_runtime
from ospy.log import log
from ospy.helpers import verify_csrf


NAME = 'Pulse Output Test'
MENU =  _('Package: Pulse Output Test')
LINK = 'start_page'
MIN_TEST_TIME = 1
MAX_TEST_TIME = 3600
runtime = get_runtime()

pulse_options = PluginOptions(
    NAME,
    {
        'test_time': 30,
        'test_output': 0
    }
)


class PulseSender(Thread):
    def __init__(self):
        Thread.__init__(self)
        self.daemon = True
        self._stop_event = Event()

        self._sleep_time = 0
        self.start()

    def stop(self):
        self._stop_event.set()

    def update(self):
        self._sleep_time = 0

    def _wait(self, seconds):
        return (
            runtime.stop_event.is_set() or
            self._stop_event.wait(seconds) or
            runtime.stop_event.is_set()
        )

    def run(self):
        global sender
        station = None
        try:
            log.clear(NAME)
            normalize_options(pulse_options)
            test_time = pulse_options['test_time']
            station = stations.get(pulse_options['test_output'])
            log.info(NAME, _('Test started for {} second.').format(test_time))

            for x in range(0, test_time):
                station.active = True
                if self._wait(0.5):
                    break
                station.active = False
                if self._wait(0.5):
                    break

            log.info(NAME, _('Test stopped.'))

        except:
            log.error(NAME, _('Pulse plugin') + ':\n' + traceback.format_exc())
        finally:
            if station is not None:
                if station.remaining_seconds != 0:
                    station.active = True
                else:
                    station.active = False
            if sender is self:
                sender = None

sender = None


################################################################################
# Helper functions:                                                            #
################################################################################
def start():
    pass


def stop():
    global sender
    worker = sender
    if worker is not None:
        worker.stop()
        worker.join(5)
        if sender is worker and not worker.is_alive():
            sender = None


def health():
    """Return selected output and pulse-test worker state."""
    normalize_options(pulse_options)
    worker_alive = sender is not None and sender.is_alive()
    details = {
        _('Test time'): '{} s'.format(pulse_options['test_time']),
        _('Worker thread'): _('Running') if worker_alive else _('Stopped'),
    }
    try:
        station = stations.get(pulse_options['test_output'])
    except Exception:
        details[_('Selected output')] = _('Not available')
        return {
            'status': 'error',
            'summary': _('Selected output is not available.'),
            'details': details,
        }
    details[_('Selected output')] = '{}: {}'.format(
        pulse_options['test_output'] + 1, station.name
    )
    details[_('Output active')] = _('Yes') if station.active else _('No')
    return {
        'status': 'ok',
        'summary': (
            _('Pulse output test is running.')
            if worker_alive else _('Pulse output test is ready.')
        ),
        'details': details,
    }


def to_int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def clamp(value, low, high):
    return max(low, min(high, value))


def normalize_options(options):
    station_count = len(stations.get())
    max_output = max(0, station_count - 1)
    options['test_output'] = clamp(to_int(options.get('test_output'), 0), 0, max_output)
    options['test_time'] = clamp(to_int(options.get('test_time'), pulse_options['test_time']), MIN_TEST_TIME, MAX_TEST_TIME)
    return options


################################################################################
# Web pages:                                                                   #
################################################################################
class start_page(ProtectedPage):
    """Load an html start page"""

    def GET(self):
        try:
            global sender

            qdict = web.input()
            stop = helpers.get_input(qdict, 'stop', False, lambda x: True)
            if sender is not None and stop:
                verify_csrf(qdict)
                worker = sender
                worker.stop()
                worker.join(5)
                if sender is worker and not worker.is_alive():
                    sender = None
                raise web.seeother(plugin_url(start_page), True)

            return self.plugin_render.pulse(pulse_options, log.events(NAME))
        except:
            log.error(NAME, _('Pulse plug-in') + ':\n' + traceback.format_exc())
            msg = _('An internal error was found in the system, see the error log for more information. The error is in part:') + ' '
            msg += _('pulse -> start_page GET')
            return self.core_render.notice('/', msg)

    def POST(self):
        try:
            global sender

            qdict = web.input()

            verify_csrf(qdict)

            normalize_options(qdict)
            pulse_options.web_update(qdict)
            if sender is not None:
                worker = sender
                worker.stop()
                worker.join(5)

            sender = PulseSender()
            runtime.register_thread(sender)

            raise web.seeother(plugin_url(start_page), True)

        except:
            log.error(NAME, _('Pulse plug-in') + ':\n' + traceback.format_exc())
            msg = _('An internal error was found in the system, see the error log for more information. The error is in part:') + ' '
            msg += _('pulse -> start_page POST')
            return self.core_render.notice('/', msg)


class help_page(ProtectedPage):
    """Load an html page for help"""

    def GET(self):
        try:
            return self.plugin_render.pulse_help()
        except:
            log.error(NAME, _('Pulse plug-in') + ':\n' + traceback.format_exc())
            msg = _('An internal error was found in the system, see the error log for more information. The error is in part:') + ' '
            msg += _('pulse -> help_page GET')
            return self.core_render.notice('/', msg)


class settings_json(ProtectedPage):
    """Returns plugin settings in JSON format."""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        try:
            return json.dumps(pulse_options)
        except:
            return {}
