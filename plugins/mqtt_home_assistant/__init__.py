# !/usr/bin/env python3
# -*- coding: utf-8 -*-

__author__ = 'Martin Pihrt'

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

from threading import Thread, Event, Timer                              # For use a separate thread in which the plugin is running

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
        'measurement_refresh_interval': 30,                      # Default: 30 seconds (refresh measuring data. Ex: from air temp humi plugin)
        'ext_ds1-6': True,                                       # Including temperature sensors DS1 to DS6 from the temperature and humidity monitor extension 
        'ext_dht': False,                                        # Including temperature/humidity sensors DHT from the temperature and humidity monitor extension
        'ext_water_sonic': False,                                # Including water level from the water tank (sonic) monitor extension
        'ext_water_current': True                                # Including water level from the water tank (tanks with current loop) monitor extension
    })

mqtt = None
_client = None
_subscriptions = {}
_is_connected = False

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
        self.sensors_temp_humi_ds = None
        self.sensors_tanks = None
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
                
        while not self._stop_event.is_set():                                                    # main data update loop, with addition to signals
            try:
                if self.sensors_temp_humi_ds is not None:
                    update_temp_humi_ds(self.sensors_temp_humi_ds)                              # update air temp plugin only if devices exist
                if self.sensors_tanks is not None:
                    update_tank_level(self.sensors_tanks)                                       # update water tank plugin only if devices exist
                self._sleep(plugin_options['measurement_refresh_interval'])
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
                _client.on_log = on_log                    # debug MQTT communication log
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
    global _subscriptions, sender, _is_connected
    client = sender.client
    if client:
        _is_connected = True
        if topic not in _subscriptions:
            _subscriptions[topic] = [(callback, data)]
            client.subscribe(topic, qos)
            log.debug(NAME, datetime_string() + ' ' + _('Subscribe topic') + ': ' + str(topic))
        else:
            _subscriptions[topic].append((callback, data))
            log.debug(NAME, datetime_string() + ' ' + _('Append topic callback') + ': ' + str((callback, data)))


def unsubscribe(topic):
    """ Unsubscribes to a topic """
    global _subscriptions, sender
    client = sender.client
    if client:
        if topic in _subscriptions:
            del _subscriptions[topic]
            client.unsubscribe(topic)


def on_restart():
    global sender, _is_connected
    if sender is not None:
        if sender.client is not None:
            sender.client.disconnect()
            sender.client.loop_stop()
            sender.client = None
        _is_connected = False


def is_connected():
    """Check if MQTT client is connected"""
    global _is_connected
    return _is_connected

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
    remove_hass_ospy()
    if sender is not None:
        if sender.client is not None:
            sender.client.disconnect()
            sender.client.loop_stop()
            sender.client = None
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


def removeTopic(topic):
    global sender
    client = sender.client
    if client:
        client.publish(topic, None, 0, False)


class hass_device:
    def __init__(self):
        _deviceclass = None # sensor, binary-sensor, number....
        _devicetype = None  # temperature, humidity, duration, battery...
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
    
    def createButton(self, _devicetype, _type, _property, _name, _icon, _callback):
        self._deviceclass = "button"
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
    
    def createCategory(self, _devicetype, _type, _property, _name, _icon):
        self._deviceclass = "sensor"
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
    
    def createSensor(self, _devicetype, _type, _property, _name, _icon, _unit):
        self._deviceclass = "sensor"
        self._devicetype = _devicetype
        self._type = _type
        self._property = _property
        self._name = _name
        self._icon = _icon
        self._unit = _unit
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
    
program_runnow = signal('program_runnow')
def report_program_runnow():
    program_runnow.send()

def program_set(client, msg, device):
    payload = msg.payload.decode("utf-8")
    if payload == device._type:
        # first stop stations
        # log.finish_run(None)
        # stations.clear()
        # next run program id: xx
        # print(device._id)
        programs.run_now(int(device._id))
        Timer(0.1, programs.calculate_balances).start()
        report_program_runnow()
        time.sleep(0.2)
        stationsList = [] 
        for device in sender.devices:
            if device._type == "stations":
                stationsList.append(device)
        set_devices_default_values(stationsList)
        
    else:
        pass

