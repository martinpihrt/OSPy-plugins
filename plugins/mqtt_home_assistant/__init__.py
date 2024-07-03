# !/usr/bin/env python3
# -*- coding: utf-8 -*-

__author__ = 'Martin Pihrt'                                      # original author in SIP system "embak", ported to OSPy Martin Pihrt

import web                                                       # Framework web.py
import json                                                      # For working with json file
import traceback                                                 # For Errors listing via callback where the event occurred
import time                                                      # For working with time, see the def _sleep function
import uuid
import re
import socket

from threading import Thread, Event                              # For use a separate thread in which the plugin is running

from plugins import PluginOptions, plugin_url, plugin_data_dir   # For access to settings, address and plugin data folder
from ospy.log import log                                         # For events logs printing (debug, error, info)
from ospy.helpers import datetime_string                         # For using date time in events logs
from ospy.helpers import is_fqdn                                 # Fully qualified domain name
from ospy.webpages import ProtectedPage                          # For check user login permissions

from ospy.webpages import showInFooter                           # Enable plugin to display readings in UI footer

from ospy.options import options


################################################################################
# Plugin name, translated name, link for web page in init, plugin options      #
################################################################################
NAME = 'Home Assistant'                                          # The unique name of the plugin listed in the plugin manager
MENU =  _('Package: MQTT Home Assistant')                        # The name of the plugin that will be visible in the running plugins tab and will be translated
LINK = 'settings_page'                                           # The default webpage when loading the plugin will be the settings page class

plugin_options = PluginOptions(
    NAME,
    {
        'use_footer': False,                                     # Show data from plugin in footer on home page
        'hass_uuid': '',                                         # Unique identifier used as prefix for MQTT Discovery by HASS
        'hass_ospy_topic': '',                                   # Default: System name
        'hass_ospy_name': '',                                    # Default: System name
        'hass_ospy_fqdn': '',                                    # Default: auto detect
        'hass_device_is_station_name': False,                    # Default: uncheck
        'hass_pub_disabled': False                               # Default: uncheck

    }
)

# local defines
HASS_ON = "On"
HASS_OFF = "Off"

HASS_MQTT_DATA_FILE = "./data/mqtt_hass.json"
MQTT_HASS_DISCOVERY_TOPIC_PREFIX = "homeassistant"
MQTT_HASS_SYSTEM_NAME_DEFAULT = "ospy"
MQTT_HASS_SYSTEM_ENABLE_SUB_TOPIC = "/system/enable"

# Base MQTT settings
BASE_MQTT_BROKER_HOST = "broker_host"
BASE_MQTT_STATE_TOPIC = "publish_up_down"
BASE_MQTT_STATE_ON = '"UP"'
BASE_MQTT_STATE_OFF = '"DOWN"'

# MQTT HASS settings
MQTT_HASS_TOPIC = "hass_ospy_topic"
MQTT_HASS_TOPIC_DEFAULT = ""
MQTT_HASS_NAME = "hass_ospy_name"
MQTT_HASS_NAME_DEFAULT = ""
MQTT_HASS_SIP_FQDN = "hass_ospy_fqdn"
MQTT_HASS_SIP_FQDN_DEFAULT = ""
MQTT_HASS_DEVICE_IS_STATION_NAME = "hass_device_is_station_name"
MQTT_HASS_DEVICE_IS_STATION_NAM_DEFAULT = HASS_OFF
MQTT_HASS_PUB_DISABLED = "hass_pub_disabled"
MQTT_HASS_PUB_DISABLED_DEFAULT = HASS_OFF
MQTT_HASS_UUID = "hass_uuid"
MQTT_HASS_UUID_DEFAULT = "ospy_uuid"

slugify_is_installed = False
try:
    import slugify as unicode_slug                                   # python-slugify package
    slugify_is_installed = True
