#!/usr/bin/env python
# -*- coding: utf-8 -*-
__author__ = 'Martin Pihrt'
# This plugins check wind speed in meter per second. 
# This plugin read data from I2C counter PCF8583 on I2C address 0x50. Max count PCF8583 is 1 milion pulses per seconds

import json
import time
import sys
import traceback

from threading import Thread, Event

import web
from ospy.stations import stations
from ospy.options import options
from ospy.log import log
from plugins import PluginOptions, plugin_url
from ospy.webpages import ProtectedPage
from ospy.helpers import get_rpi_revision
from ospy.helpers import datetime_string

import i18n

NAME = 'Wind Speed Monitor'
LINK = 'settings_page'

wind_options = PluginOptions(
    NAME,
    {
        "use_wind_monitor": False,
        "address": False,            # True = 0x51, False = 0x50 for PCF8583
        "sendeml": True,             # True = send email with error
        "pulses": 2,                 # 2 pulses per rotation
        "metperrot": 1.492,          # 1.492 meter per hour per rotation
        "maxspeed": 20               # 20 max speed to deactivate stations  
    }
)

################################################################################
# Main function loop:                                                          #
################################################################################

class WindSender(Thread):
    def __init__(self):
        Thread.__init__(self)
        self.daemon = True
        self._stop = Event()
   
        self.bus = None
        self.pcf = None
        self.status = {}
        self.status['meter'] = 0.0
        self.status['kmeter'] = 0.0

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

            self.bus = smbus.SMBus(1 if get_rpi_revision() >= 2 else 0)
        except ImportError:
            log.warning(NAME, _('Could not import smbus.'))

        if self.bus is not None:
            self.pcf = set_counter(self.bus)     # set pcf8583 as counter

        log.clear(NAME)
        send = False      # send email
        disable_text = True
        val = 0.0
        maxval = 0.0
        timer_reset = 0

        while not self._stop.is_set():
            try:
                if self.bus is not None and wind_options['use_wind_monitor']:  # if wind plugin is enabled
                    disable_text = True
                                        
                    puls = counter(self.bus)/10.0 # counter value is value/10sec
                                                                                                      
                    val = puls/(wind_options['pulses']*1.0)
                    val = val*wind_options['metperrot'] 
                    
                    if val > maxval:
                        maxval = val

                    if timer_reset >= 86400: # 1 day
                       timer_reset = 0
                       maxval = 0.0

                    self.status['meter'] = round(val,2)
                    self.status['kmeter'] = round(val*3.6,2)

                    log.clear(NAME)
                    log.info(NAME, _('Please wait 10 sec...'))
                    log.info(NAME, _('Speed') + ' ' + str(round(val,2)) + ' ' + _('m/sec'))
                    log.info(NAME, _('Speed Peak 24 hour') + ' ' + str(round(maxval,2)) + ' ' + _('m/sec') )
                    log.info(NAME, _('Pulses') + ' ' + str(puls) + ' ' + _('pulses/sec') )

                      
                    if val >= 42: 
                       log.error(NAME, _('Wind speed > 150 km/h (42 m/sec)'))
                   
                   
                    if get_station_is_on():                               # if station is on
                       if val >= int(wind_options['maxspeed']):           # if wind speed is > options max speed
                          log.clear(NAME)
                          log.finish_run(None)                            # save log
                          stations.clear()                                # set all station to off
                          log.clear(NAME)
                          log.info(NAME, _('Stops all stations and sends email if enabled sends email.'))
                          if wind_options['sendeml']:                     # if enabled send email
                             send = True                    
                                      
                else:
                    # text on the web if plugin is disabled
                    if disable_text:  
                       log.clear(NAME)
                       log.info(NAME, _('Wind speed monitor plug-in is disabled.'))
                       disable_text = False                        

                if send:
                    TEXT = (datetime_string() + ': ' + _('System detected error: wind speed monitor. All stations set to OFF. Wind is') + ': ' + str(round(val*3.6,2)) + ' km/h.' )
                    try:
                        from plugins.email_notifications import email 
                        email(TEXT)                             # send email without attachments
                        log.info(NAME, _('Email was sent') + ': ' + TEXT)
                        send = False
                    except Exception:
                        log.clear(NAME)
                        log.error(NAME, _('Email was not sent') + '! ' + traceback.format_exc())

                timer_reset+=10 # measure is 10 sec long
                

            except Exception:
                log.clear(NAME)
                log.error(NAME, _('Wind Speed monitor plug-in') + ':\n' + traceback.format_exc())
                self._sleep(60)
                self.pcf = set_counter(self.bus)     # set pcf8583 as counter