def stop_all(client, msg, device):
    if not options.manual_mode:
        options.scheduler_enabled = False
        programs.run_now_program = None
        run_once.clear()
        log.finish_run(None)
        stations.clear()
        stationsList = []
        for device in sender.devices:
            if device._type == "stations":
                stationsList.append(device)
        set_devices_default_values(stationsList)


def discovery_payload(device):
    """ Compose HASS discovery payload """
    payload = {}
    
    if device._type == "stations":
        payload["device"] = {
        "identifiers": ["ospy_{}_s{}".format(system_UID(), device._id)],
        "manufacturer": "www.pihrt.com",
        "model": _('Station'),
        "name": device._name,
        "sw_version": system_version(),
        "serial_number": system_UID(),
        "configuration_url": system_web_url(),
        "via_device": "ospy_{}_{}".format(system_UID(), "station")
        }
    elif device._type == "sensor_THDS":
        payload["device"] = {
        "identifiers": ["ospy_{}_sensorTHDS{}".format(system_UID(), device._id)],
        "manufacturer": "www.pihrt.com",
        "model": _('THDS Sensor'),
        "name": device._name,
        "sw_version": system_version(),
        "serial_number": system_UID(),
        "configuration_url": system_web_url(),
        "via_device": "ospy_{}".format(system_UID())
        }
    elif device._type == "sensor_WTL":
        payload["device"] = {
        "identifiers": ["ospy_{}_sensor_WTL{}".format(system_UID(), device._id)],
        "manufacturer": "www.pihrt.com",
        "model": _('WTL Sensor'),
        "name": device._name,
        "sw_version": system_version(),
        "serial_number": system_UID(),
        "configuration_url": system_web_url(),
        "via_device": "ospy_{}".format(system_UID())
        }
    elif device._type == "programs":
        payload["device"] = {
        "identifiers": ["ospy_{}_p{}".format(system_UID(), device._id)],
        "manufacturer": "www.pihrt.com",
        "model": _('Program'),
        "name": device._name,
        "sw_version": system_version(),
        "serial_number": system_UID(),
        "configuration_url": system_web_url(),
        "via_device": "ospy_{}_{}".format(system_UID(), "program")
        }
    elif device._type == "program" or device._type == "station":
        payload["device"] = {
        "identifiers": ["ospy_{}_{}".format(system_UID(), device._type)],
        "manufacturer": "www.pihrt.com",
        "model": _('Component'),
        "name":  _('Programs') if device._type == "program"  else _('Stations') if device._type == "station" else _('Undefined'),
        "sw_version": system_version(),
        "serial_number": system_UID(),
        "configuration_url": system_web_url(),
        "via_device": "ospy_{}".format(system_UID())
        }
    else:
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
    if device._devicetype is not None:
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
        if device._type == "stations":     # stations
            payload["name"] = ""
        if device._type == "sensor_THDS":  # air temp humi plugin (6xDS18b20 and DHT11 or DHT22)
            payload["name"] = ""
        if device._type == "sensor_WTL":   # tank monitor plugin (ultrasonic or current loop 4-20mA)
            payload["name"] = ""
        if device._type == "programs":     # programs
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
            payload["command_topic"] = '{}/{}/{}/set'.format(plugin_options['mqtt_hass_topic'], device._type, device._property)
            payload["payload_off"] = "False"
            payload["payload_on"] = "True"
            subscribe(payload["command_topic"], device._callback, device)
        else:
            raise ValueError(_('Callback cannot be Null for device_class = switch'))
    elif device._deviceclass == "button":
        if device._callback is not None:
            payload["value_template"] = "{{ value_json.state }}"
            payload["command_topic"] = '{}/{}/{}/set'.format(plugin_options['mqtt_hass_topic'], device._type, device._property)
            payload["payload_press"] = device._type
            subscribe(payload["command_topic"], device._callback, device)
        else:
            raise ValueError(_('Callback cannot be Null for device_class = button'))
        

    return payload

