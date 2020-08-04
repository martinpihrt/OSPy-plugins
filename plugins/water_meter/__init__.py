# -*- coding: utf-8 -*-
__author__ = 'Martin Pihrt'
# This plugin read data from I2C counter PCF8583 on I2C address 0x50. Max count PCF8583 is 1 milion pulses per seconds

import json
import time
import traceback

from threading import Thread, Event

import web

from ospy.log import log
from plugins import PluginOptions, plugin_url
from ospy.webpages import ProtectedPage
from ospy.helpers import datetime_string
from ospy import helpers


NAME = 'Water Meter'
MENU =  _('Package: Water Meter')
LINK = 'settings_page'

options = PluginOptions(
    NAME,
    {'enabled': False,                          # enable or disable this plugin
     'pulses': 10.0,                            # pulses/liter
     'address': False,                          # True = 0x51, False = 0x50 for PCF8583
     'sum': 0,                                  # saved summary
     'log_date_last_reset':  datetime_string()  # last summary reset
    }
)

################################################################################
# Main function loop:                                                          #
################################################################################


class WaterSender(Thread):
    def __init__(self):
        Thread.__init__(self)
        self.daemon = True
        self._stop = Event()

        self.bus = None
        self.pcf = None
        self.status = {}
        self.status['meter'] = 0.0

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
            import smbus  # for PCF 8583
            self.bus = smbus.SMBus(0 if helpers.get_rpi_revision() == 1 else 1)

        except ImportError:
            log.warning(NAME, _('Could not import smbus.'))

        if self.bus is not None:
            self.pcf = set_counter(self.bus)     # set pcf8583 as counter

        log.clear(NAME)
        once_text = True  # text enabled plugin
        two_text = True   # text disabled plugin

        val = 0                     # actual water per second
        sum_water = options['sum']  # saved value of summary water 
        minute_water = 0            # actual water per minutes
        hour_water = 0              # actual water per hours

        last_minute_time = int(time.time())
        last_hour_time = int(time.time())
        actual_time = int(time.time())

        while not self._stop.is_set():
            try:
                if self.bus is not None and options['enabled']:  # if water meter plugin is enabled
                    val = counter(self.bus) / options['pulses']
                    self.status['meter'] = val

                    if once_text:
                        log.clear(NAME)
                        log.info(NAME, _('Water Meter plug-in is enabled.'))
                        once_text = False
                        two_text = True
                        if self.pcf is None:
                            log.warning(NAME, _('Could not find PCF8583.'))
                        else:
                            log.info(NAME, _('Please wait for min/hour data...'))
                            log.info(NAME, '________________________________')
                            log.info(NAME, _('Water in liters'))
                            log.info(NAME, str(options['log_date_last_reset']) + ' '+ _('Saved water summary') + ': ' + str(sum_water))

                    if self.pcf is not None:
                        sum_water = sum_water + val
                        minute_water = minute_water + val
                        hour_water = hour_water + val

                        actual_time = int(time.time())
                        if actual_time - last_minute_time >= 60:          # minute counter
                            last_minute_time = actual_time
                            log.clear(NAME)
                            log.info(NAME, _('Water in liters'))
                            log.info(NAME, _('Water per minutes') + ': ' + str(minute_water))
                            log.info(NAME, _('Water per hours') + ': ' + str(hour_water))
                            log.info(NAME, str(options['log_date_last_reset']) + ' ' + _('Water summary') + ': ' + str(sum_water))
                            minute_water = 0

                            # save summary water to options only 1 minutes
                            # options.__setitem__('sum', sum_water)  
                            qdict = {}       
                            if options['enabled']:
                                qdict['enabled'] = u'on' 
                            if options['address']:
                                qdict['address']  = u'on'
                            qdict['sum'] = sum_water
                            options.web_update(qdict)   

                        if actual_time - last_hour_time >= 3600:          # hour counter
                            last_hour_time = actual_time
                            hour_water = 0

                else:
                    if two_text:
                        self.status['meter'] = '0.0'
                        log.clear(NAME)
                        log.info(NAME, _('Water Meter plug-in is disabled.'))
                        two_text = False
                        once_text = True

                self._sleep(1)

            except Exception:
                self.bus = None
                log.error(NAME, _('Water Meter plug-in') + ':\n' + traceback.format_exc())
                self._sleep(60)


water_sender = None
           

################################################################################
# Helper functions:                                                            #
################################################################################
def start():
    global water_sender
    if water_sender is None:
        water_sender = WaterSender()


