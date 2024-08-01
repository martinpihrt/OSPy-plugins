# !/usr/bin/env python3
# -*- coding: utf-8 -*-

__author__ = 'Martin Pihrt'                                      # original author for SIP system "embak", ported to OSPy Martin Pihrt

import web                                                       # Framework web.py
import json                                                      # For working with json file
import traceback                                                 # For Errors listing via callback where the event occurred
import time                                                      # For working with time, see the def _sleep function
import uuid
import re
import socket
import atexit
import ssl
import datetime
from datetime import timedelta

from threading import Thread, Event                              # For use a separate thread in which the plugin is running

from plugins import PluginOptions, plugin_url, plugin_data_dir   # For access to settings, address and plugin data folder
from ospy.log import log                                         # For events logs printing (debug, error, info)
from ospy.helpers import datetime_string                         # For using date time in events logs
from ospy.helpers import is_fqdn                                 # Fully qualified domain name
from ospy.helpers import stop_onrain                             # For rain delay timer
from ospy.webpages import ProtectedPage                          # For check user login permissions
from ospy.webpages import showInFooter                           # Enable plugin to display readings in UI footer
from ospy.programs import programs
from ospy.stations import stations
from ospy.runonce import run_once
from ospy.inputs import inputs
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
        'use_tls': False,                                        # MQTT with SSL
        'use_mqtt_log': True,   
        'use_footer': False,                                     # Show data from plugin in footer on home page
        'mqtt_broker_host': '192.168.88.118',                    # Ex: localhost 
        'mqtt_broker_port': 1883,                                # Default: 1883
        'mqtt_user_name': 'user',                                # Ex: user admin in mqtt Mosquitto broker
        'mqtt_user_password': 'passwd',                          # Ex: pass 1234 in mqtt Mosquitto broker
        'mqtt_hass_topic': options.name,                         # Default: System name
        'hass_ospy_name': options.name,                          # Default: System name
        'mqtt_hass_discovery_topic_prefix': 'homeassistant',     # Default: homeassistant
        'hass_uuid': hex(uuid.getnode()),                        # Unique identifier used as prefix for MQTT Discovery by HASS. UUID based on the network adapter MAC address
        'hass_ospy_fqdn': '',                                    # Default: auto detect
        'hass_device_is_station_name': True,                     # Default: uncheck
    }
)

mqtt = None
_client = None
_subscriptions = {}

slugify_is_installed = False
try:
    import slugify as unicode_slug                              # python-slugify package
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
        self.client = None
        self.devices = None
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
      
        if not self._stop_event.is_set():
            try:
                log.clear(NAME)
                if mqtt_is_installed:
                    self.client = get_client()
                    log.info(NAME, _('Plugin is started.'))
                    atexit.register(on_restart)
                    discovery_publish()

                if self.client:
                    msg = _('Client OK')
                elif self.client is None:
                    msg = _('Client not ready!')
                else:
                    msg = ''
                if plugin_options['use_footer']:
                    if in_footer is not None:
                        in_footer.val = msg.encode('utf8').decode('utf8')

            except Exception:
                log.error(NAME, _('MQTT Home Assistant') + ':\n' + traceback.format_exc())

sender = None

################################################################################
# MQTT Client                                                                  #
################################################################################
def on_message(client, userdata, msg):
    """ Callback for MQTT data recieved """
    global _subscriptions
    if not msg.topic in _subscriptions:
        log.clear(NAME)
        log.info(NAME, _('Message on topic:') + '{}'.format(msg.topic))
    else:
        for cb, data in _subscriptions[msg.topic]:
            cb(client, msg, data)

def on_log(client, userdata, level, buf):
    log.debug(NAME, datetime_string() + ' log: {}'.format(buf))



def get_client():
        try:
            # using MQTT version 5 here, for 3.1.1: MQTTv311, 3.1: MQTTv31
            # userdata is user defined data of any type, updated by user_data_set()
            # client_id is the given name of the client
            _client = paho.Client(client_id=options.name)  # Use system name as client ID
            _client.on_message = on_message
            if plugin_options['use_mqtt_log']:
                _client.on_log = on_log                                                        # debug MQTT communication log
            if plugin_options['use_tls']:
                _client.tls_set(tls_version=mqtt.client.ssl.PROTOCOL_TLSv1_2,
                                ciphers=None, 
                                certfile=None,
                                keyfile=None,
                                )
                _client.tls_insecure_set(False)
            log.clear(NAME)
            log.info(NAME, datetime_string() + ' ' + _('Connecting to broker') + '...')
            _client.username_pw_set(plugin_options['mqtt_user_name'], plugin_options['mqtt_user_password'])
            _client.connect(plugin_options['mqtt_broker_host'], plugin_options['mqtt_broker_port'], 60)
            time.sleep(5)
            _client.loop_start()
            log.info(NAME, datetime_string() + ' ' + _('OK'))
            return _client

        except Exception as e:
            log.error(NAME, _('Plugin could not initalize client:') + '{}'.format(e))
            return None


