!/usr/bin/env python
# -*- coding: utf-8 -*-
__author__ = 'Martin Pihrt' # first author: "Orginally written by Daniel Casner <daniel@danielcasner.org> Modified from OSPy Martin Pihrt."

import json
import time
import datetime
import traceback

from threading import Thread, Event

import web

from ospy.log import log
from plugins import PluginOptions, plugin_url, plugin_data_dir
from ospy.webpages import ProtectedPage
from ospy.options import options
from ospy.stations import stations


import i18n

NAME = 'MQTT Slave'
LINK = 'settings_page'

plugin_options = PluginOptions(
    NAME,
    {
        'use_mqtt': False,
        'control_topic': '',
        'first_station': '1',
        'station_count': '8'
     }
)


################################################################################
# Main function:                                                               #
################################################################################

class Sender(Thread):
    def __init__(self):
        Thread.__init__(self)
        self.daemon = True
        self._stop = Event()

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
        log.info(NAME, _('MQTT Slave Plugin started.'))
        once = True
        
        if not self._stop.is_set(): 
            if plugin_options['use_mqtt']:  
                once = True
                try:     
                    from plugins import mqtt

                except ImportError:
                    log.error(NAME, _('MQTT Slave Plugin requires MQTT plugin.'))               
                
                try:                    
                    subscribe()                             

                except Exception:
                    log.error(NAME, _('MQTT Slave plug-in') + ':\n' + traceback.format_exc())
                    self._sleep(5)

            else:
                if once: 
                    log.info(NAME, _('MQTT Slave Plugin is disabled.'))
                    once = False
                self._sleep(5)
                             
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

def on_message(client, msg):
    "Callback when MQTT message is received."
    #if not gv.sd['en']: # check operation status
    #    return
    
    #num_brds = gv.sd['nbrd']
    #num_sta  = num_brds * 8
    try:
        cmd = json.loads(msg.payload)
        # example: cmd = [{'status': 'off', 'reason': 'master', 'station': 0, 'name': u'\u010cerpadlo'}, {'status': 'off', 'reason': '', 'station': 1, 'name': u'Kv\u011btiny'}, {'status': 'off', 'reason': '', 'station': 2, 'name': u'3'}, {'status': 'off', 'reason': '', 'station': 3, 'name': u'Ventil\xe1tor'}, {'status': 'off', 'reason': '', 'station': 4, 'name': u'5'}, {'status': 'off', 'reason': '', 'station': 5, 'name': u'6'}, {'status': 'off', 'reason': '', 'station': 6, 'name': u'7'}, {'status': 'off', 'reason': '', 'station': 7, 'name': u'8'}, {'status': 'off', 'reason': '', 'station': 8, 'name': u'9'}, {'status': 'off', 'reason': '', 'station': 9, 'name': u'J\xeddlo mp3'}, {'status': 'off', 'reason': '', 'station': 10, 'name': u'Konec mp3'}, {'status': 'off', 'reason': '', 'station': 11, 'name': u'12'}]

    except ValueError as e:
        log.info(NAME, _('MQTT Slave could not decode command: ') + msg.payload + e)
        return
    
    zones = cmd['zone_list']  #  list of all zones sent from master
    first = int(plugin_options['first_station']) - 1
    count = int(plugin_options['station_count'])
    local_zones = zones[first : first + count] 
    #for i in range(len(local_zones)):
    #    if (local_zones[i] and not gv.srvals[i]): # if this element has a value and is not on
    #        gv.rs[i][0] = gv.now
    #        gv.rs[i][1] = float('inf')
    #        gv.rs[i][3] = 99
    #        gv.ps[i][0] = 99 
    #    elif (gv.srvals[i] and not local_zones[i]):
    #        gv.rs[i][1] = gv.now
    #if any(gv.rs):
    #    gv.sd['bsy'] = 1

    self._sleep(1)

    
def subscribe():
    "Subscribe to messages"
    topic = plugin_options['control_topic']
    if topic:
        mqtt.subscribe(topic, on_message, 2)
       
       
################################################################################
# Web pages:                                                                   #
################################################################################

class settings_page(ProtectedPage):
    """Load an html page for entering plugin settings."""

    def GET(self):
        return self.plugin_render.mqtt_slave(plugin_options, log.events(NAME))

    def POST(self): 
        plugin_options.web_update(web.input())
        if sender is not None:
            sender.update()
        
        raise web.seeother(plugin_url(settings_page), True)

class settings_json(ProtectedPage):
    """Returns plugin settings in JSON format."""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        return json.dumps(plugin_options)    
