#!/usr/bin/env python
# -*- coding: utf-8 -*-
__author__ = 'Martin Pihrt'

import json
import time
import datetime
import traceback
import web

import i18n

from blinker import signal

from ospy import helpers
from ospy.helpers import datetime_string
from ospy.log import log, logEM
from threading import Thread, Event
from plugins import PluginOptions, plugin_url
from ospy.webpages import ProtectedPage
from ospy.stations import stations
from ospy.options import options


NAME = 'Water Consumption Counter'  ### name for plugin in plugin manager ###
LINK = 'settings_page'              ### link for page in plugin manager ###
 
plugin_options = PluginOptions(
    NAME,
    { ### here is your plugin options ###
    'liter_per_sec_master_one': 0.45, # l/s  
    'liter_per_sec_master_two': 0.01, # l/s
    'last_reset': '-',                # from helpers datetime_string
    'sum_one': 0.00,                  # sum for master 1
    'sum_two': 0.00,                  # sum for master 2
    'sendeml': False,
    'emlsubject': _('Report from OSPy Water Consumption Counter plugin')
    }
)

master_one_start = datetime.datetime.now() # start time for master 1
master_two_start = datetime.datetime.now() # start time for master 2
status = { }

################################################################################
# Main function loop:                                                          #
################################################################################

class Sender(Thread):
    def __init__(self):
        Thread.__init__(self)
        self.daemon = True
        self._stop = Event()

        global status 
        
        status['sum1%d'] = plugin_options['sum_one'] #round(plugin_options['sum_one'],2)
        status['sum2%d'] = plugin_options['sum_two'] #round(plugin_options['sum_two'],2)
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
            master_one_on = signal('master_one_on')
            master_one_on.connect(notify_master_one_on)
            master_one_off = signal('master_one_off')
            master_one_off.connect(notify_master_one_off)
            master_two_on = signal('master_two_on')
            master_two_on.connect(notify_master_two_on)
            master_two_off = signal('master_two_off')
            master_two_off.connect(notify_master_two_off)  

        except Exception:
            log.clear(NAME)
            log.error(NAME, _('Water Consumption Counter plug-in') + traceback.format_exc())       
            self._sleep(60)

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


### convert number to decimal ###
def to_decimal(number):
    try:
    	import decimal
        return decimal.Decimal(number)
    
    except decimal.InvalidOperation:
        log.clear(NAME)
        log.error(NAME, _('Water Consumption Counter plug-in') + traceback.format_exc()) 
        return 0.00    

### send email ###
def send_email(msg, msglog):
    message = datetime_string() + ': ' + msg
    try:
        from plugins.email_notifications import email

        Subject = plugin_options['emlsubject']

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


### master one on ###
def notify_master_one_on(name, **kw):
    global master_one_start
    log.clear(NAME)
    log.info(NAME, datetime_string() + ': ' + _('Master station 1 running, please wait...'))
    master_one_start = datetime.datetime.now()

### master one off ###
def notify_master_one_off(name, **kw):
    global status
    log.info(NAME, datetime_string() + ': ' + _('Master station 1 stopped, counter finished...')) 
    master_one_stop  = datetime.datetime.now()
    master_one_time_delta  = (master_one_stop - master_one_start).total_seconds() # run time in seconds
    difference = to_decimal(master_one_time_delta) * to_decimal(plugin_options['liter_per_sec_master_one'])
    plugin_options['sum_one'] =  plugin_options['sum_one'] + round(difference,2)  # to 2 places

    if plugin_options['sum_one'] < 1000:
        status['sum1%d'] = plugin_options['sum_one']       # in liters
    else:
        status['sum1%d'] = plugin_options['sum_one']/1000  # in m3

    msg = '<b>' + _('Water Consumption Counter plug-in') + '</b> ' + '<br><p style="color:green;">' + _('Water Consumption') + ' ' + str(round(difference,2)) + _('liter') + '</p>'
    msglog = _('Water Consumption Counter plug-in') + ': ' + _('Water Consumption for master 1') + ': ' + str(round(difference,2)) + ' ' + _('liter')
    try:
        send_email(msg, msglog)
    except Exception:
        log.error(NAME, _('Email was not sent') + '! '  + traceback.format_exc())
    

### master two on ###
def notify_master_two_on(name, **kw):
    global master_two_start
    log.clear(NAME)
    log.info(NAME, datetime_string() + ': ' + _('Master station 2 running, please wait...'))
    master_two_start = datetime.datetime.now()  

### master two off ###
def notify_master_two_off(name, **kw):
    global status
    log.info(NAME, datetime_string() + ': ' + _('Master station 2 stopped, counter finished...')) 
    master_two_stop  = datetime.datetime.now()
    master_two_time_delta  = (master_two_stop - master_two_start).total_seconds() 
    difference = to_decimal(master_two_time_delta) * to_decimal(plugin_options['liter_per_sec_master_two'])
    plugin_options['sum_two'] =  plugin_options['sum_two'] + round(difference,2)  # to 2 places
  
    if plugin_options['sum_two'] < 1000:
        status['sum2%d'] = plugin_options['sum_two'] 
    else:
        status['sum2%d'] = plugin_options['sum_two']/1000

    msg = '<b>' + _('Water Consumption Counter plug-in') + '</b> ' + '<br><p style="color:green;">' + _('Water Consumption') + ' ' + str(round(difference,2)) + _('liter') + '</p>'
    msglog = _('Water Consumption Counter plug-in') + ': ' + _('Water Consumption for master 2') + ': ' + str(round(difference,2)) + ' ' + _('liter')
    try:
        send_email(msg, msglog)
    except Exception:
        log.error(NAME, _('Email was not sent') + '! '  + traceback.format_exc())        


################################################################################
# Web pages:                                                                   #
################################################################################

class settings_page(ProtectedPage):
    """Load an html page for entering adjustments."""

    def GET(self):
        global sender, status

        qdict = web.input()
        reset = helpers.get_input(qdict, 'reset', False, lambda x: True)
        if sender is not None and reset:
            plugin_options['sum_one'] = 0
            plugin_options['sum_two'] = 0
            plugin_options['last_reset'] = datetime_string()
            status['sum1%d'] = 0.00
            status['sum2%d'] = 0.00
            log.clear(NAME)
            log.info(NAME, datetime_string() + ': ' + _('Counter has reseted'))
            raise web.seeother(plugin_url(settings_page), True)

        return self.plugin_render.water_consumption_counter(plugin_options, status, log.events(NAME))       

    def POST(self):
        plugin_options.web_update(web.input()) ### update options from web ###

        if sender is not None:
            sender.update()                
        raise web.seeother(plugin_url(settings_page), True)

class settings_json(ProtectedPage):            ### return plugin_options as JSON data ###
    """Returns plugin settings in JSON format."""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        return json.dumps(plugin_options)
