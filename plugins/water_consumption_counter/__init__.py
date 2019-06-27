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
from ospy.log import log
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
    'liter_per_sec_master_one': 1.15, # l/s  
    'liter_per_sec_master_two': 0.01, # l/s
    'last_reset': '-',                # from helpers datetime_string
    'sum_one': 0.00,                  # sum for master 1
    'sum_two': 0.00                   # sum for master 2
    }
)

master_one_start = datetime.datetime.now() # start time for master 1
master_one_stop  = datetime.datetime.now() # stop time for master 1
master_two_start = datetime.datetime.now() # start time for master 2
master_two_stop  = datetime.datetime.now() # stop time for master 2
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
        
        status['sum1%d'] = round(plugin_options['sum_one'],2)
        status['sum2%d'] = round(plugin_options['sum_two'],2)
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

### master one on ###
def notify_master_one_on(name, **kw):
    global master_one_start
    log.clear(NAME)
    log.info(NAME, datetime_string() + ': ' + _('Master station 1 running, please wait...'))
    master_one_start = datetime.datetime.now()

### master one off ###
def notify_master_one_off(name, **kw):
    global master_one_stop, status
    log.info(NAME, datetime_string() + ': ' + _('Master station 1 stopped, counter finished...')) 
    master_one_stop  = datetime.datetime.now()
    master_one_time_delta  = (master_one_stop - master_one_start).total_seconds() 
    plugin_options['sum_one'] =  master_one_time_delta * plugin_options['liter_per_sec_master_one']
    if plugin_options['sum_one'] < 1000:
        status['sum1%d'] = round(plugin_options['sum_one'],2)
    else:
        status['sum1%d'] = round(plugin_options['sum_one']/1000,2)

### master two on ###
def notify_master_two_on(name, **kw):
    global master_two_start
    log.clear(NAME)
    log.info(NAME, datetime_string() + ': ' + _('Master station 2 running, please wait...'))
    master_two_start = datetime.datetime.now()  

### master two off ###
def notify_master_two_off(name, **kw):
    global master_two_stop, status
    log.info(NAME, datetime_string() + ': ' + _('Master station 2 stopped, counter finished...')) 
    master_two_stop  = datetime.datetime.now()
    master_two_time_delta  = (master_two_stop - master_two_start).total_seconds() 
    plugin_options['sum_two'] =  master_two_time_delta * plugin_options['liter_per_sec_master_two']
    if plugin_options['sum_two'] < 1000:
        status['sum2%d'] = round(plugin_options['sum_two'],2)
    else:
        status['sum2%d'] = round(plugin_options['sum_two']/1000,2)


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
            status['sum1%d'] = 0
            status['sum2%d'] = 0
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
