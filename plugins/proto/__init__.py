# !/usr/bin/env python
# -*- coding: utf-8 -*-

__author__ = 'Martin Pihrt'                                      # Ported and supplemented plugin from SIP. By Dan Kimberling

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
from ospy.webpages import showOnTimeline                         # Enable plugin to display station data on timeline


################################################################################
# Plugin name, translated name, link for web page in init, plugin options      #
################################################################################
NAME = 'Proto'                                                   # The unique name of the plugin listed in the plugin manager
MENU =  _('Package: Prototype default example')                  # The name of the plugin that will be visible in the running plugins tab and will be translated
LINK = 'settings_page'                                           # The default webpage when loading the plugin will be the settings page class

plugin_options = PluginOptions(
    NAME,
    {
        'check-1': False,                                        # Default value True/False for checker 1
        'check-2': True,                                         # Default value True/False for checker 2
        'text-1': _('Hello'),                                    # Default text for textfield 1
        'text-2': _('Nice plugin'),                              # Default text for textfield 2
        'number-1': 10,                                          # Default value for number-1
        'number-2': 2.5,                                         # Default value for number-2
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
            in_footer.button = 'proto/settings'                   # Button redirect on footer
            in_footer.label =  _('Proto')                         # Label on footer

        # Example plugin data on timeline. Used to display plugin data next to station time countdown on home page timeline.
        flow1 = None
        flow1 = showOnTimeline()                                  # Instantiate class to enable data display
        flow1.unit = 'lph'                                        # Use [instance name].unit = [unit name] to set unit for data e.g. "lph".
        flow1.val = 50.2                                          # Use [instance name].val = [plugin data] to display plugin data
        # flow1.clear                                             # Use [instance name].clear to remove from display e.g. if station not included in plugin.

        #  Example plugin data on timeline
        flow2 = None
        flow2 = showOnTimeline()                                  # Instantiate class to enable data display
        flow2.unit = 'rpm'
        flow2.val = 2300
        # flow2.clear
        
        log.clear(NAME)                                           # Clear events window on webpage
        log.info(NAME, _('Plugin is started.'))                   # Save to log (to OSPy log if logging is enabled) and events window on webpage
        # Available is: log.info, debug, error

        example_counter = 0

        while not self._stop_event.is_set():                      # Plugin repeating loop
            try:                                                  # It is a good idea to use try and except because it is possible to debug any errors encountered in the plugin.
                if plugin_options['use_footer']:                  # Notice: footer refreshing is 3 seconds...
                    msg = _('Example counter {}').format(example_counter)
                    if in_footer is not None:
                        in_footer.val = msg.encode('utf8').decode('utf8')
                        in_footer.unit = ' sec'
                
                example_counter += 1
                if example_counter > 10:
                    example_counter = 0                           # Clear example counter after number 10
                    log.clear(NAME)                               # Clear events window on webpage



                log.info(NAME, datetime_string() + ' ' + _('Example counter {}').format(example_counter))
                self._sleep(1)                                    # The loop is executed every second

            except Exception:                                     # In the event of an error (the try did not turn out correctly), a callback is used to write where the error is
                log.clear(NAME)
                log.error(NAME, _('Proto plugin') + ':\n' + traceback.format_exc())
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
        return self.plugin_render.proto(plugin_options, log.events(NAME)) # Return proto.html web page in OSPy/plugin_name/templates with plugin options and log events. Change the proto name to your own according to the name of the new plugin.

    def POST(self):
        #plugin_options.web_update(web.input(**proto))        # For save multiple elements (example selector with more selected elements)
        plugin_options.web_update(web.input())                # For save only one element (example selector with one selected element, checkbox, fieldname...)
        raise web.seeother(plugin_url(settings_page), True)   # Redirect to settings_page after saving filds from form


class help_page(ProtectedPage):
    """Load an html page for help"""

    def GET(self):
        return self.plugin_render.proto_help()                # Return help page in OSPy/plugin_name/templates. Change the proto_help name to your own according to the name of the new plugin.


class settings_json(ProtectedPage):
    """Returns plugin settings in JSON format."""
    """Try in web browser: OSPy/plugin_name/settings_json"""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        return json.dumps(plugin_options)                     # Return plugin_options as json file