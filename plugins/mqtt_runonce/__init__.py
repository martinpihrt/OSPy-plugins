# -*- coding: utf-8 -*-
__author__ = u'Martin Pihrt' 

import json
import time
import traceback
import os
import subprocess

import datetime
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

import atexit # For publishing down message


NAME = 'MQTT Run-once'
MENU =  _(u'Package: MQTT Run-once')
LINK = 'settings_page'

plugin_options = PluginOptions(
    NAME,
    {  
        'use_mqtt': False,
        'schedule_topic': u'run-once',
        'broker_host': 'broker.mqttdashboard.com', # http://www.hivemq.com/demos/websocket-client/
        'broker_port': 1883,
        'publish_up_down': 'ospy/system',
        'user_name': '',
        'user_password': '',        
     }
)

_client = None
_subscriptions = {}
mqtt = None
last_status = ''
flag_connected = 0

################################################################################
# Main function:                                                               #
################################################################################

class Sender(Thread):
    def __init__(self):
        Thread.__init__(self)
        self.daemon = True
        self._stop_event = Event()

        self._sleep_time = 0
        self.start()

    def stop(self):
        self._stop_event.set()

    def update(self):
        self._sleep_time = 0

    def _sleep(self, secs):
        self._sleep_time = secs
        while self._sleep_time > 0 and not self._stop_event.is_set():
            time.sleep(1)
            self._sleep_time -= 1

    def run(self):
        self._sleep(3)
        if not self._stop_event.is_set(): 
            if plugin_options['use_mqtt'] and plugin_options['schedule_topic'] != '':  
                try: 
                    atexit.register(on_restart)
                    publish_status()
                    self._sleep(1)

                except Exception:
                    log.error(NAME, _('MQTT plug-in') + ':\n' + traceback.format_exc())
                    self._sleep(1)
                    pass

            else:
                log.clear(NAME)
                log.info(NAME, _('MQTT Run-once Plugin is disabled.'))
                on_stop()
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

def proc_install(cmd):
    """installation"""
    proc = subprocess.Popen(
    cmd,
    stderr=subprocess.STDOUT, # merge stdout and stderr
    stdout=subprocess.PIPE,
    shell=True)
    output = proc.communicate()[0].decode('utf8')
    log.info(NAME, output)        

def get_client():
    if not os.path.exists("/usr/lib/python3/dist-packages/pip"):
        log.clear(NAME)
        log.info(NAME, _('PIP3 is not installed.'))
        log.info(NAME, _('Please wait installing python3-pip...'))
        log.info(NAME, _('This operation takes longer (minutes)...'))
        cmd = "sudo apt-get install python3-pip -y"
        proc_install(cmd)                

    try:
        import paho.mqtt.client as mqtt
    except ImportError:
        log.error(NAME, _('MQTT Plugin requires paho mqtt.'))
        log.info(NAME, _('Paho-mqtt is not installed.'))
        log.info(NAME, _('Please wait installing paho-mqtt...'))
        log.info(NAME, _('This operation takes longer (minutes)...'))
        cmd = "sudo pip3 install paho-mqtt"    
        proc_install(cmd)
    try:
        import paho.mqtt.client as mqtt
    except ImportError:      
        mqtt = None
        log.error(NAME, _('Error try install paho-mqtt manually.'))
        time.sleep(60)
 
    if mqtt is not None and plugin_options["use_mqtt"]:  
        try:
            _client = mqtt.Client(options.name)                  # Use system name as client ID 
            _client.on_connect = on_connect                      # flag = 1 is connected
            _client.on_disconnect = on_disconnect                # flag = 0 is disconnected
            _client.on_message = on_message                      # Attach function to callback            
            log.clear(NAME)
            log.info(NAME, datetime_string() + ' ' + _('Connecting to broker') + '...')
            _client.username_pw_set(plugin_options['user_name'], plugin_options['user_password'])
            _client.connect(plugin_options['broker_host'], plugin_options['broker_port'], 60)
            _client.loop_start()
            log.info(NAME, datetime_string() + ' ' + _('OK'))
            return _client
            
        except Exception:
            log.error(NAME, _('MQTT plugin couldnot initalize client') + ':\n' + traceback.format_exc())
            pass
            return None