def discovery_topic_get(component, name):
    """Return HASS Discovery topic for the entity"""
    return ('{}/{}/{}/{}/config'.format(plugin_options['mqtt_hass_discovery_topic_prefix'], component, system_UID(), name))

def compare_hass_devices(device1, device2):
    return (
        device1._deviceclass == device2._deviceclass and
        device1._devicetype == device2._devicetype and
        device1._type == device2._type and
        device1._property == device2._property)
    
def find_missing_elements(array1, array2):
    missing_devices = []
    try:
        for device2 in array2:
            found = False
            for device1 in array1:
                if compare_hass_devices(device1, device2):
                    found = True
                    break
            if not found:
                missing_devices.append(device2)
    except:
        log.error(NAME, _('Cannot find missing elements.'))
        pass

    return missing_devices

def discovery_publish():
    """Publish MQTT HASS Discovery config to HASS"""

    # https://www.home-assistant.io/integrations/mqtt/#configuration-via-mqtt-discovery sekce Configuration of MQTT components via MQTT discovery
    
    baseDevices = []
    sensorTHDSDevices = []
    sensorWTLDevices = []

    baseDevices.append(hass_device().createNumber("duration", "system", "rain_delay",  _('Rain delay'), "mdi:timer-cog-outline", "h", 0, 100, rain_delay_set)) #TODO add max value based on settings
    baseDevices.append(hass_device().createNumber(None, "system", "water_level",  _('Water level'), "mdi:car-coolant-level", "%", 0, 500, water_level_set))
    baseDevices.append(hass_device().createSwitch("switch", "system", "scheduler_enabled",  _('Scheduler'), "mdi:calendar", scheduler_enable_set))
    baseDevices.append(hass_device().createSwitch("switch", "system", "manual_mode",  _('Manual operation'), None, manual_mode_set))
    baseDevices.append(hass_device().createBinarySensor("moisture", "system", "rain_sensed",  _('Rain sensor'), None))

    #create subcategories
    baseDevices.append(hass_device().createButton(None, "station", "station",  _("Stop All Stations"), "mdi:sprinkler-variant", stop_all))
    baseDevices.append(hass_device().createButton(None, "program", "program",  _("Stop All Stations"), "mdi:timer-play-outline", stop_all))
    
    
    for i in range(0, options.output_count): # create stations
        device = hass_device().createSwitch(None, "stations", "station_{}".format(i),  stations.get(int(i)).name if plugin_options['hass_device_is_station_name'] else _("Station") + " {0:02d}".format(i + 1), "mdi:sprinkler-variant", station_set)
        device._id = i
        if stations.get(int(device._id)).enabled:
            baseDevices.append(device)
        else:
            remove_device(device)

    for program in programs.get():           # create programs
        device = hass_device().createButton(None, "programs", "program_{}".format(program.index),  _('Run') + ": {0:02d}".format(program.index + 1) + " " + program.name, "mdi:timer-play-outline", program_set)
        device._id = program.index
        baseDevices.append(device)

    try:
        if plugin_options['ext_water_sonic']:
            from plugins import tank_monitor
            if (tank_monitor.tank_options['use_sonic']):
                sensor_water_tank_percent = hass_device().createSensor("humidity", "sensor_WTL", "tank_percent", _('Tank level'), "mdi:waves-arrow-up", "%")
                sensor_water_tank_volume = hass_device().createSensor("humidity", "sensor_WTL", "tank_volume", _('Tank volume'), "mdi:waves-arrow-up", "m³")
                sensor_water_tank_percent._id = 400 # mqtt unique ID placeholder, 400 for water level percent, 401 for volume
                sensor_water_tank_volume._id = 401
                sensorWTLDevices.append(sensor_water_tank_percent)
                sensorWTLDevices.append(sensor_water_tank_volume)
                body = '<br><b>' + _('Tank monitor') + '</b><ul>'
                logtext = _('Tank monitor') + '-> \n'
                percent = tank_monitor.get_all_values()[1]
                volume = tank_monitor.get_all_values()[3]
                #cm = tank_monitor.get_all_values()[0]
                #ping = tank_monitor.get_all_values()[2]
                #units = tank_monitor.get_all_values()[4] 
                body += '<li>' + _('Percent {}%').format(percent) + '\n</li>'
                body += '<li>' + _('Volume {}m3').format(volume) + '\n</li>'  
                logtext += _('Percent {}%, volume {}m3').format(percent, volume)
                body += '</ul>'   
                log.info(NAME, logtext)
            else:
                sensor_water_tank_percent = hass_device().createSensor("moisture", "sensor_WTL", "tank_percent", _('Tank level'), "mdi:waves-arrow-up", "%")
                sensor_water_tank_volume = hass_device().createSensor("volume", "sensor_WTL", "tank_volume", _('Tank volume'), "mdi:waves-arrow-up", "m³")
                remove_device(sensor_water_tank_percent)
                remove_device(sensor_water_tank_volume)
            
    except ImportError:
        log.debug(NAME, _('Cannot import plugin: tank_monitor.'))
        pass

    try:
        from plugins import air_temp_humi
        #TODO remove from discovery topic when removed - create remove function. HASS dahsboard removes entity after refresh.
        if air_temp_humi.plugin_options['enabled']: #plugin enabled
            if air_temp_humi.plugin_options['enable_dht']: ##DHT enabled, add to discovery
                if plugin_options['ext_dht']:
                    dhtName = air_temp_humi.plugin_options['label']
                    sensorH = hass_device().createSensor( "humidity", "sensor_THDS", "HDT_humidity", dhtName + " " +  _('Humidity'), None, "%")
                    sensorH._isDHT = True
                    sensorH._isDS = False 
                    sensorH._id = 500 #mqtt unique ID placeholder, 500 for humidity, 501 for temperature
                    sensorT = hass_device().createSensor( "temperature", "sensor_THDS", "HDT_temperature", dhtName + " " + _('Temperature'), None, "°C")
                    sensorT._isDHT = True
                    sensorT._isDS = False
                    sensorT._id = 501
                    sensorTHDSDevices.append(sensorH)
                    sensorTHDSDevices.append(sensorT)
            
            if air_temp_humi.plugin_options['ds_enabled'] and air_temp_humi.plugin_options['ds_used'] > 0:
                if plugin_options['ext_ds1-6']:
                    for ds in range(0, air_temp_humi.plugin_options['ds_used']):
                        sensor = hass_device().createSensor( "temperature", "sensor_THDS", "DS_temperature{}".format(ds), air_temp_humi.plugin_options['label_ds%d' % ds] + " " + _('Temperature'), None, "℃")
                        sensor._isDS = True
                        sensor._isDHT = False
                        sensor._id = ds
                        sensorTHDSDevices.append(sensor)
                        
            if plugin_options['ext_ds1-6']:
                body = '<br><b>' + _('Temperature DS1-DS6') + '</b><ul>'
                logtext = _('Temperature DS1-DS6') + '-> \n'
                for i in range(0, air_temp_humi.plugin_options['ds_used']):
                    body += '<li>' + '%s' % air_temp_humi.plugin_options['label_ds%d' % i] + ': ' + '%.1f \u2103' % air_temp_humi.DS18B20_read_probe(i) + '\n</li>'  
                    logtext += '%s' % air_temp_humi.plugin_options['label_ds%d' % i] + ': ' + '%.1f \u2103\n' % air_temp_humi.DS18B20_read_probe(i) 
                body += '</ul>'   
                log.info(NAME, logtext) 

    except ImportError:
        log.debug(NAME, _('Cannot import plugin: air temp humi.'))
        pass

    try:
        if plugin_options['ext_water_current']:
            from plugins import current_loop_tanks_monitor
            tank_options = current_loop_tanks_monitor.plugin_options
            i = 0 # jsou 4 nadrze 0-3 TODO 
            if tank_options['en_tank{}'.format(i+1)]:
                label = current_loop_tanks_monitor.tanks['label'][i]
                percent = current_loop_tanks_monitor.tanks['levelPercent'][i]
                volume = current_loop_tanks_monitor.tanks['volumeLiter'][i]
                #level_cm = current_loop_tanks_monitor.tanks['levelCm'][i]
                #volt = current_loop_tanks_monitor.tanks['voltage'][i]
                sensor_water_tank_percent = hass_device().createSensor("humidity", "sensor_WTL", "tank_percent", '{} '.format(label), "mdi:waves-arrow-up", "%")
                sensor_water_tank_volume = hass_device().createSensor("humidity", "sensor_WTL", "tank_volume", '{} '.format(label), "mdi:waves-arrow-up", "m³")
                sensor_water_tank_percent._id = 410 # mqtt unique ID placeholder, 410 for water level percent, 411 for volume
                sensor_water_tank_volume._id = 411
                sensorWTLDevices.append(sensor_water_tank_percent)
                sensorWTLDevices.append(sensor_water_tank_volume)
                body = '<br><b>' + _('Tank monitor') + '</b><ul>'
                logtext = _('Tank monitor') + '-> \n'    
                body += '<li>' + ('{}').format(label) + '\n</li>'
                body += '<li>' + '{:.2f} %'.format(percent) + '\n</li>'
                body += '<li>' + '{:.2f} m3'.format(volume/1000) + '\n</li>'  
                logtext += _('{} {:.2f} %, {:.2f} m3').format(label, percent, volume/1000)
                body += '</ul>'   
                log.info(NAME, logtext)
            else:
                sensor_water_tank_percent = hass_device().createSensor("moisture", "sensor_WTL", "tank_percent", '{} '.format(label), "mdi:waves-arrow-up", "%")
                sensor_water_tank_volume = hass_device().createSensor("volume", "sensor_WTL", "tank_volume",'{} '.format(label), "mdi:waves-arrow-up", "m³")
                remove_device(sensor_water_tank_percent)
                remove_device(sensor_water_tank_volume)
            
    except ImportError:
        log.debug(NAME, _('Cannot import plugin: current_loop_tanks_monitor.'))
        pass 

    for component in baseDevices:
        payload = discovery_payload(component)
        topic = discovery_topic_get(component._deviceclass, component._property)
        if topic and payload:
            publish(topic, payload)
        set_devices_online(component)
        
    for sensor in sensorTHDSDevices:
        payload = discovery_payload(sensor)
        topic = discovery_topic_get(sensor._deviceclass, sensor._property)
        if topic and payload:
            publish(topic, payload)
        set_devices_online(sensor)
    
    if sender.sensors_temp_humi_ds is not None:
        missingDevices = find_missing_elements(sensorTHDSDevices, sender.sensors_temp_humi_ds)
        for device in missingDevices:
            remove_device(device)
            
    if sender.devices is not None:
        missingDevices = find_missing_elements(baseDevices, sender.devices)
        for device in missingDevices:
            remove_device(device)

    for sensor in sensorWTLDevices:
        payload = discovery_payload(sensor)
        topic = discovery_topic_get(sensor._deviceclass, sensor._property)
        if topic and payload:
            publish(topic, payload)
        set_devices_online(sensor)
  
    sender.devices = baseDevices
    sender.sensors_temp_humi_ds = sensorTHDSDevices
    sender.sensors_tanks = sensorWTLDevices
    
    set_devices_default_values(baseDevices)

    update_temp_humi_ds(sensorTHDSDevices)
    update_tank_level(sensorWTLDevices)
    
    set_devices_signal()


