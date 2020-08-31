# -*- coding: utf-8 -*-
__author__ = 'Martin Pihrt'

import json
import time
from datetime import datetime
import traceback
import os
from threading import Thread, Event

import web

from ospy.log import log
from plugins import PluginOptions, plugin_url, plugin_data_dir
from ospy.webpages import ProtectedPage
from ospy.helpers import get_rpi_revision
from ospy.helpers import datetime_string
from ospy import helpers
from ospy.stations import stations

from ospy.webpages import showInFooter # Enable plugin to display readings in UI footer
#from ospy.webpages import showOnTimeline # Enable plugin to display station data on timeline

import RPi.GPIO as GPIO


NAME = 'Temperature Switch'
MENU =  _('Package: Temperature Switch')
LINK = 'settings_page'


plugin_options = PluginOptions(
    NAME,
    {'enabled_a': False,
     'enabled_b': False,
     'enabled_c': False,
     'probe_A_on': _('None'),
     'probe_B_on': _('None'),
     'probe_C_on': _('None'),
     'probe_A_off': _('None'),
     'probe_B_off': _('None'),
     'probe_C_off': _('None'),
     'temp_a_on': 30,
     'temp_b_on': 40,
     'temp_c_on': 50,
     'temp_a_off': 25,
     'temp_b_off': 35,
     'temp_c_off': 45,
     'control_output_A': _('None'),
     'control_output_B': _('None'),
     'control_output_C': _('None')
     }
)


################################################################################
# Main function loop:                                                          #
################################################################################


class Sender(Thread):
    
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

    def _sleep(self, secs):
        self._sleep_time = secs
        while self._sleep_time > 0 and not self._stop.is_set():
            time.sleep(1)
            self._sleep_time -= 1

    def run(self):
        
        while not self._stop.is_set():
            try:
                
                self._sleep(1)    
 
            except Exception:
                log.error(NAME, _(u'Temperature Switch plug-in') + ':\n' + traceback.format_exc())
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
    """Load an html page for entering adjustments and deleting logs"""

    def GET(self):
        return self.plugin_render.temperature_switch(plugin_options, log.events(NAME))

    def POST(self):
        plugin_options.web_update(web.input())

        if sender is not None:
            sender.update()                
        raise web.seeother(plugin_url(settings_page), True)


class settings_json(ProtectedPage):
    """Returns plugin settings in JSON format."""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        return json.dumps(plugin_options)