def stop():
    global water_sender
    if water_sender is not None:
        water_sender.stop()
        water_sender.join()
        water_sender = None


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
            time.sleep(0.01)
        else:
            break

    if not tries:
        raise error

    return result        


def set_counter(i2cbus):
    try:
        if options['address']:
            addr = 0x51
        else:
            addr = 0x50 
        #i2cbus.write_byte_data(addr, 0x00, 0x20) # status registr setup to "EVENT COUNTER"
        #i2cbus.write_byte_data(addr, 0x01, 0x00) # reset LSB
        #i2cbus.write_byte_data(addr, 0x02, 0x00) # reset midle Byte
        #i2cbus.write_byte_data(addr, 0x03, 0x00) # reset MSB
        try_io(lambda: i2cbus.write_byte_data(addr, 0x00, 0x20)) # status registr setup to "EVENT COUNTER"
        try_io(lambda: i2cbus.write_byte_data(addr, 0x01, 0x00)) # reset LSB
        try_io(lambda: i2cbus.write_byte_data(addr, 0x02, 0x00)) # reset midle Byte
        try_io(lambda: i2cbus.write_byte_data(addr, 0x03, 0x00)) # reset MSB        
        log.debug(NAME, _('Setup PCF8583 as event counter is OK'))
        return 1  
    except:
        log.error(NAME, _('Water Meter plug-in') + ':\n' + _('Setup PCF8583 as event counter - FAULT'))
        log.error(NAME, _('Water Meter plug-in') + traceback.format_exc())
        return None

def counter(i2cbus): # reset PCF8583, measure pulses and return number pulses per second
    try:
        if options['address']:
            addr = 0x51
        else:
            addr = 0x50 
        # reset PCF8583
        #i2cbus.write_byte_data(addr, 0x01, 0x00) # reset LSB
        #i2cbus.write_byte_data(addr, 0x02, 0x00) # reset midle Byte
        #i2cbus.write_byte_data(addr, 0x03, 0x00) # reset MSB
        try_io(lambda: i2cbus.write_byte_data(addr, 0x01, 0x00)) # reset LSB
        try_io(lambda: i2cbus.write_byte_data(addr, 0x02, 0x00)) # reset midle Byte
        try_io(lambda: i2cbus.write_byte_data(addr, 0x03, 0x00)) # reset MSB        
        time.sleep(1)
        # read number (pulses in counter) and translate to DEC
        #counter = i2cbus.read_i2c_block_data(addr, 0x00)
        counter = try_io(lambda: i2cbus.read_i2c_block_data(addr, 0x00))
        num1 = (counter[1] & 0x0F)             # units
        num10 = (counter[1] & 0xF0) >> 4       # dozens
        num100 = (counter[2] & 0x0F)           # hundred
        num1000 = (counter[2] & 0xF0) >> 4     # thousand
        num10000 = (counter[3] & 0x0F)         # tens of thousands
        num100000 = (counter[3] & 0xF0) >> 4   # hundreds of thousands
        pulses = (num100000 * 100000) + (num10000 * 10000) + (num1000 * 1000) + (num100 * 100) + (num10 * 10) + num1
        return pulses
    except:
    	log.error(NAME, _('Water Meter plug-in') + traceback.format_exc())
        return 0

def get_all_values():
    return options['sum'], options['log_date_last_reset']             

################################################################################
# Web pages:                                                                   #
################################################################################

class settings_page(ProtectedPage):
    """Load an html page for entering water meter adjustments."""

    def GET(self):
        global water_sender

        qdict = web.input()
        reset = helpers.get_input(qdict, 'reset', False, lambda x: True)

        if water_sender is not None and reset:
            if options['enabled']:
                qdict['enabled'] = u'on' 
            if options['address']:
                qdict['address']  = u'on'
            qdict['sum'] = 0
            qdict['log_date_last_reset'] =  datetime_string()
                
            options.web_update(qdict)    
            log.clear(NAME)
            log.info(NAME, str(options['log_date_last_reset']) + ' ' + _('Water summary was reseting...'))
            log.info(NAME, _('Please wait for min/hour data...'))
            
            raise web.seeother(plugin_url(settings_page), True)

        return self.plugin_render.water_meter(options, water_sender.status, log.events(NAME))

    def POST(self):
        options.web_update(web.input())

        if water_sender is not None:
            water_sender.update()

        raise web.seeother(plugin_url(settings_page), True)


class settings_json(ProtectedPage):
    """Returns plugin settings in JSON format."""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        return json.dumps(options)
