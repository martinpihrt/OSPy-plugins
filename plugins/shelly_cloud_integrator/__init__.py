# !/usr/bin/env python3
# -*- coding: utf-8 -*-

__author__ = 'Martin Pihrt'

import web                                                       # Framework web.py
import json                                                      # For working with json file
import traceback                                                 # For Errors listing via callback where the event occurred
import time                                                      # For working with time, see the def _sleep function
from threading import Thread, Event                              # For use a separate thread in which the plugin is running

from plugins import PluginOptions, plugin_url, plugin_data_dir   # For access to settings, address and plugin data folder
from ospy.log import log                                         # For events logs printing (debug, error, info)
from ospy.helpers import datetime_string                         # For using date time in events logs
from ospy.webpages import ProtectedPage                          # For check user login permissions

from ospy.webpages import showInFooter                           # Enable plugin to display readings in UI footer


################################################################################
# Plugin name, translated name, link for web page in init, plugin options      #
################################################################################
NAME = 'Shelly Cloud Integration'                                # The unique name of the plugin listed in the plugin manager
MENU =  _('Package: Shelly Cloud Integration')                   # The name of the plugin that will be visible in the running plugins tab and will be translated
LINK = 'settings_page'                                           # The default webpage when loading the plugin will be the settings page class

plugin_options = PluginOptions(
    NAME,
    {
        'use_footer': True,                                      # Show data from plugin in footer on home page
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
        # Exmple data in footer
        in_footer = None
        if plugin_options['use_footer']:
            in_footer = showInFooter()                            # Instantiate class to enable data in footer
            in_footer.button = 'shelly_cloud_integration/settings'# Button redirect on footer
            in_footer.label =  _('Shelly Cloud Integration')      # Label on footer
        
        log.clear(NAME)                                           # Clear events window on webpage
        log.info(NAME, _('Plugin is started.'))                   # Save to log (to OSPy log if logging is enabled) and events window on webpage

        while not self._stop_event.is_set():                      # Plugin repeating loop
            try:                                                  # It is a good idea to use try and except because it is possible to debug any errors encountered in the plugin.
                if plugin_options['use_footer']:                  # Notice: footer refreshing is 3 seconds...
                    msg = _('test')
                    if in_footer is not None:
                        in_footer.val = msg.encode('utf8').decode('utf8')

                self._sleep(1)                                    # The loop is executed every second

            except Exception:                                     # In the event of an error (the try did not turn out correctly), a callback is used to write where the error is
                log.clear(NAME)
                log.error(NAME, _('Shelly Cloud Integration plugin') + ':\n' + traceback.format_exc())
                self._sleep(60)                                   # In case of an error, it is advisable to wait longer than 1 second

sender = None

################################################################################
# Helper functions:                                                            #
################################################################################
def start():                                                      # This function starts the plugin core
    global sender
    if sender is None:
        sender = Sender()


def stop():                                                       # This function stops the plugin core
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
        return self.plugin_render.shelly_cloud_integration(plugin_options, log.events(NAME))

    def POST(self):
        
        plugin_options.web_update(web.input()) 
        raise web.seeother(plugin_url(settings_page), True)


class help_page(ProtectedPage):
    """Load an html page for help"""

    def GET(self):
        return self.plugin_render.shelly_cloud_integration_help()


class settings_json(ProtectedPage):
    """Returns plugin settings in JSON format."""
    """Try in web browser: OSPy/plugin_name/settings_json"""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        return json.dumps(plugin_options)