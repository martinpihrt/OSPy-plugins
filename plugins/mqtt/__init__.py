# -*- coding: utf-8 -*-
__author__ = 'Martin Pihrt'

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
from ospy.options import options, rain_blocks
from ospy.helpers import datetime_string, get_cpu_temp, uptime
from ospy.stations import stations
from ospy.inputs import inputs
from ospy import version

from blinker import signal 

import atexit # For publishing down message
import ssl


NAME = 'MQTT'
MENU =  _('Package: MQTT')
LINK = 'settings_page'

plugin_options = PluginOptions(
    NAME,
    {
    ### core ###
    'use_mqtt': False,
    'use_mqtt_log': False,
    'use_tls': True,
    'broker_host': '****.eu.hivemq.cloud', # for testing use http://www.hivemq.com/demos/websocket-client/
    'broker_port': 8883,
    'publish_up_down': 'ospy/system',
    'user_name': '',
    'user_password': '',
    ### manual control ###
    'use_mqtt_secondary': False,
    'control_topic': 'ospy/control/zones',
    'first_station': 1,
    'station_count': 8,
    ### zones ###
    'use_zones': False,
    'zone_topic': 'ospy/events/zones',
    ### run-once ###
    'use_runonce': False,
    'runonce_topic': 'ospy/control/run-once',
    ### get values ###
    'use_get_val': False,
    'get_val_topic': 'ospy/values',

     }
)

_client = None
_subscriptions = {}
mqtt = None
last_status = '-'
flag_connected = 0
last_stations = []

################################################################################
# Main function:                                                               #
################################################################################

class Sender(Thread):
    def __init__(self):
        Thread.__init__(self)
        self.daemon = True
        self._stop_event = Event()

        self._sleep_time = 0
        self.client = None
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
        if not self._stop_event.is_set(): 
            if plugin_options["use_mqtt"]:
                try:
                    self.client = get_client()
                    if self.client is not None:
                        publish_status()
                        atexit.register(on_stop)
                except Exception:
                    log.error(NAME, _('MQTT plug-in') + ':\n' + traceback.format_exc())
            else:
                log.clear(NAME)
                log.info(NAME, _('MQTT plug-in is disabled.'))

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


def validateJSON(jsonData):
    """Checking if the json format is correct"""
    try:
        json.loads(jsonData)
    except ValueError as err:
        return False
    return True


def station_names():
    """Return station names as a list"""
    station_list = []
    try:
        for station in stations.get():
            station_list.append(station.name)
        return json.dumps(station_list)
    except:
        return station_list


def on_log(client, userdata, level, buf):
    log.debug(NAME, datetime_string() + ' log: {}'.format(buf))


