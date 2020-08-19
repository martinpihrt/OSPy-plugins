# -*- coding: utf-8 -*-
__author__ = 'Martin Pihrt' 

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
from ospy.helpers import datetime_string
from ospy.stations import stations
from ospy.runonce import run_once
from ospy.programs import programs
from ospy.programs import ProgramType


NAME = 'MQTT Run-once'
MENU =  _(u'Package: MQTT Run-once')
LINK = 'settings_page'

plugin_options = PluginOptions(
    NAME,
    {  
        'use_mqtt': False,
        'schedule_topic': u'runonce'
     }
)

client = None

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
        log.info(NAME, _('MQTT Run-once Plugin started.'))
        once = True
        two = True

        while not self._stop.is_set(): 
            if plugin_options['use_mqtt']:  
                once = True
                if two:
                    try:    
                        subscribe()
                        two = False

                    except Exception:
                        log.error(NAME, _('MQTT Run-once plug-in') + ':\n' + traceback.format_exc())    

            else:
                if once: 
                    log.clear(NAME)
                    log.info(NAME, _('MQTT Run-once Plugin is disabled.'))
                    once = False
                    two = True

            self._sleep(1)

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

def on_message(client, userdata, message):
    """Callback when MQTT message is received."""
    if not options.enable:  # check operation status
        log.error(NAME, _(u'System OSPy is not switched to enabled. Skipping decoding command.'))
        return
    
    log.info(NAME, _(u'Received message') + ' :' + str(message.payload) + ' ' +_('on topic') + str(message.topic) + ' ' + _('with QoS') + ' ' + str(message.qos))

    try:
        cmd = json.loads(message.payload)
        # Ex. command for run-now station 1 and 3 for 5 minutes and 20 seconds (6 minutes and 10 seconds): [{0,5,20},{2,6,10}]
    except ValueError as e:
        log.error(NAME, _(u'MQTT Run-once could not decode command:'), message.payload, e)
        return

    num_sta = options.output_count    

    if type(cmd) is list:
        if len(cmd) < num_sta:
            log.error(NAME, _(u'MQTT Run-once, not enough stations specified, assuming first {} of {}').format(len(cmd), num_sta))
            rovals = cmd + ([0] * (num_sta - len(cmd)))
        elif len(cmd) > num_sta:
            log.error(NAME, _(u'MQTT Run-once, too many stations specified, truncating to {}').format(num_sta))
            rovals = cmd[0:num_sta]
        else:
            rovals = cmd
    else:
        log.error(NAME, _(u'MQTT Run-once unexpected command: '), message.payload)
        return

    if any(rovals):
       log.info(NAME, _(u'MQTT Run-once: '), rovals)

    #moje      qdict = web.input()
    #    station_seconds = {}
    #    for station in stations.enabled_stations():
    #        mm_str = "mm" + str(station.index)
    #        ss_str = "ss" + str(station.index)
    #        if mm_str in qdict and ss_str in qdict:
    #            seconds = int(qdict[mm_str] or 0) * 60 + int(qdict[ss_str] or 0)
    #            station_seconds[station.index] = seconds

        
    #    run_once.set(station_seconds)

    #  stop ...if stop_all:
    #         if not options.manual_mode:
    #             options.scheduler_enabled = False
    #             programs.run_now_program = None
    #             run_once.clear()
    #         log.finish_run(None)
    #         stations.clear()


def subscribe():
    """Subscribe to messages"""
    topic = plugin_options['schedule_topic']
    if topic:
        try:
            from plugins import mqtt
            client = mqtt.get_client()

            if client:           
                log.clear(NAME) 
                log.info(NAME, datetime_string() + ' ' + _('MQTT Run-once Plugin subscribe') + ': ' + topic)
                #client.subscribe(topic, on_message, 2) 
                client.subscribe(topic, 2) 
                client.on_message = on_message       

        except ImportError:
            log.error(NAME, _('MQTT Run-once Plugin requires MQTT plugin.'))        
       
################################################################################
# Web pages:                                                                   #
################################################################################

class settings_page(ProtectedPage):
    """Load an html page for entering plugin settings."""

    def GET(self):
        return self.plugin_render.mqtt_runonce(plugin_options, log.events(NAME))

    def POST(self): 
        plugin_options.web_update(web.input())
        subscribe()
        
        raise web.seeother(plugin_url(settings_page), True)


class settings_json(ProtectedPage):
    """Returns plugin settings in JSON format."""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        return json.dumps(plugin_options)    