def subscribe(topic, callback, data, qos=0):
    """ Subscribes to a topic with the given callback """
    global _subscriptions, sender
    client = sender.client
    if client:
        if topic not in _subscriptions:
            _subscriptions[topic] = [(callback, data)]
            client.subscribe(topic, qos)
            log.info(NAME, datetime_string() + ' ' + _('Subscribe topic') + ': ' + str(topic))
        else:
            _subscriptions[topic].append((callback, data))
            log.info(NAME, datetime_string() + ' ' + _('Append topic callback') + ': ' + str((callback, data)))


def unsubscribe(topic):
    """ Unsubscribes to a topic """
    global _subscriptions, sender
    client = sender.client
    if client:
        if topic in _subscriptions:
            del _subscriptions[topic]
            client.unsubscribe(topic)


def on_restart():
    global _client
    if _client is not None:
        _client.disconnect()
        _client.loop_stop()
        _client = None




################################################################################
# Helper functions:                                                            #
################################################################################
def start():
    global sender
    if sender is None:
        sender = Sender()


def stop():
    global sender
    global _client
    if sender is not None:
        sender.stop()
        sender.join()
        sender = None
    if _client is not None:
        _client.disconnect()
        _client.loop_stop()
        _client = None


def get_local_ip(destination='10.255.255.255'):
    """ Return the interface ip to a destination server """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # does not even have to be reachable
        s.connect((destination, 1))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip


def ospy_web_url(host=None):
    """ Return OSPy web server URL """
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
    """ Slugify a given text to a valid MQTT topic """
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
    """ Slugify name to HASS Entity ID format """
    if name == '':
        return ''
    slug = unicode_slug.slugify(name, separator="_")
    return slug


def hass_system_name(slugify=False):
    """ Return a valid System name from Options setting (Default: OSPy) """
    name = options.name if len(options.name) else _('OSPy')
    if slugify:
        name = hass_entity_ID_slugify(name)
    return name


def validateJSON(jsonData):
    """Checking if the json format is correct"""
    try:
        json.loads(jsonData)
    except ValueError as err:
        return False
    return True

##################################################################################################################

def system_version():
    """ OSPy version and date """
    return ver_str + ' ' + ver_date


def system_UID():
    """ OSPy UUID based on the network adapter MAC address """
    return plugin_options['hass_uuid']


def system_web_url():
    """ URL to access OSPy web user interface.
    Redirection displayed in HASS devices user interface options """
    url = ospy_web_url()
    plugin_options['hass_ospy_fqdn'] = url
    return plugin_options['hass_ospy_fqdn']


def publish(topic, payload=''):
    """ MQTT publish helper function. Publish dictionary as JSON """
    global sender
    client = sender.client
    if client:
        if isinstance(payload, dict):
            payload = json.dumps(payload, sort_keys=True)
        log.debug(NAME, datetime_string() + ' ' + _('Publish to topic') + ': {}, '.format(topic) + _('payload') + ': {}'.format(payload))
        client.publish(topic, payload, qos=0, retain=True)


class hass_device:
    def __init__(self):
        _deviceclass = None # sensor, binary-sensor, number....
        _devicetype = None # temperature, humidity, duration, battery...
        _type = None
        _property = None
        _name = None
        _icon = None
        _unit = None
        _min = None
        _max = None
        _callback = None

    def createNumber(self, _devicetype, _type, _property, _name, _icon, _unit, _min, _max, _callback):
        self._deviceclass = "number"
        self._devicetype = _devicetype
        self._type = _type
        self._property = _property
        self._name = _name
        self._icon = _icon
        self._unit = _unit
        self._min = _min
        self._max = _max
        self._callback = _callback
        return self

    def createSwitch(self, _devicetype, _type, _property, _name, _icon, _callback):
        self._deviceclass = "switch"
        self._devicetype = _devicetype
        self._type = _type
        self._property = _property
        self._name = _name
        self._icon = _icon
        self._unit = None
        self._min = None
        self._max = None
        self._callback = _callback
        return self
    
    def createBinarySensor(self, _devicetype, _type, _property, _name, _icon):
        self._deviceclass = "binary_sensor"
        self._devicetype = _devicetype
        self._type = _type
        self._property = _property
        self._name = _name
        self._icon = _icon
        self._unit = None
        self._min = None
        self._max = None
        self._callback = None
        return self




