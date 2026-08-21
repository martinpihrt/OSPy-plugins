# !/usr/bin/env python3
# -*- coding: utf-8 -*-

__author__ = 'Martin Pihrt'

import web                                                       # Framework web.py
import json                                                      # For working with json file
import traceback                                                 # For Errors listing via callback where the event occurred
import time                                                      # For working with time, see the def _sleep function
import uuid
from threading import Thread, Lock                              # For use a separate thread in which the plugin is running

from plugins import PluginOptions, plugin_url, plugin_data_dir, get_runtime
from ospy.log import log                                         # For events logs printing (debug, error, info)
from ospy.helpers import datetime_string, now, get_input, verify_csrf # For using date time in events logs
from ospy.options import options
from ospy.webpages import ProtectedPage                          # For check user login permissions

from ospy.webpages import showInFooter                           # Enable plugin to display readings in UI footer

from requests import Session, exceptions
from json.decoder import JSONDecodeError

import datetime

from .three_phase_meter import parse_three_phase_meter
from .device_config import default_device, delete_device, normalize_devices, serialize_devices, upsert_device


################################################################################
# Plugin name, translated name, link for web page in init, plugin options      #
################################################################################
NAME = 'Shelly Cloud Integration'                                # The unique name of the plugin listed in the plugin manager
MENU =  _('Package: Shelly Cloud Integration')                   # The name of the plugin that will be visible in the running plugins tab and will be translated
LINK = 'status_page'                                             # The default webpage when loading the plugin

plugin_options = PluginOptions(
    NAME,
    {
        'use_footer': True,                                      # Show data from plugin in footer on home page
        'auth_key': '',                                          # Account verification key
        'server_uri': 'shelly-59-eu.shelly.cloud',               # The server URL where all the devices and client accounts are located. This can be obtained from Shelly > User Settings > Cloud Authorization Key
        'request_interval': 5,                                   # The refresh interval for request from Shelly server
        'use_sensor': [],                                        # Enable or disable Shelly in OSPy system
        'sensor_label': [],                                      # User-facing Shelly device name
        'sensor_id': [],                                         # Shelly device ID
        'sensor_type': [],
         # 0=Shelly Plus HT, 1=Shelly Plus Plug S,
         # 2=Shelly Pro 2PM, 3=Shelly 1PM Mini,
         # 4=Shelly 2.5, 5=Shelly Pro 4PM,
         # 6=Shelly 1 Mini, 7=Shelly 2PM Addon,
         # 8=Shelly 1PM Addon, 9= Shelly H&T
         # 10=Shelly Pro 3EM
         # 11=Shelly Wall Display 
        'gen_type': [],                                          # 0=Gen1, 1=Gen2
        'number_sensors': 0,
        'device_uid': [],                                        # Stable UI identity independent of list position
        'device_view': 'cards',                                  # cards or list
        'addons_labels_1': [],                                   # label for addons temperature:100 (DS18B20 nr1)
        'addons_labels_2': [],                                   # label for addons temperature:101
        'addons_labels_3': [],                                   # label for addons temperature:102
        'addons_labels_4': [],                                   # label for addons temperature:103
        'addons_labels_5': [],                                   # label for addons temperature:104 (DS18B20 nr5)
        'reading_type': [],                                      # 0=Locally via IP, 1=Shelly cloud API
        'sensor_ip': [],
    }
)
runtime = get_runtime()
health_lock = Lock()
health_state = {
    'last_cycle': 0,
    'last_success': 0,
    'last_error': 0,
    'last_error_message': '',
}

