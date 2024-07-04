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

from ospy.options import options, rain_blocks                    # OSPy options (system name...), rain blocking
from ospy.version import ver_str, ver_date                       # OSPy system version (ex: 3.0.65) and date (ex: 2024)

from blinker import signal                                       # To receive station notifications

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
        ### core ###         # neni v html pridat
        'use_mqtt': False,
        'mqtt_use_tls': True,
        'mqtt_broker_host': '',                                  # for testing use http://www.hivemq.com/demos/websocket-client/
        'mqtt_broker_port': 8883,
        'mqtt_user_name': '',
        'mqtt_user_password': '',
        'mqtt_hass_topic': '',
        'mqtt_hass_system_enable_sub_topic': '',
        'mqtt_hass_discovery_topic_prefix': 'homeassistant',
        'mqtt_state_topic': 'publish_up_down',
        'mqtt_state_on': 'UP',
        'mqtt_state_off': 'DOWN',        
        ### hass ? vycistit###
        'hass_uuid': hex(uuid.getnode()),                        # Unique identifier used as prefix for MQTT Discovery by HASS. UUID based on the network adapter MAC address
        'hass_ospy_topic': '',                                   # Default: System name
        'hass_ospy_name': '',                                    # Default: System name
        'hass_ospy_fqdn': '',                                    # Default: auto detect
        'hass_device_is_station_name': False,                    # Default: uncheck
        'hass_pub_disabled': False,                              # Default: uncheck
    }
)

slugify_is_installed = False
try:
    import slugify as unicode_slug                                   # python-slugify package
    slugify_is_installed = True
except ImportError:
    pass

mqtt_is_installed = False
try:
    import paho.mqtt.client as paho
    from paho import mqtt
    mqtt_is_installed = True
except ImportError:
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
                # start MQTT HASS
                hass = mqtt_hass_to_ospy()

                ### Subscribe MQTT HASS to OSPy system notifications
                option_change = signal("option_change")
                option_change.connect(hass.notify_system_settings_change)

                mqtt_settings_change = signal("mqtt_settings_change")
                mqtt_settings_change.connect(hass.notify_base_mqtt_settings_change)

                value_change = signal("value_change")
                value_change.connect(hass.notify_system_options_change)

                rain_change = signal("rain_changed")
                rain_change.connect(hass.notify_rain_change)

                rain_delay_change = signal("rain_delay_change")
                rain_delay_change.connect(hass.notify_rain_delay_change)

                running_program_change = signal("running_program_change")
                running_program_change.connect(hass.notify_running_program_change)

                zone_names = signal("station_names")
                zone_names.connect(hass.notify_zones_options_change)

                zones_change = signal("zone_change")
                zones_change.connect(hass.notify_zone_states_change)

                rebooted = signal("rebooted")
                rebooted.connect(hass.notify_restart_after)

                restart = signal("restart")
                restart.connect(hass.notify_restart_before)
                
                if plugin_options['use_footer']:
                    msg = _('Only test! not use')
                    if in_footer is not None:
                        in_footer.val = msg.encode('utf8').decode('utf8')
                

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
            host = get_local_ip(plugin_options['mqtt_broker_host'])
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