def rain_delay_set(client, msg, device):
    payload = msg.payload.decode("utf-8")
    publish('{}/{}/{}/state'.format(plugin_options['mqtt_hass_topic'], device._type, device._property), payload)
    rain_blocks['hass'] = datetime.datetime.now() + datetime.timedelta(hours=float(int(payload)))
    stop_onrain()

def water_level_set(client, msg, device):
    payload = msg.payload.decode("utf-8")
    publish('{}/{}/{}/state'.format(plugin_options['mqtt_hass_topic'], device._type, device._property), payload)
    options.level_adjustment = int(payload) / 100

def scheduler_enable_set(client, msg, device):
    payload = msg.payload.decode("utf-8")
    publish('{}/{}/{}/state'.format(plugin_options['mqtt_hass_topic'], device._type, device._property), payload)
    options.scheduler_enabled = True if payload == "True" else False

def manual_mode_set(client, msg, device):
    payload = msg.payload.decode("utf-8")
    publish('{}/{}/{}/state'.format(plugin_options['mqtt_hass_topic'], device._type, device._property), payload)
    options.manual_mode = True if payload == "True" else False
    if payload == "True":
        publish('{}/{}/{}/availability'.format(plugin_options['mqtt_hass_topic'], "system", "scheduler_enabled"), "offline")
    else:
        publish('{}/{}/{}/availability'.format(plugin_options['mqtt_hass_topic'], "system", "scheduler_enabled"), "online")
    
def station_set(client, msg, device):
    payload = msg.payload.decode("utf-8")
    publish('{}/{}/{}/state'.format(plugin_options['mqtt_hass_topic'], device._type, device._property), payload)
    if payload == "True":
        start = datetime.datetime.now()
        mqn = _('Home Assistant')
        new_schedule = {
        'active': True,
        'program': -1,
        'station': device._id,
        'program_name': mqn,
        'fixed': True,
        'cut_off': 0,
        'manual': True,
        'blocked': False,
        'start': start,
        'original_start': start,
        'end': start + datetime.timedelta(days=3650),
        'uid': '%s-%s-%d' % (str(start), mqn, device._id),
        'usage': stations.get(device._id).usage
        }

        log.start_run(new_schedule)
        stations.activate(new_schedule['station'])
    else:
        stations.deactivate(device._id)
        active = log.active_runs()
        for interval in active:
            if interval['station'] == device._id:
                log.finish_run(interval)
    



def discovery_payload(device):
    """ Compose HASS discovery payload """
    payload = {}
    

    

    if device._type == "stations":
        # Device attributes
        payload["device"] = {
        "identifiers": ["ospy_{}_s{}".format(system_UID(), device._id)],
        "manufacturer": "www.pihrt.com",
        "model": _('Station'),
        "name": device._name,
        "sw_version": system_version(),
        "serial_number": system_UID(),
        "configuration_url": system_web_url(),
        "via_device": "ospy_{}".format(system_UID())
        }
    else:
        # Device attributes
        payload["device"] = {
        "identifiers": ["ospy_{}".format(system_UID())],
        "manufacturer": "www.pihrt.com",
        "model": "OpenSprinkler Python",
        "name": hass_system_name(),
        "sw_version": system_version(),
        "serial_number": system_UID(),
        "configuration_url": system_web_url(),

        }

    payload["unique_id"] = 'ospy_{}{}{}_{}'.format(device._deviceclass, device._type, device._property, system_UID())
    payload["device_class"] = device._devicetype
    payload["state_topic"] = '{}/{}/{}/state'.format(plugin_options['mqtt_hass_topic'], device._type, device._property)
    payload["availability_topic"] = '{}/{}/{}/availability'.format(plugin_options['mqtt_hass_topic'], device._type, device._property)
    
    if device._icon is not None:
        payload["icon"] = device._icon
    if device._unit is not None:
        payload["unit_of_measurement"] = device._unit
    if device._min is not None:
        payload["min"] = device._min
    if device._max is not None:
        payload["max"] = device._max
    if device._name is not None:
        payload["name"] = device._name
        if device._type == "stations":
            payload["name"] = ""
    

    if device._deviceclass == "sensor":
        payload["value_template"] = "{{ value_json.state }}"
    elif device._deviceclass == "binary_sensor":
        payload["value_template"] = "{{ value_json.state }}"
        payload["payload_off"] = "False"
        payload["payload_on"] = "True"
    elif device._deviceclass == "number":
        if device._callback is not None:
            payload["value_template"] = "{{ value_json.number }}"
            payload["command_topic"] = '{}/{}/{}/set'.format(plugin_options['mqtt_hass_topic'], device._type, device._property)
            subscribe(payload["command_topic"], device._callback, device)
        else:
            raise ValueError(_('Callback cannot be Null for device_class = number'))
    elif device._deviceclass == "switch":
        if device._callback is not None:
            payload["value_template"] = "{{ value_json.state }}"
            payload["command_topic"] = '{}/{}/{}/set'.format(plugin_options['mqtt_hass_topic'], device._type, device._property)
            payload["payload_off"] = "False"
            payload["payload_on"] = "True"
            subscribe(payload["command_topic"], device._callback, device)
        else:
            raise ValueError(_('Callback cannot be Null for device_class = switch'))

    return payload

