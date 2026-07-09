# !/usr/bin/env python
# -*- coding: utf-8 -*-

__author__ = 'Martin Pihrt'

import web                                                       # Framework web.py
import json                                                      # For working with json file
import copy                                                      # For working with copy of source registry
import traceback                                                 # For Errors listing via callback where the event occurred
import time                                                      # For working with time, see the def _sleep function
from threading import Thread, Event                              # For use a separate thread in which the plugin is running

from plugins import PluginOptions, plugin_url, plugin_data_dir   # For access to settings, address and plugin data folder
from ospy.log import log                                         # For events logs printing (debug, error, info)
from ospy.helpers import datetime_string, verify_csrf            # For using date time in events logs
from ospy.webpages import ProtectedPage                          # For check user login permissions
from ospy.sensors import sensors

SHELLY_VALUE_TYPES = [
    'temperature',
    'temperature_2',
    'temperature_3',
    'temperature_4',
    'temperature_5',
    'humidity',
    'humidity_2',
    'illuminance',
    'illuminance_2',
    'output',
    'output_2',
    'output_3',
    'output_4',
    'power',
    'power_2',
    'power_3',
    'power_4',
    'retpower',
    'retpower_2',
    'retpower_3',
    'voltage',
    'battery',
    'rssi',
    'online'
]

################################################################################
# Plugin name, translated name, link for web page in init, plugin options      #
################################################################################
NAME = 'Weather Dashboard'                                       # The unique name of the plugin listed in the plugin manager
MENU =  _('Package: Weather Dashboard')                          # The name of the plugin that will be visible in the running plugins tab and will be translated
LINK = 'canvas_page'                                             # The default webpage when loading the plugin will be the settings page class

plugin_options = PluginOptions(
    NAME,
    {
        'dashboard_mode': 'canvas',
        'canvas_size_xy': 250,
        'txt_size_font': 40,

        'gauges': []
    }
)


SOURCE_REGISTRY = {
    'air_temp': {
        'title': 'Air Temperature',
        'channels': 6,
        'channel_names': [
            'DS18B20 #1',
            'DS18B20 #2',
            'DS18B20 #3',
            'DS18B20 #4',
            'DS18B20 #5',
            'DS18B20 #6'
        ],
        'types': ['temperature']
    },

    'tank_monitor': {
        'title': 'Tank Monitor',
        'channels': 2,
        'channel_names': [
            'Percent',
            'Volume'
        ],
        'types': ['percent', 'volume']
    },

    'current_loop': {
        'title': 'Current Loop',
        'channels': 4,
        'channel_names': [
            'Tank 1',
            'Tank 2',
            'Tank 3',
            'Tank 4'
        ],
        'types': [
            'percent',
            'cm',
            'liter',
            'voltage'
        ]
    },

    'wind_monitor': {
        'title': 'Wind Monitor',
        'channels': 1,
        'channel_names': [
            'Wind Speed'
        ],
        'types': ['speed']
    },

    'ospy_sensor': {
        'title': 'OSPy Sensor',
        'channels': -1,
        'channel_names': [],
        'types': ['auto']
    },

    'shelly_cloud': {
        'title': 'Shelly Cloud',
        'channels': -1,
        'channel_names': [],
        'types': SHELLY_VALUE_TYPES
    }
}

################################################################################
# Main function loop:                                                          #
################################################################################
class Sender(Thread):
    def __init__(self):
        Thread.__init__(self)
        self.daemon = True
        self._stop_event = Event()

        self.status = {}

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
        log.clear(NAME)
        log.info(NAME, _('Weather Dashboard plug-in is enabled.'))

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
        sender.join(15)
        sender = None


def default_gauge():
    return {
        'enabled': True,
        'name': 'Gauge',
        'unit': '',
        'source': 'current_loop',
        'channel': 0,
        'value_type': 'percent',
        'tick': '0,25,50,75,100',
        'min': '0',
        'max': '100',
        'red_from': 0,
        'red_to': 20,
        'blue_from': 20,
        'blue_to': 60,
        'green_from': 60,
        'green_to': 100
    }

def safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def normalize_gauge(gauge):
    data = default_gauge()
    if isinstance(gauge, dict):
        data.update(gauge)
    data['enabled'] = bool(data.get('enabled', True))
    data['name'] = str(data.get('name') or _('Gauge'))[:80]
    data['unit'] = str(data.get('unit') or '')[:20]
    if data['source'] not in SOURCE_REGISTRY:
        data['source'] = 'current_loop'
    data['channel'] = max(0, safe_int(data.get('channel'), 0))
    if data['value_type'] not in SOURCE_REGISTRY[data['source']]['types'] and data['value_type'] not in SHELLY_VALUE_TYPES:
        data['value_type'] = SOURCE_REGISTRY[data['source']]['types'][0]
    data['canvas_size_xy'] = max(120, min(800, safe_int(plugin_options.get('canvas_size_xy', 250), 250)))
    for key in ('red_from', 'red_to', 'blue_from', 'blue_to', 'green_from', 'green_to'):
        data[key] = safe_int(data.get(key), safe_int(default_gauge().get(key), 0))
    data['tick'] = str(data.get('tick') or '0,25,50,75,100')[:120]
    data['min'] = str(data.get('min') or '0')[:20]
    data['max'] = str(data.get('max') or '100')[:20]
    return data


