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

from requests import get
from json.decoder import JSONDecodeError

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
         # 6=Shelly 1 Mini
        'gen_type': [0, 1],                                      # 0=Gen1, 1=Gen2
        'number_sensors': 2,                                     # default 2 sensors for example
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
                            url = 'https://{}/device/status?auth_key={}&id={}'.format(plugin_options['server_uri'], plugin_options['auth_key'], id)
                            try:
                                response = get(url, timeout=5)
                                if response.status_code == 401:
                                    log.error(NAME, _('Shelly Cloud Bad Login'))
                                elif response.status_code == 404:
                                    log.error(NAME, _('Shelly Cloud Not Found'))
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
                                            temperature = response_data["data"]["device_status"]["temperature:0"]["tC"]
                                            humidity = response_data["data"]["device_status"]["humidity:0"]["rh"]
                                            updated = response_data["data"]["device_status"]["_updated"]
                                            isok = response_data["isok"]
                                            battery = response_data["data"]["device_status"]["devicepower:0"]["battery"]
                                            online = response_data["data"]["online"]
                                            wifi = response_data["data"]["device_status"]["wifi"]
                                            sta_ip = wifi["sta_ip"]
                                            rssi = wifi["rssi"]
                                            batt_V = battery["V"]
                                            batt_perc = battery["percent"]
                                            if online:
                                                msg += _('[{}: {}°C {}RV] ').format(name, temperature, humidity, batt_perc)
                                                msg_info += _('{}: {}°C {}RV BAT{}% IP:{} RSSI:{}dbm {}\n').format(name, temperature, humidity, batt_perc, sta_ip, rssi, str(updated))
                                            else:
                                                msg += _('[{}: OFFLINE] ').format(name)
                                                msg_info += _('{}: OFFLINE\n').format(name)

                                    # typ: 1=Shelly Plus Plug S ver 1
                                    # gen: 0 = GEN1, 1 = GEN 2+
                                    if plugin_options['sensor_type'][i] == 1:
                                        if plugin_options['gen_type'][i] == 0:
                                            name = plugin_options['sensor_label'][i]
                                            updated = response_data["data"]["device_status"]["_updated"]
                                            isok = response_data["isok"]
                                            online = response_data["data"]["online"]
                                            wifi = response_data["data"]["device_status"]["wifi_sta"]
                                            sta_ip = wifi["ip"]
                                            rssi = wifi["rssi"]
                                            power = response_data["data"]["device_status"]["meters"][0]["power"]
                                            total = response_data["data"]["device_status"]["meters"][0]["total"]
                                            output = response_data["data"]["device_status"]["relays"][0]["ison"]
                                            if online:
                                                if output:
                                                    msg += _('[{}: ON {}W] ').format(name, power)
                                                    msg_info += _('{}: ON {}W IP:{} RSSI:{}dbm {}\n').format(name, power, sta_ip, rssi, updated)
                                                else:
                                                    msg += _('[{}: OFF {}W] ').format(name, power)
                                                    msg_info += _('{}: OFF {}W IP:{} RSSI:{}dbm {}\n').format(name, power, sta_ip, rssi, updated)
                                            else:
                                                msg += _('[{}: OFFLINE] ').format(name)
                                                msg_info += _('{}: OFFLINE\n').format(name)
                                        if plugin_options['gen_type'][i] == 1:
                                            name = plugin_options['sensor_label'][i]
                                            msg_info += _('{}: GEN2 not available yet \n').format(name)

                                    # typ: 2=Shelly Pro 2PM
                                    # gen: 0 = GEN1, 1 = GEN 2+
                                    if plugin_options['sensor_type'][i] == 2:
                                        if plugin_options['gen_type'][i] == 0:
                                            name = plugin_options['sensor_label'][i]
                                            msg_info += _('{}: GEN1 not available yet \n').format(name)
                                        if plugin_options['gen_type'][i] == 1:
                                            name = plugin_options['sensor_label'][i]
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
                                            updated = response_data["data"]["device_status"]["_updated"]
                                            isok = response_data["isok"]
                                            online = response_data["data"]["online"]
                                            wifi = response_data["data"]["device_status"]["wifi"]
                                            sta_ip = wifi["sta_ip"]
                                            rssi = wifi["rssi"]
                                            if online:
                                                if a_output:
                                                    msg += _('[{}: 1 ON {}W ({}kW/h) ').format(name, a_power, round(a_total/1000.0, 2))
                                                    msg_info += _('{}: 1 ON {}W ({}kW/h) {}V IP:{} RSSI:{}dbm ').format(name, a_power, round(a_total/1000.0, 2), a_voltage, sta_ip, rssi)
                                                else:
                                                    msg += _('[{}: 1 OFF {}W ({}kW/h) ').format(name, a_power, round(a_total/1000.0, 2))
                                                    msg_info += _('{}: 1 OFF {}W ({}kW/h) {}V IP:{} RSSI:{}dbm ').format(name, a_power, round(a_total/1000.0, 2), a_voltage, sta_ip, rssi)    
                                                if b_output:
                                                    msg += _('2 ON {}W ({}kW/h)] ').format(b_power, round(b_total/1000.0, 2))
                                                    msg_info += _('2 ON {}W ({}kW/h) {}V {}\n').format(b_power, round(b_total/1000.0, 2), b_voltage, updated)
                                                else:
                                                    msg += _('2 OFF {}W ({}kW/h)] ').format(b_power, round(b_total/1000.0, 2))
                                                    msg_info += _('2 OFF {}W ({}kW/h) {}V {}\n').format(b_power, round(b_total/1000.0, 2), b_voltage, updated)
                                            else:
                                                msg += _('[{}: OFFLINE] ').format(name)
                                                msg_info += _('{}: OFFLINE\n').format(name)

                                    # typ: 3=Shelly 1PM Mini
                                    # gen: 0 = GEN1, 1 = GEN 2+
                                    if plugin_options['sensor_type'][i] == 3:
                                        if plugin_options['gen_type'][i] == 0:
                                            name = plugin_options['sensor_label'][i]
                                            msg_info += _('{}: GEN1 not available yet \n').format(name)
                                        if plugin_options['gen_type'][i] == 1:
                                            name = plugin_options['sensor_label'][i]
                                            total = response_data["data"]["device_status"]["switch:0"]["aenergy"]["total"]
                                            output = response_data["data"]["device_status"]["switch:0"]["output"]
                                            power = response_data["data"]["device_status"]["switch:0"]["apower"]
                                            voltage = response_data["data"]["device_status"]["switch:0"]["voltage"]
                                            updated = response_data["data"]["device_status"]["_updated"]
                                            isok = response_data["isok"]
                                            online = response_data["data"]["online"]
                                            wifi = response_data["data"]["device_status"]["wifi"]
                                            sta_ip = wifi["sta_ip"]
                                            rssi = wifi["rssi"]
                                            if online:
                                                if output:
                                                    msg += _('[{}: ON {}W ({}kW/h)] ').format(name, power, round(total/1000.0, 2))
                                                    msg_info += _('{}: ON {}W ({}kW/h) {}V IP:{} RSSI:{}dbm {}\n').format(name, power, round(total/1000.0, 2), voltage, sta_ip, rssi, updated)
                                                else:
                                                    msg += _('[{}: OFF {}W ({}kW/h)] ').format(name, power, round(total/1000.0, 2))
                                                    msg_info += _('{}: OFF {}W ({}kW/h) {}V IP:{} RSSI:{}dbm {}\n').format(name, power, round(total/1000.0, 2), voltage, sta_ip, rssi, updated)
                                            else:
                                                msg += _('[{}: OFFLINE] ').format(name)
                                                msg_info += _('{}: OFFLINE\n').format(name)

                                    # typ: 4=Shelly 2.5
                                    # gen: 0 = GEN1, 1 = GEN 2+
                                    if plugin_options['sensor_type'][i] == 4:
                                        if plugin_options['gen_type'][i] == 0:
                                            name = plugin_options['sensor_label'][i]
                                            a_total = response_data["data"]["device_status"]["meters"][0]["total"]
                                            b_total = response_data["data"]["device_status"]["meters"][1]["total"]
                                            try:
                                                roller = response_data["data"]["device_status"]["rollers"][0]["state"]
                                            except:
                                                roller = None
                                                # TODO switch   
                                                a_output = 0
                                                b_output = 0
                                            a_power = response_data["data"]["device_status"]["meters"][0]["power"]
                                            b_power = response_data["data"]["device_status"]["meters"][1]["power"]
                                            voltage = response_data["data"]["device_status"]["voltage"]
                                            updated = response_data["data"]["device_status"]["_updated"]
                                            isok = response_data["isok"]
                                            online = response_data["data"]["online"]
                                            wifi = response_data["data"]["device_status"]["wifi_sta"]
                                            sta_ip = wifi["ip"]
                                            rssi = wifi["rssi"]
                                            if online:
                                                if roller is None:
                                                    if a_output:
                                                        msg += _('[{}: 1 ON {}W ({}kW/h) ').format(name, a_power, round(a_total/1000.0, 2))
                                                        msg_info += _('{}: 1 ON {}W ({}kW/h) {}V IP:{} RSSI:{}dbm ').format(name, a_power, round(a_total/1000.0, 2), a_voltage, sta_ip, rssi)
                                                    else:
                                                        msg += _('[{}: 1 OFF {}W ({}kW/h) ').format(name, a_power, round(a_total/1000.0, 2))
                                                        msg_info += _('{}: 1 OFF {}W ({}kW/h) {}V IP:{} RSSI:{}dbm ').format(name, a_power, round(a_total/1000.0, 2), a_voltage, sta_ip, rssi)    
                                                    if b_output:
                                                        msg += _('2 ON {}W ({}kW/h)] ').format(b_power, round(b_total/1000.0, 2))
                                                        msg_info += _('2 ON {}W ({}kW/h) {}\n').format(b_power, round(b_total/1000.0, 2), updated)
                                                    else:
                                                        msg += _('2 OFF {}W ({}kW/h)] ').format(b_power, round(b_total/1000.0, 2))
                                                        msg_info += _('2 OFF {}W ({}kW/h) {}\n').format(b_power, round(b_total/1000.0, 2), updated)
                                                else:
                                                    msg += _('[{}: {} 1: {}W ({}kW/h) 2: {}W ({}kW/h)] ').format(name, roller, a_power, round(a_total/1000.0, 2), b_power, round(b_total/1000.0, 2))
                                                    msg_info += _('{}: {} 1: {}W ({}kW/h) 2: {}W ({}kW/h) {}V IP:{} RSSI:{}dbm {}\n').format(name, roller, a_power, round(a_total/1000.0, 2), b_power, round(b_total/1000.0, 2), a_voltage, sta_ip, rssi, updated)       
                                            else:
                                                msg += _('[{}: OFFLINE] ').format(name)
                                                msg_info += _('{}: OFFLINE\n').format(name)
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
                                            updated = response_data["data"]["device_status"]["_updated"]
                                            isok = response_data["isok"]
                                            online = response_data["data"]["online"]
                                            wifi = response_data["data"]["device_status"]["wifi"]
                                            sta_ip = wifi["sta_ip"]
                                            rssi = wifi["rssi"]
                                            if online:
                                                if a_output:
                                                    msg += _('[{}: 1 ON {}W ({}kW/h) ').format(name, a_power, round(a_total/1000.0, 2))
                                                    msg_info += _('{}: 1 ON {}W ({}kW/h) {}V IP:{} RSSI:{}dbm ').format(name, a_power, round(a_total/1000.0, 2), voltage, sta_ip, rssi)
                                                else:
                                                    msg += _('[{}: 1 OFF {}W ({}kW/h) ').format(name, a_power, round(a_total/1000.0, 2))
                                                    msg_info += _('{}: 1 OFF {}W ({}kW/h) {}V IP:{} RSSI:{}dbm ').format(name, a_power, round(a_total/1000.0, 2), voltage, sta_ip, rssi)
                                                if b_output:
                                                    msg += _('2 ON {}W ({}kW/h)] ').format(b_power, round(b_total/1000.0, 2))
                                                    msg_info += _('2 ON {}W ({}kW/h) ').format(b_power, round(b_total/1000.0, 2))
                                                else:
                                                    msg += _('2 OFF {}W ({}kW/h)] ').format(b_power, round(b_total/1000.0, 2))
                                                    msg_info += _('2 OFF {}W ({}kW/h) ').format(b_power, round(b_total/1000.0, 2))
                                                if c_output:
                                                    msg += _('2 ON {}W ({}kW/h)] ').format(c_power, round(c_total/1000.0, 2))
                                                    msg_info += _('2 ON {}W ({}kW/h) ').format(c_power, round(c_total/1000.0, 2))
                                                else:
                                                    msg += _('2 OFF {}W ({}kW/h)] ').format(c_power, round(c_total/1000.0, 2))
                                                    msg_info += _('2 OFF {}W ({}kW/h) ').format(c_power, round(c_total/1000.0, 2))
                                                if d_output:
                                                    msg += _('2 ON {}W ({}kW/h)] ').format(d_power, round(d_total/1000.0, 2))
                                                    msg_info += _('2 ON {}W ({}kW/h) {}\n').format(d_power, round(d_total/1000.0, 2), updated)
                                                else:
                                                    msg += _('2 OFF {}W ({}kW/h)] ').format(d_power, round(d_total/1000.0, 2))
                                                    msg_info += _('2 OFF {}W ({}kW/h) {}\n').format(d_power, round(d_total/1000.0, 2), updated)
                                            else:
                                                msg += _('[{}: OFFLINE] ').format(name)
                                                msg_info += _('{}: OFFLINE\n').format(name)

                                    # typ: 6=Shelly 1 Mini
                                    # gen: 0 = GEN1, 1 = GEN 2+
                                    if plugin_options['sensor_type'][i] == 3:
                                        if plugin_options['gen_type'][i] == 0:
                                            name = plugin_options['sensor_label'][i]
                                            msg_info += _('{}: GEN1 not available yet \n').format(name)
                                        if plugin_options['gen_type'][i] == 1:
                                            name = plugin_options['sensor_label'][i]
                                            output = response_data["data"]["device_status"]["switch:0"]["output"]
                                            updated = response_data["data"]["device_status"]["_updated"]
                                            isok = response_data["isok"]
                                            online = response_data["data"]["online"]
                                            wifi = response_data["data"]["device_status"]["wifi"]
                                            sta_ip = wifi["sta_ip"]
                                            rssi = wifi["rssi"]
                                            if online:
                                                if output:
                                                    msg += _('[{}: ON] ').format(name)
                                                    msg_info += _('{}: ON IP:{} RSSI:{}dbm {}\n').format(name, sta_ip, rssi, updated)
                                                else:
                                                    msg += _('[{}: OFF] ').format(name)
                                                    msg_info += _('{}: OFF IP:{} RSSI:{}dbm {}\n').format(name, sta_ip, rssi, updated)
                                            else:
                                                msg += _('[{}: OFFLINE] ').format(name)
                                                msg_info += _('{}: OFFLINE\n').format(name)

                                except JSONDecodeError:
                                    raise BadResponse("Bad JSON")
                            except:
                                response = None
                                log.error(NAME, _('Shelly Cloud Integration plugin') + ':\n' + traceback.format_exc())
                                pass

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