################################################################################
# Main function loop:                                                          #
################################################################################
class Sender(Thread):
    def __init__(self):
        Thread.__init__(self)
        self.daemon = True
        self._stop_event = runtime.stop_event
        self.devices = []
        self._sleep_time = 0
        self._session = Session()
        self._next_request_time = {}
        self._request_failures = {}
        self._last_msg_info = None
        self._last_msg_log = 0
        self.start()
        runtime.register_thread(self)

    def stop(self):
        self._stop_event.set()

    def update(self):
        self._sleep_time = 0

    def _sleep(self, secs):
        self._sleep_time = secs
        while self._sleep_time > 0 and not self._stop_event.is_set():
            time.sleep(1)
            self._sleep_time -= 1

    def _backoff_remaining(self, key):
        return max(0, self._next_request_time.get(key, 0) - time.time())

    def _mark_request_success(self, key):
        self._next_request_time.pop(key, None)
        self._request_failures.pop(key, None)
        with health_lock:
            health_state['last_success'] = time.time()
            health_state['last_error_message'] = ''

    def _mark_request_failure(self, key, base_delay=60):
        failures = self._request_failures.get(key, 0) + 1
        self._request_failures[key] = failures
        delay = min(600, base_delay * (2 ** (failures - 1)))
        self._next_request_time[key] = time.time() + delay
        with health_lock:
            health_state['last_error'] = time.time()
            health_state['last_error_message'] = _('Request failed for a configured Shelly device.')

    def _write_status(self, msg_info):
        now_time = time.time()
        if msg_info and (msg_info != self._last_msg_info or now_time - self._last_msg_log >= 60):
            log.clear(NAME)
            log.info(NAME, datetime_string() + '\n{}'.format(msg_info))
            self._last_msg_info = msg_info
            self._last_msg_log = now_time

    def run(self):
        # Exmple data in footer
        in_footer = None
        if plugin_options['use_footer']:
            in_footer = showInFooter()                            # Instantiate class to enable data in footer
            in_footer.button = 'shelly_cloud_integrator/status'   # Button redirect on footer
            in_footer.label =  _('Shelly Cloud Integration')      # Label on footer
        
        log.clear(NAME)                                           # Clear events window on webpage
        log.info(NAME, _('Plugin is started.'))                   # Save to log (to OSPy log if logging is enabled) and events window on webpage

        while not self._stop_event.is_set():                      # Plugin repeating loop
            try:                                                  # It is a good idea to use try and except because it is possible to debug any errors encountered in the plugin.
                msg = ''
                msg_info = ''
                if len(plugin_options['auth_key']) > 5 and len(plugin_options['server_uri']) > 5:
                    for i in range(0, plugin_options['number_sensors']):
                        id = plugin_options['sensor_id'][i]
                        if len(id) > 5 and plugin_options['use_sensor'][i]:
                            if self._backoff_remaining(id) > 0:
                                continue
                            self._sleep(2)                                  # client has sent too many requests in a given amount of time. 2 second is optimal waiting.
                            if plugin_options['reading_type'][i] == 1:      # 0=Locally via IP, 1=Shelly cloud API
                                url = 'https://{}/device/status?auth_key={}&id={}'.format(plugin_options['server_uri'], plugin_options['auth_key'], id)
                            else:
                                if plugin_options['gen_type'][i] == 0:      # gen1 device. url=http://IP/status
                                    url = 'http://{}/status'.format(plugin_options['sensor_ip'][i])
                                else:                                       # gen2+ device. url=http://IP/rpc/Shelly.GetStatus
                                    url = 'http://{}/rpc/Shelly.GetStatus'.format(plugin_options['sensor_ip'][i])
                            response = None
                            try:
                                response = self._session.get(url, timeout=5)
                                if response.status_code == 401:
                                    if plugin_options['reading_type'][i] == 1:
                                        log.error(NAME, _('Shelly Cloud Bad Login'))
                                    else:
                                        log.error(NAME, _('Locally Bad Login to device'))
                                    self._mark_request_failure(id, 300)
                                    msg += _('[{}: ERROR] ').format(plugin_options['sensor_label'][i])
                                    msg_info += _('{}: Error: HTTP 401\n').format(plugin_options['sensor_label'][i])
                                    continue
                                elif response.status_code == 404:
                                    if plugin_options['reading_type'][i] == 1:
                                        log.error(NAME, _('Shelly Cloud Not Found'))
                                    else:
                                        log.error(NAME, _('Device Not Found'))
                                    self._mark_request_failure(id, 300)
                                    msg += _('[{}: ERROR] ').format(plugin_options['sensor_label'][i])
                                    msg_info += _('{}: Error: HTTP 404\n').format(plugin_options['sensor_label'][i])
                                    continue
                                elif response.status_code == 429:
                                    if plugin_options['reading_type'][i] == 1:
                                        log.error(NAME, _('Shelly Cloud Too Many Requests'))
                                    else:
                                        log.error(NAME, _('Device Not Found'))
                                    self._mark_request_failure(id, 120)
                                    msg += _('[{}: ERROR] ').format(plugin_options['sensor_label'][i])
                                    msg_info += _('{}: Error: HTTP 429\n').format(plugin_options['sensor_label'][i])
                                    continue
                                elif response.status_code == 200:
                                    if plugin_options['reading_type'][i] == 0:
                                        log.debug(NAME, _('Device Response'))
                                else:
                                    log.debug(NAME, _('Response from Shelly cloud: {}'.format(response.status_code)))
                                    self._mark_request_failure(id, 60)
                                    msg += _('[{}: ERROR] ').format(plugin_options['sensor_label'][i])
                                    msg_info += _('{}: Error: HTTP {}\n').format(plugin_options['sensor_label'][i], response.status_code)
                                    continue

                                try:
                                    response_data = response.json()
                                    self._mark_request_success(id)
                                    # typ: 0 = Shelly Plus HT, 
                                    # gen: 0 = GEN1, 1 = GEN 2+
                                    if plugin_options['sensor_type'][i] == 0:
                                        if plugin_options['gen_type'][i] == 0:
                                            name = plugin_options['sensor_label'][i]
                                            msg_info += _('{}: GEN1 not available \n').format(name)
                                        if plugin_options['gen_type'][i] == 1:
                                            name = plugin_options['sensor_label'][i]
                                            try:
                                                isok = response_data["isok"]
                                            except:
                                                isok = False
                                                log.error(NAME, _('Shelly Cloud Integration plugin') + ':\n' + traceback.format_exc())
                                            err = ""
                                            if not isok:
                                                try:
                                                    errors = response_data["errors"]["device_not_found"]
                                                    err = _('Your device has not been connected to the cloud!')
                                                except:
                                                    err = _('Unknown')
                                                    pass
                                                msg += _('[{}: Error] ').format(name)
                                                msg_info += _('{}: Error: {}\n').format(name, err)
                                            else:
                                                temperature = response_data["data"]["device_status"]["temperature:0"]["tC"]
                                                humidity = response_data["data"]["device_status"]["humidity:0"]["rh"]
                                                updated = now()
                                                battery = response_data["data"]["device_status"]["devicepower:0"]["battery"]
                                                online = response_data["data"]["online"]
                                                wifi = response_data["data"]["device_status"]["wifi"]
                                                sta_ip = wifi["sta_ip"]
                                                rssi = wifi["rssi"]
                                                batt_V = battery["V"]
                                                batt_perc = battery["percent"]
                                                if online:
                                                    msg += _('[{}: {} °C {} RV] ').format(name, temperature, humidity, batt_perc)
                                                    msg_info += _('{}: {} °C {} RV BAT{} % IP:{} RSSI:{} dbm {}\n').format(name, temperature, humidity, batt_perc, sta_ip, rssi, format_timestamp(updated))
                                                else:
                                                    msg += _('[{}: -] ').format(name)
                                                    msg_info += _('{}: OFFLINE\n').format(name)
                                            
                                                payload = {
                                                    'id': id,
                                                    'ip': sta_ip,
                                                    'voltage': batt_V,
                                                    'battery': batt_perc,
                                                    'temperature': [temperature],
                                                    'humidity': [humidity],
                                                    'illuminance': [],                                                    
                                                    'rssi': rssi,
                                                    'output': [],
                                                    'power': [],
                                                    'retpower': [],
                                                    'label': name,
                                                    'online': online,
                                                    'updated': updated,
                                                    'gen': _('GEN1') if plugin_options['gen_type'][i]==0 else _('GEN2+'),
                                                    'hw': _('Shelly Plus HT'),
                                                    'hw_nbr': plugin_options['sensor_type'][i]
                                                }
                                                update_or_add_device(self, payload)

                                    # typ: 1=Shelly Plus Plug S ver 1
                                    # gen: 0 = GEN1, 1 = GEN 2+
                                    if plugin_options['sensor_type'][i] == 1:
                                        if plugin_options['gen_type'][i] == 0:              # GEN 1 device
                                            name = plugin_options['sensor_label'][i]
                                            if plugin_options['reading_type'][i] == 1:      # only cloud API data
                                                isok = response_data["isok"]
                                            else:
                                                isok = True
                                            err = ""
                                            if not isok:
                                                errors = response_data["errors"]
                                                try:
                                                    test = errors["device_not_found"]
                                                    err = _('Your device has not been connected to the cloud!')
                                                except:
                                                    err = _('Unknown')
                                                    pass
                                                msg += _('[{}: Error] ').format(name)
                                                msg_info += _('{}: Error: {}\n').format(name, err)
                                            else:
                                                if plugin_options['reading_type'][i] == 1:  # only cloud API data
                                                    updated = now()
                                                    online = response_data["data"]["online"]
                                                    wifi = response_data["data"]["device_status"]["wifi_sta"]
                                                    sta_ip = wifi["ip"]
                                                    rssi = wifi["rssi"]
                                                    power = response_data["data"]["device_status"]["meters"][0]["power"]
                                                    total = response_data["data"]["device_status"]["meters"][0]["total"]
                                                    output = response_data["data"]["device_status"]["relays"][0]["ison"]
                                                else:                                       # via local IP data
                                                    updated = now()
                                                    online = True
                                                    wifi = response_data["wifi_sta"]
                                                    sta_ip = wifi["ip"]
                                                    rssi = wifi["rssi"]
                                                    power = response_data["meters"][0]["power"]
                                                    total = response_data["meters"][0]["total"]
                                                    output = response_data["relays"][0]["ison"]
                                                if online:
                                                    if output:
                                                        msg += _('[{}: ON {} W] ').format(name, power)
                                                        msg_info += _('{}: ON {} W IP:{} RSSI:{} dbm {}\n').format(name, power, sta_ip, rssi, format_timestamp(updated))
                                                    else:
                                                        msg += _('[{}: OFF {} W] ').format(name, power)
                                                        msg_info += _('{}: OFF {} W IP:{} RSSI:{} dbm {}\n').format(name, power, sta_ip, rssi, format_timestamp(updated))
                                                else:
                                                    msg += _('[{}: -] ').format(name)
                                                    msg_info += _('{}: OFFLINE\n').format(name)
                                                payload = {
                                                    'id': id,
                                                    'ip': sta_ip,
                                                    'voltage': 0,
                                                    'battery': 0,
                                                    'temperature': [],
                                                    'humidity': [],
                                                    'illuminance': [],                                                    
                                                    'rssi': rssi,
                                                    'output': [output],
                                                    'power': [power],
                                                    'retpower': [],
                                                    'label': name,
                                                    'online': online,
                                                    'updated': updated,
                                                    'gen': _('GEN1') if plugin_options['gen_type'][i]==0 else _('GEN2+'),
                                                    'hw': _('Shelly Plus Plug S'),
                                                    'hw_nbr': plugin_options['sensor_type'][i]
                                                }
                                                update_or_add_device(self, payload)
                                        if plugin_options['gen_type'][i] == 1:          # GEN 2+ device
                                            name = plugin_options['sensor_label'][i]
                                            if plugin_options['reading_type'][i] == 1:  # only cloud API data
                                                isok = response_data["isok"]
                                            else:
                                                isok = True
                                            err = ""
                                            if not isok:
                                                errors = response_data["errors"]
                                                try:
                                                    test = errors["device_not_found"]
                                                    err = _('Your device has not been connected to the cloud!')
                                                except:
                                                    err = _('Unknown')
                                                    pass
                                                msg += _('[{}: Error] ').format(name)
                                                msg_info += _('{}: Error: {}\n').format(name, err)
                                            else:
                                                if plugin_options['reading_type'][i] == 1:  # only cloud API data
                                                    updated = now()
                                                    online = response_data["data"]["online"]
                                                    wifi = response_data["data"]["device_status"]["wifi"]
                                                    sta_ip = wifi["sta_ip"]
                                                    rssi = wifi["rssi"]
                                                    power = response_data["data"]["device_status"]["switch:0"]["apower"]
                                                    total = response_data["data"]["device_status"]["switch:0"]["aenergy"]["total"]
                                                    output = response_data["data"]["device_status"]["switch:0"]["output"]
                                                    voltage = response_data["data"]["device_status"]["switch:0"]["voltage"]
                                                else:                                       # via local IP data
                                                    updated = now()
                                                    online = True
                                                    wifi = response_data["wifi"]
                                                    sta_ip = wifi["sta_ip"]
                                                    rssi = wifi["rssi"]
                                                    power = response_data["switch:0"]["apower"]
                                                    total = response_data["switch:0"]["aenergy"]["total"]
                                                    output = response_data["switch:0"]["output"]
                                                    voltage = response_data["switch:0"]["voltage"]
                                                if online:
                                                    if output:
                                                        msg += _('[{}: ON {} W ({} kW/h)] ').format(name, power, round(total/1000.0, 2))
                                                        msg_info += _('{}: ON {} W ({} kW/h) {} V IP:{} RSSI:{} dbm {}\n').format(name, power, round(total/1000.0, 2), voltage, sta_ip, rssi, format_timestamp(updated))
                                                    else:
                                                        msg += _('[{}: OFF {} W ({} kW/h)] ').format(name, power, round(total/1000.0, 2))
                                                        msg_info += _('{}: OFF {} W ({} kW/h) {} V IP:{} RSSI:{} dbm {}\n').format(name, power, round(total/1000.0, 2), voltage, sta_ip, rssi, format_timestamp(updated))
                                                else:
                                                    msg += _('[{}: -] ').format(name)
                                                    msg_info += _('{}: OFFLINE\n').format(name)
                                                payload = {
                                                    'id': id,
                                                    'ip': sta_ip,
                                                    'voltage': voltage,
                                                    'battery': 0,
                                                    'temperature': [],
                                                    'humidity': [],
                                                    'illuminance': [],                                                    
                                                    'rssi': rssi,
                                                    'output': [output],
                                                    'power': [power],
                                                    'retpower': [],
                                                    'label': name,
                                                    'online': online,
                                                    'updated': updated,
                                                    'gen': _('GEN1') if plugin_options['gen_type'][i]==0 else _('GEN2+'),
                                                    'hw': _('Shelly Plus Plug S'),
                                                    'hw_nbr': plugin_options['sensor_type'][i]
                                                }
                                                update_or_add_device(self, payload)

                                    # typ: 2=Shelly Pro 2PM
                                    # gen: 0 = GEN1, 1 = GEN 2+
                                    if plugin_options['sensor_type'][i] == 2:
                                        if plugin_options['gen_type'][i] == 0:          # GEN 1 device
                                            name = plugin_options['sensor_label'][i]
                                            msg_info += _('{}: GEN1 not available yet \n').format(name)
                                        if plugin_options['gen_type'][i] == 1:          # GEN 2+ device
                                            name = plugin_options['sensor_label'][i]
                                            if plugin_options['reading_type'][i] == 1:  # only cloud API data
                                                isok = response_data["isok"]
                                            else:
                                                isok = True
                                            err = ""
                                            if not isok:
                                                errors = response_data["errors"]
                                                try:
                                                    test = errors["device_not_found"]
                                                    err = _('Your device has not been connected to the cloud!')
                                                except:
                                                    err = _('Unknown')
                                                    pass
                                                msg += _('[{}: Error] ').format(name)
                                                msg_info += _('{}: Error: {}\n').format(name, err)
                                            else:
                                                if plugin_options['reading_type'][i] == 1:  # only cloud API data
                                                    a_energy = response_data["data"]["device_status"]["switch:0"]["aenergy"]
                                                    b_energy = response_data["data"]["device_status"]["switch:1"]["aenergy"]
                                                    a_total = response_data["data"]["device_status"]["switch:0"]["aenergy"]["total"]
                                                    b_total = response_data["data"]["device_status"]["switch:1"]["aenergy"]["total"]
                                                    a_output = response_data["data"]["device_status"]["switch:0"]["output"]
                                                    b_output = response_data["data"]["device_status"]["switch:1"]["output"]
                                                    a_power = response_data["data"]["device_status"]["switch:0"]["apower"]
                                                    b_power = response_data["data"]["device_status"]["switch:1"]["apower"]
                                                    a_voltage = response_data["data"]["device_status"]["switch:0"]["voltage"]
                                                    b_voltage = response_data["data"]["device_status"]["switch:1"]["voltage"]
                                                    updated = now()
                                                    online = response_data["data"]["online"]
                                                    wifi = response_data["data"]["device_status"]["wifi"]
                                                    sta_ip = wifi["sta_ip"]
                                                    rssi = wifi["rssi"]
                                                else:                                       # via local IP data
                                                    a_energy = response_data["switch:0"]["aenergy"]
                                                    b_energy = response_data["switch:1"]["aenergy"]
                                                    a_total = response_data["switch:0"]["aenergy"]["total"]
                                                    b_total = response_data["switch:1"]["aenergy"]["total"]
                                                    a_output = response_data["switch:0"]["output"]
                                                    b_output = response_data["switch:1"]["output"]
                                                    a_power = response_data["switch:0"]["apower"]
                                                    b_power = response_data["switch:1"]["apower"]
                                                    a_voltage = response_data["switch:0"]["voltage"]
                                                    b_voltage = response_data["switch:1"]["voltage"]
                                                    updated = now()
                                                    online = True
                                                    wifi = response_data["wifi"]
                                                    sta_ip = wifi["sta_ip"]
                                                    rssi = wifi["rssi"]
                                                if online:
                                                    if a_output:
                                                        msg += _('[{}: 1-ON {} W ({} kW/h) ').format(name, a_power, round(a_total/1000.0, 2))
                                                        msg_info += _('{}: 1-ON {} W ({} kW/h) {} V IP:{} RSSI:{} dbm ').format(name, a_power, round(a_total/1000.0, 2), a_voltage, sta_ip, rssi)
                                                    else:
                                                        msg += _('[{}: 1-OFF {}W ({}kW/h) ').format(name, a_power, round(a_total/1000.0, 2))
                                                        msg_info += _('{}: 1-OFF {} W ({} kW/h) {} V IP:{} RSSI:{} dbm ').format(name, a_power, round(a_total/1000.0, 2), a_voltage, sta_ip, rssi)    
                                                    if b_output:
                                                        msg += _('2-ON {} W ({} kW/h)] ').format(b_power, round(b_total/1000.0, 2))
                                                        msg_info += _('2-ON {} W ({} kW/h) {} V {}\n').format(b_power, round(b_total/1000.0, 2), b_voltage, format_timestamp(updated))
                                                    else:
                                                        msg += _('2-OFF {} W ({} kW/h)] ').format(b_power, round(b_total/1000.0, 2))
                                                        msg_info += _('2-OFF {} W ({} kW/h) {} V {}\n').format(b_power, round(b_total/1000.0, 2), b_voltage, format_timestamp(updated))
                                                else:
                                                    msg += _('[{}: -] ').format(name)
                                                    msg_info += _('{}: OFFLINE\n').format(name)

                                                payload = {
                                                    'id': id,
                                                    'ip': sta_ip,
                                                    'voltage': a_voltage,
                                                    'battery': 0,
                                                    'temperature': [],
                                                    'humidity': [],
                                                    'illuminance': [],                                                    
                                                    'rssi': rssi,
                                                    'output': [a_output, b_output],
                                                    'power': [a_power, b_power],
                                                    'retpower': [],
                                                    'label': name,
                                                    'online': online,
                                                    'updated': updated,
                                                    'gen': _('GEN1') if plugin_options['gen_type'][i]==0 else _('GEN2+'),
                                                    'hw': _('Shelly Pro 2PM'),
                                                    'hw_nbr': plugin_options['sensor_type'][i]
                                                }
                                                update_or_add_device(self, payload)

                                    # typ: 3=Shelly 1PM Mini
                                    # gen: 0 = GEN1, 1 = GEN 2+
                                    if plugin_options['sensor_type'][i] == 3:
                                        if plugin_options['gen_type'][i] == 0:          # GEN 1 device
                                            name = plugin_options['sensor_label'][i]
                                            msg_info += _('{}: GEN1 not available yet \n').format(name)
                                        if plugin_options['gen_type'][i] == 1:          # GEN 2+ device
                                            name = plugin_options['sensor_label'][i]
                                            if plugin_options['reading_type'][i] == 1:  # only cloud API data
                                                isok = response_data["isok"]
                                            else:
                                                isok = True
                                            err = ""
                                            if not isok:
                                                errors = response_data["errors"]
                                                try:
                                                    test = errors["device_not_found"]
                                                    err = _('Your device has not been connected to the cloud!')
                                                except:
                                                    err = _('Unknown')
                                                    pass
                                                msg += _('[{}: Error] ').format(name)
                                                msg_info += _('{}: Error: {}\n').format(name, err)
                                            else:
                                                if plugin_options['reading_type'][i] == 1:  # only cloud API data
                                                    total = response_data["data"]["device_status"]["switch:0"]["aenergy"]["total"]
                                                    output = response_data["data"]["device_status"]["switch:0"]["output"]
                                                    power = response_data["data"]["device_status"]["switch:0"]["apower"]
                                                    voltage = response_data["data"]["device_status"]["switch:0"]["voltage"]
                                                    updated = now()
                                                    online = response_data["data"]["online"]
                                                    wifi = response_data["data"]["device_status"]["wifi"]
                                                    sta_ip = wifi["sta_ip"]
                                                    rssi = wifi["rssi"]
                                                else:                                       # via local IP data
                                                    total = response_data["switch:0"]["aenergy"]["total"]
                                                    output = response_data["switch:0"]["output"]
                                                    power = response_data["switch:0"]["apower"]
                                                    voltage = response_data["switch:0"]["voltage"]
                                                    updated = now()
                                                    online = True
                                                    wifi = response_data["wifi"]
                                                    sta_ip = wifi["sta_ip"]
                                                    rssi = wifi["rssi"]
                                                if online:
                                                    if output:
                                                        msg += _('[{}: ON {} W ({} kW/h)] ').format(name, power, round(total/1000.0, 2))
                                                        msg_info += _('{}: ON {} W ({} kW/h) {} V IP:{} RSSI:{} dbm {}\n').format(name, power, round(total/1000.0, 2), voltage, sta_ip, rssi, format_timestamp(updated))
                                                    else:
                                                        msg += _('[{}: OFF {} W ({} kW/h)] ').format(name, power, round(total/1000.0, 2))
                                                        msg_info += _('{}: OFF {} W ({} kW/h) {} V IP:{} RSSI:{} dbm {}\n').format(name, power, round(total/1000.0, 2), voltage, sta_ip, rssi, format_timestamp(updated))
                                                else:
                                                    msg += _('[{}: -] ').format(name)
                                                    msg_info += _('{}: OFFLINE\n').format(name)
                                                payload = {
                                                    'id': id,
                                                    'ip': sta_ip,
                                                    'voltage': voltage,
                                                    'battery': 0,
                                                    'temperature': [],
                                                    'humidity': [],
                                                    'illuminance': [],                                                    
                                                    'rssi': rssi,
                                                    'output': [output],
                                                    'power': [power],
                                                    'retpower': [],
                                                    'label': name,
                                                    'online': online,
                                                    'updated': updated,
                                                    'gen': _('GEN1') if plugin_options['gen_type'][i]==0 else _('GEN2+'),
                                                    'hw': _('Shelly 1PM Mini'),
                                                    'hw_nbr': plugin_options['sensor_type'][i]
                                                }
                                                update_or_add_device(self, payload)

                                    # typ: 4=Shelly 2.5
                                    # gen: 0 = GEN1, 1 = GEN 2+
                                    if plugin_options['sensor_type'][i] == 4:
                                        if plugin_options['gen_type'][i] == 0:          # GEN 1 device
                                            name = plugin_options['sensor_label'][i]
                                            if plugin_options['reading_type'][i] == 1:  # only cloud API data
                                                isok = response_data["isok"]
                                            else:
                                                isok = True
                                            err = ""
                                            if not isok:
                                                errors = response_data["errors"]
                                                try:
                                                    test = errors["device_not_found"]
                                                    err = _('Your device has not been connected to the cloud!')
                                                except:
                                                    err = _('Unknown')
                                                    pass
                                                msg += _('[{}: Error] ').format(name)
                                                msg_info += _('{}: Error: {}\n').format(name, err)
                                            else:
                                                roller = None
                                                if plugin_options['reading_type'][i] == 1:  # only cloud API data
                                                    try: # roller mode
                                                        roller = response_data["data"]["device_status"]["rollers"][0]["state"]
                                                        a_power = response_data["data"]["device_status"]["meters"][0]["power"]
                                                        b_power = response_data["data"]["device_status"]["meters"][1]["power"]
                                                        a_total = response_data["data"]["device_status"]["meters"][0]["total"]
                                                        b_total = response_data["data"]["device_status"]["meters"][1]["total"]
                                                        voltage = response_data["data"]["device_status"]["voltage"]
                                                        wifi = response_data["data"]["device_status"]["wifi_sta"]
                                                        sta_ip = wifi["ip"]
                                                    except: # switch mode
                                                        a_power = response_data["data"]["device_status"]["switch:0"]["apower"]
                                                        b_power = response_data["data"]["device_status"]["switch:1"]["apower"]
                                                        a_total = response_data["data"]["device_status"]["switch:0"]["aenergy"]["total"]
                                                        b_total = response_data["data"]["device_status"]["switch:1"]["aenergy"]["total"]
                                                        voltage = response_data["data"]["device_status"]["switch:0"]["voltage"]
                                                        a_output = response_data["data"]["device_status"]["switch:0"]["output"]
                                                        b_output = response_data["data"]["device_status"]["switch:1"]["output"]
                                                        wifi = response_data["data"]["device_status"]["wifi"]
                                                        sta_ip = wifi["sta_ip"]
                                                        pass  
                                                    updated = now()
                                                    online = response_data["data"]["online"]
                                                    rssi = wifi["rssi"]
                                                else:                                       # via local IP data
                                                    try: # roller mode
                                                        roller = response_data["rollers"][0]["state"]
                                                        a_power = response_data["meters"][0]["power"]
                                                        b_power = response_data["meters"][1]["power"]
                                                        a_total = response_data["meters"][0]["total"]
                                                        b_total = response_data["meters"][1]["total"]
                                                        voltage = response_data["voltage"]
                                                        wifi = response_data["wifi_sta"]
                                                        sta_ip = wifi["ip"]
                                                    except: # switch mode
                                                        a_power = response_data["switch:0"]["apower"]
                                                        b_power = response_data["switch:1"]["apower"]
                                                        a_total = response_data["switch:0"]["aenergy"]["total"]
                                                        b_total = response_data["switch:1"]["aenergy"]["total"]
                                                        voltage = response_data["switch:0"]["voltage"]
                                                        a_output = response_data["switch:0"]["output"]
                                                        b_output = response_data["switch:1"]["output"]
                                                        wifi = response_data["sta_ip"]
                                                        sta_ip = wifi["ip"]
                                                        pass  
                                                    updated = now()
                                                    online = True
                                                    rssi = wifi["rssi"]
                                                if online:
                                                    if roller is None:
                                                        if a_output:
                                                            msg += _('[{}: 1-ON {} W ({} kW/h) ').format(name, a_power, round(a_total/1000.0, 2))
                                                            msg_info += _('{}: 1-ON {} W ({} kW/h) {} V IP:{} RSSI:{} dbm ').format(name, a_power, round(a_total/1000.0, 2), a_voltage, sta_ip, rssi)
                                                        else:
                                                            msg += _('[{}: 1-OFF {} W ({} kW/h) ').format(name, a_power, round(a_total/1000.0, 2))
                                                            msg_info += _('{}: 1-OFF {} W ({} kW/h) {} V IP:{} RSSI:{} dbm ').format(name, a_power, round(a_total/1000.0, 2), a_voltage, sta_ip, rssi)    
                                                        if b_output:
                                                            msg += _('2-ON {} W ({} kW/h)] ').format(b_power, round(b_total/1000.0, 2))
                                                            msg_info += _('2-ON {} W ({} kW/h) {}\n').format(b_power, round(b_total/1000.0, 2), format_timestamp(updated))
                                                        else:
                                                            msg += _('2-OFF {} W ({} kW/h)] ').format(b_power, round(b_total/1000.0, 2))
                                                            msg_info += _('2-OFF {} W ({} kW/h) {}\n').format(b_power, round(b_total/1000.0, 2), format_timestamp(updated))
                                                    else:
                                                        msg += _('[{}: {} 1: {} W ({} kW/h) 2: {} W ({} kW/h)] ').format(name, roller, a_power, round(a_total/1000.0, 2), b_power, round(b_total/1000.0, 2))
                                                        msg_info += _('{}: {} 1: {} W ({} kW/h) 2: {} W ({} kW/h) {} V IP:{} RSSI:{} dbm {}\n').format(name, roller, a_power, round(a_total/1000.0, 2), b_power, round(b_total/1000.0, 2), a_voltage, sta_ip, rssi, format_timestamp(updated))
                                                else:
                                                    msg += _('[{}: -] ').format(name)
                                                    msg_info += _('{}: OFFLINE\n').format(name)
                                                payload = {
                                                    'id': id,
                                                    'ip': sta_ip,
                                                    'voltage': voltage,
                                                    'battery': 0,
                                                    'temperature': [],
                                                    'humidity': [],
                                                    'illuminance': [],                                                    
                                                    'rssi': rssi,
                                                    'output': [a_output, b_output] if roller is None else [roller],
                                                    'power': [a_power, b_power],
                                                    'retpower': [],
                                                    'label': name,
                                                    'online': online,
                                                    'updated': updated,
                                                    'gen': _('GEN1') if plugin_options['gen_type'][i]==0 else _('GEN2+'),
                                                    'hw': _('Shelly 2.5'),
                                                    'hw_nbr': plugin_options['sensor_type'][i]
                                                }
                                                update_or_add_device(self, payload)
                                            if plugin_options['gen_type'][i] == 1:
                                                name = plugin_options['sensor_label'][i]
                                                msg_info += _('{}: GEN2 not available yet \n').format(name)

                                    # typ: 5=Shelly Pro 4PM
                                    # gen: 0 = GEN1, 1 = GEN 2+
                                    if plugin_options['sensor_type'][i] == 5:
                                        if plugin_options['gen_type'][i] == 0:
                                            name = plugin_options['sensor_label'][i]
                                            msg_info += _('{}: GEN1 not available yet \n').format(name)
                                        if plugin_options['gen_type'][i] == 1:
                                            name = plugin_options['sensor_label'][i]
                                            if plugin_options['reading_type'][i] == 1:  # only cloud API data
                                                isok = response_data["isok"]
                                            else:
                                                isok = True
                                            err = ""
                                            if not isok:
                                                errors = response_data["errors"]
                                                try:
                                                    test = errors["device_not_found"]
                                                    err = _('Your device has not been connected to the cloud!')
                                                except:
                                                    err = _('Unknown')
                                                    pass
                                                msg += _('[{}: Error] ').format(name)
                                                msg_info += _('{}: Error: {}\n').format(name, err)
                                            else:
                                                if plugin_options['reading_type'][i] == 1:  # only cloud API data
                                                    a_total = response_data["data"]["device_status"]["switch:0"]["aenergy"]["total"]
                                                    b_total = response_data["data"]["device_status"]["switch:1"]["aenergy"]["total"]
                                                    c_total = response_data["data"]["device_status"]["switch:2"]["aenergy"]["total"]
                                                    d_total = response_data["data"]["device_status"]["switch:3"]["aenergy"]["total"]
                                                    a_output = response_data["data"]["device_status"]["switch:0"]["output"]
                                                    b_output = response_data["data"]["device_status"]["switch:1"]["output"]
                                                    c_output = response_data["data"]["device_status"]["switch:2"]["output"]
                                                    d_output = response_data["data"]["device_status"]["switch:3"]["output"]
                                                    a_power = response_data["data"]["device_status"]["switch:0"]["apower"]
                                                    b_power = response_data["data"]["device_status"]["switch:1"]["apower"]
                                                    c_power = response_data["data"]["device_status"]["switch:2"]["apower"]
                                                    d_power = response_data["data"]["device_status"]["switch:3"]["apower"]
                                                    voltage = response_data["data"]["device_status"]["switch:0"]["voltage"]
                                                    updated = now()
                                                    online = response_data["data"]["online"]
                                                    wifi = response_data["data"]["device_status"]["wifi"]
                                                    sta_ip = wifi["sta_ip"]
                                                    rssi = wifi["rssi"]
                                                else:                                       # via local IP data
                                                    a_total = response_data["switch:0"]["aenergy"]["total"]
                                                    b_total = response_data["switch:1"]["aenergy"]["total"]
                                                    c_total = response_data["switch:2"]["aenergy"]["total"]
                                                    d_total = response_data["switch:3"]["aenergy"]["total"]
                                                    a_output = response_data["switch:0"]["output"]
                                                    b_output = response_data["switch:1"]["output"]
                                                    c_output = response_data["switch:2"]["output"]
                                                    d_output = response_data["switch:3"]["output"]
                                                    a_power = response_data["switch:0"]["apower"]
                                                    b_power = response_data["switch:1"]["apower"]
                                                    c_power = response_data["switch:2"]["apower"]
                                                    d_power = response_data["switch:3"]["apower"]
                                                    voltage = response_data["switch:0"]["voltage"]
                                                    updated = now()
                                                    online = True
                                                    wifi = response_data["wifi"]
                                                    sta_ip = wifi["sta_ip"]
                                                    rssi = wifi["rssi"]
                                                if online:
                                                    msg += '[{}: '.format(name)
                                                    msg_info += '{}: '.format(name)
                                                    if a_output:
                                                        msg += _('1-ON {} W ({} kW/h) ').format(a_power, round(a_total/1000.0, 2))
                                                        msg_info += _('1-ON {} W ({} kW/h) ').format(a_power, round(a_total/1000.0, 2))
                                                    else:
                                                        msg += _('1-OFF {} W ({} kW/h) ').format(a_power, round(a_total/1000.0, 2))
                                                        msg_info += _('1-OFF {} W ({} kW/h) ').format(a_power, round(a_total/1000.0, 2))
                                                    if b_output:
                                                        msg += _('2-ON {} W ({} kW/h) ').format(b_power, round(b_total/1000.0, 2))
                                                        msg_info += _('2-ON {} W ({} kW/h) ').format(b_power, round(b_total/1000.0, 2))
                                                    else:
                                                        msg += _('2-OFF {} W ({} kW/h) ').format(b_power, round(b_total/1000.0, 2))
                                                        msg_info += _('2-OFF {} W ({} kW/h) ').format(b_power, round(b_total/1000.0, 2))
                                                    if c_output:
                                                        msg += _('3-ON {} W ({} kW/h) ').format(c_power, round(c_total/1000.0, 2))
                                                        msg_info += _('3-ON {} W ({} kW/h) ').format(c_power, round(c_total/1000.0, 2))
                                                    else:
                                                        msg += _('3-OFF {}W ({}kW/h) ').format(c_power, round(c_total/1000.0, 2))
                                                        msg_info += _('3-OFF {}W ({}kW/h) ').format(c_power, round(c_total/1000.0, 2))
                                                    if d_output:
                                                        msg += _('4-ON {} W ({} kW/h)] ').format(d_power, round(d_total/1000.0, 2))
                                                        msg_info += _('4-ON {} W ({} kW/h) {} V IP:{} RSSI:{} dbm {}\n').format(d_power, round(d_total/1000.0, 2), voltage, sta_ip, rssi, format_timestamp(updated))
                                                    else:
                                                        msg += _('4-OFF {} W ({} kW/h)] ').format(d_power, round(d_total/1000.0, 2))
                                                        msg_info += _('4-OFF {} W ({} kW/h) {} V IP:{} RSSI:{} dbm {}\n').format(d_power, round(d_total/1000.0, 2), voltage, sta_ip, rssi, format_timestamp(updated))
                                                else:
                                                    msg += _('[{}: -] ').format(name)
                                                    msg_info += _('{}: OFFLINE\n').format(name)
                                                payload = {
                                                    'id': id,
                                                    'ip': sta_ip,
                                                    'voltage': voltage,
                                                    'battery': 0,
                                                    'temperature': [],
                                                    'humidity': [],
                                                    'illuminance': [],                                                    
                                                    'rssi': rssi,
                                                    'output': [a_output, b_output, c_output, d_output],
                                                    'power': [a_power, b_power, c_power, d_power],
                                                    'retpower': [],
                                                    'label': name,
                                                    'online': online,
                                                    'updated': updated,
                                                    'gen': _('GEN1') if plugin_options['gen_type'][i]==0 else _('GEN2+'),
                                                    'hw': _('Shelly Pro 4PM'),
                                                    'hw_nbr': plugin_options['sensor_type'][i]
                                                }
                                                update_or_add_device(self, payload)

                                    # typ: 6=Shelly 1 Mini
                                    # gen: 0 = GEN1, 1 = GEN 2+
                                    if plugin_options['sensor_type'][i] == 6:
                                        if plugin_options['gen_type'][i] == 0:
                                            name = plugin_options['sensor_label'][i]
                                            msg_info += _('{}: GEN1 not available yet \n').format(name)
                                        if plugin_options['gen_type'][i] == 1:
                                            name = plugin_options['sensor_label'][i]
                                            if plugin_options['reading_type'][i] == 1:  # only cloud API data
                                                isok = response_data["isok"]
                                            else:
                                                isok = True
                                            err = ""
                                            if not isok:
                                                errors = response_data["errors"]
                                                try:
                                                    test = errors["device_not_found"]
                                                    err = _('Your device has not been connected to the cloud!')
                                                except:
                                                    err = _('Unknown')
                                                    pass
                                                msg += _('[{}: Error] ').format(name)
                                                msg_info += _('{}: Error: {}\n').format(name, err)
                                            else:
                                                if plugin_options['reading_type'][i] == 1:  # only cloud API data
                                                    output = response_data["data"]["device_status"]["switch:0"]["output"]
                                                    updated = now()
                                                    online = response_data["data"]["online"]
                                                    wifi = response_data["data"]["device_status"]["wifi"]
                                                    sta_ip = wifi["sta_ip"]
                                                    rssi = wifi["rssi"]
                                                else:                                       # via local IP data
                                                    output = response_data["switch:0"]["output"]
                                                    updated = now()
                                                    online = True
                                                    wifi = response_data["wifi"]
                                                    sta_ip = wifi["sta_ip"]
                                                    rssi = wifi["rssi"]
                                                if online:
                                                    if output:
                                                        msg += _('[{}: ON] ').format(name)
                                                        msg_info += _('{}: ON IP:{} RSSI:{} dbm {}\n').format(name, sta_ip, rssi, format_timestamp(updated))
                                                    else:
                                                        msg += _('[{}: OFF] ').format(name)
                                                        msg_info += _('{}: OFF IP:{} RSSI:{} dbm {}\n').format(name, sta_ip, rssi, format_timestamp(updated))
                                                else:
                                                    msg += _('[{}: -] ').format(name)
                                                    msg_info += _('{}: OFFLINE\n').format(name)
                                                payload = {
                                                    'id': id,
                                                    'ip': sta_ip,
                                                    'voltage': 0,
                                                    'battery': 0,
                                                    'temperature': [],
                                                    'humidity': [],
                                                    'illuminance': [],                                                    
                                                    'rssi': rssi,
                                                    'output': [output],
                                                    'power': [],
                                                    'retpower': [],
                                                    'label': name,
                                                    'online': online,
                                                    'updated': updated,
                                                    'gen': _('GEN1') if plugin_options['gen_type'][i]==0 else _('GEN2+'),
                                                    'hw': _('Shelly 1 Mini'),
                                                    'hw_nbr': plugin_options['sensor_type'][i]
                                                }
                                                update_or_add_device(self, payload)

                                    # typ: 7=Shelly 2PM Addon
                                    # gen: 0 = GEN1, 1 = GEN 2+
                                    if plugin_options['sensor_type'][i] == 7:
                                        if plugin_options['gen_type'][i] == 0:
                                            name = plugin_options['sensor_label'][i]
                                            msg_info += _('{}: GEN1 not available yet \n').format(name)
                                        if plugin_options['gen_type'][i] == 1:
                                            name = plugin_options['sensor_label'][i]
                                            if plugin_options['reading_type'][i] == 1:  # only cloud API data
                                                isok = response_data["isok"]
                                            else:
                                                isok = True
                                            err = ""
                                            if not isok:
                                                errors = response_data["errors"]
                                                try:
                                                    test = errors["device_not_found"]
                                                    err = _('Your device has not been connected to the cloud!')
                                                except:
                                                    err = _('Unknown')
                                                    pass
                                                msg += _('[{}: Error] ').format(name)
                                                msg_info += _('{}: Error: {}\n').format(name, err)
                                            else:
                                                temperature100 = None
                                                temperature101 = None
                                                temperature102 = None
                                                temperature103 = None
                                                temperature104 = None
                                                temp100name = ''
                                                temp101name = ''
                                                temp102name = ''
                                                temp103name = ''
                                                temp104name = ''
                                                if plugin_options['reading_type'][i] == 1:  # only cloud API data
                                                    a_total = response_data["data"]["device_status"]["switch:0"]["aenergy"]["total"]
                                                    b_total = response_data["data"]["device_status"]["switch:1"]["aenergy"]["total"]
                                                    a_output = response_data["data"]["device_status"]["switch:0"]["output"]
                                                    b_output = response_data["data"]["device_status"]["switch:1"]["output"]
                                                    a_power = response_data["data"]["device_status"]["switch:0"]["apower"]
                                                    b_power = response_data["data"]["device_status"]["switch:1"]["apower"]
                                                    try:
                                                        temperature100 = response_data["data"]["device_status"]["temperature:100"]["tC"]
                                                        temp100name = plugin_options['addons_labels_1'][i] # response_data["data"]["device_status"]["addons"][0]
                                                    except:
                                                        pass
                                                    try:
                                                        temperature101 = response_data["data"]["device_status"]["temperature:101"]["tC"]
                                                        temp101name = plugin_options['addons_labels_2'][i] # response_data["data"]["device_status"]["addons"][1]
                                                    except:
                                                        pass
                                                    try:
                                                        temperature102 = response_data["data"]["device_status"]["temperature:102"]["tC"]
                                                        temp102name = plugin_options['addons_labels_3'][i] # response_data["data"]["device_status"]["addons"][2]
                                                    except:
                                                        pass
                                                    try:
                                                        temperature103 = response_data["data"]["device_status"]["temperature:103"]["tC"]
                                                        temp103name = plugin_options['addons_labels_4'][i] # response_data["data"]["device_status"]["addons"][3]
                                                    except:
                                                        pass
                                                    try:
                                                        temperature104 = response_data["data"]["device_status"]["temperature:104"]["tC"]
                                                        temp104name = plugin_options['addons_labels_5'][i] # response_data["data"]["device_status"]["addons"][4]
                                                    except:
                                                        pass
                                                    voltage = response_data["data"]["device_status"]["switch:0"]["voltage"]
                                                    updated = now()
                                                    online = response_data["data"]["online"]
                                                    wifi = response_data["data"]["device_status"]["wifi"]
                                                    sta_ip = wifi["sta_ip"]
                                                    rssi = wifi["rssi"]
                                                else:                                       # via local IP data
                                                    a_total = response_data["switch:0"]["aenergy"]["total"]
                                                    b_total = response_data["switch:1"]["aenergy"]["total"]
                                                    a_output = response_data["switch:0"]["output"]
                                                    b_output = response_data["switch:1"]["output"]
                                                    a_power = response_data["switch:0"]["apower"]
                                                    b_power = response_data["switch:1"]["apower"]
                                                    try:
                                                        temperature100 = response_data["temperature:100"]["tC"]
                                                        temp100name = plugin_options['addons_labels_1'][i] # response_data["data"]["device_status"]["addons"][0]
                                                    except:
                                                        pass
                                                    try:
                                                        temperature101 = response_data["temperature:101"]["tC"]
                                                        temp101name = plugin_options['addons_labels_2'][i] # response_data["data"]["device_status"]["addons"][1]
                                                    except:
                                                        pass
                                                    try:
                                                        temperature102 = response_data["temperature:102"]["tC"]
                                                        temp102name = plugin_options['addons_labels_3'][i] # response_data["data"]["device_status"]["addons"][2]
                                                    except:
                                                        pass
                                                    try:
                                                        temperature103 = response_data["temperature:103"]["tC"]
                                                        temp103name = plugin_options['addons_labels_4'][i] # response_data["data"]["device_status"]["addons"][3]
                                                    except:
                                                        pass
                                                    try:
                                                        temperature104 = response_data["temperature:104"]["tC"]
                                                        temp104name = plugin_options['addons_labels_5'][i] # response_data["data"]["device_status"]["addons"][4]
                                                    except:
                                                        pass
                                                    voltage = response_data["switch:0"]["voltage"]
                                                    updated = now()
                                                    online = True
                                                    wifi = response_data["wifi"]
                                                    sta_ip = wifi["sta_ip"]
                                                    rssi = wifi["rssi"]
                                                if online:
                                                    if a_output:
                                                        msg += _('[{}: 1-ON {} W ({} kW/h) ').format(name, a_power, round(a_total/1000.0, 2))
                                                        msg_info += _('{}: 1-ON {} W ({} kW/h) {} V IP:{} RSSI:{} dbm ').format(name, a_power, round(a_total/1000.0, 2), voltage, sta_ip, format_timestamp(updated))
                                                    else:
                                                        msg += _('[{}: 1-OFF {} W ({} kW/h) ').format(name, a_power, round(a_total/1000.0, 2))
                                                        msg_info += _('{}: 1-OFF {} W ({} kW/h) {} V IP:{} RSSI:{} dbm ').format(name, a_power, round(a_total/1000.0, 2), voltage, sta_ip, format_timestamp(updated))
                                                    if b_output:
                                                        msg += _('2-ON {} W ({} kW/h) ').format(b_power, round(b_total/1000.0, 2))
                                                        msg_info += _('2-ON {} W ({} kW/h) ').format(b_power, round(b_total/1000.0, 2))
                                                    else:
                                                        msg += _('2-OFF {} W ({} kW/h) ').format(b_power, round(b_total/1000.0, 2))
                                                        msg_info += _('2-OFF {} W ({} kW/h) ').format(b_power, round(b_total/1000.0, 2))
                                                    if temperature100 is not None:
                                                        msg += _('{} {} °C ').format(temp100name, temperature100)
                                                        msg_info += _('{} {} °C ').format(temp100name, temperature100)
                                                    if temperature101 is not None:
                                                        msg += _('{} {} °C ').format(temp101name, temperature101)
                                                        msg_info += _('{} {} °C ').format(temp101name, temperature101)
                                                    if temperature102 is not None:
                                                        msg += _('{} {} °C ').format(temp102name, temperature102)
                                                        msg_info += _('{} {} °C ').format(temp102name, temperature102)
                                                    if temperature103 is not None:
                                                        msg += _('{} {} °C ').format(temp103name, temperature103)
                                                        msg_info += _('{} {} °C ').format(temp103name, temperature103)
                                                    if temperature104 is not None:
                                                        msg += _('{} {} °C ').format(temp104name, temperature104)
                                                        msg_info += _('{} {} °C ').format(temp104name, temperature104)
                                                    msg += '] '
                                                    msg_info += '] '
                                                else:
                                                    msg += _('[{}: -] ').format(name)
                                                    msg_info += _('{}: OFFLINE\n').format(name)
                                                payload = {
                                                    'id': id,
                                                    'ip': sta_ip,
                                                    'voltage': voltage,
                                                    'battery': 0,
                                                    'temperature': [temperature100, temperature101, temperature102, temperature103, temperature104],
                                                    'humidity': [],
                                                    'illuminance': [],                                                    
                                                    'rssi': rssi,
                                                    'output': [a_output, b_output],
                                                    'power': [a_power, b_power],
                                                    'retpower': [],
                                                    'label': name,
                                                    'online': online,
                                                    'updated': updated,
                                                    'gen': _('GEN1') if plugin_options['gen_type'][i]==0 else _('GEN2+'),
                                                    'hw': _('Shelly 2PM Addon'),
                                                    'hw_nbr': plugin_options['sensor_type'][i]
                                                }
                                                update_or_add_device(self, payload)

                                    # typ: 8=Shelly 1PM Addon
                                    # gen: 0 = GEN1, 1 = GEN 2+
                                    if plugin_options['sensor_type'][i] == 8:
                                        if plugin_options['gen_type'][i] == 0:
                                            name = plugin_options['sensor_label'][i]
                                            msg_info += _('{}: GEN1 not available yet \n').format(name)
                                        if plugin_options['gen_type'][i] == 1:
                                            name = plugin_options['sensor_label'][i]
                                            if plugin_options['reading_type'][i] == 1:  # only cloud API data
                                                isok = response_data["isok"]
                                            else:
                                                isok = True
                                            err = ""
                                            if not isok:
                                                errors = response_data["errors"]
                                                try:
                                                    test = errors["device_not_found"]
                                                    err = _('Your device has not been connected to the cloud!')
                                                except:
                                                    err = _('Unknown')
                                                    pass
                                                msg += _('[{}: Error] ').format(name)
                                                msg_info += _('{}: Error: {}\n').format(name, err)
                                            else:
                                                temperature100 = None
                                                temperature101 = None
                                                temperature102 = None
                                                temperature103 = None
                                                temperature104 = None
                                                temp100name = ''
                                                temp101name = ''
                                                temp102name = ''
                                                temp103name = ''
                                                temp104name = ''
                                                if plugin_options['reading_type'][i] == 1:  # only cloud API data
                                                    a_total = response_data["data"]["device_status"]["switch:0"]["aenergy"]["total"]
                                                    a_output = response_data["data"]["device_status"]["switch:0"]["output"]
                                                    a_power = response_data["data"]["device_status"]["switch:0"]["apower"]
                                                    try:
                                                        temperature100 = response_data["data"]["device_status"]["temperature:100"]["tC"]
                                                        temp100name = plugin_options['addons_labels_1'][i] # response_data["data"]["device_status"]["addons"][0]
                                                    except:
                                                        pass
                                                    try:
                                                        temperature101 = response_data["data"]["device_status"]["temperature:101"]["tC"]
                                                        temp101name = plugin_options['addons_labels_2'][i] # response_data["data"]["device_status"]["addons"][1]
                                                    except:
                                                        pass
                                                    try:
                                                        temperature102 = response_data["data"]["device_status"]["temperature:102"]["tC"]
                                                        temp102name = plugin_options['addons_labels_3'][i] # response_data["data"]["device_status"]["addons"][2]
                                                    except:
                                                        pass
                                                    try:
                                                        temperature103 = response_data["data"]["device_status"]["temperature:103"]["tC"]
                                                        temp103name = plugin_options['addons_labels_4'][i] # response_data["data"]["device_status"]["addons"][3]
                                                    except:
                                                        pass
                                                    try:
                                                        temperature104 = response_data["data"]["device_status"]["temperature:104"]["tC"]
                                                        temp104name = plugin_options['addons_labels_5'][i] # response_data["data"]["device_status"]["addons"][4]
                                                    except:
                                                        pass
                                                    voltage = response_data["data"]["device_status"]["switch:0"]["voltage"]
                                                    updated = now()
                                                    online = response_data["data"]["online"]
                                                    wifi = response_data["data"]["device_status"]["wifi"]
                                                    sta_ip = wifi["sta_ip"]
                                                    rssi = wifi["rssi"]
                                                else:                                       # via local IP data
                                                    a_total = response_data["switch:0"]["aenergy"]["total"]
                                                    a_output = response_data["switch:0"]["output"]
                                                    a_power = response_data["switch:0"]["apower"]
                                                    try:
                                                        temperature100 = response_data["temperature:100"]["tC"]
                                                        temp100name = plugin_options['addons_labels_1'][i] # response_data["data"]["device_status"]["addons"][0]
                                                    except:
                                                        pass
                                                    try:
                                                        temperature101 = response_data["temperature:101"]["tC"]
                                                        temp101name = plugin_options['addons_labels_2'][i] # response_data["data"]["device_status"]["addons"][1]
                                                    except:
                                                        pass
                                                    try:
                                                        temperature102 = response_data["temperature:102"]["tC"]
                                                        temp102name = plugin_options['addons_labels_3'][i] # response_data["data"]["device_status"]["addons"][2]
                                                    except:
                                                        pass
                                                    try:
                                                        temperature103 = response_data["temperature:103"]["tC"]
                                                        temp103name = plugin_options['addons_labels_4'][i] # response_data["data"]["device_status"]["addons"][3]
                                                    except:
                                                        pass
                                                    try:
                                                        temperature104 = response_data["temperature:104"]["tC"]
                                                        temp104name = plugin_options['addons_labels_5'][i] # response_data["data"]["device_status"]["addons"][4]
                                                    except:
                                                        pass
                                                    voltage = response_data["switch:0"]["voltage"]
                                                    updated = now()
                                                    online = True
                                                    wifi = response_data["wifi"]
                                                    sta_ip = wifi["sta_ip"]
                                                    rssi = wifi["rssi"]
                                                if online:
                                                    if a_output:
                                                        msg += _('[{}: 1-ON {} W ({} kW/h) ').format(name, a_power, round(a_total/1000.0, 2))
                                                        msg_info += _('{}: 1-ON {} W ({} kW/h) {} V IP:{} RSSI:{} dbm ').format(name, a_power, round(a_total/1000.0, 2), voltage, sta_ip, format_timestamp(updated))
                                                    else:
                                                        msg += _('[{}: 1-OFF {} W ({} kW/h) ').format(name, a_power, round(a_total/1000.0, 2))
                                                        msg_info += _('{}: 1-OFF {} W ({} kW/h) {} V IP:{} RSSI:{} dbm ').format(name, a_power, round(a_total/1000.0, 2), voltage, sta_ip, format_timestamp(updated))
                                                    if temperature100 is not None:
                                                        msg += _('{} {} °C ').format(temp100name, temperature100)
                                                        msg_info += _('{} {} °C ').format(temp100name, temperature100)
                                                    if temperature101 is not None:
                                                        msg += _('{} {} °C ').format(temp101name, temperature101)
                                                        msg_info += _('{} {} °C ').format(temp101name, temperature101)
                                                    if temperature102 is not None:
                                                        msg += _('{} {} °C ').format(temp102name, temperature102)
                                                        msg_info += _('{} {} °C ').format(temp102name, temperature102)
                                                    if temperature103 is not None:
                                                        msg += _('{} {} °C ').format(temp103name, temperature103)
                                                        msg_info += _('{} {} °C ').format(temp103name, temperature103)
                                                    if temperature104 is not None:
                                                        msg += _('{} {} °C ').format(temp104name, temperature104)
                                                        msg_info += _('{} {} °C ').format(temp104name, temperature104)
                                                    msg += '] '
                                                    msg_info += '] '
                                                else:
                                                    msg += _('[{}: -] ').format(name)
                                                    msg_info += _('{}: OFFLINE\n').format(name)
                                                payload = {
                                                    'id': id,
                                                    'ip': sta_ip,
                                                    'voltage': voltage,
                                                    'battery': 0,
                                                    'temperature': [temperature100, temperature101, temperature102, temperature103, temperature104],
                                                    'humidity': [],
                                                    'illuminance': [],                                                    
                                                    'rssi': rssi,
                                                    'output': [a_output],
                                                    'power': [a_power],
                                                    'retpower': [],
                                                    'label': name,
                                                    'online': online,
                                                    'updated': updated,
                                                    'gen': _('GEN1') if plugin_options['gen_type'][i]==0 else _('GEN2+'),
                                                    'hw': _('Shelly 1PM Addon'),
                                                    'hw_nbr': plugin_options['sensor_type'][i]
                                                }
                                                update_or_add_device(self, payload)

                                    # typ: 9= Shelly H&T
                                    # gen: 0 = GEN1, 1 = GEN 2+
                                    if plugin_options['sensor_type'][i] == 9:
                                        if plugin_options['gen_type'][i] == 1:
                                            name = plugin_options['sensor_label'][i]
                                            msg_info += _('{}: GEN2+ not available \n').format(name)
                                        if plugin_options['gen_type'][i] == 0:
                                            name = plugin_options['sensor_label'][i]
                                            isok = response_data["isok"]
                                            err = ""
                                            if not isok:
                                                errors = response_data["errors"]
                                                try:
                                                    test = errors["device_not_found"]
                                                    err = _('Your device has not been connected to the cloud!')
                                                except:
                                                    err = _('Unknown')
                                                    pass
                                                msg += _('[{}: Error] ').format(name)
                                                msg_info += _('{}: Error: {}\n').format(name, err)
                                            else:
                                                temperature = response_data["data"]["device_status"]["tmp"]["value"]
                                                humidity = response_data["data"]["device_status"]["hum"]["value"]
                                                updated = now()
                                                battery = response_data["data"]["device_status"]["bat"]
                                                online = response_data["data"]["online"]
                                                wifi = response_data["data"]["device_status"]["wifi_sta"]
                                                sta_ip = wifi["ip"]
                                                rssi = wifi["rssi"]
                                                batt_V = battery["voltage"]
                                                batt_perc = battery["value"]
                                                if online:
                                                    msg += _('[{}: {} °C {} RV] ').format(name, temperature, humidity, batt_perc)
                                                    msg_info += _('{}: {} °C {} RV BAT{} % IP:{} RSSI:{} dbm {}\n').format(name, temperature, humidity, batt_perc, sta_ip, rssi, format_timestamp(updated))
                                                else:
                                                    msg += _('[{}: -] ').format(name)
                                                    msg_info += _('{}: OFFLINE\n').format(name)
                                                
                                                payload = {
                                                    'id': id,
                                                    'ip': sta_ip,
                                                    'voltage': batt_V,
                                                    'battery': batt_perc,
                                                    'temperature': [temperature],
                                                    'humidity': [humidity],
                                                    'illuminance': [],                                                    
                                                    'rssi': rssi,
                                                    'output': [],
                                                    'power': [],
                                                    'retpower': [],
                                                    'label': name,
                                                    'online': online,
                                                    'updated': updated,
                                                    'gen': _('GEN1') if plugin_options['gen_type'][i]==0 else _('GEN2+'),
                                                    'hw': _('Shelly HT'),
                                                    'hw_nbr': plugin_options['sensor_type'][i]
                                                }
                                                update_or_add_device(self, payload)

                                    # typ: 10=Shelly Pro 3EM / Shelly 3EM-63T Gen3
                                    # gen: 0 = GEN1, 1 = GEN 2+
                                    if plugin_options['sensor_type'][i] == 10:
                                        if plugin_options['gen_type'][i] == 0:
                                            name = plugin_options['sensor_label'][i]
                                            msg_info += _('{}: GEN1 not available yet \n').format(name)
                                        if plugin_options['gen_type'][i] == 1:
                                            name = plugin_options['sensor_label'][i]
                                            if plugin_options['reading_type'][i] == 1:  # only cloud API data
                                                isok = response_data["isok"]
                                            else:
                                                isok = True
                                            err = ""
                                            if not isok:
                                                errors = response_data["errors"]
                                                try:
                                                    test = errors["device_not_found"]
                                                    err = _('Your device has not been connected to the cloud!')
                                                except:
                                                    err = _('Unknown')
                                                    pass
                                                msg += _('[{}: Error] ').format(name)
                                                msg_info += _('{}: Error: {}\n').format(name, err)
                                            else:
                                                meter = parse_three_phase_meter(response_data, plugin_options['reading_type'][i] == 1)
                                                a_power, b_power, c_power = meter['powers']
                                                a_voltage, b_voltage, c_voltage = meter['voltages']
                                                a_revpower, b_revpower, c_revpower = meter['reverse_powers']
                                                a_total, b_total, c_total = meter['energy_kwh']
                                                internal_temperature = meter['temperature']
                                                updated = now()
                                                online = meter['online']
                                                sta_ip = meter['ip']
                                                rssi = meter['rssi']
                                                if online:
                                                        msg += _('[{}: L1 {} W, L2 {} W, L3 {} W]').format(name, a_power, b_power, c_power)
                                                        msg_info += _('{}: L1 {} W ({} kWh, {} V) L2 {} W ({} kWh, {} V) L3 {} W ({} kWh, {} V) IP:{} RSSI:{} dBm internal temperature:{} °C {}\n').format(name, a_power, a_total, a_voltage, b_power, b_total, b_voltage, c_power, c_total, c_voltage, sta_ip, rssi, internal_temperature if internal_temperature is not None else '-', format_timestamp(updated))
                                                else:
                                                    msg += _('[{}: -] ').format(name)
                                                    msg_info += _('{}: OFFLINE\n').format(name)
                                                payload = {
                                                    'id': id,
                                                    'ip': sta_ip,
                                                    'voltage': a_voltage,
                                                    'voltages': meter['voltages'],
                                                    'current': meter['currents'],
                                                    'power_factor': meter['power_factors'],
                                                    'energy': meter['energy_kwh'],
                                                    'returned_energy': meter['returned_energy_kwh'],
                                                    'total_power': meter['total_power'],
                                                    'total_energy': meter['total_energy'],
                                                    'total_returned_energy': meter['total_returned_energy'],
                                                    'battery': 0,
                                                    'temperature': [internal_temperature] if internal_temperature is not None else [],
                                                    'humidity': [],
                                                    'illuminance': [],                                                    
                                                    'rssi': rssi,
                                                    'output': [],
                                                    'power': [a_power, b_power, c_power],
                                                    'retpower': [a_revpower, b_revpower, c_revpower],
                                                    'label': name,
                                                    'online': online,
                                                    'updated': updated,
                                                    'gen': _('GEN1') if plugin_options['gen_type'][i]==0 else _('GEN2+'),
                                                    'hw': _('Shelly Pro 3EM / Shelly 3EM-63T Gen3'),
                                                    'hw_nbr': plugin_options['sensor_type'][i]
                                                }
                                                update_or_add_device(self, payload)

                                    # typ: 11=Shelly Wall Display
                                    # gen: 0 = GEN1, 1 = GEN 2+
                                    if plugin_options['sensor_type'][i] == 11:
                                        if plugin_options['gen_type'][i] == 0:
                                            name = plugin_options['sensor_label'][i]
                                            msg_info += _('{}: GEN1 not available yet \n').format(name)
                                        if plugin_options['gen_type'][i] == 1:
                                            name = plugin_options['sensor_label'][i]
                                            if plugin_options['reading_type'][i] == 1:  # only cloud API data
                                                try:
                                                    isok = response_data["isok"]
                                                except:
                                                    isok = False
                                                    log.error(NAME, _('Shelly Cloud Integration plugin') + ':\n' + traceback.format_exc())
                                            else:
                                                isok = True
                                            err = ""
                                            if not isok:
                                                try:
                                                    errors = response_data["errors"]["device_not_found"]
                                                    err = _('Your device has not been connected to the cloud!')
                                                except:
                                                    err = _('Unknown')
                                                    pass
                                                msg += _('[{}: Error] ').format(name)
                                                msg_info += _('{}: Error: {}\n').format(name, err)
                                            else:
                                                if plugin_options['reading_type'][i] == 1:  # only cloud API data
                                                    illuminance = response_data["data"]["device_status"]["illuminance:0"]["lux"]  # ex: 5 lux
                                                    temperature = response_data["data"]["device_status"]["temperature:0"]["tC"]   # ex: 18.3 C
                                                    humidity = response_data["data"]["device_status"]["humidity:0"]["rh"]         # ex: 46 % 
                                                    output = response_data["data"]["device_status"]["switch:0"]["output"]         # ex: false
                                                    Input = response_data["data"]["device_status"]["input:0"]["state"]            # ex: false
                                                    updated = now()
                                                    online = response_data["data"]["online"]
                                                    wifi = response_data["data"]["device_status"]["wifi"]
                                                    sta_ip = wifi["sta_ip"]
                                                    rssi = wifi["rssi"]
                                                else:                                       # via local IP data (not supported)
                                                    illuminance = 0
                                                    temperature = 0
                                                    humidity = 0
                                                    output = 0
                                                    Input = 0
                                                    updated = now()
                                                    online = False
                                                    wifi = 0
                                                    sta_ip = 0
                                                    rssi = 0
                                                if online:
                                                    if output:
                                                        msg += _('[{}: ON {} °C {} RV {} Lx] ').format(name, round(temperature, 2), humidity, illuminance)
                                                        msg_info += _('{}: ON {} °C {} RV {} Lx IP:{} RSSI:{} dbm {}\n').format(name, round(temperature, 2), humidity, illuminance, sta_ip, rssi, format_timestamp(updated))
                                                    else:
                                                        msg += _('[{}: OFF {} °C {} RV {} Lx] ').format(name, round(temperature, 2), humidity, illuminance)
                                                        msg_info += _('{}: OFF {} °C {} RV {} Lx IP:{} RSSI:{} dbm {}\n').format(name, round(temperature, 2), humidity, illuminance, sta_ip, rssi, format_timestamp(updated))
                                                else:
                                                    msg += _('[{}: -] ').format(name)
                                                    msg_info += _('{}: OFFLINE\n').format(name)
                                                payload = {
                                                    'id': id,
                                                    'ip': sta_ip,
                                                    'voltage': 0,
                                                    'battery': 0,
                                                    'temperature': [round(temperature, 2)],
                                                    'humidity': [humidity],
                                                    'illuminance': [illuminance],
                                                    'rssi': rssi,
                                                    'output': [output],
                                                    'power': [],
                                                    'retpower': [],
                                                    'label': name,
                                                    'online': online,
                                                    'updated': updated,
                                                    'gen': _('GEN1') if plugin_options['gen_type'][i]==0 else _('GEN2+'),
                                                    'hw': _('Shelly Wall Display'),
                                                    'hw_nbr': plugin_options['sensor_type'][i]
                                                }
                                                update_or_add_device(self, payload)

                                except JSONDecodeError:
                                    self._mark_request_failure(id, 60)
                                    msg += _('[{}: ERROR] ').format(plugin_options['sensor_label'][i])
                                    msg_info += _('{}: Error: Bad JSON\n').format(plugin_options['sensor_label'][i])

                            except exceptions.InvalidURL as e:
                                self._mark_request_failure(id, 300)
                                if "No host supplied" in str(e):
                                    response = None
                                    msg += _('[{}: ERROR] ').format(plugin_options['sensor_label'][i])
                                    msg_info += _('{}: Error: The URL entered is invalid, no host was specified\n').format(plugin_options['sensor_label'][i])
                                else:
                                    response = None
                                    msg += _('[{}: ERROR] ').format(plugin_options['sensor_label'][i])
                                    msg_info += _('{}: Error: {}\n').format(plugin_options['sensor_label'][i], e)
                            except exceptions.RequestException as e:
                                self._mark_request_failure(id, 60)
                                response = None
                                msg += _('[{}: ERROR] ').format(plugin_options['sensor_label'][i])
                                msg_info += _('{}: Error: {}\n').format(plugin_options['sensor_label'][i], e)
                            finally:
                                if response is not None:
                                    response.close()

                    self._write_status(msg_info)
                    if plugin_options['use_footer']:
                        if in_footer is not None:
                            in_footer.val = msg.encode('utf8').decode('utf8')

                with health_lock:
                    health_state['last_cycle'] = time.time()
                self._sleep(plugin_options['request_interval'])   # The loop is executed every second

            except Exception:                                     # In the event of an error (the try did not turn out correctly), a callback is used to write where the error is
                message = traceback.format_exc().splitlines()[-1]
                with health_lock:
                    health_state['last_error'] = time.time()
                    health_state['last_error_message'] = message
                log.clear(NAME)
                log.error(NAME, _('Shelly Cloud Integration plugin') + ':\n' + traceback.format_exc())
                self._sleep(60)                                   # In case of an error, it is advisable to wait longer than 1 second

