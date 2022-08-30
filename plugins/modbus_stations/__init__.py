# -*- coding: utf-8 -*-
__author__ = u'Martin Pihrt'

import json
import time
import traceback
import web
import subprocess
import os
import mimetypes

from blinker import signal

from ospy.stations import stations
from ospy.options import options
from ospy.helpers import datetime_string
from ospy import helpers 
from ospy.log import log
from threading import Thread, Event
from plugins import PluginOptions, plugin_url, plugin_data_dir
from ospy.webpages import ProtectedPage

import serial

NAME = 'Modbus Stations'     ### name for plugin in plugin manager ###
MENU =  _('Package: Modbus Stations')
LINK = 'settings_page'       ### link for page in plugin manager ###

plugin_options = PluginOptions(
    NAME,
    {'use_control': False,
     'use_log': False,
     'port': '/dev/ttyUSB0',
     'baud': 9600,
     'nr_boards': 1 
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
        if plugin_options['use_control']:  # if plugin is enabled
            log.clear(NAME)
            log.info(NAME, _('Modbus Stations enabled.'))
            try:
                station_on = signal('station_on')
                station_on.connect(on_station_on)
                station_off = signal('station_off')
                station_off.connect(on_station_off)
                station_clear = signal('station_clear')
                station_clear.connect(on_station_clear)
            except Exception:
                log.error(NAME, _('Modbus Stations plug-in') + ':\n' + traceback.format_exc())
                pass
        else:
            log.clear(NAME)
            log.info(NAME, _('Modbus Stations is disabled.'))

sender = None

################################################################################
# Helper functions:                                                            #
################################################################################

### start ###
def start():
    global sender
    if sender is None:
        sender = Sender()
 
### stop ###
def stop():
    global sender
    if sender is not None:
        sender.stop()
        sender.join()
        sender = None


def on_station_on(name, **kw):
    """ Send CMD to ON when core program signals in station state."""
    index = int(kw["txt"])
    log.clear(NAME)
    log.info(NAME, _('Station {} change to ON').format(index+1))
    if plugin_options['nr_boards'] == 1: # relay 1-8, adr 1
        Send_data(address=0x01, command=0x05, relay_nr=int(index), state='on')
    #else:
        # todo adr 2... station 9 as relay 1, 10 -> 2 ...        
    

def on_station_off(name, **kw):
    """ Send CMD to OFF when core program signals in station state."""
    index = int(kw["txt"])    
    log.clear(NAME)
    log.info(NAME, _('Station {} change to OFF').format(index+1))
    if plugin_options['nr_boards'] == 1: # relay 1-8, adr 1
        Send_data(address=0x01, command=0x05, relay_nr=int(index), state='off')
    #else:
        # todo adr 2... station 9 as relay 1, 10 -> 2 ...
    

def on_station_clear(name, **kw):
    """ Send all CMD to OFF when core program signals in station state."""
    log.clear(NAME)
    log.info(NAME, _('All station change to OFF'))
    for i in range(plugin_options['nr_boards']*8):
        Send_data(address=0x01, command=0x05, relay_nr=i, state='off')
    

def read_log():
    """Read log data from json file."""
    try:
        with open(os.path.join(plugin_data_dir(), 'log.json')) as logf:
            return json.load(logf)
    except IOError:
        return []

def write_log(json_data):
    """Write data to log json file."""
    with open(os.path.join(plugin_data_dir(), 'log.json'), 'w') as outfile:
        json.dump(json_data, outfile)

def update_log(cmd, status):
    """Update data in json files."""
    try:
        log_data = read_log()
    except:   
        write_log([])
        log_data = read_log()

    from datetime import datetime 

    data = {}
    data['cmd'] = cmd
    data['status'] = status
    data['datetime'] = datetime_string()

    log_data.insert(0, data)
    write_log(log_data)


""" Table of CRC values for high–order byte """
CRCTableHigh = [
  0x00, 0xC1, 0x81, 0x40, 0x01, 0xC0, 0x80, 0x41, 0x01, 0xC0, 0x80, 0x41, 0x00, 0xC1, 0x81,
  0x40, 0x01, 0xC0, 0x80, 0x41, 0x00, 0xC1, 0x81, 0x40, 0x00, 0xC1, 0x81, 0x40, 0x01, 0xC0,
  0x80, 0x41, 0x01, 0xC0, 0x80, 0x41, 0x00, 0xC1, 0x81, 0x40, 0x00, 0xC1, 0x81, 0x40, 0x01,
  0xC0, 0x80, 0x41, 0x00, 0xC1, 0x81, 0x40, 0x01, 0xC0, 0x80, 0x41, 0x01, 0xC0, 0x80, 0x41,
  0x00, 0xC1, 0x81, 0x40, 0x01, 0xC0, 0x80, 0x41, 0x00, 0xC1, 0x81, 0x40, 0x00, 0xC1, 0x81,
  0x40, 0x01, 0xC0, 0x80, 0x41, 0x00, 0xC1, 0x81, 0x40, 0x01, 0xC0, 0x80, 0x41, 0x01, 0xC0,
  0x80, 0x41, 0x00, 0xC1, 0x81, 0x40, 0x00, 0xC1, 0x81, 0x40, 0x01, 0xC0, 0x80, 0x41, 0x01,
  0xC0, 0x80, 0x41, 0x00, 0xC1, 0x81, 0x40, 0x01, 0xC0, 0x80, 0x41, 0x00, 0xC1, 0x81, 0x40,
  0x00, 0xC1, 0x81, 0x40, 0x01, 0xC0, 0x80, 0x41, 0x01, 0xC0, 0x80, 0x41, 0x00, 0xC1, 0x81,
  0x40, 0x00, 0xC1, 0x81, 0x40, 0x01, 0xC0, 0x80, 0x41, 0x00, 0xC1, 0x81, 0x40, 0x01, 0xC0,
  0x80, 0x41, 0x01, 0xC0, 0x80, 0x41, 0x00, 0xC1, 0x81, 0x40, 0x00, 0xC1, 0x81, 0x40, 0x01,
  0xC0, 0x80, 0x41, 0x01, 0xC0, 0x80, 0x41, 0x00, 0xC1, 0x81, 0x40, 0x01, 0xC0, 0x80, 0x41,
  0x00, 0xC1, 0x81, 0x40, 0x00, 0xC1, 0x81, 0x40, 0x01, 0xC0, 0x80, 0x41, 0x00, 0xC1, 0x81,
  0x40, 0x01, 0xC0, 0x80, 0x41, 0x01, 0xC0, 0x80, 0x41, 0x00, 0xC1, 0x81, 0x40, 0x01, 0xC0,
  0x80, 0x41, 0x00, 0xC1, 0x81, 0x40, 0x00, 0xC1, 0x81, 0x40, 0x01, 0xC0, 0x80, 0x41, 0x01,
  0xC0, 0x80, 0x41, 0x00, 0xC1, 0x81, 0x40, 0x00, 0xC1, 0x81, 0x40, 0x01, 0xC0, 0x80, 0x41,
  0x00, 0xC1, 0x81, 0x40, 0x01, 0xC0, 0x80, 0x41, 0x01, 0xC0, 0x80, 0x41, 0x00, 0xC1, 0x81,
  0x40
]


""" Table of CRC values for low–order byte """
CRCTableLow = [
  0x00, 0xC0, 0xC1, 0x01, 0xC3, 0x03, 0x02, 0xC2, 0xC6, 0x06, 0x07, 0xC7, 0x05, 0xC5, 0xC4,
  0x04, 0xCC, 0x0C, 0x0D, 0xCD, 0x0F, 0xCF, 0xCE, 0x0E, 0x0A, 0xCA, 0xCB, 0x0B, 0xC9, 0x09,
  0x08, 0xC8, 0xD8, 0x18, 0x19, 0xD9, 0x1B, 0xDB, 0xDA, 0x1A, 0x1E, 0xDE, 0xDF, 0x1F, 0xDD,
  0x1D, 0x1C, 0xDC, 0x14, 0xD4, 0xD5, 0x15, 0xD7, 0x17, 0x16, 0xD6, 0xD2, 0x12, 0x13, 0xD3,
  0x11, 0xD1, 0xD0, 0x10, 0xF0, 0x30, 0x31, 0xF1, 0x33, 0xF3, 0xF2, 0x32, 0x36, 0xF6, 0xF7,
  0x37, 0xF5, 0x35, 0x34, 0xF4, 0x3C, 0xFC, 0xFD, 0x3D, 0xFF, 0x3F, 0x3E, 0xFE, 0xFA, 0x3A,
  0x3B, 0xFB, 0x39, 0xF9, 0xF8, 0x38, 0x28, 0xE8, 0xE9, 0x29, 0xEB, 0x2B, 0x2A, 0xEA, 0xEE,
  0x2E, 0x2F, 0xEF, 0x2D, 0xED, 0xEC, 0x2C, 0xE4, 0x24, 0x25, 0xE5, 0x27, 0xE7, 0xE6, 0x26,
  0x22, 0xE2, 0xE3, 0x23, 0xE1, 0x21, 0x20, 0xE0, 0xA0, 0x60, 0x61, 0xA1, 0x63, 0xA3, 0xA2,
  0x62, 0x66, 0xA6, 0xA7, 0x67, 0xA5, 0x65, 0x64, 0xA4, 0x6C, 0xAC, 0xAD, 0x6D, 0xAF, 0x6F,
  0x6E, 0xAE, 0xAA, 0x6A, 0x6B, 0xAB, 0x69, 0xA9, 0xA8, 0x68, 0x78, 0xB8, 0xB9, 0x79, 0xBB,
  0x7B, 0x7A, 0xBA, 0xBE, 0x7E, 0x7F, 0xBF, 0x7D, 0xBD, 0xBC, 0x7C, 0xB4, 0x74, 0x75, 0xB5,
  0x77, 0xB7, 0xB6, 0x76, 0x72, 0xB2, 0xB3, 0x73, 0xB1, 0x71, 0x70, 0xB0, 0x50, 0x90, 0x91,
  0x51, 0x93, 0x53, 0x52, 0x92, 0x96, 0x56, 0x57, 0x97, 0x55, 0x95, 0x94, 0x54, 0x9C, 0x5C,
  0x5D, 0x9D, 0x5F, 0x9F, 0x9E, 0x5E, 0x5A, 0x9A, 0x9B, 0x5B, 0x99, 0x59, 0x58, 0x98, 0x88,
  0x48, 0x49, 0x89, 0x4B, 0x8B, 0x8A, 0x4A, 0x4E, 0x8E, 0x8F, 0x4F, 0x8D, 0x4D, 0x4C, 0x8C,
  0x44, 0x84, 0x85, 0x45, 0x87, 0x47, 0x46, 0x86, 0x82, 0x42, 0x43, 0x83, 0x41, 0x81, 0x80,
  0x40
]


def ModbusCRC(data):
    """ Compute CRC from first 6 byte """
    crcHigh = 0xff;
    crcLow = 0xff; 
    index = 0;
    for byte in data:
        index = crcLow ^ byte
        crcLow  = crcHigh ^ CRCTableHigh[index]
        crcHigh = CRCTableLow[index]
    
    return (crcHigh << 8 | crcLow)


def Send_data(address=0x01, command=0x05, relay_nr=0, state='off'):
    cmd = [0]*8
    try:
        s = None
        try:
            s = serial.Serial(plugin_options['port'], plugin_options['baud'])
        except:
            log.info(NAME, _('No such file or directory') + ': {}'.format(plugin_options['port']))

        if s is not None:    
            cmd[0] = address  # 0 x 00 is broadcast address； 0x01-0xFF are device addresses (Device address is 01 by default)
            cmd[1] = command  # Command for controlling Relay
            cmd[2] = 0        # The register address of controlled Relay, 0x0000 - 0x0008 (in relay mode)
            cmd[3] = relay_nr # Output relay 1-8 (in single mode)
            if state == 'on':
                cmd[4] = 0xFF # Command 0xFF = ON,
            if state == 'off':
                cmd[4] = 0x00 # Command 0x0 = OFF
            if state == 'flip':
                cmd[4] = 0x55 # Command 0x55 = Flip relay            
            cmd[5] = 0
            crc = ModbusCRC(cmd[0:6]) # CRC from first 6 byte
            cmd[6] = crc & 0xFF
            cmd[7] = crc >> 8
            s.write(cmd)
            status = _('Addr: {} Out: {} To: {}').format(address, relay_nr, state)
            update_log(cmd, status)

    except Exception:
        log.error(NAME, _('Modbus Stations plug-in') + ':\n' + traceback.format_exc())
        status = _('Err: {}').format(traceback.format_exc())
        update_log(cmd, status)        
        pass

################################################################################
# Web pages:                                                                   #
################################################################################

class settings_page(ProtectedPage):
    """Load an html page for entering adjustments."""

    def GET(self):
        global sender
        qdict = web.input()
        delete = helpers.get_input(qdict, 'delete', False, lambda x: True)
        show = helpers.get_input(qdict, 'show', False, lambda x: True)
 
        if sender is not None and delete:
            write_log([])
            log.info(NAME, _('Deleted all log files OK'))
            raise web.seeother(plugin_url(settings_page), True)

        if sender is not None and show:
            raise web.seeother(plugin_url(log_page), True)

        return self.plugin_render.modbus_stations(plugin_options, log.events(NAME))

    def POST(self):
        try:
            plugin_options.web_update(web.input())
            if sender is not None:
                sender.update()

        except Exception:
            log.error(NAME, _('Modbus Stations plug-in') + ':\n' + traceback.format_exc())
            pass

        raise web.seeother(plugin_url(settings_page), True)

class help_page(ProtectedPage):
    """Load an html page for help"""

    def GET(self):
        return self.plugin_render.modbus_stations_help()

class log_page(ProtectedPage):
    """Load an html page for help"""

    def GET(self):
        return self.plugin_render.modbus_stations_log(read_log())

class settings_json(ProtectedPage): 
    """Returns plugin settings in JSON format."""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        return json.dumps(plugin_options)

class log_json(ProtectedPage):
    """Returns data in JSON format."""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        return json.dumps(read_log())

class log_csv(ProtectedPage):
    """Simple Log API"""

    def GET(self):
        data = "Date/Time; Command; State \n"
        log_file = read_log()
        for interval in log_file:
            data += '; '.join([
                interval['datetime'],
                u'{}'.format(interval['cmd']),
                u'{}'.format(interval['status']),
            ]) + '\n'

        content = mimetypes.guess_type(os.path.join(plugin_data_dir(), 'log.json')[0])
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-type', content) 
        web.header('Content-Disposition', 'attachment; filename="modbus_stations_log.csv"')
        return data
