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
from plugins import PluginOptions, plugin_url
from ospy.log import log
from ospy.helpers import verify_csrf


NAME = 'Pulse Output Test'
MENU =  _('Package: Pulse Output Test')
LINK = 'start_page'
MIN_TEST_TIME = 1
MAX_TEST_TIME = 3600

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

    def run(self):
        station = None
        try:
            log.clear(NAME)
            normalize_options(pulse_options)
            test_time = pulse_options['test_time']
            station = stations.get(pulse_options['test_output'])
            log.info(NAME, _('Test started for {} second.').format(test_time))

            for x in range(0, test_time):
                station.active = True
                if self._stop_event.wait(0.5):
                    break
                station.active = False
                if self._stop_event.wait(0.5):
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

sender = None


################################################################################
# Helper functions:                                                            #
################################################################################
def start():
    pass


stop = start


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
                sender.stop()
                sender.join(5)
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
                sender.stop()
                sender.join(5)

            sender = PulseSender()

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