sender = None

################################################################################
# Helper functions:                                                            #
################################################################################
def _new_device_uid():
    return uuid.uuid4().hex


def _device_type_label(sensor_type):
    labels = {
        0: _('Shelly Plus HT'),
        1: _('Shelly Plus Plug S'),
        2: _('Shelly Pro 2PM'),
        3: _('Shelly 1PM Mini'),
        4: _('Shelly 2.5'),
        5: _('Shelly Pro 4PM'),
        6: _('Shelly 1 Mini'),
        7: _('Shelly 2PM Addon'),
        8: _('Shelly 1PM Addon'),
        9: _('Shelly HT'),
        10: _('Shelly Pro 3EM / Shelly 3EM-63T Gen3'),
        11: _('Shelly Wall Display'),
    }
    return labels.get(sensor_type, _('Unknown device'))


DEVICE_PREVIEWS = {
    '0': {'default': {'image': 'HT.webp', 'url': 'https://kb.shelly.cloud/knowledge-base/shelly-plus-h-t'}},
    '1': {
        '0': {'image': 'plugSgen1.webp', 'url': 'https://kb.shelly.cloud/knowledge-base/shelly-plug-s'},
        '1': {'image': 'plugSgen2.webp', 'url': 'https://kb.shelly.cloud/knowledge-base/shelly-plus-plug-s-1'},
    },
    '2': {'default': {'image': 'pro2pm.webp', 'url': 'https://kb.shelly.cloud/knowledge-base/shelly-pro-2pm-v1'}},
    '3': {'default': {'image': 'mini.webp', 'url': 'https://kb.shelly.cloud/knowledge-base/shelly-1pm-mini-gen3'}},
    '4': {'default': {'image': '25.webp', 'url': 'https://kb.shelly.cloud/knowledge-base/shelly-2-5'}},
    '5': {'default': {'image': 'pro4pm.webp', 'url': 'https://kb.shelly.cloud/knowledge-base/shelly-pro-4pm-v2'}},
    '6': {'default': {'image': '1Mini.webp', 'url': 'https://kb.shelly.cloud/knowledge-base/shelly-1-mini-gen3'}},
    '7': {'default': {'image': '2pmaddon.webp', 'url': 'https://kb.shelly.cloud/knowledge-base/shelly-plus-add-on'}},
    '8': {'default': {'image': 'addon.webp', 'url': 'https://kb.shelly.cloud/knowledge-base/shelly-plus-add-on'}},
    '9': {'default': {'image': 'HaT.webp', 'url': 'https://kb.shelly.cloud/knowledge-base/shelly-h-t'}},
    '10': {'default': {'image': 'pro3em.png', 'url': 'https://kb.shelly.cloud/knowledge-base/shelly-3em-63-gen3'}},
    '11': {'default': {'image': 'wallDisplay.png', 'url': 'https://kb.shelly.cloud/knowledge-base/shelly-wall-display'}},
}