def discovery_topic_get(component, name):
    """Return HASS Discovery topic for the entity"""
    return ('{}/{}/{}_{}/config'.format(plugin_options['mqtt_hass_discovery_topic_prefix'], component, system_UID(), name))

def discovery_publish():
    """Publish MQTT HASS Discovery config to HASS"""

    # https://www.home-assistant.io/integrations/mqtt/#configuration-via-mqtt-discovery sekce Configuration of MQTT components via MQTT discovery
    
    components = []

    components.append(hass_device().createNumber("duration", "system", "rain_delay",  _('Rain delay'), "mdi:timer-cog-outline", "h", 0, 24, rain_delay_set))
    components.append(hass_device().createNumber( None, "system", "water_level",  _('Water level'), "mdi:car-coolant-level", "%", 0, 100, water_level_set))
    components.append(hass_device().createSwitch( "switch", "system", "scheduler_enabled",  _('Scheduler'), "mdi:calendar", scheduler_enable_set))
    components.append(hass_device().createSwitch( "switch", "system", "manual_mode",  _('Manual operation'), None, manual_mode_set))
    components.append(hass_device().createBinarySensor( "moisture", "system", "rain_sensed",  _('Rain sensor'), None))

    for i in range(0, options.output_count):
        device = hass_device().createSwitch( None, "stations", "station_{}".format(i),  stations.get(int(i)).name if plugin_options['hass_device_is_station_name'] else _("Station") + " {0:02d}".format(i + 1), "mdi:sprinkler-variant", station_set)
        device._id = i
        components.append(device)

    for component in components:
        payload = discovery_payload(component)
        topic = discovery_topic_get(component._deviceclass, component._property)
        publish(topic, payload)
        set_devices_online(component)
    
    set_devices_default_values(components)

    sender.devices = components

    set_devices_signal()

    

# https://prod.liveshare.vsengsaas.visualstudio.com/join?85CA0FB5E1E238A97A5231EA9806CF8807C0

def set_devices_online(device): # set inital values to HASS after plugin start
    topic = '{}/{}/{}/availability'.format(plugin_options['mqtt_hass_topic'], device._type, device._property)
    if device._property == "scheduler_enabled" and options.manual_mode:
        publish(topic, "offline")
    elif device._property == "rain_sensed" and not options.rain_sensor_enabled:
        publish(topic, "offline")
    elif device._type == "stations" and not stations.get(int(device._id)).enabled:
        publish(topic, "offline")
    else:
        publish(topic, "online")

def set_devices_default_values(devices):
    for device in devices:
        payload = {}
        topic = {}
        if device._property == "rain_delay":
            topic = '{}/{}/{}/state'.format(plugin_options['mqtt_hass_topic'], device._type, device._property)
            payload["number"] = int(int(round(rain_blocks.seconds_left())) / 3600)
        elif device._property == "water_level":
            topic = '{}/{}/{}/state'.format(plugin_options['mqtt_hass_topic'], device._type, device._property)
            payload["number"] = int(options.level_adjustment * 100)
        elif device._property == "scheduler_enabled":
            topic = '{}/{}/{}/state'.format(plugin_options['mqtt_hass_topic'], device._type, device._property)
            payload["state"] = str(options.scheduler_enabled)
        elif device._property == "manual_mode":
            topic = '{}/{}/{}/state'.format(plugin_options['mqtt_hass_topic'], device._type, device._property)
            payload["state"] = str(options.manual_mode)
        elif device._property == "rain_sensed":
            topic = '{}/{}/{}/state'.format(plugin_options['mqtt_hass_topic'], device._type, device._property)
            payload["state"] = str(inputs.rain_sensed())
        elif device._type == "stations":
            topic = '{}/{}/{}/state'.format(plugin_options['mqtt_hass_topic'], device._type, device._property)
            payload["state"] = str(stations.get(device._id).active)
        publish(topic, payload)