def mqtt_hass_system_name(slugify=False):
    """Return a valid System name from Options setting (Default: OSPy)"""
    name = options.name if len(options.name) else _('OSPy')
    if slugify:
        name = hass_entity_ID_slugify(name)
    return name


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

    def _system_version(self):
        """OSPy version and date"""
        return ver_str + ' ' + ver_date

    def _system_UID(self):
        """OSPy UUID based on the network adapter MAC address"""
        return plugin_options['hass_uuid']

    def _system_web_url(self):
        """URL to access OSPy web user interface.
        Redirection displayed in HASS devices user interface options"""
        return ospy_web_url()

    def _publish(self, topic, payload=''):
        """
        MQTT publish helper function.
        Publish dictionary as JSON
        """
        client = mqtt.get_client()
        if client:
            if isinstance(payload, dict):
                payload = json.dumps(payload, sort_keys=True)

            client.publish(topic, payload, qos=1, retain=True)

    def _publish_disabled(self):
        """Return True if publish and control is disabled"""
        return False

    def update_settings(self, force_enable=False):
        """Update topics and discovery according to MQTT HASS settings"""
        availability_topic = self.availability_topic_get()
        set_topic = self.set_topic_get()
        state_topic = self.state_topic_get()

        if availability_topic != self.availability_topic or force_enable:
            self.availability_unpublish(force_enable)
            self.availability_topic = availability_topic
            self.availability_publish()

        if set_topic != self.set_topic or force_enable:
            self.set_unsubscribe(force_enable)
            self.set_topic = set_topic
            self.set_subscribe()

        if state_topic != self.state_topic or force_enable:
            self.state_unpublish(force_enable)
            self.state_topic = state_topic
            self.state_publish(force_enable=False, force_update=True)

        if force_enable:
            self.discovery_unpublish(force_enable)
        self.discovery_publish()

    def ospy_set_value(self, value):
        """
        Set OSPy parameter according to value
        Stub. To be implemented in children class
        """
        return

    def ospy_get_value(self):
        """
        Return processed value from OSPy parameter
        Stub. To be implemented in children class
        """
        return

    def device_name(self):
        """
        HASS Device name
        To be supplemented by children class
        """
        return mqtt_hass_system_name()

    def device_uid(self):
        """
        HASS Device unique ID
        Default to System UID.
        """
        return self._system_UID()

    def entity_name(self):
        """
        HASS slugified Entity name
        To be supplemented by children class
        """
        return ""

    def entity_uid(self):
        """
        HASS slugified Entity ID
        Stub. To be implemented in children class
        """
        return

    def start_publish(self, force_update=False):
        """
        MQTT actions to publish discovery, state and subcribe
        force = True will resend previous state value
        """
        self.state_publish(force_update=force_update)
        self.availability_publish()
        self.discovery_publish()
        self.set_subscribe()

    def stop_publish(self):
        """MQTT actions to remove discovery, state and subcribe"""
        self.set_unsubscribe()
        self.discovery_unpublish()
        self.availability_unpublish()
        self.state_unpublish()

    def discovery_topic_get(self):
        """Return HASS Discovery topic for the entity"""
        return (
            plugin_options['mqtt_hass_discovery_topic_prefix']
            + "/"
            + self._component
            + "/"
            + self.entity_uid()
            + "/"
            + self._component
            + "/config"
        )        

    def discovery_payload(self):
        """Compose HASS discovery payload"""
        payload = {}

        # Entity basic attributes
        payload.update(
            {
                "icon": self._icon,
                "json_attributes_topic": self.state_topic,
                "name": self.entity_name(),
                "state_topic": self.state_topic,
                "unique_id": self.entity_uid(),
                "value_template": self.state_value_template(),
            }
        )

        # Entity availability state depending on other entities or topic values
        payload["availability_mode"] = "all"
        payload["availability"] = []
        if plugin_options['mqtt_state_topic']:
            payload["availability"].append(
                {  # Status of base MQTT
                    "topic": plugin_options['mqtt_state_topic'],
                    "payload_available": "On",
                    "payload_not_available": "Off",
                }
            )
        if (
            self.state_topic
            != plugin_options['mqtt_hass_topic'] + plugin_options['mqtt_hass_system_enable_sub_topic']
        ):
            payload["availability"].append(
                {  # Status of OSPy System Enable state
                    "topic": plugin_options['mqtt_hass_topic']
                    + plugin_options['mqtt_hass_system_enable_sub_topic'],
                    "payload_available": "On",
                    "payload_not_available": "Off",
                    "value_template": "{{ value_json.state }}",
                }
            )

        # Device attributes
        payload["device"] = {
            "identifiers": [self.device_uid()],
            "manufacturer": "OSPy",
            "model": "controler",
            "name": self.device_name(),
            "sw_version": self._system_version(),
            "configuration_url": self._system_web_url(),
        }

        # Device vs Entity relation
        if self._category:
            payload["entity_category"] = self._category

        # Entity component specific attributes
        if self._component == "select":
            payload["options"] = list(self._options.keys())
            payload["command_topic"] = self.set_topic

        elif self._component == "number":
            payload["min"] = self._min
            payload["max"] = self._max
            payload["command_topic"] = self.set_topic
            if self._unit:
                payload["unit_of_measurement"] = self._unit

        elif self._component == "switch":
            payload["command_topic"] = self.set_topic
            payload["payload_off"] = "Off"
            payload["payload_on"] = "On"

        elif self._component == "binary_sensor":
            payload["payload_off"] = "Off"
            payload["payload_on"] = "On"

        elif self._component == "sensor":
            if self._unit:
                payload["unit_of_measurement"] = self._unit

        return payload

    def discovery_publish(self, force_enable=False):
        """Publish MQTT HASS Discovery config to HASS"""
        payload = self.discovery_payload()
        self._publish(self.discovery_topic, payload)

    def discovery_unpublish(self, force_enable=False):
        """Remove MQTT HASS Discovery config"""
        self._publish(self.discovery_topic)

    def state_topic_get(self):
        """Return entity state MQTT topic"""
        return plugin_options['mqtt_hass_topic'] + "/" + self._name

    def state_value_template(self):
        """Return state value decoding template"""
        if self._json_state:
            return "{{ value_json.state }}"
        return "{{ value }}"

    def state_publish(self, force_enable=False, force_update=False):
        """
        Publish system value if updated
        force = True will republish the value
        """
        value = self.get_sip_value()

        # Don't publish the same value
        if value == self._value and not force_update:
            return
        self._value = value
        if self._json_state:
            payload = {}
            payload["state"] = value
        else:
            payload = value
        self._publish(self.state_topic, payload)

    def state_unpublish(self, force_enable=False):
        """Remove published state topic from the MQTT broker"""
        self._publish(self.state_topic)

    def availability_topic_get(self):
        """
        Return entity state MQTT topic
        Stub. To be implemented by children class
        """
        return

    def availability_publish(self, force_enable=False):
        """
        Publish entity specific availability
        Stub. To be implemented by children class
        """
        return

    def availability_unpublish(self, force_enable=False):
        """
        Remove published entity availability topic from the MQTT broker
        Stub. To be implemented by children class
        """
        return

    def set_topic_get(self):
        """Return MQTT listening topic to set internal SIP state"""
        return self.state_topic_get() + "/set"

    def set_subscribe(self, force_enable=False):
        """Start listening to MQTT messages"""
        if self._component in ["sensor", "binary_sensor"]:
            return
        mqtt.subscribe(self.set_topic, self.set_incoming_message)

    def set_unsubscribe(self, force_enable=False):
        """Stop listening to MQTT messages"""
        if self._component in ["sensor", "binary_sensor"]:
            return
        mqtt.unsubscribe(self.set_topic)
        self._publish(self.set_topic)  # Clear set topic

    def set_incoming_message(self, client, msg):
        """
        Callback when MQTT message is received from the MQTT broker
        Stub. To be implemented by children class
        """
        return


