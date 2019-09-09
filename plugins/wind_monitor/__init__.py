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
from ospy.log import log, logEM
from plugins import PluginOptions, plugin_url
from ospy.webpages import ProtectedPage
from ospy.helpers import datetime_string
from ospy import helpers


import i18n

NAME = 'Wind Speed Monitor'
LINK = 'settings_page'

wind_options = PluginOptions(
    NAME,
    {
        'use_wind_monitor': False,
        'address': False,            # True = 0x51, False = 0x50 for PCF8583
        'sendeml': True,             # True = send email with error
        'pulses': 2,                 # 2 pulses per rotation
        'metperrot': 1.492,          # 1.492 meter per hour per rotation
        'maxspeed': 20,              # 20 max speed to deactivate stations  
        'emlsubject': _('Report from OSPy WIND SPEED MONITOR plugin'),
        'log_speed': 0,              # actual speed
        'log_maxspeed': 0,           # maximal speed (log) in km/h
        'log_date_maxspeed': _('Measuring...') # maximal speed (date log)
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
        log.clear(NAME)
        send = False      # send email
        disable_text = True
        val = 0
        maxval = 0

        while not self._stop.is_set():
            try:
                if wind_options['use_wind_monitor']:    # if wind plugin is enabled
                    disable_text = True
                    
                    try:
                        import smbus  # for PCF 8583
                        self.bus = smbus.SMBus(0 if helpers.get_rpi_revision() == 1 else 1) 

                    except ImportError:
                        log.warning(NAME, _('Could not import smbus.'))

                    if self.bus is not None:
                        set_counter(self.bus)     # set pcf8583 as counter
                        puls = counter(self.bus)  # read pulses

                    if puls is not None:                    
                        puls = counter(self.bus)/10.0           # counter value is value/10sec
                        val = puls/(wind_options['pulses']*1.0)
                        val = val*wind_options['metperrot']   

                        wind_options['log_speed'] = round(val,2) # m/sec

                        if val > wind_options['log_maxspeed']:
                            wind_options['log_maxspeed'] = val
                            
                            qdict = {} # save to options max speed and datetime
                            if wind_options['use_wind_monitor']:
                                qdict['use_wind_monitor'] = u'on' 
                            if wind_options['address']:
                                qdict['address']  = u'on'
                            if wind_options['sendeml']:     
                                qdict['sendeml'] = u'on' 
                            qdict['log_maxspeed'] = round(val,2) # m/sec
                            qdict['log_date_maxspeed'] = datetime_string()
                            wind_options.web_update(qdict)                           

                        self.status['meter']  = round(val,2)
                        self.status['kmeter'] = round(val*3.6,2)

                        log.clear(NAME)
                        log.info(NAME, _('Please wait 10 sec...'))
                        log.info(NAME, _('Speed') + ' ' + str(round(val,2)) + ' ' + _('m/sec'))
                        log.info(NAME, _('Pulses') + ' ' + str(puls) + ' ' + _('pulses/sec'))
                        if wind_options['log_maxspeed'] > 0:
                            log.info(NAME, str(wind_options['log_date_maxspeed']) + ' ' + _('Maximal speed') + ': ' + str(wind_options['log_maxspeed']) + ' ' + _('m/sec') + '.')  
            
                        if val >= 42: 
                            log.error(NAME, _('Wind speed > 150 km/h (42 m/sec)'))
                                     
                        if get_station_is_on():                               # if station is on
                            if val >= int(wind_options['maxspeed']):          # if wind speed is > options max speed
                                log.clear(NAME)
                                log.finish_run(None)                          # save log
                                stations.clear()                              # set all station to off
                                log.clear(NAME)
                                log.info(NAME, _('Stops all stations and sends email if enabled sends email.'))
                                if wind_options['sendeml']:                   # if enabled send email
                                    send = True  
                    else:
                        self._sleep(1)                                
                                      
                else:
                    # text on the web if plugin is disabled
                    if disable_text:  
                        log.clear(NAME)
                        log.info(NAME, _('Wind speed monitor plug-in is disabled.'))
                        disable_text = False   
                    self._sleep(1)                        

                if send:
                    msg = '<b>' + _('Wind speed monitor plug-in') + '</b> ' + '<br><p style="color:red;">' + _('System detected error: wind speed monitor. All stations set to OFF. Wind is') + ': ' + str(round(val*3.6,2)) + ' km/h. </p>'
                    msglog= _('System detected error: wind speed monitor. All stations set to OFF. Wind is') + ': ' + str(round(val*3.6,2)) + ' km/h.'
                    send_email(msg, msglog)
                    send = False
                

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


def send_email(msg, msglog):
    """Send email"""
    message = datetime_string() + ': ' + msg
    try:
        from plugins.email_notifications import email

        Subject = wind_options['emlsubject']

        email(message, subject=Subject)

        if not options.run_logEM:
            log.info(NAME, _('Email logging is disabled in options...'))
        else:        
            logEM.save_email_log(Subject, msglog, _('Sent'))

        log.info(NAME, _('Email was sent') + ': ' + msglog)

    except Exception:
        if not options.run_logEM:
            log.info(NAME, _('Email logging is disabled in options...'))
        else:
            logEM.save_email_log(Subject, msglog, _('Email was not sent'))

        log.info(NAME, _('Email was not sent') + '! ' + traceback.format_exc())


def set_counter(i2cbus):
    try:
    	addr = 0
        if wind_options['address']:
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
        log.debug(NAME, _('Wind speed monitor plug-in') + ': ' + _('Setup PCF8583 as event counter - OK')) 

    except:
        log.error(NAME, _('Wind speed monitor plug-in') + ':\n' + _('Setup PCF8583 as event counter - FAULT'))
        log.error(NAME, _('Wind speed monitor plug-in') + traceback.format_exc())


def counter(i2cbus): # reset PCF8583, measure pulses and return number pulses per second
    try:
        pulses = 0
    	addr = 0
        
        if wind_options['address']:
            addr = 0x51
        else:
            addr = 0x50

        # reset PCF8583
        try_io(lambda: i2cbus.write_byte_data(addr, 0x01, 0x00)) # reset LSB
        try_io(lambda: i2cbus.write_byte_data(addr, 0x02, 0x00)) # reset midle Byte
        try_io(lambda: i2cbus.write_byte_data(addr, 0x03, 0x00)) # reset MSB
        time.sleep(10)
        # read number (pulses in counter) and translate to DEC
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
        log.error(NAME, _('Wind speed monitor plug-in') + traceback.format_exc())
        time.sleep(10)
        return None


def get_station_is_on(): # return true if stations is ON
    if not options.manual_mode:                   # if not manual control
        for station in stations.get():
                if station.active:                # if station is active
                    return True
                else:
                    return False


def get_all_values():
    return wind_options['log_speed'], wind_options['log_maxspeed'], wind_options['log_date_maxspeed']                     


################################################################################
# Web pages:                                                                   #
################################################################################


class settings_page(ProtectedPage):
    """Load an html page for entering wind speed monitor settings."""

    def GET(self):
        global wind_sender

        qdict = web.input()
        reset = helpers.get_input(qdict, 'reset', False, lambda x: True)

        if wind_sender is not None and reset:
            if wind_options['use_wind_monitor']:
                qdict['use_wind_monitor'] = u'on' 
            if wind_options['address']:
                qdict['address']  = u'on'
            if wind_options['sendeml']:     
                qdict['sendeml'] = u'on' 
            qdict['log_maxspeed'] = 0
            qdict['log_date_maxspeed'] =  datetime_string()
                
            wind_options.web_update(qdict)    
            log.clear(NAME)
            log.info(NAME, datetime_string() + ': ' + _('Maximal speed has reseted.'))
            
            raise web.seeother(plugin_url(settings_page), True)

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


class data_json(ProtectedPage):
    """Returns plugin data in JSON format."""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        data =  {
          'log_maxspeed': round(wind_options['log_maxspeed'],2),    # in m/sec
          'log_speed': round(wind_options['log_speed'],2),          # in m/sec
          'log_date_maxspeed': wind_options['log_date_maxspeed'],
          'label': wind_options['emlsubject']
        }

        return json.dumps(data)