def update_device_values(name, **kw):
    for device in sender.devices:
        set_devices_online(device)
    set_devices_default_values(sender.devices)

def update_device_plugin_settings(name, **kw):
    discovery_publish()

def set_devices_signal():
    # print("setting the signals")
    loggedin = signal('loggedin')  ### associations with signal ###
    loggedin.connect(update_device_values)  ### define which subroutine will be triggered in helper ###
    value_change = signal('value_change')
    value_change.connect(update_device_values)
    option_change = signal('option_change')
    option_change.connect(update_device_values)
    rebooted = signal('rebooted')
    rebooted.connect(update_device_values)
    restarted = signal('restarted')
    restarted.connect(update_device_values)
    station_names = signal('station_names')
    station_names.connect(update_device_values)
    program_change = signal('program_change')
    program_change.connect(update_device_values)
    program_deleted = signal('program_deleted')
    program_deleted.connect(update_device_values)
    program_toggled = signal('program_toggled')
    program_toggled.connect(update_device_values)
    program_runnow = signal('program_runnow')
    program_runnow.connect(update_device_values)
    zone_change = signal('zone_change')
    zone_change.connect(update_device_values)
    rain_active = signal('rain_active')
    rain_active.connect(update_device_values)
    rain_not_active = signal('rain_not_active')
    rain_not_active.connect(update_device_values)
    master_one_on = signal('master_one_on')
    master_one_on.connect(update_device_values)
    master_one_off = signal('master_one_off')
    master_one_off.connect(update_device_values)
    master_two_on = signal('master_two_on')
    master_two_on.connect(update_device_values)
    master_two_off = signal('master_two_off')
    master_two_off.connect(update_device_values)
    pressurizer_master_relay_on = signal('pressurizer_master_relay_on')
    pressurizer_master_relay_on.connect(update_device_values)
    pressurizer_master_relay_off = signal('pressurizer_master_relay_off')
    pressurizer_master_relay_off.connect(update_device_values)
    poweroff = signal('poweroff')
    poweroff.connect(update_device_values)
    ospyupdate = signal('ospyupdate')
    ospyupdate.connect(update_device_values)
    station_on = signal('station_on')
    station_on.connect(update_device_values)
    station_off = signal('station_off')
    station_off.connect(update_device_values)
    station_clear = signal('station_clear')
    station_clear.connect(update_device_values)
    internet_available = signal('internet_available')
    internet_available.connect(update_device_values)
    internet_not_available = signal('internet_not_available')
    internet_not_available.connect(update_device_values)
    rain_delay_set = signal('rain_delay_set')
    rain_delay_set.connect(update_device_values)
    rain_delay_remove = signal('rain_delay_remove')
    rain_delay_remove.connect(update_device_values)
    hass_plugin_update = signal('hass_plugin_update')
    hass_plugin_update.connect(update_device_plugin_settings) ## completely reinitialize only on plugin settings change
    


################################################################################
# Web pages:                                                                   #
################################################################################

class settings_page(ProtectedPage):
    """ Load an html page for entering adjustments. """

    def GET(self):
        global slugify_is_installed
        global mqtt_is_installed
        msg = ''
        if not slugify_is_installed:
            msg = _('Error: slugify not installed. Install it to system. sudo apt install python3 slugify.')
        elif not mqtt_is_installed:
            msg += ' ' + _('Error: paho-mqtt is not installed. Install it to system. sudo pip3 install paho-mqtt.')
        else:
            client = sender.client
            if client:
                msg = _('Client OK')
            elif client is None:
                msg = _('Client not ready!')
            else:
                msg = ''
        return self.plugin_render.mqtt_home_assistant(plugin_options, log.events(NAME), msg)

    def POST(self):
        plugin_options.web_update(web.input())
        updateSignal = signal('hass_plugin_update')
        updateSignal.send()
        raise web.seeother(plugin_url(settings_page), True)


class help_page(ProtectedPage):
    """ Load an html page for help """

    def GET(self):
        return self.plugin_render.mqtt_home_assistant_help()


class settings_json(ProtectedPage):
    """ Returns plugin settings in JSON format """

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        return json.dumps(plugin_options)