# MQTT HASS system parameter classes
class mqtt_hass_system_param(mqtt_hass_base):
    """
    MQTT HASS class for OSPy system parameter
    Each paramater is a single HASS Entity
    A single HASS Device regroup all parameters (Entities)
    """

    def __init__(
        self,
        name=None,
        component=None,
        category=None,
        options={},
        icon="mdi:application-cog-outline",
        min=None,
        max=None,
        unit=None,
        gv_sd=None,
    ):
        super().__init__(
            name=name,
            component=component,
            category=category,
            options=options,
            icon=icon,
            min=min,
            max=max,
            unit=unit,
        )
        self._gv_sd = gv_sd
        if self._component == "binary_sensor":
            self._options = {"Off": 0, "On": 1}

    def set_ospy_value(self, value):
        """Set OSPy setting according to direct value or key name in option{}"""
        if self._component == "number":
            if value.isdigit():
#TODO                #gv.sd[self._gv_sd] = int(value)
                print(int(value), "set_ospy_value")

        elif self._component == "select":
            if value in self._options:
#TODO                #gv.sd[self._gv_sd] = self._options[value]
                print(self._options[value], "set_ospy_value")

    def get_ospy_value(self):
#TODO        """According to OSPy setting, return direct value or corresponding option key name"""
"""
        if self._gv_sd == None:
            return None
        s = gv.sd[self._gv_sd]
        if self._component in ["select", "binary_sensor"]:
            for option, state in self._options.items():
                if state == s:
                    return option
        return s
"""
        return

    def entity_name(self):
        """System parameter entity name"""
        """Parameter name - HA discovery will prepend device name"""
        return self._name

    def entity_uid(self):
        """System parameter entity UID"""
        return self._system_UID() + "_" + self._name

    def state_topic_get(self):
        """System parameter Entity state topic"""
        return plugin_options['mqtt_hass_topic'] + "/system/" + self._name

    def set_incoming_message(self, client, msg):
        """Callback when MQTT set message is received from MQTT broker."""
        if self._component not in ["select", "number"]:
            return

        try:
            cmd = json.loads(msg.payload)
            # decode command as json
            if type(cmd) is dict:
                if "state" not in cmd:
                    return
                value = str(cmd["state"])
            else:
                value = msg.payload.decode("utf-8")

        except ValueError as e:
            # decode direct command
            value = msg.payload.decode("utf-8")

        value = value.strip().capitalize()

        if value == self._value:
            return

        self.set_sip_value(value)
        self.state_publish()
   