def publish_status(status="RunOnce Ready"):
    global last_status, flag_connected
    client = get_client()
    time.sleep(2)
    if client and plugin_options["use_mqtt"]:  # Publish message
        if status != last_status:
            last_status = status  
            log.info(NAME, datetime_string() + ' ' + _('Subscribing to topic') + ': ' + str(plugin_options['schedule_topic']))    
            client.subscribe(plugin_options['schedule_topic'])        
            client.publish(plugin_options['publish_up_down'], status)

def on_message(client, userdata, message):
    log.clear(NAME) 
    log.info(NAME, datetime_string() + ' ' + _('Message received') + ': ' + str(message.payload.decode("utf-8")))
    #print("Message topic=",message.topic)
    #print("Message qos=",message.qos)
    #print("Message retain flag=",message.retain)

    try:
        cmd = json.loads(message.payload)
    except:
        cmd = []
        status = "RunOnce Error"
        client.publish(plugin_options['publish_up_down'], status)
        pass

    try:
        log.info(NAME, datetime_string() + ' ' + _(u'Try-ing to processing command.'))
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
            log.error(NAME, datetime_string() + ' ' + _(u'Unexpected command') + (u': %s') % message.payload)
            rovals = None
            status = "RunOnce Error"
            client.publish(plugin_options['publish_up_down'], status)

        if rovals is not None and any(rovals):  
            for i in range(0, len(rovals)):     
                sid = i                                                                                
                start = datetime.datetime.now()
                try:
                    end = datetime.datetime.now() + datetime.timedelta(seconds=int(rovals[i]))
                except:
                    end = datetime.datetime.now()
                    log.error(NAME, _(u'MQTT Run-once plug-in') + ':\n' + traceback.format_exc())
                    pass

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

            status = "RunOnce Processing"
            client.publish(plugin_options['publish_up_down'], status)                                                                    

    except Exception:
        log.clear(NAME)
        log.error(NAME, _(u'MQTT Run-once plug-in') + ':\n' + traceback.format_exc())
        status = "RunOnce Error"
        client.publish(plugin_options['publish_up_down'], status)
        pass

def station_names():
    """ Return station names as a list. """
    station_list = []

    for station in stations.get():
        station_list.append(station.name)

    return json.dumps(station_list)                            

def subscribe(topic, callback, qos=0):
    "Subscribes to a topic with the given callback"
    global _subscriptions
    client = get_client()
    
    if client and plugin_options["use_mqtt"]:
        if topic not in _subscriptions:
            _subscriptions[topic] = [callback]
            client.subscribe(topic, qos)
            log.info(NAME, datetime_string() + ' ' + _('Subscribe topic') + ': ' + str(topic))
        else:
            _subscriptions[topic].append(callback)                

def on_connect(client, userdata, flags, rc):
   global flag_connected
   flag_connected = 1
   #log.debug(NAME, datetime_string() + ' ' + _('Connected to broker.'))

def on_disconnect(client, userdata, rc):
   global flag_connected
   flag_connected = 0
   #log.debug(NAME, datetime_string() + ' ' + _('Disconnected from broker!'))

def on_restart():
    client = get_client()
    if client is not None:
        status = "RunOnce Restart"
        client.publish(plugin_options['publish_up_down'], status)
        client.disconnect()
        client.loop_stop()
        client = None
        log.info(NAME, datetime_string() + ' ' +  _('Client on restart'))

def on_stop():
    client = get_client()
    if client is not None:
        status = "RunOnce Exit"
        client.publish(plugin_options['publish_up_down'], status)
        client.disconnect()
        client.loop_stop()
        client = None
        log.info(NAME, datetime_string() + ' ' +  _('Client on stop'))
       
################################################################################
# Web pages:                                                                   #
################################################################################

class settings_page(ProtectedPage):
    """Load an html page for entering plugin settings."""

    def GET(self):
        return self.plugin_render.mqtt_runonce(plugin_options, log.events(NAME), options.name)

    def POST(self): 
        plugin_options.web_update(web.input())
        if sender is not None:
            sender.update()        
        raise web.seeother(plugin_url(settings_page), True)

class help_page(ProtectedPage):
    """Load an html page for help"""

    def GET(self):
        return self.plugin_render.mqtt_runonce_help()

class settings_json(ProtectedPage):
    """Returns plugin settings in JSON format."""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        return json.dumps(plugin_options)    
