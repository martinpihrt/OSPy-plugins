#!/usr/bin/env python
# -*- coding: utf-8 -*-
__author__ = 'Martin Pihrt' 

import json
import time
import traceback
import os
import subprocess

from datetime import datetime
from threading import Thread, Event

import web

from ospy.log import log
from plugins import PluginOptions, plugin_url, plugin_data_dir
from ospy.webpages import ProtectedPage
from ospy.options import options
from ospy.helpers import datetime_string

import atexit # For publishing down message

import i18n

NAME = 'MQTT'
LINK = 'settings_page'

plugin_options = PluginOptions(
    NAME,
    {
     'use_mqtt': False,
     'broker_host': 'broker.mqttdashboard.com', # http://www.hivemq.com/demos/websocket-client/
     'broker_port': 1883,
     'publish_up_down': 'ospy/system',
     'user_name': '',
     'user_password': ''
     }
)

_client = None
_subscriptions = {}
mqtt = None
last_status = ''

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
        disable_text = True
        if not self._stop.is_set(): 
            if plugin_options["use_mqtt"]:  
                disable_text = True   
                try:
                    atexit.register(on_restart)
                    publish_status()
                    self._sleep(1)

                except Exception:
                    log.error(NAME, _('MQTT plug-in') + ':\n' + traceback.format_exc())
                    self._sleep(60)
            else:
                # text on the web if plugin is disabled
                if disable_text:  
                    log.clear(NAME)
                    log.info(NAME, _('MQTT plug-in is disabled.'))
                    disable_text = False 
                    self._sleep(1)
        else:
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
    output = proc.communicate()[0]
    log.info(NAME, output)

def on_message(client, userdata, message):
    log.info(NAME, datetime_string() + ' ' + _('Message received') + ': ' + str(message.payload.decode("utf-8")))
    #print("Message topic=",message.topic)
    #print("Message qos=",message.qos)
    #print("Message retain flag=",message.retain)

def get_client():
    if not os.path.exists("/usr/lib/python2.7/dist-packages/pip"):
        log.clear(NAME)
        log.info(NAME, _('PIP is not installed.'))
        log.info(NAME, _('Please wait installing pip...'))
        log.info(NAME, _('This operation takes longer (minutes)...'))
        cmd = "sudo apt-get install python-pip -y"
        proc_install(cmd)

    try:
        import paho.mqtt.client as mqtt
    except ImportError:
        log.error(NAME, _('MQTT Plugin requires paho mqtt.'))
        log.info(NAME, _('Paho-mqtt is not installed.'))
        log.info(NAME, _('Please wait installing paho-mqtt...'))
        log.info(NAME, _('This operation takes longer (minutes)...'))
        cmd = "sudo pip install paho-mqtt"
        proc_install(cmd)
    try:
        import paho.mqtt.client as mqtt
    except ImportError:      
        mqtt = None
        log.error(NAME, _('Error try install paho-mqtt manually.'))
 
    if mqtt is not None and plugin_options["use_mqtt"]:  
        try:
            _client = mqtt.Client(options.name)                  # Use system name as client ID 
            _client.on_message = on_message                      # Attach function to callback
            log.clear(NAME)
            log.info(NAME, datetime_string() + ' ' + _('Connecting to broker') + '...')
            _client.username_pw_set(plugin_options['user_name'], plugin_options['user_password'])
            _client.connect(plugin_options['broker_host'], plugin_options['broker_port'], 60)
            _client.loop_start()
            return _client
            
        except Exception:
            log.error(NAME, _('MQTT plugin couldnot initalize client') + ':\n' + traceback.format_exc())
            return None
 
def publish_status(status="UP"):
    global last_status
    client = get_client()
    if client and plugin_options["use_mqtt"]:  
        if status != last_status:
            last_status = status  
            log.info(NAME, datetime_string() + ' ' + _('Subscribing to topic') + ': ' + str(plugin_options['publish_up_down']))
            client.subscribe(plugin_options['publish_up_down'])
            client.publish(plugin_options['publish_up_down'], status)

def subscribe(topic, callback, qos=0):
    "Subscribes to a topic with the given callback"
    global _subscriptions
    client = get_client()
    
    if client and plugin_options["use_mqtt"]:
        if topic not in _subscriptions:
            _subscriptions[topic] = [callback]
            client.subscribe(topic, qos)
            log.info(NAME, datetime_string() + ' ' + _('Subscribe') + ': ' + str(topic))
        else:
            _subscriptions[topic].append(callback)    

def on_restart():
    client = get_client()
    if client is not None:
        publish_status("DOWN")
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
        publish_status()
        raise web.seeother(plugin_url(settings_page), True)

class settings_json(ProtectedPage):
    """Returns plugin settings in JSON format."""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        return json.dumps(plugin_options)    