# ----------------------
class mqtt_hass_rain_delay_timer(mqtt_hass_system_param):
    """MQTT HASS system setting for rain delay timer"""

    def __init__(self):
        super().__init__(
            name="rain_delay_timer",
            component="number",
            category="config",
            icon="mdi:timer-cog-outline",
            min=0,
            max=24,
            unit="h",
        )
        self._sd_param = "rd"
        self._json_state = True

    def get_ospy_value(self):
#        return gv.sd[self._sd_param]
         return

    def set_ospy_value(self, value):
        """Set OSPy settings for rain delay timer according to direct value"""
"""
        if value.isdigit():
            gv.sd[self._sd_param] = int(value)
            gv.sd[u"rdst"] = int(gv.now + gv.sd[self._sd_param] * 3600)
            stop_onrain()
"""
        print("stop_onrain()", 697)

    def state_publish(self, force_update=False):
        """
        Publish system value if updated
        force = True will republish the value
        """
        value = self.get_ospy_value()
"""
        # Don't publish the same value
        if value == self._value and not force_update:
            return
        self._value = value
        duration = gv.sd[self._sd_param] * 3600
        if duration:
            start_time = gv.sd[u"rdst"]
        else:
            start_time = "None"

        payload = {
            "state": value,
            "start_time": start_time,
            "duration": duration,
        }
        self._publish(self.state_topic, payload)
"""

class mqtt_hass_running_program(mqtt_hass_system_param):
    """MQTT HASS system sensor for running program number"""

    def __init__(self):
        super().__init__(
            name="running_program",
            component="sensor",
            category="diagnostic",
            icon="mdi:application-outline",
        )
        self._value = -1

    def get_ospy_value(self):
        """Return running program number or name"""
#TODO        return ospy_program_to_name(gv.pon)
        return


# MQTT HASS zone class
class mqtt_hass_zone(mqtt_hass_base):
    """
    MQTT HASS class for OSPy zones
    Each zone is a distinct HASS Device with a single switch Entity
    """

    def __init__(self, index):
        self._index = index
        self._enable = self._get_enable_option()
        self._json_state = True
        super().__init__(
            name=self._get_name_option(),
            component="switch",
            category=None,  # Control
            options={"Off": 0, "On": 1},
            icon="mdi:water",
        )
        self._json_state = True

    def _publish_disabled(self, force_enable=False):
        """
        Return if zone publish and control is disabled
        Don't publish disabled zones unless override by MQTT HASS option
        """
        if force_enable:
            return False

        if plugin_options['mqqt_hass_pub_disabled'] == "Off" and self._enable == 0:
            return True
        else:
            return False

    def _get_enable_option(self):
        """Return zone enable state"""
"""
        bid = int(self._index / 8)
        s = self._index % 8
        return (gv.sd["show"][bid] >> s) & 1
"""
        return

    def _get_name_option(self):
        return gv.snames[self._index]

    def update_options(self):
        """Updated zone name and enable option"""
        ZONE_RESTART = 1
        ZONE_DISCOVERY = 2
        update = None

        name = self._get_name_option()
        if name != self._name:
            self._name = name
            update = ZONE_DISCOVERY

        enable = self._get_enable_option()
        if enable != self._enable:
            update = ZONE_RESTART

        if update == ZONE_RESTART:
            self.stop_publish()
            self._enable = enable
            self.start_publish(force_update=True)
        elif update == ZONE_DISCOVERY:
            self.discovery_publish()

    def set_ospy_value(self, value):
        """Set OSPy zone state according to options name"""
