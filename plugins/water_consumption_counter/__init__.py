#!/usr/bin/env python
# -*- coding: utf-8 -*-
__author__ = 'Martin Pihrt'

import json
import time
import traceback
import web

import i18n

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
    'liter_per_sec_master_two': 1.15, # l/s
    'last_reset': '-',                # from helpers datetime_string
    'sum_one': 0,                     # sum for master 1
    'sum_two': 0                      # sum for master 2
    }
)


################################################################################
# Main function loop:                                                          #
################################################################################

class Sender(Thread):
    def __init__(self):
        Thread.__init__(self)
        self.daemon = True
        self._stop = Event()

        self.status = {}

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
        while not self._stop.is_set():
            try:
                if get_master_is_on():       # if master station is on
                   plugin_options['sum_one'] = plugin_options['sum_one'] + plugin_options['liter_per_sec_master_one'] 
                
                if get_master_two_is_on():   # if master 2 station is on
                   plugin_options['sum_two'] = plugin_options['sum_two'] + plugin_options['liter_per_sec_master_two']                

                log.clear(NAME)
                if plugin_options['sum_one'] <= 1000: 
                    log.info(NAME, _('Sum master station one:') + ' ' + str(plugin_options['sum_one']) + ' ' + _('liter.'))
                else:
                    log.info(NAME, _('Sum master station one:') + ' ' + str(plugin_options['sum_one']) + ' ' + _('m3.'))

                if plugin_options['sum_two'] <= 1000: 
                    log.info(NAME, _('Sum master station two:') + ' ' + str(plugin_options['sum_two']) + ' ' + _('liter.'))
                else:
                    log.info(NAME, _('Sum master station two:') + ' ' + str(plugin_options['sum_two']) + ' ' + _('m3.'))

                log.info(NAME, _('Last counter reset:') + ' ' + plugin_options['last_reset'] + '.')

                self._sleep(1)   

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

### master on ###
def get_master_is_on():
    if stations.master is not None:                            # if is use master station
        for station in stations.get():
            if station.is_master:                              # if station is master
                if station.active:                             # if master is active
                    return True
                else:
                    return False  
    else:                     
        return False

### master 2 on ###
def get_master_two_is_on():
    if stations.master_two is not None:                        # if is use master 2 station
        for station in stations.get():
            if station.is_master_two:                          # if station is master 2
                if station.active:                             # if master 2 is active
                    return True
                else:
                    return False  
    else:                     
        return False


################################################################################
# Web pages:                                                                   #
################################################################################

class settings_page(ProtectedPage):
    """Load an html page for entering adjustments."""

    def GET(self):
        global sender

        qdict = web.input()
        reset = helpers.get_input(qdict, 'reset', False, lambda x: True)
        if sender is not None and reset:
            plugin_options['sum_one'] = 0
            plugin_options['sum_two'] = 0
            plugin_options['last_reset'] = datetime_string()
            log.info(NAME, datetime_string() + ': ' + _('Counter has reseted'))
            raise web.seeother(plugin_url(settings_page), True)

        return self.plugin_render.water_consumption_counter(plugin_options, log.events(NAME))       

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