def _device_preview(sensor_type, gen_type):
    choices = DEVICE_PREVIEWS.get(str(sensor_type), {})
    preview = choices.get(str(gen_type), choices.get('default', {}))
    result = dict(preview)
    if result.get('image'):
        result['image'] = '/plugins/shelly_cloud_integrator/static/images/' + result['image']
    return result


def _persist_devices(devices):
    """Persist legacy parallel lists in an order safe for the running worker."""
    serialized = serialize_devices(devices)
    old_count = int(plugin_options.get('number_sensors', 0) or 0)
    new_count = serialized['number_sensors']
    if new_count < old_count:
        plugin_options['number_sensors'] = new_count
    for field, values in serialized.items():
        if field != 'number_sensors' and plugin_options.get(field) != values:
            plugin_options[field] = values
    if new_count >= old_count and old_count != new_count:
        plugin_options['number_sensors'] = new_count


def configured_devices():
    devices = normalize_devices(dict(plugin_options), _new_device_uid)
    _persist_devices(devices)
    view = str(plugin_options.get('device_view', 'cards')).lower()
    if view not in ('cards', 'list'):
        view = 'cards'
        plugin_options['device_view'] = view
    return devices


def _device_for_template(device):
    result = dict(device)
    result['type_label'] = _device_type_label(result['sensor_type'])
    result['source_label'] = _('Shelly cloud API') if result['reading_type'] == 1 else _('Locally via IP')
    result['state_label'] = _('Enabled') if result['use_sensor'] else _('Disabled')
    result['preview'] = _device_preview(result['sensor_type'], result['gen_type'])
    return result


