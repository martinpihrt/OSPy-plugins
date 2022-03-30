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
from ospy.helpers import datetime_string, is_python2
from ospy.stations import stations
from ospy.options import rain_blocks
from ospy.inputs import inputs

import atexit # For publishing down message


NAME = 'MQTT'
MENU =  _(u'Package: MQTT')
LINK = 'settings_page'

plugin_options = PluginOptions(
    NAME,
    {
     'use_mqtt': False,
     'broker_host': 'broker.mqttdashboard.com', # http://www.hivemq.com/demos/websocket-client/
     'broker_port': 1883,
     'publish_up_down': 'ospy/system',
     'user_name': '',
     'user_password': '',
     'use_mqtt_secondary': False,
     'control_topic': 'ospy/system/stations',
     'first_station': 1,
     'station_count': 8
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
        log.clear(NAME) 
        self._sleep(2)
        if not self._stop_event.is_set(): 
            if plugin_options["use_mqtt"]:   
                try: 
                    atexit.register(on_restart)
                    publish_status()
                    self._sleep(1)

                except Exception:
                    log.error(NAME, _('MQTT plug-in') + ':\n' + traceback.format_exc())
                    self._sleep(60)
            else:
                # text on the web if plugin is disabled
                log.clear(NAME)
                log.info(NAME, _('MQTT plug-in is disabled.'))
                on_stop()
                self._sleep(1)
        else:
            self._sleep(2)

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

def on_message(client, userdata, message):
    log.clear(NAME) 
    log.info(NAME, datetime_string() + ' ' + _('Message received') + ': ' + str(message.payload.decode("utf-8")))
    #print("Message topic=",message.topic)
    #print("Message qos=",message.qos)
    #print("Message retain flag=",message.retain)

    if plugin_options["use_mqtt_secondary"]:
        if not options.manual_mode:     # check operation status
            log.info(NAME, datetime_string() + ' ' + _('You must this OSPy switch to manual mode!'))
            return

        if inputs.rain_sensed():        # check rain sensor
            log.info(NAME, datetime_string() + ' ' + _('Skipping command, rain sense is detected!'))
            return        

        if rain_blocks.seconds_left():  # check rain delay
            log.info(NAME, datetime_string() + ' ' + _('Skipping command, rain delay is activated!'))
            return             

        try:
            rec_data = str(message.payload)
            cmd = json.loads(rec_data)
        except ValueError as e:
            log.info(NAME, _('Could not decode command:') + ':\n' + message.payload, e)
            return
 
        first = int(plugin_options["first_station"])-1       # first secondary station
        count = int(plugin_options["station_count"])         # count secondary station

        try:
            for i in range(first, first+count):              # count of station (example on main OSPy: 5 to 10) 
                zone    = cmd[i]["status"]                   # "off" or "on" state 
                #station = cmd[i]["station"] 
                #name    = cmd[i]["name"] 
                #print station, name, zone

                sid = i-first
                if sid <= stations.count():                  # local station size check
                    if zone == "on":
                        start = datetime.datetime.now()
                        mqn = _('MQTT Manual')
                        new_schedule = {
                            'active': True,
                            'program': -1,
                            'station': sid,
                            'program_name': mqn,
                            'fixed': True,
                            'cut_off': 0,
                            'manual': True,
                            'blocked': False,
                            'start': start,
                            'original_start': start,
                            'end': start + datetime.timedelta(days=3650),
                            'uid': '%s-%s-%d' % (str(start), mqn, sid),
                            'usage': stations.get(sid).usage
                        }
                        # if an optional duration time is given
                        #set_time = xxx second
                        #new_schedule['end'] = datetime.datetime.now() + datetime.timedelta(seconds=set_time)

                        log.start_run(new_schedule)
                        stations.activate(new_schedule['station'])
                    if zone == "off":
                        stations.deactivate(sid)
                        active = log.active_runs()
                        for interval in active:
                            if interval['station'] == i:
                                log.finish_run(interval)
                            
                else:
                    log.error(NAME, _('MQTT plug-in') + ':\n' + _('Setup stations count is smaler! Set correct first station and station count.'))   
        except Exception:
            log.error(NAME, _('MQTT plug-in') + ':\n' + traceback.format_exc())

        time.sleep(1)
            
        

def get_client():
    if is_python2():
        if not os.path.exists("/usr/lib/python2.7/dist-packages/pip"):
            log.clear(NAME)
            log.info(NAME, _('PIP is not installed.'))
            log.info(NAME, _('Please wait installing python-pip...'))
            log.info(NAME, _('This operation takes longer (minutes)...'))
            cmd = "sudo apt-get install python-pip -y"
            proc_install(cmd)
    else:
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
        if is_python2():
            cmd = "sudo pip install paho-mqtt"
        else:
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
            return None
 
def publish_status(status="UP"):
    global last_status, flag_connected
    client = get_client()
    time.sleep(2)
    if client and plugin_options["use_mqtt"]:  # Publish message
        if status != last_status:
            last_status = status  
            log.info(NAME, datetime_string() + ' ' + _('Subscribing to topic') + ': ' + str(plugin_options['publish_up_down']))
            client.subscribe(plugin_options['publish_up_down'])
            if plugin_options["use_mqtt_secondary"]:
                log.info(NAME, datetime_string() + ' ' + _('Subscribing to topic') + ': ' + str(plugin_options['control_topic']))    
                client.subscribe(plugin_options['control_topic'])        
            client.publish(plugin_options['publish_up_down'], status)

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
    time.sleep(2)
    if client is not None:
        publish_status("DOWN")
        client.disconnect()
        client.loop_stop()
        client = None
        log.info(NAME, datetime_string() + ' ' +  _('Client stop'))

def on_stop():
    client = get_client()
    if client is not None:
        client.disconnect()
        client.loop_stop()
        client = None
        log.info(NAME, datetime_string() + ' ' +  _('Client stop'))        

################################################################################
# Web pages:                                                                   #
################################################################################

class settings_page(ProtectedPage):
    """Load an html page for entering plugin settings."""

    def GET(self):
        return self.plugin_render.mqtt(plugin_options, log.events(NAME), options.name)

    def POST(self): 
        plugin_options.web_update(web.input())
        if sender is not None:
            sender.update()
        raise web.seeother(plugin_url(settings_page), True)

class help_page(ProtectedPage):
    """Load an html page for help"""

    def GET(self):
        return self.plugin_render.mqtt_help()        

class settings_json(ProtectedPage):
    """Returns plugin settings in JSON format."""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        return json.dumps(plugin_options)    
