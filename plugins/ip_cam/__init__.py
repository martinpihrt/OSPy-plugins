# -*- coding: utf-8 -*-
__author__ = u'Martin Pihrt'

import json
import time
import datetime
import traceback
import os
from threading import Thread, Event

import web

from ospy.log import log
from plugins import PluginOptions, plugin_url, plugin_data_dir
from ospy.webpages import ProtectedPage
from ospy.helpers import get_rpi_revision, datetime_string, get_input
from ospy import helpers
from ospy.options import options


NAME = 'IP Cam'
MENU =  _(u'Package: IP Cam')
LINK = 'settings_page'


plugin_options = PluginOptions(
    NAME,
    {
        'jpg':   ['']*options.output_count,        # IP address for jpeg image
        'mjpeg': ['']*options.output_count,        # IP address for jpeg image
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
        while not self._stop_event.is_set():
            try:
                self._sleep(1)
            except Exception:
                log.error(NAME, _(u'IP Cam plug-in') + ':\n' + traceback.format_exc())
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
    """Main html page"""

    def GET(self):
        global sender
        qdict = web.input()

        cam = get_input(qdict, 'cam', False, lambda x: True)
        if sender is not None and cam:
            cam_nr = int(qdict['cam'])
            if plugin_options['mjpeg'][cam_nr]:
                return self.plugin_render.ip_cam_mjpeg(plugin_options, cam_nr)

        return self.plugin_render.ip_cam(plugin_options, log.events(NAME))

class setup_page(ProtectedPage):
    """Load an html setup page."""

    def GET(self):
        qdict = web.input()
        msg = 'none'
  
        try:
            return self.plugin_render.ip_cam_setup(plugin_options, msg)   
        except:
            plugin_options.__setitem__('jpg', ['']*options.output_count)            
            plugin_options.__setitem__('mjpeg', ['']*options.output_count)

            return self.plugin_render.ip_cam_setup(plugin_options, msg)

    def POST(self):
        global sender
        try:
            qdict = web.input()
            commands = {'jpg': [], 'mjpeg': []}
            for i in range(0, options.output_count):
                if 'jpg'+str(i) in qdict:
                    commands['jpg'].append(qdict['jpg'+str(i)])
                else:
                    commands['jpg'].append('')

                if 'mjpeg'+str(i) in qdict:
                    commands['mjpeg'].append(qdict['mjpeg'+str(i)])
                else:
                    commands['mjpeg'].append('')                    

            plugin_options.__setitem__('jpg', commands['jpg'])
            plugin_options.__setitem__('mjpeg', commands['mjpeg'])

            if sender is not None:
                sender.update()

        except Exception:
            log.debug(NAME, _('IP cam plug-in') + ':\n' + traceback.format_exc())
            pass

        msg = 'saved'
        return self.plugin_render.ip_cam_setup(plugin_options, msg)


class help_page(ProtectedPage):
    """Load an html page for help page."""

    def GET(self):
        return self.plugin_render.ip_cam_help()         


class settings_json(ProtectedPage):
    """Returns plugin settings in JSON format."""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        return json.dumps(plugin_options)