def _form_integer(qdict, key, default, minimum, maximum):
    try:
        value = int(qdict.get(key, default))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _device_from_form(qdict, uid):
    sensor_type = _form_integer(qdict, 'sensor_type', 0, 0, 11)
    reading_type = _form_integer(qdict, 'reading_type', 1, 0, 1)
    if sensor_type in (0, 9):
        reading_type = 1
    return {
        'device_uid': uid,
        'use_sensor': qdict.get('use_sensor') == 'on',
        'sensor_label': str(qdict.get('sensor_label', '')).strip(),
        'sensor_id': str(qdict.get('sensor_id', '')).strip(),
        'sensor_type': sensor_type,
        'gen_type': _form_integer(qdict, 'gen_type', 1, 0, 1),
        'addons_labels_1': str(qdict.get('addons_labels_1', '')).strip(),
        'addons_labels_2': str(qdict.get('addons_labels_2', '')).strip(),
        'addons_labels_3': str(qdict.get('addons_labels_3', '')).strip(),
        'addons_labels_4': str(qdict.get('addons_labels_4', '')).strip(),
        'addons_labels_5': str(qdict.get('addons_labels_5', '')).strip(),
        'reading_type': reading_type,
        'sensor_ip': str(qdict.get('sensor_ip', '')).strip(),
    }


