# -*- coding: utf-8 -*-

__author__ = 'Martin Pihrt' # www.pihrt.com

import json
import time
import datetime

import sys
import traceback
import os

from threading import Thread, Event

import web
import smbus

from ospy import helpers
from ospy.options import options, rain_blocks
from ospy.log import log, logEM
from plugins import PluginOptions, plugin_url, plugin_data_dir
from ospy.helpers import get_rpi_revision
from ospy.webpages import ProtectedPage
from ospy.helpers import datetime_string

from ospy.webpages import showInFooter # Enable plugin to display readings in UI footer


NAME = 'Current Loop Tanks Monitor'
MENU =  _('Package: Current Loop Tanks Monitor')
LINK = 'settings_page'

plugin_options = PluginOptions(
    NAME,
    {  
        'label1':  _('Tank 1'),                  # label for tank 1 - 4
        'label2':  _('Tank 2'),
        'label3':  _('Tank 3'),
        'label4':  _('Tank 4'),
        'en_tank1': True,                        # enabling or disabling tank 1 - 4
        'en_tank2':False,
        'en_tank3': False,
        'en_tank4': False,
        'maxHeightCm1': 400,                     # maximal water height for measuring tank 1 - 4 (in cm)
        'maxHeightCm2': 400,
        'maxHeightCm3': 400,
        'maxHeightCm4': 400,
        'maxVolume1': 3000,                      # max volume in the tank 1 - 4 (in liters)
        'maxVolume2': 3000,
        'maxVolume3': 3000,
        'maxVolume4': 3000,
        'minVolt1': 0.0,                         # AIN0 min input value for 4mA
        'minVolt2': 0.0,                         # AIN0 min input value
        'minVolt3': 0.0,                         # AIN0 min input value
        'minVolt4': 0.0,                         # AIN0 min input value
        'maxVolt1': 0.552,                       # AIN0 max input value for 20mA
        'maxVolt2': 4.096,                       # AIN1 max input value
        'maxVolt3': 4.096,                       # AIN2 max input value
        'maxVolt4': 4.096,                       # AIN3 max input value
        'i2c': 0,                                # I2C for ADC converter ADS1115 (0x48 default)
        'use_footer': False,
        'en_sql_log': False,                     # logging to sql database
        'en_log': False,                         # logging to local json file
        'type_log': 0,                           # 0 = show log and graph from local log file, 1 = from database
        'dt_from' : '2024-01-01T00:00',          # for graph history (from date time ex: 2024-02-01T6:00)
        'dt_to' : '2024-01-01T00:00',            # for graph history (to date time ex: 2024-03-17T12:00)
    }
)

# Registers and cmd for ADS1115
ADS1115_CONVERSION_REG = 0x00
ADS1115_CONFIG_REG = 0x01

# Mode setting for independent channels (single-ended) AIN0 to AIN3
CONFIG_GAIN = 0x0200  # Gain 1 (range ±4.096V)
CONFIG_MODE = 0x0100  # Mode: single-shot

tanks = {}
tanks['levelCm']        = [0, 0, 0, 0]
tanks['volumeLiter']    = [0, 0, 0, 0]
tanks['levelPercent']   = [0, 0, 0, 0]
tanks['voltage']        = [0.0, 0.0, 0.0, 0.0]
tanks['label']          = [plugin_options['label1'], plugin_options['label2'], plugin_options['label3'], plugin_options['label4']]


################################################################################
# Main function loop:                                                          #
################################################################################

class Sender(Thread):
    global tanks

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
        tanks['label']   = [plugin_options['label1'], plugin_options['label2'], plugin_options['label3'], plugin_options['label4']]

    def _sleep(self, secs):
        self._sleep_time = secs
        while self._sleep_time > 0 and not self._stop_event.is_set():
            time.sleep(1)
            self._sleep_time -= 1

    def run(self):
        tank_mon = None
        tempText = ""

        if plugin_options['use_footer']:
            tank_mon = showInFooter()                                           # instantiate class to enable data in footer
            tank_mon.button = "current_loop_tanks_monitor/settings"             # button redirect on footer
            tank_mon.label =  _('Tanks')                                        # label on footer

        while not self._stop_event.is_set():
            try:
                log.clear(NAME)
                
