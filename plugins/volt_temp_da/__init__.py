#!/usr/bin/env python
# -*- coding: utf-8 -*-
__author__ = 'Martin Pihrt'
# This plugin read data (temp or voltage) from I2C PCF8591 on adress 0x48. For temperature probe use LM35D (LM35DZ). 

import json
import time
import traceback
import os
from threading import Thread, Event

import web

from ospy.log import log
from plugins import PluginOptions, plugin_url, plugin_data_dir
from ospy.webpages import ProtectedPage
from ospy.helpers import get_rpi_revision
from ospy.helpers import datetime_string

import i18n

NAME = 'Voltage and Temperature Monitor'
LINK = 'settings_page'

pcf_options = PluginOptions(
    NAME,
    {'enabled': False,
     'enable_log': False,
     'log_interval': 1,
     'log_records': 0,
     'voltage': 5.0,

     'ad0_temp': False,
     'ad1_temp': False,
     'ad2_temp': False,
     'ad3_temp': False,

     'ad0_label': 'AD 1',
     'ad1_label': 'AD 2',
     'ad2_label': 'AD 3',
     'ad3_label': 'AD 4',

     'da_value': 0
    }
)


################################################################################
# Main function loop:                                                          #
################################################################################


class PCFSender(Thread):
    def __init__(self):
        Thread.__init__(self)
        self.daemon = True
        self._stop = Event()

        self.adc = None
        self.status = {}
        for i in range(4):
            self.status['ad%d_raw' % i] = 0
            self.status['ad%d' % i] = 0

        self._sleep_time = 0
        self.start()

    def stop(self):
        self._stop.set()

    def update(self):
        self._sleep_time = 0

    def _sleep(self, secs):
        self._sleep_time = secs
        while self._sleep_time > 0 and not self._stop.is_set():
            time.sleep(1)
            self._sleep_time -= 1

    def run(self):
        try:
            import smbus  # for PCF 8591

            self.adc = smbus.SMBus(1 if get_rpi_revision() >= 2 else 0)
        except ImportError:
            log.warning(NAME, _('Could not import smbus.'))

        while not self._stop.is_set():
            log.clear(NAME)
            try:
                if self.adc is not None and pcf_options['enabled']:  # if pcf plugin is enabled
                    for i in range(4):
                        val = read_AD(self.adc, i + 1)
                        self.status['ad%d_raw' % i] = val
                        self.status['ad%d' % i] = get_temp(val) if pcf_options['ad%d_temp' % i] else get_volt(val)

                    log.info(NAME, datetime_string())
                    for i in range(4):
                        log.info(NAME, pcf_options['ad%d_label' % i] + ': ' + format(self.status['ad%d' % i],
                                                                                     pcf_options['ad%d_temp' % i]))

                    if pcf_options['enable_log']:
                        update_log(self.status)

                try:
                    write_DA(self.adc, pcf_options['da_value'])
                except Exception:
                    self.adc = None
                    
                self._sleep(max(60, pcf_options['log_interval'] * 60))

            except Exception:
                self.adc = None
                log.error(NAME, _('Voltage and Temperature Monitor plug-in') + ':\n' + traceback.format_exc())
                self._sleep(60)


pcf_sender = None

################################################################################
# Helper functions:                                                            #
################################################################################
def start():
    global pcf_sender
    if pcf_sender is None:
        pcf_sender = PCFSender()
       

def stop():
    global pcf_sender
    if pcf_sender is not None:
        pcf_sender.stop()
        pcf_sender.join()
        pcf_sender = None


def get_volt(data):
    """Return voltage 0-XX V from number"""
    volt = data / 255.0 * pcf_options['voltage']
    volt = round(volt, 1)
    return volt


def get_temp(data):
    """Return temperature 0-100C from data"""
    """ 255 is 2^8, value where the analog value can be represented by PCD A/D converter. The actual voltage obtained by VOLTAGE_ON_AD_INPUT/ 255."""
    """ 1000 is used to change the unit from V to mV. """
    """ 10 is constant. Each 10 mV is directly proportional to 1 Celcius. """
    """ math: (supply voltage * 1000 / 255) / 10 """
    temp = data * (((pcf_options['voltage'])*1000.0/255.0) / 10.0) + 10
    temp = round(temp, 1)
    return temp


def format(ad_value, is_temp):
    if is_temp:
        return u'%.1f \u2103' % ad_value
    else:
        return '%.1f V' % ad_value


def read_AD(adc, pin):
    """Return number 0-255 from A/D PCF8591 to webpage."""
    result = 0
    if adc is not None:
        adc.write_byte_data(0x48, (0x40 + pin), pin)
        result = adc.read_byte(0x48)
    return result


def write_DA(adc, value):  # PCF8591 D/A converter Y=(0-255) for future use
    """Write analog voltage to output"""
    if adc is not None:
        adc.write_byte_data(0x48, 0x40, value)


def read_log():
    """Read pcf log from json file."""
    try:
        with open(os.path.join(plugin_data_dir(), 'log.json')) as logf:
            return json.load(logf)
    except IOError:
        return []


def write_log(json_data):
    """Write json to log file."""
    with open(os.path.join(plugin_data_dir(), 'log.json'), 'w') as outfile:
        json.dump(json_data, outfile)


def update_log(status):
    log_data = read_log()
    data = {'datetime': datetime_string()}
    for i in range(4):
        data['ad%d' % i] = format(status['ad%d' % i], pcf_options['ad%d_temp' % i])
    log_data.insert(0, data)
    if pcf_options['log_records'] > 0:
        log_data = log_data[:pcf_options['log_records']]
    write_log(log_data)


################################################################################
# Web pages:                                                                   #
################################################################################

class settings_page(ProtectedPage):
    """Load an html page for entering pcf adjustments."""

    def GET(self):
        return self.plugin_render.volt_temp_da(pcf_options, pcf_sender.status, log.events(NAME))

    def POST(self):
        pcf_options.web_update(web.input())

        if pcf_sender is not None:
            pcf_sender.update()                
        raise web.seeother(plugin_url(settings_page), True)


class settings_json(ProtectedPage):
    """Returns plugin settings in JSON format."""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        return json.dumps(pcf_options)


class log_json(ProtectedPage):
    """Returns plugin settings in JSON format."""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        return json.dumps(read_log())


class log_csv(ProtectedPage):  # save log file from web as csv file type
    """Simple PCF Log API"""

    def GET(self):
        log_records = read_log()
        data = "Date/Time"
        for i in range(4):
            data += ";\t" + pcf_options['ad%d_label' % i]
        data += '\n'

        for record in log_records:
            data += record['datetime']
            for i in range(4):
                data += ";\t" + record['ad%d' % i]
            data += '\n'

        web.header('Content-Type', 'text/csv')
        return data


class delete_log_page(ProtectedPage):  # delete log file from web
    """Delete all pcflog log_records"""

    def GET(self):
        write_log([])
        log.info(NAME, _('Deleted log file'))
        raise web.seeother(plugin_url(settings_page), True)


