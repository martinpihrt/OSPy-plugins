# -*- coding: utf-8 -*-
__author__ = u'Martin Pihrt'

import json
import time
import datetime
import traceback
import os
from threading import Thread, Event

import web

from ospy.options import options
from ospy.log import log
from plugins import PluginOptions, plugin_url, plugin_data_dir
from ospy.webpages import ProtectedPage
from ospy.helpers import get_rpi_revision
from ospy.helpers import datetime_string
from ospy import helpers
from ospy.stations import stations
from ospy.sensors import sensors

from ospy.webpages import showInFooter # Enable plugin to display readings in UI footer
#from ospy.webpages import showOnTimeline # Enable plugin to display station data on timeline


NAME = 'Photovoltaic Boiler'
MENU =  _(u'Package: Photovoltaic Boiler')
LINK = 'settings_page'


plugin_options = PluginOptions(
    NAME,
    {
    'enabled_a': False,   # enable or disable regulation
    'probe_A_on': 0,      # for selector temperature probe ON (0-5)
    'temp_a_on': 45,      # temperature for output ON
    'control_output_A': 0,# selector for output (0 to station count)
    'start_hh': 20,       # hour for start
    'start_mm': 0,        # minute for start
    'stop_hh': 23,        # hour for stop
    'stop_mm': 0,         # minute for stop    
    'probe_A_on_sens': 0, # for selector from sensors xx - temperature ON
    'sensor_probe': 0,    # selector for type probes: 0=none, 1=sensors, 2=air temp plugin
    'use_footer': True,   # show data from plugin in footer on home page
    }
)


global status
################################################################################
# Main function loop:                                                          #
################################################################################