################################################################################
# Web pages:                                                                   #
################################################################################

class status_page(ProtectedPage):
    """Load an html page for entering adjustments."""

    def GET(self):
        return self.plugin_render.shelly_cloud_integration(log.events(NAME))


class sensors_page(ProtectedPage):
    """Load an html page for entering adjustments."""

    def GET(self):
        msg = 'none'
        return self.plugin_render.shelly_cloud_integration_sensors(plugin_options, msg)

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


            commands = {'sensor_type': [], 'gen_type': [], 'use_sensor': [], 'sensor_label': [], 'sensor_id': []}

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

            plugin_options.__setitem__('sensor_type', commands['sensor_type'])
            plugin_options.__setitem__('gen_type', commands['gen_type'])
            plugin_options.__setitem__('use_sensor', commands['use_sensor'])
            plugin_options.__setitem__('sensor_label', commands['sensor_label'])
            plugin_options.__setitem__('sensor_id', commands['sensor_id'])

            if sender is not None:
                sender.update()

            msg = 'saved'
            return self.plugin_render.shelly_cloud_integration_sensors(plugin_options, msg)

        except Exception:
            log.debug(NAME, _('Shelly Cloud Integration plugin') + ':\n' + traceback.format_exc())
            pass

        msg = 'error'
        return self.plugin_render.shelly_cloud_integration_sensors(plugin_options, msg)


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