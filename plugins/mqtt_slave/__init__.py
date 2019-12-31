# -*- coding: utf-8 -*-
__author__ = 'Martin Pihrt' # first author: "Orginally written by Daniel Casner <daniel@danielcasner.org> Modified from OSPy Martin Pihrt."

#NOT READY FOR USE

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

import paho.mqtt.client as MQTT

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
        if not self._stop.is_set(): 
            if plugin_options['use_mqtt']:  
                _subscribe()  
                log.clear(NAME)
                log.info(NAME, _('MQTT Slave Plugin is enabled.'))           

            else:
                _unsubscribe()
                log.clear(NAME)
                log.info(NAME, _('MQTT Slave Plugin is disabled.'))
                             
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
        _unsubscribe()


def on_connect(client, userdata, flags, rc):                 # The callback for when the client connects to the broker
    print("Connected with result code {0}".format(str(rc)))  # Print result of connection attempt
    client.subscribe(plugin_options['control_topic'])        # Subscribe to the topic..., receive any messages published on it


def on_message(client, userdata, message):
    "Callback when MQTT message is received."
    if not options.scheduler_enabled: # ? is scheduler enabled
        log.clear(NAME) 
        log.info(NAME, _('Scheduler is disabled...')) 
    #    return
    
    num_sta  = options.output_count   # number of outputs available
    cmd = [{ }]

    try:
        log.clear(NAME) 
        log.debug(NAME, _('MQTT data') + ': ' + message.payload.decode("utf-8"))

        cmd = json.loads(message.payload)

        #print(message.payload.decode("utf-8")))
        #print("Message topic=",message.topic)
        #print("Message qos=",message.qos)
        #print("Message retain flag=",message.retain)

        # data example:
        # [{'status': 'off', 'reason': 'master', 'station': 0, 'name': u'\u010cerpadlo'}, {'status': 'off', 'reason': '', 'station': 1, 'name': u'Kv\u011btiny'}, {'status': 'off', 'reason': '', 'station': 2, 'name': u'3'}, {'status': 'off', 'reason': '', 'station': 3, 'name': u'Ventil\xe1tor'}, {'status': 'off', 'reason': '', 'station': 4, 'name': u'5'}, {'status': 'off', 'reason': '', 'station': 5, 'name': u'6'}, {'status': 'off', 'reason': '', 'station': 6, 'name': u'7'}, {'status': 'off', 'reason': '', 'station': 7, 'name': u'8'}, {'status': 'off', 'reason': '', 'station': 8, 'name': u'9'}, {'status': 'off', 'reason': '', 'station': 9, 'name': u'J\xeddlo mp3'}, {'status': 'off', 'reason': '', 'station': 10, 'name': u'Konec mp3'}, {'status': 'off', 'reason': '', 'station': 11, 'name': u'12'}]

    except ValueError as e:
        log.info(NAME, _('MQTT Slave could not decode command: ') + message.payload + e)
        return
    
    zones = cmd['zone_list']  #  list of all zones sent from master OSPy system
    first = int(plugin_options['first_station']) - 1
    count = int(plugin_options['station_count'])
    local_zones = zones[first : first + count] 


    #for station in stations.get():
    #    if station.enabled or station.is_master or station.is_master_two: 
    #        if local_zones and not station.active:
    #             if station.active:

    #for i in range(len(local_zones)):
    #    if (local_zones[i] and not gv.srvals[i]): # if this element has a value and is not on
    #        gv.rs[i][0] = 
    #        gv.rs[i][1] = float('inf')
    #        gv.rs[i][3] = 99
    #        gv.ps[i][0] = 99 
    #    elif (gv.srvals[i] and not local_zones[i]): je gv.srvals	shift register values, used to turn zones on or off (list of one byte per station, 1 = turn on, 0 = turn off)
    #        gv.rs[i][1] = gv.now  je gv.now	current time, updated once per second at top of timing loop
    #if any(gv.rs): je gv.rs	run schedule (list [scheduled start time, scheduled stop time, duration, program index])
    #    gv.sd['bsy'] = 1  je program busy

    
def _subscribe():
    "Subscribe to messages"
    try:
        from plugins import mqtt            # from OSPY plugin broker host and port

        topic = plugin_options['control_topic']
        client = MQTT.Client(topic)         # Create instance of client with client ID 

        if client and topic:           
            log.clear(NAME) 
            log.info(NAME, _('MQTT Slave Plugin subscribe') + ': ' + str(topic))
            client.on_connect = on_connect  # Define callback function for successful connection
            client.on_message = on_message  # Define callback function for receipt of a message
            client.connect(mqtt.plugin_options['broker_host'], mqtt.plugin_options['broker_port'])   
            client.loop_forever()
               
    except ImportError:
        log.error(NAME, _('MQTT Slave Plugin requires MQTT plugin.'))                 


def _unsubscribe():
    "Unsubscribe from messages"
    try:
        topic = plugin_options['control_topic']
        client = MQTT.Client(topic) 
        client.disconnect()
        log.clear(NAME) 
        log.info(NAME, _('MQTT Slave Plugin unsubscribe') + ': ' + str(topic))
    
    except ImportError:
        log.error(NAME, _('MQTT Slave Plugin requires MQTT plugin.'))  

       
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