class Sender(Thread):
    
    def __init__(self):
        Thread.__init__(self)
        self.daemon = True
        self._stop_event = Event()

        self.status = {}

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

    def _try_read(self, val):
        try:
            return val
        except:
            pass
            return -127.0

    def run(self):
        temperature_ds = [-127,-127,-127,-127,-127,-127]
        msg_a_on = True
        last_text = ''
        send = False
        temp_sw = None

        if plugin_options['use_footer']:
            temp_sw = showInFooter() #  instantiate class to enable data in footer
            temp_sw.button = "photovoltaic_boiler/settings"   # button redirect on footer
            temp_sw.label =  _('Photovoltaic Boiler')         # label on footer

        ds_a_on  = -127.0

        millis = 0                                 # timer for clearing status on the web pages after 5 sec
        last_millis = int(round(time.time() * 1000))
        
        a_state = -3                               # for state in footer "Waiting."
        regulation_text = _(u'Waiting to turned on or off.')
        
        if not plugin_options['enabled_a']:
            a_state = -1                           # for state in footer "Waiting (not enabled regulation in options)."

        log.info(NAME, datetime_string() + ' ' + _('Waiting.'))
        end = datetime.datetime.now()

        while not self._stop_event.is_set():
            try:
                if plugin_options["sensor_probe"] == 2:                                # loading probe name from plugin air_temp_humi
                    try:
                        from plugins.air_temp_humi import plugin_options as air_temp_data
                        self.status['ds_name_0'] = air_temp_data['label_ds0']
                        self.status['ds_name_1'] = air_temp_data['label_ds1']
                        self.status['ds_name_2'] = air_temp_data['label_ds2']
                        self.status['ds_name_3'] = air_temp_data['label_ds3']
                        self.status['ds_name_4'] = air_temp_data['label_ds4']
                        self.status['ds_name_5'] = air_temp_data['label_ds5']
                        self.status['ds_count']  = air_temp_data['ds_used']

                        from plugins.air_temp_humi import DS18B20_read_probe           # value with temperature from probe DS1-DS6
                        temperature_ds = [DS18B20_read_probe(0), DS18B20_read_probe(1), DS18B20_read_probe(2), DS18B20_read_probe(3), DS18B20_read_probe(4), DS18B20_read_probe(5)]
                    
                    except:
                        log.error(NAME, _('Unable to load settings from Air Temperature and Humidity Monitor plugin! Is the plugin Air Temperature and Humidity Monitor installed and set up?'))
                        self.status['ds_count'] = 0
                        pass

                # regulation
                if plugin_options['enabled_a'] and plugin_options["sensor_probe"] != 0:# enabled regulation and selected input for probes sensor/airtemp plugin
                    if plugin_options["sensor_probe"] == 1 and sensors.count()>0:
                        sensor_on = sensors.get(int(plugin_options['probe_A_on_sens']))
                        if sensor_on.sens_type == 5:                                   # temperature sensor
                            ds_a_on = self._try_read(sensor_on.last_read_value)
                        elif sensor_on.sens_type == 6 and sensor_on.multi_type == 0:   # multitemperature sensor DS1
                            ds_a_on = self._try_read(sensor_on.last_read_value[0])
                        elif sensor_on.sens_type == 6 and sensor_on.multi_type == 1:   # multitemperature sensor DS2
                            ds_a_on = self._try_read(sensor_on.last_read_value[1])
                        elif sensor_on.sens_type == 6 and sensor_on.multi_type == 2:   # multitemperature sensor DS3
                            ds_a_on = self._try_read(sensor_on.last_read_value[2])
                        elif sensor_on.sens_type == 6 and sensor_on.multi_type == 3:   # multitemperature sensor DS4
                            ds_a_on = self._try_read(sensor_on.last_read_value[3])
                        else:
                            ds_a_on = -127.0

                        if isinstance(ds_a_on, (str)):
                            ds_a_on = -127.0

                    elif plugin_options["sensor_probe"] == 2:
                        ds_a_on = temperature_ds[plugin_options['probe_A_on']]         # air temp sensor
                        
                    station_a = stations.get(plugin_options['control_output_A'])

                    probes_ok = True
                    if ds_a_on == -127.0:
                        probes_ok = False
                        a_state = -2
                        # The station switches off if the sensors has a fault
                        sid = station_a.index
                        active = log.active_runs()
                        for interval in active:
                            if interval['station'] == sid:
                                stations.deactivate(sid)
                                log.finish_run(interval)
                                regulation_text = datetime_string() + ' ' + _('Regulation set OFF.') + ' ' + ' (' + _('Output') + ' ' +  str(station_a.index+1) + ').'
                                log.clear(NAME)
                                log.info(NAME, regulation_text)
                        # release msg_a_on and msg_a_off to true for future regulation (after probes is ok)
                        msg_a_on = True
                        msg_a_off = True
                    
                    current_time  = datetime.datetime.now()
                    start_ok = False
                    stop_ok = False
                    if int(current_time.hour) >= int(plugin_options['start_hh']) and int(current_time.minute) >= int(plugin_options['start_mm']):
                        start_ok = True
                    if int(current_time.hour) <= int(plugin_options['stop_hh']) and int(current_time.minute) <= int(plugin_options['stop_mm']):
                        stop_ok = True

                    if int(ds_a_on) < int(plugin_options['temp_a_on']) and probes_ok and start_ok and stop_ok: # ON
                        a_state = 1
                        if msg_a_on:
                            msg_a_on = False
                            regulation_text = datetime_string() + ' ' + _('Regulation set ON.') + ' ' + ' (' + _('Output') + ' ' +  str(station_a.index+1) + ').'
                            log.clear(NAME) 
                            log.info(NAME, regulation_text)
                            start = datetime.datetime.now()
                            sid = station_a.index
                            end = datetime.datetime.now() + datetime.timedelta(hours=plugin_options['stop_hh'], minute=plugin_options['stop_mm'])
                            new_schedule = {
                                'active': True,
                                'program': -1,
                                'station': sid,
                                'program_name': _(u'Photovoltaic Boiler'),
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
                    else:
                        msg_a_on = True        
       
                    ### if "boiler" end in schedule release msg_a_on to true in regulation for next scheduling ###
                    now = datetime.datetime.now()
                    if now > end:
                        msg_a_off = False
                        msg_a_on = True
                        if probes_ok:
                            a_state = -3

                else:
                    a_state = -1

                # footer text
                tempText = ' '

                if a_state == 0:
                    tempText += regulation_text
                if a_state == 1:
                    tempText += regulation_text
                if a_state == -1:
                    tempText = _('Waiting (not enabled regulation in options, or not selected input).')
                if a_state == -2:
                    tempText = _('Some probe shows a fault, regulation is blocked!')
                if a_state == -3:
                    tempText = _('Waiting.')                    

                if plugin_options['use_footer']:
                    if temp_sw is not None:
                        temp_sw.val = tempText.encode('utf8').decode('utf8')    # value on footer

                self._sleep(2)

                millis = int(round(time.time() * 1000))
                if (millis - last_millis) > 15000:        # 15 second to clearing status on the webpage
                    last_millis = millis
                    log.clear(NAME)
                    if plugin_options["sensor_probe"] == 1:
                        try:
                            if options.temp_unit == 'C':
                                log.info(NAME, datetime_string() + '\n' + sensor_on.name + ' (' + _('Boiler') + ') %.1f \u2103 \n' % ds_a_on + sensor_off.name + ' ('+ _('Solar') + ') %.1f \u2103' % ds_a_off)
                            else:
                                log.info(NAME, datetime_string() + '\n' + sensor_on.name + ' (' + _('Boiler') + ') %.1f \u2109 \n' % ds_a_on + sensor_off.name + ' ('+ _('Solar') + ') %.1f \u2103' % ds_a_off)
                        except:
                            pass
                    elif plugin_options["sensor_probe"] == 2:
                        log.info(NAME, datetime_string() + '\n' + _('Boiler') + u' %.1f \u2103 \n' % ds_a_on)
                        
                    if last_text != tempText:
                        log.info(NAME, tempText)
                        last_text = tempText                        
 
            except Exception:
                log.error(NAME, _('Photovoltaic Boiler plug-in') + ':\n' + traceback.format_exc())
                self._sleep(60)
          
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
    """Load an html page for entering adjustments and deleting logs"""

    def GET(self):
        global sender
        
        if sender is not None:
            sender.update()

        return self.plugin_render.photovoltaic_boiler(plugin_options, log.events(NAME), sender.status)

    def POST(self):
        global sender
        plugin_options.web_update(web.input())

        if sender is not None:
            sender.update()
            log.clear(NAME)

        raise web.seeother(plugin_url(settings_page), True)
        #return self.plugin_render.photovoltaic_boiler(plugin_options, log.events(NAME))  


class help_page(ProtectedPage):
    """Load an html page for help"""

    def GET(self):
        return self.plugin_render.photovoltaic_boiler_help()


class settings_json(ProtectedPage):
    """Returns plugin settings in JSON format."""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        return json.dumps(plugin_options)