wind_sender = None

################################################################################
# Helper functions:                                                            #
################################################################################
def start():
    global wind_sender
    if wind_sender is None:
        wind_sender = WindSender()


def stop():
    global wind_sender
    if wind_sender is not None:
        wind_sender.stop()
        wind_sender.join()
        wind_sender = None


def set_counter(i2cbus):
    try:
        if wind_options['address']:
            pcf_addr = 0x51
        else:
            pcf_addr = 0x50 
        i2cbus.write_byte_data(pcf_addr, 0x00, 0x20) # status registr setup to "EVENT COUNTER"
        i2cbus.write_byte_data(pcf_addr, 0x01, 0x00) # reset LSB
        i2cbus.write_byte_data(pcf_addr, 0x02, 0x00) # reset midle Byte
        i2cbus.write_byte_data(pcf_addr, 0x03, 0x00) # reset MSB
        log.info(NAME, _('Wind speed monitor plug-in') + ': ' + _('Setup PCF8583 as event counter - OK'))
        return 1  
    except:
        log.error(NAME, _('Wind speed monitor plug-in') + ':\n' + _('Setup PCF8583 as event counter - FAULT'))
        return None


def counter(i2cbus): # reset PCF8583, measure pulses and return number pulses per second
    try:
        if wind_options['address']:
            pcf_addr = 0x51
        else:
            pcf_addr = 0x50 
        # reset PCF8583
        i2cbus.write_byte_data(pcf_addr, 0x01, 0x00) # reset LSB
        i2cbus.write_byte_data(pcf_addr, 0x02, 0x00) # reset midle Byte
        i2cbus.write_byte_data(pcf_addr, 0x03, 0x00) # reset MSB
        time.sleep(10)
        # read number (pulses in counter) and translate to DEC
        counter = i2cbus.read_i2c_block_data(pcf_addr, 0x00)
        num1 = (counter[1] & 0x0F)             # units
        num10 = (counter[1] & 0xF0) >> 4       # dozens
        num100 = (counter[2] & 0x0F)           # hundred
        num1000 = (counter[2] & 0xF0) >> 4     # thousand
        num10000 = (counter[3] & 0x0F)         # tens of thousands
        num100000 = (counter[3] & 0xF0) >> 4   # hundreds of thousands
        pulses = (num100000 * 100000) + (num10000 * 10000) + (num1000 * 1000) + (num100 * 100) + (num10 * 10) + num1
        return pulses
    except:
        return 0


def get_station_is_on(): # return true if stations is ON
    if not options.manual_mode:                   # if not manual control
        for station in stations.get():
                if station.active:                # if station is active
                    return True
                else:
                    return False


################################################################################
# Web pages:                                                                   #
################################################################################


class settings_page(ProtectedPage):
    """Load an html page for entering wind speed monitor settings."""

    def GET(self):
        return self.plugin_render.wind_monitor(wind_options, wind_sender.status, log.events(NAME))

    def POST(self):
        wind_options.web_update(web.input())

        if wind_sender is not None:
            wind_sender.update()
        raise web.seeother(plugin_url(settings_page), True)


class settings_json(ProtectedPage):
    """Returns plugin settings in JSON format."""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        return json.dumps(wind_options)