"""
        if value in self._options:
            gv.srvals[self._index] = self._options[value]
"""
        return

    def get_ospy_value(self):
        """Return OSPy zone state name according to options"""
"""
        sip_state = gv.srvals[self._index]
        for value, state in self._options.items():
            if state == sip_state:
                return value
"""                
        return None

    def device_name(self):
        """Return zone Device name"""
        if _settings[MQTT_HASS_DEVICE_IS_STATION_NAME] == HASS_ON:
            return super().device_name() + " - " + self._name
        else:
            return super().device_name() + " Z" + "{0:02d}".format(self._index + 1)

    def device_uid(self):
        """Return zone Device UID"""
        return self._system_UID() + "_Z" + "{0:02d}".format(self._index + 1)

    def entity_name(self):
        """Return zone switch Entity name"""
        """Empty - HA discovery default to device name for device with single entity"""
        return ""

    def entity_uid(self):
        """Return zone Entity UID"""
        return self._system_UID() + "_Z" + "{0:02d}".format(self._index + 1)

    def discovery_payload(self):
        """Return zone HASS Discovery configuration attributes"""
        payload = super().discovery_payload()
        payload["availability"].append(
            {
                "topic": self.state_topic + "/availability",
                "payload_available": "online",
                "payload_not_available": "offline",
            }
        )
        payload["device"]["via_device"] = self._system_UID()
        return payload

    def discovery_publish(self, force_enable=False):
        """Publish HASS Discovery configuration for enabled zones"""
        if self._publish_disabled(force_enable):
            return
        return super().discovery_publish()

    def discovery_unpublish(self, force_enable=False):
        """Publish HASS Discovery configuration for enabled zones"""
        if self._publish_disabled(force_enable):
            return
        return super().discovery_unpublish()

    def state_topic_get(self):
        """Return zone MQTT state topic"""
        return plugin_options['mqtt_hass_topic'] + "/zone/" + "{0:02d}".format(self._index + 1)

    def state_publish(self, force_enable=False, force_update=False):
        """
        Publish zone state only if changed unless forces to do it
        Attributes includes state, start time, total duration in seconds and the program that trigered the state "ON" """
        if self._publish_disabled(force_enable):
            return
"""
        value = self.get_ospy_value()

        if value == self._value and not force_update:
            return

        self._value = value
        if value == "On":
            start_time = gv.rs[self._index][0]
            duration = gv.rs[self._index][2]
            if duration == float("inf") or duration == 0:
                duration = "inf"
            program = ospy_program_to_name(gv.rs[self._index][3])
        else:
            start_time = "None"
            duration = "inf"
            program = "None"

        payload = {
            "state": value,
            "start_time": start_time,
            "duration": duration,
            "program": program,
        }
        self._publish(self.state_topic, payload)
"""
    def state_unpublish(self, force_enable=False):
        """Remove zone state from MQTT broker"""
        if self._publish_disabled(force_enable):
            return
        super().state_unpublish()

    def availability_topic_get(self):
        """Return zone availability topic"""
        return self.state_topic_get() + "/availability"

    def availability_publish(self, force_enable=False):
        """Publish zone availability matching enabled state"""
        if self._publish_disabled(force_enable):
            return

        payload = "online" if self._get_enable_option() else "offline"
        self._publish(self.availability_topic, payload)

    def availability_unpublish(self, force_enable=False):
        """Remove zone availability from MQTT broker"""
        if self._publish_disabled(force_enable):
            return
        self._publish(self.availability_topic)

    def set_subscribe(self, force_enable=False):
        """Listen to zone state change requests"""
        if self._publish_disabled(force_enable):
            return
        super().set_subscribe()

    def set_unsubscribe(self, force_enable=False):
        """Stop listening to zone state change requests"""
        if self._publish_disabled(force_enable):
            return
        super().set_unsubscribe()

    def set_incoming_message(self, client, msg):
        """Process MQTT received zone set messages."""
        # Don't execute if system is disabled
        return