def set_devices_online(device): # set inital values to HASS after plugin start
    try:
        topic = '{}/{}/{}/availability'.format(plugin_options['mqtt_hass_topic'], device._type, device._property)
        if device._property == "scheduler_enabled" and options.manual_mode:
            publish(topic, "offline")
        elif device._property == "rain_sensed" and not options.rain_sensor_enabled:
            publish(topic, "offline")
        elif device._type == "stations" and not stations.get(int(device._id)).enabled:
            publish(topic, "offline")
        elif device._type == "sensor_THDS" and device._isDS: #error with DS sensor, set to offline
            try:
                if not device._isOK:
                    if plugin_options['ext_ds1-6']:
                        publish(topic, "offline")
                else:
                    if plugin_options['ext_ds1-6']:
                        publish(topic, "online")
            except AttributeError:
                pass
        elif device._type == "sensor_WTL":
            publish(topic, "online")
        elif device._type == "programs":
            publish(topic, "online")
        else:
            publish(topic, "online")
    except Exception as e:
        log.error(NAME, _('Cannot set devices online.') + '{}'.format(e))
        pass

def remove_device(device):
    try:
        topic = discovery_topic_get(device._deviceclass, device._property)
        removeTopic(topic)
    except:
        log.error(NAME, _('Cannot remove device.'))
        pass

