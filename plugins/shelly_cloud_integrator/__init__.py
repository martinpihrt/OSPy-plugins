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
from ospy.helpers import datetime_string, now                    # For using date time in events logs
from ospy.webpages import ProtectedPage                          # For check user login permissions

from ospy.webpages import showInFooter                           # Enable plugin to display readings in UI footer

from requests import get, exceptions
from json.decoder import JSONDecodeError

import datetime


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
        'use_sensor': [False, False],                            # Enable or disable shelly in OSPy system
        'sensor_label': ['label', 'label'],                      # The server URL where all the devices and client accounts are located. This can be obtained from Shelly > User Settings > Cloud Authorization Key.
        'sensor_id': ['', ''],                                   # Shelly ID. This can be obtained from Shelly > User Settings > Cloud Authorization Key
        'sensor_type': [0, 1],                                   
         # 0=Shelly Plus HT, 1=Shelly Plus Plug S,
         # 2=Shelly Pro 2PM, 3=Shelly 1PM Mini,
         # 4=Shelly 2.5, 5=Shelly Pro 4PM,
         # 6=Shelly 1 Mini, 7=Shelly 2PM Addon,
         # 8=Shelly 1PM Addon, 9= Shelly H&T
        'gen_type': [0, 1],                                      # 0=Gen1, 1=Gen2
        'number_sensors': 2,                                     # default 2 sensors for example
        'addons_labels_1': [_('A')],                             # label for addons temperature:100 (DS18B20 nr1)
        'addons_labels_2': [_('B')],                             # label for addons temperature:101
        'addons_labels_3': [_('C')],                             # label for addons temperature:101
        'addons_labels_4': [_('D')],                             # label for addons temperature:101
        'addons_labels_5': [_('E')],                             # label for addons temperature:101 (DS18B20 nr5)
        'reading_type': [1]*20,                                  # 0=Locally via IP, 1=Shelly cloud API
        'sensor_ip': ['']*20,
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
        self.devices = []
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
            in_footer.button = 'shelly_cloud_integrator/status'   # Button redirect on footer
            in_footer.label =  _('Shelly Cloud Integration')      # Label on footer
        
        log.clear(NAME)                                           # Clear events window on webpage
        log.info(NAME, _('Plugin is started.'))                   # Save to log (to OSPy log if logging is enabled) and events window on webpage

        while not self._stop_event.is_set():                      # Plugin repeating loop
            try:                                                  # It is a good idea to use try and except because it is possible to debug any errors encountered in the plugin.
                log.clear(NAME)
                msg = ''
                msg_info = ''
                if len(plugin_options['auth_key']) > 10 and len(plugin_options['server_uri']) > 10:
                    for i in range(0, plugin_options['number_sensors']):
                        id = plugin_options['sensor_id'][i]
                        if len(id) > 5 and plugin_options['use_sensor'][i]:
                            if plugin_options['reading_type'][i] == 1:      # 0=Locally via IP, 1=Shelly cloud API
                                url = 'https://{}/device/status?auth_key={}&id={}'.format(plugin_options['server_uri'], plugin_options['auth_key'], id)
                            else:
                                if plugin_options['gen_type'][i] == 0:      # gen1 device. url=http://IP/status
                                    url = 'http://{}/status'.format(plugin_options['sensor_ip'][i])
                                else:                                       # gen2+ device. url=http://IP/rpc/Shelly.GetStatus
                                    url = 'http://{}/rpc/Shelly.GetStatus'.format(plugin_options['sensor_ip'][i])
                            try:
                                response = get(url, timeout=5)
                                if response.status_code == 401:
                                    if plugin_options['reading_type'][i] == 1:
                                        log.error(NAME, _('Shelly Cloud Bad Login'))
                                    else:
                                        log.error(NAME, _('Locally Bad Login to device'))
                                elif response.status_code == 404:
                                    if plugin_options['reading_type'][i] == 1:
                                        log.error(NAME, _('Shelly Cloud Not Found'))
                                    else:
                                        log.error(NAME, _('Device Not Found'))

                                try:
                                    response_data = response.json()
                                    # typ: 0 = Shelly Plus HT, 
                                    # gen: 0 = GEN1, 1 = GEN 2+
                                    if plugin_options['sensor_type'][i] == 0:
                                        if plugin_options['gen_type'][i] == 0:
                                            name = plugin_options['sensor_label'][i]
                                            msg_info += _('{}: GEN1 not available \n').format(name)
                                        if plugin_options['gen_type'][i] == 1:
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
                                                    'rssi': rssi,
                                                    'output': [],
                                                    'power': [],
                                                    'label': name,
                                                    'online': online,
                                                    'updated': updated
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
                                                    'rssi': rssi,
                                                    'output': [output],
                                                    'power': [power],
                                                    'label': name,
                                                    'online': online,
                                                    'updated': updated,
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
                                                    'rssi': rssi,
                                                    'output': [output],
                                                    'power': [power],
                                                    'label': name,
                                                    'online': online,
                                                    'updated': updated
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
                                                        msg += _('[{}: 1 ON {} W ({} kW/h) ').format(name, a_power, round(a_total/1000.0, 2))
                                                        msg_info += _('{}: 1 ON {} W ({} kW/h) {} V IP:{} RSSI:{} dbm ').format(name, a_power, round(a_total/1000.0, 2), a_voltage, sta_ip, rssi)
                                                    else:
                                                        msg += _('[{}: 1 OFF {}W ({}kW/h) ').format(name, a_power, round(a_total/1000.0, 2))
                                                        msg_info += _('{}: 1 OFF {} W ({} kW/h) {} V IP:{} RSSI:{} dbm ').format(name, a_power, round(a_total/1000.0, 2), a_voltage, sta_ip, rssi)    
                                                    if b_output:
                                                        msg += _('2 ON {} W ({} kW/h)] ').format(b_power, round(b_total/1000.0, 2))
                                                        msg_info += _('2 ON {} W ({} kW/h) {}V {}\n').format(b_power, round(b_total/1000.0, 2), b_voltage, format_timestamp(updated))
                                                    else:
                                                        msg += _('2 OFF {} W ({} kW/h)] ').format(b_power, round(b_total/1000.0, 2))
                                                        msg_info += _('2 OFF {} W ({} kW/h) {}V {}\n').format(b_power, round(b_total/1000.0, 2), b_voltage, format_timestamp(updated))
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
                                                    'rssi': rssi,
                                                    'output': [a_output, b_output],
                                                    'power': [a_power, b_power],
                                                    'label': name,
                                                    'online': online,
                                                    'updated': updated
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
                                                    'rssi': rssi,
                                                    'output': [output],
                                                    'power': [power],
                                                    'label': name,
                                                    'online': online,
                                                    'updated': updated
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
                                                            msg += _('[{}: 1 ON {} W ({} kW/h) ').format(name, a_power, round(a_total/1000.0, 2))
                                                            msg_info += _('{}: 1 ON {} W ({} kW/h) {} V IP:{} RSSI:{} dbm ').format(name, a_power, round(a_total/1000.0, 2), a_voltage, sta_ip, rssi)
                                                        else:
                                                            msg += _('[{}: 1 OFF {} W ({} kW/h) ').format(name, a_power, round(a_total/1000.0, 2))
                                                            msg_info += _('{}: 1 OFF {} W ({} kW/h) {} V IP:{} RSSI:{} dbm ').format(name, a_power, round(a_total/1000.0, 2), a_voltage, sta_ip, rssi)    
                                                        if b_output:
                                                            msg += _('2 ON {} W ({} kW/h)] ').format(b_power, round(b_total/1000.0, 2))
                                                            msg_info += _('2 ON {} W ({} kW/h) {}\n').format(b_power, round(b_total/1000.0, 2), format_timestamp(updated))
                                                        else:
                                                            msg += _('2 OFF {} W ({} kW/h)] ').format(b_power, round(b_total/1000.0, 2))
                                                            msg_info += _('2 OFF {} W ({} kW/h) {}\n').format(b_power, round(b_total/1000.0, 2), format_timestamp(updated))
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
                                                    'rssi': rssi,
                                                    'output': [a_output, b_output] if roller is None else [roller],
                                                    'power': [a_power, b_power],
                                                    'label': name,
                                                    'online': online,
                                                    'updated': updated
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
                                                    if a_output:
                                                        msg += _('[{}: 1 ON {} W ({} kW/h) ').format(name, a_power, round(a_total/1000.0, 2))
                                                        msg_info += _('{}: 1 ON {} W ({} kW/h) {} V IP:{} RSSI:{} dbm ').format(name, a_power, round(a_total/1000.0, 2), voltage, sta_ip, rssi)
                                                    else:
                                                        msg += _('[{}: 1 OFF {} W ({} kW/h) ').format(name, a_power, round(a_total/1000.0, 2))
                                                        msg_info += _('{}: 1 OFF {} W ({} kW/h) {} V IP:{} RSSI:{} dbm ').format(name, a_power, round(a_total/1000.0, 2), voltage, sta_ip, rssi)
                                                    if b_output:
                                                        msg += _('2 ON {} W ({} kW/h)] ').format(b_power, round(b_total/1000.0, 2))
                                                        msg_info += _('2 ON {} W ({} kW/h) ').format(b_power, round(b_total/1000.0, 2))
                                                    else:
                                                        msg += _('2 OFF {} W ({} kW/h)] ').format(b_power, round(b_total/1000.0, 2))
                                                        msg_info += _('2 OFF {} W ({} kW/h) ').format(b_power, round(b_total/1000.0, 2))
                                                    if c_output:
                                                        msg += _('2 ON {} W ({} kW/h)] ').format(c_power, round(c_total/1000.0, 2))
                                                        msg_info += _('2 ON {} W ({} kW/h) ').format(c_power, round(c_total/1000.0, 2))
                                                    else:
                                                        msg += _('2 OFF {}W ({}kW/h)] ').format(c_power, round(c_total/1000.0, 2))
                                                        msg_info += _('2 OFF {}W ({}kW/h) ').format(c_power, round(c_total/1000.0, 2))
                                                    if d_output:
                                                        msg += _('2 ON {} W ({} kW/h)] ').format(d_power, round(d_total/1000.0, 2))
                                                        msg_info += _('2 ON {} W ({} kW/h) {}\n').format(d_power, round(d_total/1000.0, 2), format_timestamp(updated))
                                                    else:
                                                        msg += _('2 OFF {} W ({} kW/h)] ').format(d_power, round(d_total/1000.0, 2))
                                                        msg_info += _('2 OFF {} W ({} kW/h) {}\n').format(d_power, round(d_total/1000.0, 2), format_timestamp(updated))
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
                                                    'rssi': rssi,
                                                    'output': [a_output, b_output, c_output, d_output],
                                                    'power': [a_power, b_power, c_power, d_power],
                                                    'label': name,
                                                    'online': online,
                                                    'updated': updated
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
                                                    'rssi': rssi,
                                                    'output': [output],
                                                    'power': [],
                                                    'label': name,
                                                    'online': online,
                                                    'updated': updated
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
                                                        msg += _('[{}: 1 ON {} W ({} kW/h) ').format(name, a_power, round(a_total/1000.0, 2))
                                                        msg_info += _('{}: 1 ON {} W ({} kW/h) {} V IP:{} RSSI:{} dbm ').format(name, a_power, round(a_total/1000.0, 2), voltage, sta_ip, format_timestamp(updated))
                                                    else:
                                                        msg += _('[{}: 1 OFF {} W ({} kW/h) ').format(name, a_power, round(a_total/1000.0, 2))
                                                        msg_info += _('{}: 1 OFF {} W ({} kW/h) {} V IP:{} RSSI:{} dbm ').format(name, a_power, round(a_total/1000.0, 2), voltage, sta_ip, format_timestamp(updated))
                                                    if b_output:
                                                        msg += _('2 ON {} W ({} kW/h) ').format(b_power, round(b_total/1000.0, 2))
                                                        msg_info += _('2 ON {} W ({} kW/h) ').format(b_power, round(b_total/1000.0, 2))
                                                    else:
                                                        msg += _('2 OFF {} W ({} kW/h) ').format(b_power, round(b_total/1000.0, 2))
                                                        msg_info += _('2 OFF {} W ({} kW/h) ').format(b_power, round(b_total/1000.0, 2))
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
                                                    'rssi': rssi,
                                                    'output': [a_output, b_output],
                                                    'power': [a_power, b_power],
                                                    'label': name,
                                                    'online': online,
                                                    'updated': updated
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
                                                        msg += _('[{}: 1 ON {} W ({} kW/h) ').format(name, a_power, round(a_total/1000.0, 2))
                                                        msg_info += _('{}: 1 ON {} W ({} kW/h) {} V IP:{} RSSI:{} dbm ').format(name, a_power, round(a_total/1000.0, 2), voltage, sta_ip, format_timestamp(updated))
                                                    else:
                                                        msg += _('[{}: 1 OFF {} W ({} kW/h) ').format(name, a_power, round(a_total/1000.0, 2))
                                                        msg_info += _('{}: 1 OFF {} W ({} kW/h) {} V IP:{} RSSI:{} dbm ').format(name, a_power, round(a_total/1000.0, 2), voltage, sta_ip, format_timestamp(updated))
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
                                                    'rssi': rssi,
                                                    'output': [a_output],
                                                    'power': [a_power],
                                                    'label': name,
                                                    'online': online,
                                                    'updated': updated
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
                                                    'rssi': rssi,
                                                    'output': [],
                                                    'power': [],
                                                    'label': name,
                                                    'online': online,
                                                    'updated': updated
                                                }
                                                update_or_add_device(self, payload)

                                except JSONDecodeError:
                                    raise BadResponse(_('Bad JSON'))

                            except exceptions.InvalidURL as e:
                                if "No host supplied" in str(e):
                                    response = None
                                    msg += _('[{}: ERROR] ').format(plugin_options['sensor_label'][i])
                                    msg_info += _('{}: Error: The URL entered is invalid, no host was specified\n').format(plugin_options['sensor_label'][i])
                                else:
                                    response = None
                                    msg += _('[{}: ERROR] ').format(plugin_options['sensor_label'][i])
                                    msg_info += _('{}: Error: {}\n').format(plugin_options['sensor_label'][i], e)
                            except exceptions.RequestException as e:
                                response = None
                                msg += _('[{}: ERROR] ').format(plugin_options['sensor_label'][i])
                                msg_info += _('{}: Error: {}\n').format(plugin_options['sensor_label'][i], e)

                    log.info(NAME, datetime_string() + '\n{}'.format(msg_info))
                    if plugin_options['use_footer']:
                        if in_footer is not None:
                            in_footer.val = msg.encode('utf8').decode('utf8')

                self._sleep(plugin_options['request_interval'])   # The loop is executed every second

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