"""        
        if gv.sd["en"] == 0:
            return

        duration = 0
        try:
            cmd = json.loads(msg.payload)
        except ValueError as e:
            # decode direct command
            state = msg.payload.decode("utf-8")
        else:
            # decode command as json
            if "state" in cmd:
                state = str(cmd["state"])
            if "duration" in cmd:
                duration = int(cmd["duration"])

        state = state.strip().capitalize()
        index = self._index
        # set station to run
        if state != self.get_sip_value():
            if state == "On":
                # Start station
                gv.rs[index][0] = gv.now
                if duration:
                    gv.rs[index][1] = gv.now + duration
                    gv.rs[index][2] = duration
                    gv.rs[index][3] = 98  # Run Once
                else:

                    gv.rs[index][1] = float("inf")
                    gv.rs[index][2] = float("inf")
                    gv.rs[index][3] = 98  # Run Once
            elif state == "Off":
                # Stop station
                gv.rs[index][1] = gv.now

        # Execute
        if any(gv.rs):
            gv.sd["bsy"] = 1
"""

# MQTT HASS OSPy integration class
class mqtt_hass_to_ospy:
    """MQTT HASS plugin OSPy integration"""

    def __init__(self):
        """Initialize MQTT HASS plugin components"""
        self._system = {}
        self._zone = {}

        # Init base mqtt settings
        self.apply_base_mqtt_settings(init=True)

        # Init system parameters and sensors
        self.system_init()

        # Init zones
        self.zone_init()

    def apply_base_mqtt_settings(self, init=False):
        """Initialize MQTT HASS plugin options from saved setting in mqtt_hass.json"""
        global _settings_base_mqtt

        _settings_base_mqtt = mqtt.get_settings()
        base_topic = plugin_options['base_mqtt_state_topic']
        if base_topic != plugin_options['base_mqtt_state_topic']:
            plugin_options['base_mqtt_state_topic'] = base_topic
            if not init:
                self.system_discovery_publish()
                self.zone_discovery_publish()

    # System parameters - helper functions
    def system_init(self):
        """Initialize supported system parameters, sensors and start interactions with MQTT broker and HASS"""
        self._system["enable"] = mqtt_hass_system_param(
            name="enable",
            component="select",
            category=None,  # Control
            gv_sd="en",
            options={"Off": 0, "On": 1},
        )

        self._system["mode"] = mqtt_hass_system_param(
            name="mode",
            component="select",
            category="config",
            gv_sd="mm",
            options={"Automatic": 0, "Manual": 1},
        )

        self._system["rain_sensor_enable"] = mqtt_hass_system_param(
            name="rain_sensor_enable",
            component="select",
            category="config",
            gv_sd="urs",
            options={"Off": 0, "On": 1},
        )

        self._system["rain_delay_timer"] = mqtt_hass_rain_delay_timer()

        self._system["water_level_adjust"] = mqtt_hass_system_param(
            name="water_level_adjust",
            component="number",
            category="config",
            gv_sd="wl",
            icon="mdi:car-coolant-level",
            min=0,
            max=100,
            unit="%",
        )

        self._system["rain_detect"] = mqtt_hass_system_param(
            name="rain_detect",
            component="binary_sensor",
            category="diagnostic",  # Sensor
            gv_sd="rs",
            options=({"Off": 0, "On": 1}),
            icon="mdi:weather-rainy",
        )

        self._system["running_program"] = mqtt_hass_running_program()

        self.system_start_publish()

    def system_discovery_publish(self):
        """Publish system parameters Discovery configuraton to HASS"""
        for k in self._system.keys():
            self._system[k].discovery_publish()

    def system_start_publish(self):
        """Start publishing system parameters state to MQTT"""
        for k in self._system.keys():
            self._system[k].start_publish(force_update=True)

    def system_stop_publish(self):
        """Stop publishing and clear system parameters state to MQTT"""
        for k in self._system.keys():
            self._system[k].stop_publish()

    def system_update_settings(self):
        """Update system parameters state to MQTT"""
        for k in self._system.keys():
            self._system[k].update_settings()

    # Zones - helper functions
    def zone_init(self):
        """Initialize zones and start interactions with MQTT broker and HASS"""
        # zones : MQTT HASS switches with timer attribute
