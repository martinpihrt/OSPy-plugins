# -*- coding: utf-8 -*-
__author__ = 'Martin Pihrt' 
# https://www.eclipse.org/paho/clients/python/docs/

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
from ospy.options import rain_blocks
from ospy.programs import ProgramType
from ospy.inputs import inputs
from ospy.helpers import datetime_string



NAME = 'MQTT Zone Broadcaster'
MENU =  _('Package: MQTT Zone Broadcaster')
LINK = 'settings_page'

plugin_options = PluginOptions(
    NAME,
    {
        'use_mqtt': False,
        'zone_topic': 'stations'
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
        old_statuslist = ' '
        log.clear(NAME) 
        log.info(NAME, _('MQTT Zones Plugin started.'))
        once = True

        while not self._stop.is_set(): 
            if plugin_options['use_mqtt']:  
                once = True
                try:                    
                    statuslist = []

                    for station in stations.get():
                        if station.enabled or station.is_master or station.is_master_two: 
                            status = {
                                'station': station.index,
                                'status':  'on' if station.active else 'off',
                                'name':    station.name,
                                'reason':  'master' if station.is_master or station.is_master_two else ''}

                            if not station.is_master or not station.is_master_two:
                                if station.active:
                                    active = log.active_runs()
                                    for interval in active:
                                        if not interval['blocked'] and interval['station'] == station.index:
                                            status['reason'] = 'program'   

                                elif not options.scheduler_enabled:
                                    status['reason'] = 'system_off'
                                elif not station.ignore_rain and inputs.rain_sensed():
                                    status['reason'] = 'rain_sensed'
                                elif not station.ignore_rain and rain_blocks.seconds_left():
                                    status['reason'] = 'rain_delay'

                            statuslist.append(status)
               

                    zone_topic = plugin_options['zone_topic']
               
                    if zone_topic:
                        try:
                            from plugins import mqtt
                        except ImportError:
                            log.error(NAME, _('MQTT Zones Plugin requires MQTT plugin.'))

                        if statuslist != old_statuslist: # if status list is not actual
                            old_statuslist = statuslist
                    
                            client = mqtt.get_client()
                            
                            if client:           
                                client.publish(zone_topic, json.dumps(statuslist), qos=1, retain=True)
                                log.clear(NAME) 
                                log.info(NAME, datetime_string() + ' ' + _('MQTT Zones Plugin public') + ': ' + str(statuslist))

                    else:
                        log.clear(NAME) 
                        log.error(NAME, _('Not setup Zone Topic'))
                        self._sleep(5)
                        
                    self._sleep(5)         

                except Exception:
                    log.error(NAME, _('MQTT Zones plug-in') + ':\n' + traceback.format_exc())
                    self._sleep(60)

            else:
                if once: 
                    log.info(NAME, _('MQTT Zones Plugin is disabled.'))
                    once = False
                    try:
                        from plugins import mqtt
                        client = mqtt.get_client()
                        if client: 
                            client.disconnect()
                            client = None
                    except ImportError:
                        log.error(NAME, _('MQTT Zones Plugin requires MQTT plugin.'))

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
       
################################################################################
# Web pages:                                                                   #
################################################################################

class settings_page(ProtectedPage):
    """Load an html page for entering plugin settings."""

    def GET(self):
        return self.plugin_render.mqtt_zones(plugin_options, log.events(NAME))

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