#                scan_i2c()
                get_data()

                if plugin_options['use_footer']:
                    if tank_mon is not None:  
                        tempText = '{} {} %, {} {} %, {} {} %, {} {} %,'.format(
                            tanks['label'][0],
                            tanks['levelPercent'][0],
                            tanks['label'][1],
                            tanks['levelPercent'][1],
                            tanks['label'][2],
                            tanks['levelPercent'][2],
                            tanks['label'][3],
                            tanks['levelPercent'][3]
                            )
                        tank_mon.val = tempText.encode('utf8').decode('utf8')   # value on footer
                self._sleep(5)

            except Exception:
                log.clear(NAME)
                log.error(NAME, _('Current Loop Tanks Monitor plug-in') + ':\n' + traceback.format_exc())
                self._sleep(60)

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
        sender.join()
        sender = None


def try_io(call, tries=10):
    assert tries > 0
    error = None
    result = None

    while tries:
        try:
            result = call()
        except IOError as e:
            error = e
            tries -= 1
            time.sleep(0.1)
        else:
            break

    if not tries:
        raise error

    return result


# Functions to read ADC on a specific channel
def read_adc(bus, channel):
    if channel == 0:
        config = 0x4000  # AIN0 single-ended
    elif channel == 1:
        config = 0x5000  # AIN1 single-ended
    elif channel == 2:
        config = 0x6000  # AIN2 single-ended
    elif channel == 3:
        config = 0x7000  # AIN3 single-ended
    else:
        raise ValueError(_('Error: Invalid channel.'))

    config |= CONFIG_GAIN | CONFIG_MODE | 0x8000  # Start single-conversion
    
    
    i2c_adr_list = [0x48, 0x49, 0x4A, 0x4B]
    i2c_adr = i2c_adr_list[plugin_options["i2c"]]

    # Write config to ADS1115
    try:
        bus.write_i2c_block_data(i2c_adr, ADS1115_CONFIG_REG, [(config >> 8) & 0xFF, config & 0xFF])
    except IOError:
        raise IOError(_('Error: No I2C bus or ADC available on address 0x48, 0x49, 0x4A, 0x4B.'))

    # Waiting for the conversion to complete
    time.sleep(0.2)
    
    # Reading the result from the conversion register
    try:
        result = bus.read_i2c_block_data(i2c_adr, ADS1115_CONVERSION_REG, 2)
    except IOError:
        raise IOError(_('Error: It is not possible to read data from the AD converter.'))

    raw_adc = (result[0] << 8) | result[1]
    
    # Convert to voltage range if the result exceeds 16bit
    if raw_adc > 0x7FFF:
        raw_adc -= 0x10000
    
    # Converting ADC value to voltage
    voltage = raw_adc * 4.096 / 32768.0  # ±4.096V range, 16bit convert
    
    return round(voltage if voltage > 0 else 0, 3)  # return positive voltage or 0


def get_data():
    global tanks

    try:
        bus = smbus.SMBus(1 if get_rpi_revision() >= 2 else 0)
    except FileNotFoundError:
        log.error(NAME, _('Error: the I2C bus is not available.'))
        return
    
    # Definition for the tank level for each channel (minimum and maximum voltage)
    LEVEL_DEFINITIONS = {
        0: {"min": plugin_options['minVolt1'], "max": plugin_options['maxVolt1']},  # AIN0
        1: {"min": plugin_options['minVolt2'], "max": plugin_options['maxVolt1']},  # AIN1
        2: {"min": plugin_options['minVolt3'], "max": plugin_options['maxVolt1']},  # AIN2
        3: {"min": plugin_options['minVolt4'], "max": plugin_options['maxVolt1']}   # AIN3
    }

    # Reading all four channels
    IO_error = False
    VAL_error = False
    adc_values = []

    for channel in range(4):
        tanks['voltage'][channel] = 0.0
        tanks['levelPercent'][channel] = 0
        tanks['levelCm'][channel] = 0         
        try:
            adc_value = try_io(lambda: read_adc(bus, channel))
            adc_values.append(adc_value)
            
            # Voltage conversion to tank level for the current channel
            min_voltage = LEVEL_DEFINITIONS[channel]["min"]
            max_voltage = LEVEL_DEFINITIONS[channel]["max"]

            level_percentage = voltage_to_level(adc_value, min_voltage, max_voltage)
            level_cm = level_to_cm(level_percentage)

            tanks['voltage'][channel] = adc_value
            tanks['levelPercent'][channel] = level_percentage
            tanks['levelCm'][channel] = level_cm

        except ValueError as ve:
            VAL_error = True
            #log.error(NAME, _('Error for channel {}: {}.').format(channel, ve))

        except IOError as ioe:
            IO_error = True
            #log.error(NAME, _('I/O error for channel {}: {}.').format(channel, ioe))

    if IO_error:    
            log.error(NAME, _('I/O error.'))

    if VAL_error:
            log.error(NAME, _('Any Error on ADC channel.'))
           