def _invalidate_cached_devices(device_ids):
    if sender is None:
        return
    ids = {device_id for device_id in device_ids if device_id}
    if ids:
        sender.devices[:] = [device for device in sender.devices if device.get('id') not in ids]
        for device_id in ids:
            sender._next_request_time.pop(device_id, None)
            sender._request_failures.pop(device_id, None)


def start():                                                      # This function starts the plugin core
    global sender
    if sender is None:
        configured_devices()
        sender = Sender()


def stop():                                                       # This function stops the plugin core
    global sender
    if sender is not None:
        sender.stop()
        sender._session.close()
        sender.join(15)
        if sender.is_alive():
            log.error(NAME, _('The plug-in worker did not stop within the timeout.'))
        else:
            sender = None


def health():
    """Return configured Shelly device and worker state without credentials."""
    with health_lock:
        state = dict(health_state)
    worker_running = sender is not None and sender.is_alive()
    devices = list(sender.devices) if sender is not None else []
    configured = sum(
        1 for enabled in plugin_options['use_sensor'][:plugin_options['number_sensors']]
        if enabled
    )
    online = sum(1 for device in devices if device.get('online'))
    details = {
        _('Worker thread'): _('Running') if worker_running else _('Stopped'),
        _('Cloud authorization configured'): (
            _('Yes') if len(plugin_options['auth_key']) > 5 else _('No')
        ),
        _('Shelly server'): plugin_options['server_uri'] or _('Not configured'),
        _('Configured devices'): configured,
        _('Loaded devices'): len(devices),
        _('Online devices'): online,
        _('Devices in retry backoff'): (
            len(sender._request_failures) if sender is not None else 0
        ),
        _('Last successful cycle'): (
            datetime_string(time.localtime(state['last_cycle']))
            if state['last_cycle'] else _('Not available')
        ),
        _('Last successful device request'): (
            datetime_string(time.localtime(state['last_success']))
            if state['last_success'] else _('Not available')
        ),
    }
    if state['last_error_message']:
        details[_('Last error')] = state['last_error_message']
    if not worker_running:
        return {
            'status': 'error',
            'summary': _('Shelly Cloud Integration worker is not running.'),
            'details': details,
        }
    if configured == 0:
        return {
            'status': 'unknown',
            'summary': _('No Shelly devices are enabled.'),
            'details': details,
        }
    if state['last_error'] and state['last_error'] >= state['last_success']:
        return {
            'status': 'warning',
            'summary': state['last_error_message'],
            'details': details,
        }
    if not state['last_success']:
        return {
            'status': 'unknown',
            'summary': _('Shelly Cloud Integration is waiting for its first device response.'),
            'details': details,
        }
    if online < len(devices):
        return {
            'status': 'warning',
            'summary': _('One or more loaded Shelly devices are offline.'),
            'details': details,
        }
    return {
        'status': 'ok',
        'summary': _('Shelly Cloud Integration is responding.'),
        'details': details,
    }