def set_devices_default_values(devices):
    
    for device in devices:
        try:
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
                payload = str(stations.get(device._id).active)
            else:
                log.debug(NAME, _('Not visible device propertly was found') + ': {}'.format(device._property))
#TODO pryc                
                print(device._property)

            if topic and payload:
                publish(topic, payload)
        except:
            log.error(NAME, _('Cannot set devices default values.'))
            log.debug(NAME, _('Error') + ':\n' + traceback.format_exc())
            pass

def update_device_values(name, **kw):
    try:
        for device in sender.devices:
            set_devices_online(device)
        set_devices_default_values(sender.devices)
    except:
        log.error(NAME, _('Cannot update data from plugins.'))
        pass

def update_temp_humi_ds(sensors):
    for device in sensors:
        if device._type == "sensor_THDS":
            try:
                from plugins import air_temp_humi
                
                payload = {}
                topic = {}
                if device._isDHT is not None and device._isDHT and plugin_options['ext_dht']:
                    if device._property == "HDT_humidity":
                        topic = '{}/{}/{}/state'.format(plugin_options['mqtt_hass_topic'], device._type, device._property)
                        payload["state"] = air_temp_humi.sender.status['humi']
                    if device._property == "HDT_temperature":
                        topic = '{}/{}/{}/state'.format(plugin_options['mqtt_hass_topic'], device._type, device._property)
                        payload["state"] = air_temp_humi.sender.status['temp']
                    set_devices_online(device)
                if device._isDS is not None and device._isDS and plugin_options['ext_ds1-6']:                        
                    topic = '{}/{}/{}/state'.format(plugin_options['mqtt_hass_topic'], device._type, device._property)
                    payload["state"] = air_temp_humi.sender.status['DS{}'.format(device._id)]
                    device._isOK = False if payload["state"] == -127 else True
                    set_devices_online(device)
                if topic and payload:
                    publish(topic, payload)
            except ImportError:
                log.error(NAME, _('Cannot import plugin: air temp humi.'))
                pass

