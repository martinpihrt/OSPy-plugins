#!/usr/bin/env python
# -*- coding: utf-8 -*-
__author__ = 'Martin Pihrt'
# This plugin pulses a selected circuit with a 1 Hz signal with adjusted time. (For discover the location of a valve).

import json
import time
import web

from threading import Thread, Event

from ospy import helpers
from ospy.stations import stations
from ospy.webpages import ProtectedPage
from plugins import PluginOptions, plugin_url
from ospy.log import log

import i18n

NAME = 'Pulse Output Test'
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
        self._stop = Event()

        self._sleep_time = 0
        self.start()

    def stop(self):
        self._stop.set()

    def update(self):
        self._sleep_time = 0

    def run(self):
        log.clear(NAME)
        log.info(NAME, _('Test started for') + ' ' + str(pulse_options['test_time']) + ' sec.')
        station = stations.get(pulse_options['test_output'])

        for x in range(0, pulse_options['test_time']):
            station.active = True
            time.sleep(0.5)
            station.active = False
            time.sleep(0.5)

            if self._stop.is_set():
                break

        log.info(NAME, _('Test stopped.'))

        # Activate again if needed:
        if station.remaining_seconds != 0:
            station.active = True


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
        global sender

        qdict = web.input()
        stop = helpers.get_input(qdict, 'stop', False, lambda x: True)
        if sender is not None and stop:
            sender.stop()
            sender.join(5)
            sender = None
            raise web.seeother(plugin_url(start_page), True)

        return self.plugin_render.pulse(pulse_options, log.events(NAME))

    def POST(self):
        global sender

        pulse_options.web_update(web.input())
        if sender is not None:
            sender.stop()
            sender.join(5)

        sender = PulseSender()

        raise web.seeother(plugin_url(start_page), True)


class settings_json(ProtectedPage):
    """Returns plugin settings in JSON format."""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        return json.dumps(pulse_options)


