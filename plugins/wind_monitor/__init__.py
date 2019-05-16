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
from ospy import helpers


import i18n

NAME = 'Wind Speed Monitor'
LINK = 'settings_page'

wind_options = PluginOptions(
    NAME,
    {
        'use_wind_monitor': False,
        'address': 0,                # automatic search in range 0x50 - 0x51 for PCF8583
        'sendeml': True,             # True = send email with error
        'pulses': 2,                 # 2 pulses per rotation
        'metperrot': 1.492,          # 1.492 meter per hour per rotation
        'maxspeed': 20,              # 20 max speed to deactivate stations  
        'emlsubject': _('Report from OSPy WIND SPEED MONITOR plugin')
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
        if wind_options['address'] == 0:
            find_lcd_address()
        else:
            self.pcf = set_counter()     # set pcf8583 as counter

        log.clear(NAME)
        send = False      # send email
        disable_text = True
        val = 0.0
        maxval = 0.0
        timer_reset = 0

        while not self._stop.is_set():
            try:
                if wind_options['use_wind_monitor']:  # if wind plugin is enabled
                    disable_text = True
                                        
                    puls = counter()/10.0 # counter value is value/10sec
                                                                                                                         
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
                    msg = (datetime_string() + ': ' + _('System detected error: wind speed monitor. All stations set to OFF. Wind is') + ': ' + str(round(val*3.6,2)) + ' km/h.' )
                    try:
                        send_email(msg)
                        log.info(NAME, _('Email was sent') + ': ' + msg)
                        send = False
                    except Exception:
                        log.clear(NAME)
                        log.error(NAME, _('Email was not sent') + '! ' + traceback.format_exc())

                timer_reset+=10 # measure is 10 sec long
                

            except Exception:
                log.clear(NAME)
                log.error(NAME, _('Wind Speed monitor plug-in') + ':\n' + traceback.format_exc())
                self._sleep(60)


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


def send_email(msg):
    """Send email"""
    message = datetime_string() + ': ' + msg
    try:
        from plugins.email_notifications import email

        Subject = wind_options['emlsubject']

        email(message, subject=Subject)

        if not options.run_logEM:
           log.info(NAME, _('Email logging is disabled in options...'))
        else:        
           logEM.save_email_log(Subject, message, _('Sent'))

        log.info(NAME, _('Email was sent') + ': ' + message)

    except Exception:
        if not options.run_logEM:
           log.info(NAME, _('Email logging is disabled in options...'))
        else:
           logEM.save_email_log(Subject, message, _('Sent'))

        log.info(NAME, _('Email was not sent') + '! ' + traceback.format_exc())


def find_address():
    search_range = {addr: 'PCF8583' for addr in range(80, 81)}  # 0x50 converts to 80, 0x51 converts to 81

    try:
        import smbus

        bus = smbus.SMBus(0 if helpers.get_rpi_revision() == 1 else 1)
        # DF - alter RPi version test fallback to value that works on BBB
    except ImportError:
        log.warning(NAME, _('Could not import smbus.'))
    else:

        for addr, pcf_type in search_range.iteritems():
            try:
                # bus.write_quick(addr)
                bus.read_byte(addr) # DF - write_quick doesn't work on BBB
                log.info(NAME, 'Found %s on address 0x%02x' % (pcf_type, addr))
                wind_options['address'] = addr
                break
            except Exception:
                pass
        else:
            log.warning(NAME, _('Could not find any PCF8583 controller.'))


def set_counter():
    try:
        if wind_options['address'] != 0:
           import smbus
           bus = smbus.SMBus(0 if helpers.get_rpi_revision() == 1 else 1)
           bus.write_byte_data(wind_options['address'], 0x00, 0x20) # status registr setup to "EVENT COUNTER"
           bus.write_byte_data(wind_options['address'], 0x01, 0x00) # reset LSB
           bus.write_byte_data(wind_options['address'], 0x02, 0x00) # reset midle Byte
           bus.write_byte_data(wind_options['address'], 0x03, 0x00) # reset MSB
           log.info(NAME, _('Wind speed monitor plug-in') + ': ' + _('Setup PCF8583 as event counter - OK')) 
    except:
        log.error(NAME, _('Wind speed monitor plug-in') + ':\n' + _('Setup PCF8583 as event counter - FAULT'))
        log.error(NAME, _('Wind speed monitor plug-in') + traceback.format_exc())


def counter(): # reset PCF8583, measure pulses and return number pulses per second
    try:
        if wind_options['address'] != 0:
           import smbus
           bus = smbus.SMBus(0 if helpers.get_rpi_revision() == 1 else 1) 
           # reset PCF8583
           bus.write_byte_data(wind_options['address'], 0x01, 0x00) # reset LSB
           bus.write_byte_data(wind_options['address'], 0x02, 0x00) # reset midle Byte
           bus.write_byte_data(wind_options['address'], 0x03, 0x00) # reset MSB
           time.sleep(10)
           # read number (pulses in counter) and translate to DEC
           counter = bus.read_i2c_block_data(wind_options['address'], 0x00)
           num1 = (counter[1] & 0x0F)             # units
           num10 = (counter[1] & 0xF0) >> 4       # dozens
           num100 = (counter[2] & 0x0F)           # hundred
           num1000 = (counter[2] & 0xF0) >> 4     # thousand
           num10000 = (counter[3] & 0x0F)         # tens of thousands
           num100000 = (counter[3] & 0xF0) >> 4   # hundreds of thousands
           pulses = (num100000 * 100000) + (num10000 * 10000) + (num1000 * 1000) + (num100 * 100) + (num10 * 10) + num1
           return pulses
    except:
        log.error(NAME, _('Wind speed monitor plug-in') + traceback.format_exc())
        time.sleep(10)
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