def update_tank_level(sensors):
    for device in sensors:
        if device._type == "sensor_WTL":
            if plugin_options['ext_water_sonic']:
                try:
                    from plugins import tank_monitor
                
                    payload = {}
                    topic = {}
                    if device._property == "tank_percent":
                        percent = tank_monitor.get_all_values()[1]
                        topic = '{}/{}/{}/state'.format(plugin_options['mqtt_hass_topic'], device._type, device._property)
                        payload["state"] = percent
                        set_devices_online(device)
                        if topic and payload:
                            publish(topic, payload)
                    if device._property == "tank_volume":
                        volume = tank_monitor.get_all_values()[3]
                        topic = '{}/{}/{}/state'.format(plugin_options['mqtt_hass_topic'], device._type, device._property)
                        payload["state"] = volume
                        set_devices_online(device)
                        if topic and payload:
                            publish(topic, payload)
                except ImportError:
                    log.error(NAME, _('Cannot import plugin: tank_monitor.'))
                    pass

            if plugin_options['ext_water_current']:
                try:
                    from plugins import current_loop_tanks_monitor
                
                    payload = {}
                    topic = {}
                    i = 0 # meri se 4 nadrze TODO
                    if device._property == "tank_percent":
                        percent = current_loop_tanks_monitor.tanks['levelPercent'][i]
                        topic = '{}/{}/{}/state'.format(plugin_options['mqtt_hass_topic'], device._type, device._property)
                        payload["state"] = '{:.2f}'.format(percent)
                        set_devices_online(device)
                        if topic and payload:
                            publish(topic, payload)
                    if device._property == "tank_volume":
                        volume = current_loop_tanks_monitor.tanks['volumeLiter'][i]
                        topic = '{}/{}/{}/state'.format(plugin_options['mqtt_hass_topic'], device._type, device._property)
                        payload["state"] = '{:.2f}'.format(volume/1000) 
                        set_devices_online(device)
                        if topic and payload:
                            publish(topic, payload)
                except ImportError:
                    log.error(NAME, _('Cannot import plugin: current_loop_tanks_monitor.'))
                    pass