def format_timestamp(timestamp):                                  # Convert timestamp (ex: now() = 1735731059.4796138) to "01.01.2025 12:10"
    dt = datetime.datetime.fromtimestamp(timestamp)
    return dt.strftime("%d.%m.%Y %H:%M")


def update_or_add_device(self, payload):                          # Add or update payload to devices
    # Find exist device by ID
    for device in self.devices:
        if device['id'] == payload['id']:
            # update all values device hodnoty zařízení
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
        try:
            return self.plugin_render.shelly_cloud_integration(log.events(NAME))

        except:
            log.error(NAME, _('Shelly Cloud Integration plugin') + ':\n' + traceback.format_exc())
            msg = _('An internal error was found in the system, see the error log for more information. The error is in part:') + ' '
            msg += _('shelly_cloud -> status_page GET')
            return self.core_render.notice('/', msg)


class sensors_page(ProtectedPage):
    """Load an html page for entering adjustments."""

    def GET(self):
        try:
            msg = 'none'
            return self.plugin_render.shelly_cloud_integration_sensors(plugin_options, msg)

        except:
            log.error(NAME, _('Shelly Cloud Integration plugin') + ':\n' + traceback.format_exc())
            msg = _('An internal error was found in the system, see the error log for more information. The error is in part:') + ' '
            msg += _('shelly_cloud -> sensors_page GET')
            return self.core_render.notice('/', msg)

    def POST(self):
        try:
            qdict = web.input()

            if 'number_sensors' in qdict:
                plugin_options.__setitem__('number_sensors', int(qdict['number_sensors']))
            if 'request_interval' in qdict:
                plugin_options.__setitem__('request_interval', int(qdict['request_interval']))
            if 'auth_key' in qdict:
                plugin_options.__setitem__('auth_key', qdict['auth_key'])
            if 'server_uri' in qdict:
                plugin_options.__setitem__('server_uri', qdict['server_uri'])

            if 'use_footer' in qdict:
                if qdict['use_footer']=='on':
                    plugin_options.__setitem__('use_footer', True)
                else:
                    plugin_options.__setitem__('use_footer', False)


            commands = {
                'sensor_type': [],
                'gen_type': [],
                'use_sensor': [],
                'sensor_label': [],
                'sensor_id': [],
                'addons_labels_1': [],
                'addons_labels_2': [],
                'addons_labels_3': [],
                'addons_labels_4': [],
                'addons_labels_5': [],
                'reading_type': [],
                'sensor_ip': [],
                }

            for i in range(0, plugin_options['number_sensors']):
                if 'sensor_type'+str(i) in qdict:
                    commands['sensor_type'].append(int(qdict['sensor_type'+str(i)]))
                else:
                    commands['sensor_type'].append(int(0))

                if 'gen_type'+str(i) in qdict:
                    commands['gen_type'].append(int(qdict['gen_type'+str(i)]))
                else:
                    commands['gen_type'].append(int(0))

                if 'use_sensor'+str(i) in qdict:
                    if qdict['use_sensor'+str(i)]=='on':
                        commands['use_sensor'].append(True)
                else:
                    commands['use_sensor'].append(False)

                if 'sensor_label'+str(i) in qdict:
                    commands['sensor_label'].append(qdict['sensor_label'+str(i)])
                else:
                    commands['sensor_label'].append('')

                if 'sensor_id'+str(i) in qdict:
                    commands['sensor_id'].append(qdict['sensor_id'+str(i)])
                else:
                    commands['sensor_id'].append('')

                if 'addons_labels_1'+str(i) in qdict:
                    commands['addons_labels_1'].append(qdict['addons_labels_1'+str(i)])
                else:
                    commands['addons_labels_1'].append('')

                if 'addons_labels_2'+str(i) in qdict:
                    commands['addons_labels_2'].append(qdict['addons_labels_2'+str(i)])
                else:
                    commands['addons_labels_2'].append('')

                if 'addons_labels_3'+str(i) in qdict:
                    commands['addons_labels_3'].append(qdict['addons_labels_3'+str(i)])
                else:
                    commands['addons_labels_3'].append('')

                if 'addons_labels_4'+str(i) in qdict:
                    commands['addons_labels_4'].append(qdict['addons_labels_4'+str(i)])
                else:
                    commands['addons_labels_4'].append('')

                if 'addons_labels_5'+str(i) in qdict:
                    commands['addons_labels_5'].append(qdict['addons_labels_5'+str(i)])
                else:
                    commands['addons_labels_5'].append('')

                if 'reading_type'+str(i) in qdict:
                    commands['reading_type'].append(int(qdict['reading_type'+str(i)]))
                else:
                    commands['reading_type'].append(int(1))

                if 'sensor_ip'+str(i) in qdict:
                    commands['sensor_ip'].append(qdict['sensor_ip'+str(i)])
                else:
                    commands['sensor_ip'].append('')                    

            plugin_options.__setitem__('sensor_type', commands['sensor_type'])
            plugin_options.__setitem__('gen_type', commands['gen_type'])
            plugin_options.__setitem__('use_sensor', commands['use_sensor'])
            plugin_options.__setitem__('sensor_label', commands['sensor_label'])
            plugin_options.__setitem__('sensor_id', commands['sensor_id'])
            plugin_options.__setitem__('addons_labels_1', commands['addons_labels_1'])
            plugin_options.__setitem__('addons_labels_2', commands['addons_labels_2'])
            plugin_options.__setitem__('addons_labels_3', commands['addons_labels_3'])
            plugin_options.__setitem__('addons_labels_4', commands['addons_labels_4'])
            plugin_options.__setitem__('addons_labels_5', commands['addons_labels_5'])
            plugin_options.__setitem__('reading_type', commands['reading_type'])
            plugin_options.__setitem__('sensor_ip', commands['sensor_ip'])

            if sender is not None:
                sender.update()

            msg = 'saved'
            return self.plugin_render.shelly_cloud_integration_sensors(plugin_options, msg)

        except:
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


class settings_json(ProtectedPage):
    """Returns plugin settings in JSON format."""
    """Try in web browser: OSPy/plugin_name/settings_json"""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        try:
            return json.dumps(plugin_options)
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
        return sender.devices

shelly_devices = _ShellyDevices()