def mobile_status():
    result = health()
    with health_lock:
        updated = health_state.get('last_success', 0)
    return {
        'status': result.get('status', 'unknown'),
        'title': _('Shelly Cloud Integration'),
        'summary': result.get('summary', ''),
        'updated': datetime_string(time.localtime(updated)) if updated else '',
    }


def mobile_cards(**_kwargs):
    """Expose only cached device readings; never credentials or controls."""
    devices = [dict(device) for device in (sender.devices if sender is not None else [])]
    cards = []
    fields = (
        ('temperature', _('Temperature'), '°{}'.format(options.temp_unit)),
        ('humidity', _('Humidity'), '%'),
        ('illuminance', _('Illuminance'), 'lx'),
        ('power', _('Power'), 'W'),
        ('retpower', _('Returned power'), 'W'),
        ('voltage', _('Voltage'), 'V'),
        ('battery', _('Battery'), '%'),
        ('rssi', _('Wi-Fi signal'), 'dBm'),
    )
    for device in devices:
        metrics = [
            {'id': 'state', 'label': _('State'),
             'value': _('Online') if device.get('online') else _('Offline'), 'unit': ''},
        ]
        if device.get('hw'):
            metrics.append({'id': 'model', 'label': _('Model'),
                            'value': device.get('hw'), 'unit': ''})
        if device.get('ip'):
            metrics.append({'id': 'ip_address', 'label': _('IP address'),
                            'value': device.get('ip'), 'unit': ''})
        if device.get('updated'):
            metrics.append({'id': 'updated', 'label': _('Updated'),
                            'value': format_timestamp(device.get('updated')), 'unit': ''})
        for key, label, unit in fields:
            value = device.get(key)
            values = value if isinstance(value, list) else [value]
            for index, item in enumerate(values):
                if item in (None, '') or (key in ('voltage', 'battery') and item == 0):
                    continue
                metric_label = '{} {}'.format(label, index + 1) if len(values) > 1 else label
                metrics.append({'id': '{}_{}'.format(key, index), 'label': metric_label,
                                'value': item, 'unit': unit})
        if device.get('output'):
            for index, output in enumerate(device['output']):
                metrics.append({'id': 'output_{}'.format(index),
                                'label': '{} {}'.format(_('Output'), index + 1),
                                'value': _('On') if output else _('Off'), 'unit': ''})
        cards.append({
            'id': 'device_{}'.format(device.get('id', len(cards))),
            'title': device.get('label') or device.get('hw') or _('Shelly device'),
            'metrics': metrics,
            'series': [],
        })
    return cards