#        nb_zones = int(gv.sd["nbrd"] * 8)
#        for k in range(nb_zones):
#            self._zone[k] = mqtt_hass_zone(k)
        self.zone_start_publish()

    def zone_discovery_publish(self):
        """Publish zones Discovery configuraton to HASS"""
        for k in self._zone.keys():
            self._zone[k].discovery_publish()

    def zone_start_publish(self):
        """Start publishing zones state change to MQTT"""
        for k in self._zone.keys():
            self._zone[k].start_publish(force_update=True)

    def zone_stop_publish(self):
        """Stop publishing and clear zone state to MQTT"""
        for k in self._zone.keys():
            self._zone[k].stop_publish()

    def zone_update_settings(self, force_enable):
        """Stop publishing and clear zone state to MQTT"""
        for k in self._zone.keys():
            self._zone[k].update_settings(force_enable)

    # Handle system signaling - changes coming from SIP
    def notify_mqtt_hass_settings_change(self):
        """Handle MQTT HASS plugin options changed (from Web page)"""
        self.apply_hass_settings()

    def notify_base_mqtt_settings_change(self, name, **kw):
        """Handle base MQTT plugin options changed (from Web page)"""
        self.apply_base_mqtt_settings()

    def notify_system_settings_change(self, name, **kw):
        """Handle OSPy Settings changed (from web page)"""
        # Do nothing on HTTP port or HTTP IP addr changed. OSPy will reboot.
        global _settings
        global _ospy_web_url

        # System name changed -> adjust MQTT topic and HASS name prefix
#TODO chybi

        _ospy_web_url = ospy_web_url()

        # Number of zones changed
#        nb_zones_new = gv.sd["nst"]
        nb_zones = len(self._zone)
        if nb_zones_new < nb_zones:
            for k in range(nb_zones_new, nb_zones):
                if k in self._zone:
                    self._zone[k].stop_publish()
                    del self._zone[k]
        elif nb_zones_new > nb_zones:
            for k in range(nb_zones, nb_zones_new):
                self._zone[k] = mqtt_hass_zone(k)
                self._zone[k].start_publish()

        # For all remaining zones
        for k in range(0, min(nb_zones_new, nb_zones)):
            self._zone[k].update_settings()

        # For all system settings zones
        for k in self._system.keys():
            self._system[k].update_settings()

        # Rain sensor logic
        self._system["rain_sensor_enable"].start_publish()

    def notify_system_options_change(self, name, **kw):
        """Handle OSPy options from main web page"""
        for k in ["enable", "mode", "rain_delay_timer", "water_level_adjust"]:
            self._system[k].state_publish()

    def notify_rain_change(self, name, **kw):
        """Handle Rain sensor state change"""
        self._system["rain_detect"].state_publish()

    def notify_rain_delay_change(self, name, **kw):
        """Handle Rain delay timer change from main web page"""
        self._system["rain_delay_timer"].state_publish()

    def notify_running_program_change(self, name, **kw):
        """Handle Running program number change"""
        self._system["running_program"].state_publish()

    def notify_zones_options_change(self, name, **kw):
        """Handle Station names changed in gv.snames[nb_zones]"""
        for k in self._zone.keys():
            self._zone[k].update_options()

    def notify_zone_states_change(self, name, **kw):
        """Handle Zone(s) state changed"""
        for k in self._zone.keys():
            self._zone[k].state_publish()

    def notify_restart_before(self, name, **kw):
        """Handle System shutdown"""
        return

    def notify_restart_after(self, name, **kw):
        """Handle System restart"""
        return


################################################################################
# Web pages:                                                                   #
################################################################################

class settings_page(ProtectedPage):
    """Load an html page for entering adjustments."""

    def GET(self):
        global slugify_is_installed
        if not slugify_is_installed:
            error_msg = _('Error: slugify not installed. Install it to system. sudo apt install python3 slugify.')
        elif not mqtt_is_installed:
            error_msg += ' ' + _('Error: paho-mqtt is not installed. Install it to system. sudo pip3 install paho-mqtt.')
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