def scan_i2c():
    bus = None
    try:
        bus = smbus.SMBus(1)
    except FileNotFoundError:
       log.error(NAME, _('Error: the I2C bus is not available.'))
       return []

    devices = []
    for address in range(128):
        try:
            bus.write_byte(address, 0)
            devices.append(hex(address))
        except OSError:
            pass
    if devices:
        log.info(NAME, _('I2C devices found at the following addresses: {}.').format(devices))
        return devices
    else:
        log.error(NAME, _('No I2C device was found.'))
        return []


def voltage_to_level(voltage, min_voltage, max_voltage):
    if voltage < min_voltage:
        return 0.0
    elif voltage > max_voltage:
        return 100.0
    else:
        return (voltage - min_voltage) / (max_voltage - min_voltage) * 100.0


def level_to_cm(level, maxHeightCm):
    # Makes sure the level is in the range 0-100
    level = max(0, min(level, 100))
    # Calculation of the level in centimeters from the percentage
    return (level / 100) * maxHeightCm         

################################################################################
# Web pages:                                                                   #
################################################################################

class settings_page(ProtectedPage):
    """Load an html page for tank."""

    def GET(self):
        return self.plugin_render.current_loop_tanks_monitor(plugin_options)

    def POST(self):
        global sender

        #plugin_options.web_update(web.input())
        #if sender is not None:
        #    sender.update()

        log.clear(NAME)
        log.info(NAME, _('Options has updated.'))
        return 'OK'           
#        raise web.seeother(plugin_url(settings_page), True)


class help_page(ProtectedPage):
    """Load an html page for help"""

    def GET(self):
        return self.plugin_render.current_loop_tanks_monitor_help()


class graph_page(ProtectedPage):
    """Load an html page for graph"""

    def GET(self):
        return self.plugin_render.current_loop_tanks_monitor_graph(plugin_options)


class log_page(ProtectedPage):
    """Load an html page for log"""

    def GET(self):
        return self.plugin_render.current_loop_tanks_monitor_log(plugin_options)


class setup_page(ProtectedPage):
    """Load an html page for setup"""

    def GET(self):
        return self.plugin_render.current_loop_tanks_monitor_setup(plugin_options)

    def POST(self):
        global sender

        plugin_options.web_update(web.input())
        if sender is not None:
            sender.update()

        log.clear(NAME)
        log.debug(NAME, _('Options has updated.'))
            
        raise web.seeother(plugin_url(setup_page), True)


class data_json(ProtectedPage):
    """Returns tank data in JSON format."""
    global tanks

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        data = {}
        
        try:
            data =  {
                'tank1': { 'label': plugin_options['label1'], 'maxHeightCm': plugin_options['maxHeightCm1'], 'maxVolume':  plugin_options['maxVolume1'], 'level': tanks['levelCm'][0] },
                'tank2': { 'label': plugin_options['label2'], 'maxHeightCm': plugin_options['maxHeightCm2'], 'maxVolume':  plugin_options['maxVolume2'], 'level': tanks['levelCm'][1] },
                'tank3': { 'label': plugin_options['label3'], 'maxHeightCm': plugin_options['maxHeightCm3'], 'maxVolume':  plugin_options['maxVolume3'], 'level': tanks['levelCm'][2] },
                'tank4': { 'label': plugin_options['label4'], 'maxHeightCm': plugin_options['maxHeightCm4'], 'maxVolume':  plugin_options['maxVolume4'], 'level': tanks['levelCm'][3] },
                'msg': log.events(NAME)
            }
        except:
            log.error(NAME, _('Current Loop Tanks Monitor plug-in') + ':\n' + traceback.format_exc())

        return json.dumps(data)