except:
    pass

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
        in_footer = None
        if plugin_options['use_footer']:
            in_footer = showInFooter()                            # Instantiate class to enable data in footer
            in_footer.button = 'mqtt_home_assistant/settings'     # Button redirect on footer
            in_footer.label =  _('MQTT Home Assistant')           # Label on footer
      
        log.clear(NAME)                                           # Clear events window on webpage
        log.info(NAME, _('Plugin is started.'))                   # Save to log (to OSPy log if logging is enabled) and events window on webpage

        if not self._stop_event.is_set():
            try:
                if plugin_options['use_footer']:
                    msg = _('Only test! not use')
                    if in_footer is not None:
                        in_footer.val = msg.encode('utf8').decode('utf8')
                        #in_footer.unit = 'sec'
                

            except Exception:
                log.error(NAME, _('MQTT Home Assistant') + ':\n' + traceback.format_exc())
                self._sleep(10)

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


def get_local_ip(destination='10.255.255.255'):
    """Return the interface ip to a destination server"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # doesn't even have to be reachable
        s.connect((destination, 1))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip


def ospy_web_url(host=None):
    """Return OSPy web server URL"""
    # First:  Valid host setting
    if not is_fqdn(host):
        # Second: System hostname
        host = socket.getfqdn()
        if not is_fqdn(host):
            # Third : System IP used to connect with MQTT broker
            if BASE_MQTT_BROKER_HOST in _settings_base_mqtt:
                host = get_local_ip(_settings_base_mqtt[BASE_MQTT_BROKER_HOST])
    if not host:
        return None

    # Format web server URL according to OSPy port
    if options.use_ssl:
        return 'https://' + host + ':' + str(options.web_port)
    else:
        return 'http://' + host + ':' + str(options.web_port)


def mqtt_topic_slugify(text):
    """Slugify a given text to a valid MQTT topic."""
    # Apply good practice MQTT topic format
    # - Translate Unicode to ASCII characters keep case
    # - No Unicode space between words use "_"
    # - No MQTT level wildcards (#, +). Not supported by OSPy base MQTT plugin
    # - No leading and trailing forward slash and spaces
    if text == '':
        return ''
    regex_pattern = r"[^-a-zA-Z0-9_/]+"
    slug = unicode_slug.slugify(text, separator="_", regex_pattern=regex_pattern)
    slug = slug.lstrip("/_").rstrip("/_")
    return slug


def hass_entity_ID_slugify(name):
    """Slugify name to HASS Entity ID format."""
    if name == '':
        return ''
    slug = unicode_slug.slugify(name, separator="_")
    return slug


# MQTT HASS base class
class mqtt_hass_base:
    """
    MQTT HASS base class.
    Base functions for MQTT discovery (HASS feature), state publish and state subscription
    """
    def __init__(
        self,
        name=None,
        component=None,
        category=None,
        options={},
        icon=None,
        min=None,
        max=None,
        unit=None,
    ):
        self._name = name
        self._component = component
        self._category = category
        self._options = options
        self._icon = icon
        self._min = min
        self._max = max
        self._unit = unit

        self._value = None
        self._json_state = True

        self.discovery_topic = self.discovery_topic_get()
        self.state_topic = self.state_topic_get()
        self.set_topic = self.set_topic_get()
        self.availability_topic = self.availability_topic_get()

        return

    # TODO https://github.com/Dan-in-CA/sip_plugins/blob/master/mqtt_hass/mqtt_hass.py    

################################################################################
# Web pages:                                                                   #
################################################################################

class settings_page(ProtectedPage):
    """Load an html page for entering adjustments."""

    def GET(self):
        global slugify_is_installed
        if not slugify_is_installed:
            error_msg = _('Error: slugify not installed. Install it to system. sudo apt install python3 slugify.')
        else:    
            error_msg = ''
        return self.plugin_render.mqtt_home_assistant(plugin_options, log.events(NAME), error_msg)

    def POST(self):
        plugin_options.web_update(web.input())
        raise web.seeother(plugin_url(settings_page), True)


class help_page(ProtectedPage):
    """Load an html page for help"""

    def GET(self):
        return self.plugin_render.mqtt_home_assistant_help()


class settings_json(ProtectedPage):
    """Returns plugin settings in JSON format."""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        return json.dumps(plugin_options)