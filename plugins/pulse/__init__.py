# -*- coding: utf-8 -*-
__author__ = 'Martin Pihrt'
# This plugin pulses a selected circuit with a 1 Hz signal with adjusted time. (For discover the location of a valve).

import json
import time
import web
import traceback

from threading import Thread, Event

from ospy import helpers
from ospy.stations import stations
from ospy.webpages import ProtectedPage
from plugins import PluginOptions, plugin_url
from ospy.log import log


NAME = 'Pulse Output Test'
MENU =  _('Package: Pulse Output Test')
LINK = 'start_page'

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
        try:
            log.clear(NAME)
            log.info(NAME, _('Test started for {} second.').format(pulse_options['test_time']))
            station = stations.get(pulse_options['test_output'])

            for x in range(0, pulse_options['test_time']):
                station.active = True
                time.sleep(0.5)
                station.active = False
                time.sleep(0.5)

                if self._stop_event.is_set():
                    break

            log.info(NAME, _('Test stopped.'))

            # Activate again if needed:
            if station.remaining_seconds != 0:
                station.active = True

        except:
            log.error(NAME, _('Pulse plugin') + ':\n' + traceback.format_exc())

sender = None


################################################################################
# Helper functions:                                                            #
################################################################################
def start():
    pass


stop = start


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

            pulse_options.web_update(web.input())
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