def update_device_plugin_settings(name, **kw):
    discovery_publish()
    
def remove_hass_ospy():
    for device in sender.devices:
        remove_device(device)
        

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
    program_change.connect(update_device_plugin_settings)
    program_deleted = signal('program_deleted')
    program_deleted.connect(update_device_plugin_settings)
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
    hass_plugin_update.connect(update_device_plugin_settings) ## completely reinitialize on plugin settings change
    air_temp_humi_plugin_update = signal('air_temp_humi_plugin_update')
    air_temp_humi_plugin_update.connect(update_device_plugin_settings) ## completely reinitialize on temp plugin settings change
    


################################################################################
# Web pages:                                                                   #
################################################################################

class settings_page(ProtectedPage):
    """ Load an html page for entering adjustments. """

    def GET(self):
        try:
            global slugify_is_installed
            global mqtt_is_installed
            msg = ''
            if not slugify_is_installed:
                msg = _('Error: slugify not installed. Install it to system. sudo apt install python3 slugify.')
            elif not mqtt_is_installed:
                msg += ' ' + _('Error: paho-mqtt is not installed. Install it to system. sudo pip3 install paho-mqtt.')
            else:
                msg = ''
            return self.plugin_render.mqtt_home_assistant(plugin_options, log.events(NAME), msg, is_connected())
        except:
            log.error(NAME, _('MQTT Home Assistant plug-in') + ':\n' + traceback.format_exc())
            msg = _('An internal error was found in the system, see the error log for more information. The error is in part:') + ' '
            msg += _('mqtt_home_assistant -> settings_page GET')
            return self.core_render.notice('/', msg, is_connected())

    def POST(self):
        try:
            plugin_options.web_update(web.input())
            updateSignal = signal('hass_plugin_update')
            updateSignal.send()
            raise web.seeother(plugin_url(settings_page), True)
        except:
            log.error(NAME, _('MQTT plug-in') + ':\n' + traceback.format_exc())
            msg = _('An internal error was found in the system, see the error log for more information. The error is in part:') + ' '
            msg += _('mqtt_home_assistant -> settings_page POST')
            return self.core_render.notice('/', msg, is_connected())


class help_page(ProtectedPage):
    """ Load an html page for help """

    def GET(self):
        try:
            return self.plugin_render.mqtt_home_assistant_help()
        except:
            log.error(NAME, _('MQTT plug-in') + ':\n' + traceback.format_exc())
            msg = _('An internal error was found in the system, see the error log for more information. The error is in part:') + ' '
            msg += _('mqtt_home_assistant -> help_page GET')
            return self.core_render.notice('/', msg)


class settings_json(ProtectedPage):
    """ Returns plugin settings in JSON format """

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        try:
            return json.dumps(plugin_options)
        except:
            return {}