def on_message(client, userdata, message):
    log.clear(NAME)
    log.info(NAME, datetime_string() + ' ' + _('Message received') + ': {}'.format(message.payload.decode("utf-8")))
    log.info(NAME, datetime_string() + ' ' + _('Message topic') + ': {}'.format(message.topic))
    log.info(NAME, datetime_string() + ' ' + _('Message qos') + ': {}'.format(message.qos))
    log.info(NAME, datetime_string() + ' ' + _('Message retain flag') + ': {}'.format(message.retain))

    cmd = []
    payload = message.payload.decode("utf-8")

    isValid = validateJSON(payload)
    if isValid:
        cmd = json.loads(payload)

    try:
        ### manual control ###
        if plugin_options["use_mqtt_secondary"] and isValid and message.topic == plugin_options["control_topic"]:
            log.info(NAME, datetime_string() + ' ' + _('Try-ing to processing command.'))
            if options.manual_mode:                              # check operation status
                first = int(plugin_options["first_station"])-1   # first secondary station
                count = int(plugin_options["station_count"])     # count secondary station

                for i in range(first, first+count):              # count of station (example on main OSPy: 5 to 10) 
                    zone = cmd[i]["status"]                      # "off" or "on" state
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

                status = "Manual command was processed OK"
                client.publish(plugin_options['control_topic'], status)

            else:
                log.info(NAME, datetime_string() + ' ' + _('You must this OSPy switch to manual mode!'))
                status = "Manual command was not processed! You must OSPy switch to manual mode!"
                client.publish(plugin_options['control_topic'], status)

        ### run-once ###
        if plugin_options["use_runonce"] and isValid and message.topic == plugin_options["runonce_topic"]:
            log.info(NAME, datetime_string() + ' ' + _('Try-ing to processing command.'))
            if options.manual_mode:
                log.info(NAME, datetime_string() + ' ' + _('You must this OSPy switch to scheduler mode!'))
                status = "Run-once command was not processed! You must OSPy switch to scheduler mode!"
                client.publish(plugin_options['runonce_topic'], status)
            else:    
                num_sta = options.output_count
                if type(cmd) is list:            # cmd is list
                    if len(cmd) < num_sta:
                        log.info(NAME, datetime_string() + ' ' + _('Not enough stations specified, assuming first {} of {}').format(len(cmd), num_sta))
                        rovals = cmd + ([0] * (num_sta - len(cmd)))
                        status =  "Run-once command was not processed!" + " "
                        status += "Not enough stations specified, assuming first {} of {}".format(len(cmd), num_sta)
                        client.publish(plugin_options['runonce_topic'], status)
                    elif len(cmd) > num_sta:
                        log.info(NAME, datetime_string() + ' ' + _('Too many stations specified, truncating to {}').format(num_sta))
                        status =  "Run-once command was not processed!" + " "
                        status += "Too many stations specified, truncating to {}".format(num_sta)
                        client.publish(plugin_options['runonce_topic'], status)
                        rovals = cmd[0:num_sta]
                    else:
                        rovals = cmd

                elif type(cmd) is dict:          # cmd is dictionary
                    rovals = [0] * num_sta
                    snames = station_names()     # Load station names from file
                    jnames = json.loads(snames)  # Load as json
                    for k, v in list(cmd.items()):
                        if k not in snames:      # station name in dict is not in OSPy stations name (ERROR)
                            log.warning(NAME, _('No station named') + (': %s') % k)
                        else:                    # station name in dict is in OSPy stations name (OK)
                                                 # v is value for time, k is station name in dict
                            rovals[jnames.index(k)] = v

                else:
                    log.error(NAME, datetime_string() + ' ' + _('Unexpected command') + (': {}').format(cmd))
                    rovals = None
                    status =  "Run-once command was not processed!" + " "
                    status += "Unexpected command {}".format(cmd)
                    client.publish(plugin_options['runonce_topic'], status)

                if rovals is not None and any(rovals):
                    for i in range(0, len(rovals)):
                        sid = i
                        start = datetime.datetime.now()
                        try:
                            end = datetime.datetime.now() + datetime.timedelta(seconds=int(rovals[i]))
                        except:
                            end = datetime.datetime.now()
                            log.error(NAME, _('MQTT Run-once plug-in') + ':\n' + traceback.format_exc())
                            status =  "Run-once command was not processed!" + " "
                            status += "The command is not valid!"
                            client.publish(plugin_options['runonce_topic'], status)
                            pass

                        new_schedule = {
                            'active': True,
                            'program': -1,
                            'station': sid,
                            'program_name': _('MQTT Run-once'),
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

                        if int(rovals[i]) > 1:                 # station has time for run (starting)
                            log.start_run(new_schedule)
                            stations.activate(new_schedule['station'])

                        if int(rovals[i]) < 1:                 # station has no time for run (stoping)
                            stations.deactivate(sid)
                            active = log.active_runs()
                            for interval in active:
                                if interval['station'] == sid:
                                    log.finish_run(interval)
                    status = "Run-once command was processed OK"
                    client.publish(plugin_options['runonce_topic'], status)
 
    except Exception:
        log.error(NAME, _('MQTT plug-in') + ':\n' + traceback.format_exc())
        status =  "Command was not processed!" + " "
        status += "The command is probably invalid or there was some processing error in the plugin!"
        client.publish(plugin_options['runonce_topic'], status)
        pass


def get_client():
    if not os.path.exists("/usr/lib/python3/dist-packages/pip"):
        log.clear(NAME)
        log.info(NAME, _('PIP3 is not installed.'))
        log.info(NAME, _('Please wait installing python3-pip...'))
        log.info(NAME, _('This operation takes longer (minutes)...'))
        cmd = "sudo apt-get install python3-pip -y"
        proc_install(cmd)

    try:
        import paho.mqtt.client as paho
        from paho import mqtt
    except ImportError:
        log.error(NAME, _('MQTT Plugin requires paho mqtt.'))
        log.info(NAME, _('Paho-mqtt is not installed.'))
        log.info(NAME, _('Please wait installing paho-mqtt...'))
        log.info(NAME, _('This operation takes longer (minutes)...'))
        cmd = "sudo pip3 install paho-mqtt"
        proc_install(cmd)
        try:
            import paho.mqtt.client as paho
            from paho import mqtt
        except ImportError:
            mqtt = None
            log.error(NAME, _('Error try install paho-mqtt manually.'))
 
    if mqtt is not None and plugin_options["use_mqtt"]:  
        try:
            # using MQTT version 5 here, for 3.1.1: MQTTv311, 3.1: MQTTv31
            # userdata is user defined data of any type, updated by user_data_set()
            # client_id is the given name of the client
            _client = paho.Client(client_id=options.name, userdata=None, protocol=paho.MQTTv5) # Use system name as client ID 
            _client.on_connect = on_connect                                                    # flag = 1 is connected
            _client.on_disconnect = on_disconnect                                              # flag = 0 is disconnected
            _client.on_message = on_message                                                    # Attach function to callback
            if plugin_options["use_mqtt_log"]:
                _client.on_log = on_log                                                        # debug MQTT communication log
            if plugin_options["use_tls"]:
                _client.tls_set(tls_version=mqtt.client.ssl.PROTOCOL_TLSv1_2,
                                ciphers=None, 
                                certfile=None,
                                keyfile=None,
                                )
                _client.tls_insecure_set(False)
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
    global last_status, flag_connected, sender
    client = sender.client
    if client and plugin_options["use_mqtt"] and flag_connected:  # Publish message
        if status != last_status:
            last_status = status
            client.publish(plugin_options['publish_up_down'], status)


def subscribe(topic, callback, qos=0):
    "Subscribes to a topic with the given callback"
    global _subscriptions, sender
    client = sender.client
    
    if client and plugin_options["use_mqtt"]:
        if topic not in _subscriptions:
            _subscriptions[topic] = [callback]
            client.subscribe(topic, qos)
            log.info(NAME, datetime_string() + ' ' + _('Subscribe topic') + ': ' + str(topic))
        else:
            _subscriptions[topic].append(callback)


def on_connect(client, userdata, flags, rc, properties=None):
    global flag_connected
    flag_connected = 1
    ### mqtt core ###  
    log.info(NAME, datetime_string() + ' ' + _('Subscribing to topic') + ': ' + str(plugin_options['publish_up_down']))
    client.subscribe(plugin_options['publish_up_down'])
    ### manual control ###
    if plugin_options["use_mqtt_secondary"]:
        log.info(NAME, datetime_string() + ' ' + _('Subscribing to topic') + ': ' + str(plugin_options['control_topic']))
        client.subscribe(plugin_options['control_topic'])
    ### run-once ###
    if plugin_options["use_runonce"]:
        log.info(NAME, datetime_string() + ' ' + _('Subscribing to topic') + ': ' + str(plugin_options['runonce_topic']))
        client.subscribe(plugin_options['runonce_topic'])
    #log.debug(NAME, datetime_string() + ' ' + _('Connected to broker.'))


def on_disconnect(client, userdata, rc, properties=None):
    global flag_connected
    flag_connected = 0
    #log.debug(NAME, datetime_string() + ' ' + _('Disconnected from broker!'))


def on_stop():
    global sender
    client = sender.client
    if client is not None:
        publish_status("DOWN")
        client.disconnect()
        client.loop_stop()
        client = None
        log.info(NAME, datetime_string() + ' ' +  _('MQTT Client stop'))


### System value change ###
def notify_value_change(name, **kw):
    try:
        global sender
        payload = {
            "cpu_temp": get_cpu_temp(options.temp_unit),
            "temp_unit": options.temp_unit,
            "manual_mode": options.manual_mode,
            "scheduler_enabled": options.scheduler_enabled,
            "system_name": options.name,
            "output_count": options.output_count,
            "rain_sensed": inputs.rain_sensed(),
            "rain_block": rain_blocks.seconds_left(),
            "level_adjustment": options.level_adjustment,
            "ospy_version": version.ver_str,
            "release_date": version.ver_date,
            "uptime": uptime(),
        }
        if plugin_options["use_get_val"]:
            client = sender.client
            if client:
                client.publish(plugin_options["get_val_topic"], json.dumps(payload), qos=1, retain=True)
                log.clear(NAME)
                log.info(NAME, datetime_string() + ' ' +  _('Posting to topic {} because OSPy change the settings.').format(plugin_options["get_val_topic"]))
    
    except Exception:
        log.error(NAME, _('MQTT plug-in') + ':\n' + traceback.format_exc())
        pass

value = signal("value_change")
value.connect(notify_value_change)


### Stations (zone) state changed ###
def notify_zone_change(name, **kw):
    global last_stations, sender

    try:
        statuslist = []
        for station in stations.get():
            if station.enabled or station.is_master or station.is_master_two: 
                status = {
                'station': station.index,
                'status':  'on' if station.active else 'off',
                'name':    station.name,
                'reason':  'master' if station.is_master or station.is_master_two else ''
                }
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

        if plugin_options["use_zones"]:
            if last_stations != statuslist:   # if there was no change (the stations are unchanged), we will not respond
                last_stations = statuslist
                client = sender.client
                if client:
                    client.publish(plugin_options["zone_topic"], json.dumps(statuslist), qos=1, retain=True)
                    log.clear(NAME)
                    log.info(NAME, datetime_string() + ' ' +  _('Posting to topic {} because OSPy change stations state.').format(plugin_options["zone_topic"]))

    except Exception:
        log.error(NAME, _('MQTT plug-in') + ':\n' + traceback.format_exc())
        pass

value = signal("zone_change")
value.connect(notify_zone_change)

################################################################################
# Web pages:                                                                   #
################################################################################

class settings_page(ProtectedPage):
    """Load an html page for entering plugin settings."""

    def GET(self):
        try:
            return self.plugin_render.mqtt(plugin_options, log.events(NAME), options.name)
        except:
            log.error(NAME, _('MQTT plug-in') + ':\n' + traceback.format_exc())
            msg = _('An internal error was found in the system, see the error log for more information. The error is in part:') + ' '
            msg += _('mqtt -> settings_page GET')
            return self.core_render.notice('/', msg)

    def POST(self):
        try:
            global sender
            plugin_options.web_update(web.input())
            if sender is not None:
                sender.update()
            raise web.seeother(plugin_url(settings_page), True)
        except:
            log.error(NAME, _('MQTT plug-in') + ':\n' + traceback.format_exc())
            msg = _('An internal error was found in the system, see the error log for more information. The error is in part:') + ' '
            msg += _('mqtt -> settings_page POST')
            return self.core_render.notice('/', msg)

class help_page(ProtectedPage):
    """Load an html page for help"""

    def GET(self):
        try:
            return self.plugin_render.mqtt_help()
        except:
            log.error(NAME, _('MQTT plug-in') + ':\n' + traceback.format_exc())
            msg = _('An internal error was found in the system, see the error log for more information. The error is in part:') + ' '
            msg += _('mqtt -> help_page GET')
            return self.core_render.notice('/', msg)

class settings_json(ProtectedPage):
    """Returns plugin settings in JSON format."""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        try:
            return json.dumps(plugin_options)
        except:
            return {}