def normalize_options():
    plugin_options['dashboard_mode'] = plugin_options.get('dashboard_mode') if plugin_options.get('dashboard_mode') in ('canvas', 'text') else 'canvas'
    plugin_options['canvas_size_xy'] = max(120, min(800, safe_int(plugin_options.get('canvas_size_xy', 250), 250)))
    plugin_options['txt_size_font'] = max(10, min(120, safe_int(plugin_options.get('txt_size_font', 40), 40)))
    gauges = plugin_options.get('gauges', [])
    if not isinstance(gauges, list) or not gauges:
        gauges = [default_gauge()]
    plugin_options['gauges'] = [normalize_gauge(gauge) for gauge in gauges[:32]]


normalize_options()

def get_value(source, channel, value_type):
    if source == 'current_loop':
        try:
            from plugins import current_loop_tanks_monitor
            mapping = {
                'percent': 'levelPercent',
                'cm': 'levelCm',
                'liter': 'volumeLiter',
                'voltage': 'voltage'
            }
            value = current_loop_tanks_monitor.tanks[mapping[value_type]][channel]
            if value_type == 'liter':
                return int(round(value))
            return value
        except:
            return -127

    if source == 'tank_monitor':
        try:
            from plugins import tank_monitor
            values = tank_monitor.get_all_values()
            if value_type == 'percent':
                return values[1]
            if value_type == 'volume':
                return values[3]
        except:
            return -127

    if source == 'air_temp':
        try:
            from plugins import air_temp_humi
            return air_temp_humi.DS18B20_read_probe(channel)
        except:
            return -127

    if source == 'wind_monitor':
        try:
            from plugins import wind_monitor
            return round(wind_monitor.get_all_values()[0],2)
        except:
            return -127

    if source == 'ospy_sensor':
        try:
            sensor = sensors.get(channel)
            if sensor.sens_type == 5:
                return sensor.last_read_value[0]
            elif sensor.sens_type == 1:
                return sensor.last_read_value[4]
            elif sensor.sens_type == 2:
                return sensor.last_read_value[5]
            elif sensor.sens_type == 3:
                return sensor.last_read_value[6]
            elif sensor.sens_type == 4:
                return sensor.last_read_value[7]
            elif sensor.sens_type == 6:
                if sensor.multi_type >= 0 and sensor.multi_type < 4:
                    return sensor.last_read_value[sensor.multi_type]
                elif sensor.multi_type == 4:
                    return sensor.last_read_value[4]
                elif sensor.multi_type == 5:
                    return sensor.last_read_value[5]
                elif sensor.multi_type == 6:
                    return sensor.last_read_value[6]
                elif sensor.multi_type == 7:
                    return sensor.last_read_value[7]
                elif sensor.multi_type == 8:
                    return sensor.last_read_value[8]
            return -127
        except:
            return -127

    if source == 'shelly_cloud':
        try:
            devices = get_shelly_devices()
            device = devices[channel]
            return get_shelly_value(device, value_type)
        except:
            return -127

    return -127


def save_gauges(gauges):
    plugin_options['gauges'] = gauges
    if sender:
        sender.update()

def get_sensor_names():
    names = []
    try:
        for s in sensors.get():
            names.append(s.name)
    except:
        pass
    return names


def get_shelly_devices():
    try:
        from plugins import shelly_cloud_integrator
        return shelly_cloud_integrator.shelly_devices.devices()
    except:
        return []


def get_shelly_device_names():
    names = []
    try:
        for device in get_shelly_devices():
            label = device.get('label', '')
            hardware = device.get('hw', '')
            if label and hardware:
                names.append('{} ({})'.format(label, hardware))
            elif label:
                names.append(label)
            elif hardware:
                names.append(hardware)
            else:
                names.append(device.get('id', _('Shelly device')))
    except:
        pass
    return names