def safe_settings_json():
    data = dict(plugin_options)
    if data.get('auth_key'):
        data['auth_key'] = '********'
    return data


def format_timestamp(timestamp):                                  # Convert timestamp (ex: 1735731059.4796138 to "01.01.2025 12:10:10")
    dt = datetime.datetime.utcfromtimestamp(timestamp)            # Using UTC time
    return dt.strftime("%d.%m.%Y %H:%M:%S")


def update_or_add_device(self, payload):                          # Add or update payload to devices
    # Find exist device by ID
    for device in self.devices:
        if device['id'] == payload['id']:
            # update all values device hodnoty zaĹ™Ă­zenĂ­
            device.update(payload)
            return
    # If device not exist add to list
    self.devices.append(payload)


################################################################################
# Web pages:                                                                   #
################################################################################

class status_page(ProtectedPage):
    """Load an html page for entering adjustments."""

    def GET(self):
        global sender
        qdict = web.input()
        reset = get_input(qdict, 'reset', False, lambda x: True)
        if sender is not None and reset:
            verify_csrf(qdict)
            sender.devices.clear()
            log.debug(NAME, _('Reseting device list.'))
            msg = _('The list of loaded devices has been cleared. Once the Shelly cloud integrator extension reloads all devices, they will appear in the list again (depending on the request interval set in the extension. For example, 20 seconds).')
            return self.core_render.notice('/sensors?search', msg)

        return self.plugin_render.shelly_cloud_integration(log.events(NAME))


class sensors_page(ProtectedPage):
    """Manage global options and individual Shelly devices."""

    def GET(self):
        try:
            qdict = web.input()
            devices = configured_devices()
            action = str(qdict.get('action', ''))
            editor = None
            is_new = False
            if action == 'add':
                editor = default_device(_new_device_uid())
                is_new = True
            elif action == 'edit':
                requested_uid = str(qdict.get('device', ''))
                editor = next(
                    (dict(device) for device in devices if device['device_uid'] == requested_uid),
                    None,
                )
            msg = str(qdict.get('msg', 'none'))
            if msg not in ('none', 'saved', 'view_saved', 'added', 'updated', 'deleted', 'not_found'):
                msg = 'none'
            return self.plugin_render.shelly_cloud_integration_devices(
                plugin_options,
                msg,
                [_device_for_template(device) for device in devices],
                editor,
                is_new,
                DEVICE_PREVIEWS,
            )

        except Exception:
            log.error(NAME, _('Shelly Cloud Integration plugin') + ':\n' + traceback.format_exc())
            msg = _('An internal error was found in the system, see the error log for more information. The error is in part:') + ' '
            msg += _('shelly_cloud -> sensors_page GET')
            return self.core_render.notice('/', msg)

    def POST(self):
        try:
            qdict = web.input()
            verify_csrf(qdict)
            action = str(qdict.get('action', 'save_global'))
            devices = configured_devices()
            message = 'saved'

            if action == 'save_global':
                plugin_options['request_interval'] = _form_integer(
                    qdict, 'request_interval', 5, 5, 86400)
                plugin_options['auth_key'] = str(qdict.get('auth_key', '')).strip()
                plugin_options['server_uri'] = str(qdict.get('server_uri', '')).strip()
                plugin_options['use_footer'] = qdict.get('use_footer') == 'on'
            elif action == 'set_view':
                requested_view = str(qdict.get('device_view', 'cards')).lower()
                plugin_options['device_view'] = requested_view if requested_view in ('cards', 'list') else 'cards'
                message = 'view_saved'
            elif action == 'save_device':
                requested_uid = str(qdict.get('device_uid', '')).strip()
                existing = next(
                    (device for device in devices if device['device_uid'] == requested_uid),
                    None,
                )
                uid = existing['device_uid'] if existing is not None else _new_device_uid()
                old_id = existing.get('sensor_id', '') if existing is not None else ''
                device = _device_from_form(qdict, uid)
                devices, created = upsert_device(devices, device)
                _persist_devices(devices)
                _invalidate_cached_devices((old_id, device['sensor_id']))
                message = 'added' if created else 'updated'
            elif action == 'delete_device':
                requested_uid = str(qdict.get('device_uid', '')).strip()
                existing = next(
                    (device for device in devices if device['device_uid'] == requested_uid),
                    None,
                )
                devices, deleted = delete_device(devices, requested_uid)
                if deleted:
                    _persist_devices(devices)
                    _invalidate_cached_devices((existing.get('sensor_id', '') if existing else '',))
                    message = 'deleted'
                else:
                    message = 'not_found'
            else:
                raise ValueError('unknown_settings_action')

            if sender is not None:
                sender.update()
            raise web.seeother(plugin_url(sensors_page) + '?msg=' + message, True)

        except web.SeeOther:
            raise
        except Exception:
            log.error(NAME, _('Shelly Cloud Integration plugin') + ':\n' + traceback.format_exc())
            msg = _('An internal error was found in the system, see the error log for more information. The error is in part:') + ' '
            msg += _('shelly_cloud -> sensors_page POST')
            return self.core_render.notice('/', msg)


class help_page(ProtectedPage):
    """Load an html page for help"""

    def GET(self):
        try:
            return self.plugin_render.shelly_cloud_integration_help()

        except:
            log.error(NAME, _('Shelly Cloud Integration plugin') + ':\n' + traceback.format_exc())
            msg = _('An internal error was found in the system, see the error log for more information. The error is in part:') + ' '
            msg += _('shelly_cloud -> help_page GET')
            return self.core_render.notice('/', msg)


class status_json(ProtectedPage):
    """Returns the current status log in JSON format."""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Cache-Control', 'no-store')
        web.header('Content-Type', 'application/json')
        try:
            return json.dumps({'events': log.events(NAME)})
        except:
            return json.dumps({'events': []})


class settings_json(ProtectedPage):
    """Returns plugin settings in JSON format."""
    """Try in web browser: OSPy/plugin_name/settings_json"""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        try:
            return json.dumps(safe_settings_json())
        except:
            return {}


class ShellyDevices(ProtectedPage):
    global sender
    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        try:
            return json.dumps(sender.devices)
        except:
            return {}


class _ShellyDevices():
    global sender
    def __init__(self):
        super(_ShellyDevices, self).__init__()

    def devices(self):
        return list(sender.devices) if sender is not None else []

    def configured(self):
        return [
            {
                'id': device.get('sensor_id', ''),
                'label': device.get('sensor_label', ''),
                'enabled': bool(device.get('use_sensor', False)),
                'type': int(device.get('sensor_type', 0)),
            }
            for device in configured_devices()
        ]

shelly_devices = _ShellyDevices()
