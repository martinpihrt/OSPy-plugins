# -*- coding: utf-8 -*-

__author__ = 'Martin Pihrt' # www.pihrt.com

import json
import time
import datetime

import sys
import traceback
import os

from threading import Thread, Event

import web

from ospy import helpers
from ospy.options import options, rain_blocks
from ospy.log import log, logEM
from plugins import PluginOptions, plugin_url, plugin_data_dir
from ospy.helpers import get_rpi_revision
from ospy.webpages import ProtectedPage
from ospy.helpers import datetime_string
from ospy.stations import stations
from ospy.scheduler import predicted_schedule, combined_schedule

from ospy.webpages import showInFooter # Enable plugin to display readings in UI footer

from blinker import signal


NAME = 'Current Loop Tanks Monitor'
MENU =  _('Package: Current Loop Tanks Monitor')
LINK = 'settings_page'

tank_options = PluginOptions(
    NAME,
    {  
       'label_1':  _('Tank 1'),                 # label for tank 1 - 4
       'label_2':  _('Tank 2'),
       'label_3':  _('Tank 3'),
       'label_4':  _('Tank 4'),
       'en_sql_log': False,                     # logging to sql database
       'type_log': 0,                           # 0 = show log and graph from local log file, 1 = from database
       'dt_from' : '2024-01-01T00:00',          # for graph history (from date time ex: 2024-02-01T6:00)
       'dt_to' : '2024-01-01T00:00',            # for graph history (to date time ex: 2024-03-17T12:00)
    }
)


################################################################################
# Main function loop:                                                          #
################################################################################

class Sender(Thread):
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

    def _sleep(self, secs):
        self._sleep_time = secs
        while self._sleep_time > 0 and not self._stop_event.is_set():
            time.sleep(1)
            self._sleep_time -= 1

    def run(self):
        tank_mon = None

        if tank_options['use_footer']:
            tank_mon = showInFooter()                                       #  instantiate class to enable data in footer
            tank_mon.button = "current_loop_tanks_monitor/settings"         # button redirect on footer
            tank_mon.label =  _('Tanks')                                    # label on footer

        while not self._stop_event.is_set():
            try:
                self._sleep(5)

            except Exception:
                log.clear(NAME)
                log.error(NAME, _('Current Loop Tanks Monitor plug-in') + ':\n' + traceback.format_exc())
                self._sleep(60)

sender = None

################################################################################
# Helper functions:                                                            #
################################################################################
def start():
    global sender
    if sender is None:
        sender = Sender()


def stop():
    global sender
    if sender is not None:
        sender.stop()
        sender.join()
        sender = None



################################################################################
# Web pages:                                                                   #
################################################################################

class settings_page(ProtectedPage):
    """Load an html page for entering adjustments."""

    def GET(self):
        return self.plugin_render.current_loop_tanks_monitor(tank_options)


class help_page(ProtectedPage):
    """Load an html page for help"""

    def GET(self):
        return self.plugin_render.current_loop_tanks_monitor_help()