def get_shelly_value(device, value_type):
    if value_type == 'online':
        return 1 if device.get('online', False) else 0

    list_mapping = {
        'temperature': ('temperature', 0),
        'temperature_2': ('temperature', 1),
        'temperature_3': ('temperature', 2),
        'temperature_4': ('temperature', 3),
        'temperature_5': ('temperature', 4),
        'humidity': ('humidity', 0),
        'humidity_2': ('humidity', 1),
        'illuminance': ('illuminance', 0),
        'illuminance_2': ('illuminance', 1),
        'output': ('output', 0),
        'output_2': ('output', 1),
        'output_3': ('output', 2),
        'output_4': ('output', 3),
        'power': ('power', 0),
        'power_2': ('power', 1),
        'power_3': ('power', 2),
        'power_4': ('power', 3),
        'retpower': ('retpower', 0),
        'retpower_2': ('retpower', 1),
        'retpower_3': ('retpower', 2)
    }

    if value_type in list_mapping:
        key, idx = list_mapping[value_type]
        value = device.get(key, [])
        if idx < len(value):
            if isinstance(value[idx], bool):
                return 1 if value[idx] else 0
            return value[idx]
        return -127

    if value_type in ('voltage', 'battery', 'rssi'):
        value = device.get(value_type, -127)
        if isinstance(value, bool):
            return 1 if value else 0
        return value

    return -127

################################################################################
# Web pages:                                                                   #
################################################################################

class canvas_page(ProtectedPage):
    """Load an html page for canvas wieving."""
    def GET(self):
        normalize_options()
        return self.plugin_render.weather_dashboard_canvas_page(plugin_options)

class settings_page(ProtectedPage):
    def GET(self):
        normalize_options()
        return self.plugin_render.weather_dashboard_page(
            plugin_options,
            log.events(NAME),
            SOURCE_REGISTRY,
            sorted(SOURCE_REGISTRY.keys())
        )

    def POST(self):
        qdict = web.input()
        verify_csrf(qdict)
        gauges = []
        count = max(0, min(32, safe_int(qdict.get('gauge_count'), 0)))
        plugin_options['dashboard_mode'] = qdict.get('dashboard_mode', 'canvas')
        plugin_options['canvas_size_xy'] = safe_int(qdict.get('canvas_size_xy'), 250)
        plugin_options['txt_size_font'] = safe_int(qdict.get('txt_size_font'), 40)
        for i in range(count):
            gauges.append(normalize_gauge({
                'enabled': ('enabled{}'.format(i) in qdict),
                'name': qdict.get('name{}'.format(i), ''),
                'unit': qdict.get('unit{}'.format(i), ''),
                'source': qdict.get('source{}'.format(i), 'current_loop'),
                'channel': safe_int(qdict.get('channel{}'.format(i)), 0),
                'value_type': qdict.get('value_type{}'.format(i), 'percent'),
                'tick': qdict.get('tick{}'.format(i), '0,25,50,75,100'),
                'min': qdict.get('min{}'.format(i), '0'),
                'max': qdict.get('max{}'.format(i), '100'),
                'red_from': safe_int(qdict.get('red_from{}'.format(i)), 0),
                'red_to': safe_int(qdict.get('red_to{}'.format(i)), 20),
                'blue_from': safe_int(qdict.get('blue_from{}'.format(i)), 20),
                'blue_to': safe_int(qdict.get('blue_to{}'.format(i)), 60),
                'green_from': safe_int(qdict.get('green_from{}'.format(i)), 60),
                'green_to': safe_int(qdict.get('green_to{}'.format(i)), 100)
            }))
        save_gauges(gauges)
        normalize_options()
        raise web.seeother(plugin_url(settings_page), True)

class help_page(ProtectedPage):
    """Load an html page for help"""

    def GET(self):
        return self.plugin_render.weather_dashboard_help_page()


class settings_json(ProtectedPage):
    """Returns plugin settings in JSON format."""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        return json.dumps(plugin_options)


class sources_json(ProtectedPage):

    def GET(self):

        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')

        registry = copy.deepcopy(SOURCE_REGISTRY)
        registry['ospy_sensor']['channel_names'] = get_sensor_names()
        registry['shelly_cloud']['channel_names'] = get_shelly_device_names()
        return json.dumps(registry)


class add_gauge(ProtectedPage):
 
    def GET(self):
        verify_csrf()
        gauges = plugin_options['gauges']
        gauges.append(default_gauge())
        save_gauges(gauges)
        normalize_options()
        raise web.seeother(plugin_url(settings_page),True)


class delete_gauge(ProtectedPage):

    def GET(self):
        qdict = web.input()
        verify_csrf(qdict)
        try:
            idx = int(qdict.get('id', -1))
        except:
            idx = -1
        gauges = plugin_options['gauges']
        if idx >= 0 and idx < len(gauges):
            del gauges[idx]
        save_gauges(gauges)
        normalize_options()
        raise web.seeother(plugin_url(settings_page),True)


class data_json(ProtectedPage):

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')

        data = []
        normalize_options()
        for idx, gauge in enumerate(plugin_options['gauges']):

            if not gauge['enabled']:
                continue

            try:
                value = get_value(
                    gauge['source'],
                    gauge['channel'],
                    gauge['value_type']
                )

            except:
                value = -127

            data.append({
                'id': idx,
                'name': gauge['name'],
                'value': value,
                'unit': gauge['unit'],
                'timestamp': int(time.time())
            })

        return json.dumps(data)
