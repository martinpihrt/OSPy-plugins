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
from ospy.scheduler import predicted_schedule, combined_schedule

from plugins import mqtt 


NAME = 'MQTT Run-once'
MENU =  _(u'Package: MQTT Run-once')
LINK = 'settings_page'

plugin_options = PluginOptions(
    NAME,
    {  
        'use_mqtt': False,
        'schedule_topic': u'run-once'
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
        if not self._stop.is_set(): 
            if plugin_options['use_mqtt']:  
                subscribe()

            else:
                log.clear(NAME)
                log.info(NAME, _('MQTT Run-once Plugin is disabled.'))

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
    """Callback when MQTT message is received."""   
    log.info(NAME, _(u'Received message') + ' :' + str(msg.payload) + ' ' +_(u'on topic') + str(msg.topic) + ' ' + _(u'with QoS') + ' ' + str(msg.qos))

    try:
        cmd = json.loads(msg.payload)
        # Ex. command for run-now station 1 and 3 for 5 minutes and 20 seconds (6 minutes and 10 seconds): [{0,5,20},{2,6,10}]
    except ValueError as e:
        log.error(NAME, _(u'MQTT Run-once could not decode command:'), msg.payload, e)
        return

    try:
        log.info(NAME, datetime_string() + ' ' + _(u'Try-ing to processing command.'))
        cmd = json.loads(msg.payload)
        num_sta = options.output_count
        if type(cmd) is list:            # cmd is list
            if len(cmd) < num_sta:
                log.info(NAME, datetime_string() + ' ' + _(u'Not enough stations specified, assuming first {} of {}').format(len(cmd), num_sta))
                rovals = cmd + ([0] * (num_sta - len(cmd)))              
            elif len(cmd) > num_sta:
                log.info(NAME, datetime_string() + ' ' + _(u'Too many stations specified, truncating to {}').format(num_sta))
                rovals = cmd[0:num_sta]
            else:
                rovals = cmd

        elif type(cmd) is dict:          # cmd is dictionary
            rovals = [0] * num_sta
            snames = station_names()     # Load station names from file
            jnames = json.loads(snames)  # Load as json
                                                
            for k, v in list(cmd.items()):
                if k not in snames:      # station name in dict is not in OSPy stations name (ERROR)
                    log.warning(NAME, _(u'No station named') + (u': %s') % k)
                                                    
                else:                    # station name in dict is in OSPy stations name (OK)
                    # v is value for time, k is station name in dict
                    rovals[jnames.index(k)] = v         

        else:
            log.error(NAME, datetime_string() + ' ' + _(u'Unexpected command') + (u': %s') %  msg.payload)
            rovals = []   

        if any(rovals):  
            for i in range(0, len(rovals)):     
                sid = i                                                                                
                start = datetime.datetime.now()
                end = datetime.datetime.now() + datetime.timedelta(seconds=int(rovals[i]))
                new_schedule = {
                    'active': True,
                    'program': -1,
                    'station': sid,
                    'program_name': _(u'MQTT Run-once'),
                    'fixed': True,
                    'cut_off': 0,
                    'manual': True,
                    'blocked': False,
                    'start': start,
                    'original_start': start,
                    'end': end,
                    'uid': '%s-%s-%d' % (str(start), "Manual", sid),
                    'usage': stations.get(sid).usage
                }
                log.start_run(new_schedule)
                stations.activate(new_schedule['station'])

                if int(rovals[i]) < 1:                 # station has no time for run (stoping)
                    stations.deactivate(sid)
                    active = log.active_runs()
                    for interval in active:
                        if interval['station'] == sid:
                            log.finish_run(interval)                                                    

    except Exception:
        log.clear(NAME)
        log.error(NAME, _(u'MQTT Run-once plug-in') + ':\n' + traceback.format_exc())
        self._sleep(1)


def station_names():
    """ Return station names as a list. """
    station_list = []

    for station in stations.get():
        station_list.append(station.name)

    return json.dumps(station_list)                            


def subscribe():
    """Subscribe to messages"""
    topic = plugin_options['schedule_topic']
    if topic:
        try:
            log.clear(NAME) 
            log.info(NAME, datetime_string() + ' ' + _('MQTT Run-once Plugin subscribe') + ': ' + topic)    
            mqtt.subscribe(topic, on_message, 2)

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
        #subscribe()
        
        raise web.seeother(plugin_url(settings_page), True)


class settings_json(ProtectedPage):
    """Returns plugin settings in JSON format."""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        return json.dumps(plugin_options)    
