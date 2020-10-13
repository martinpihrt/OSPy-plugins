# -*- coding: utf-8 -*-
__author__ = 'Martin Pihrt'

import json
import time
from datetime import datetime
import traceback
import os
from threading import Thread, Event

import web

from ospy.log import log
from plugins import PluginOptions, plugin_url, plugin_data_dir
from ospy.webpages import ProtectedPage
from ospy.helpers import get_rpi_revision
from ospy.helpers import datetime_string
from ospy import helpers
from ospy.stations import stations

from ospy.webpages import showInFooter # Enable plugin to display readings in UI footer
#from ospy.webpages import showOnTimeline # Enable plugin to display station data on timeline


NAME = 'Pool Heating'
MENU =  _('Package: Pool Heating')
LINK = 'settings_page'


plugin_options = PluginOptions(
    NAME,
    {'enabled_a': False,   # enable or disable regulation A
     'probe_A_on': 0,      # for selector temperature probe A ON (0-5)
     'probe_A_off': 0,     # for selector temperature probe A OFF (0-5)
     'temp_a_on': 6,       # temperature for output A ON
     'temp_a_off': 3,      # temperature for output A OFF
     'control_output_A': 0,# selector for output A (0 to station count)
     'ds_name_0': '',      # name for DS probe 1 from air temp humi plugin
     'ds_name_1': '',      # name for DS probe 2 from air temp humi plugin
     'ds_name_2': '',      # name for DS probe 3 from air temp humi plugin
     'ds_name_3': '',      # name for DS probe 4 from air temp humi plugin
     'ds_name_4': '',      # name for DS probe 5 from air temp humi plugin
     'ds_name_5': '',      # name for DS probe 6 from air temp humi plugin
     'ds_count': 0         # DS probe count from air temp humi plugin
     }
)


################################################################################
# Main function loop:                                                          #
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
        temperature_ds = [-127,-127,-127,-127,-127,-127]
        msg_a_on = True
        msg_a_off = True              

        temp_sw = showInFooter() #  instantiate class to enable data in footer
        temp_sw.button = "pool_heating/settings"   # button redirect on footer
        temp_sw.label =  _(u'Pool Heating')        # label on footer

        millis = int(round(time.time() * 1000))          # timer for clearing status on the web pages after 60 sec
        last_millis = millis

        a_state = -1                                     # for state in footer (-1 disable regulation A, 0 = Aoff, 1 = Aon)
        regulation_text ='Waiting to turned on or off.'

        log.info(NAME, datetime_string() + ' ' + _(u'Waiting to turned on or off.'))

        while not self._stop.is_set():
            try:
                try:
                    from plugins.air_temp_humi import plugin_options as air_temp_data
                    plugin_options['ds_name_0'] = air_temp_data['label_ds0']
                    plugin_options['ds_name_1'] = air_temp_data['label_ds1']
                    plugin_options['ds_name_2'] = air_temp_data['label_ds2']
                    plugin_options['ds_name_3'] = air_temp_data['label_ds3']
                    plugin_options['ds_name_4'] = air_temp_data['label_ds4']
                    plugin_options['ds_name_5'] = air_temp_data['label_ds5']
                    plugin_options['ds_count'] = air_temp_data['ds_used']

                    from plugins.air_temp_humi import DS18B20_read_probe
                    temperature_ds = [DS18B20_read_probe(0), DS18B20_read_probe(1), DS18B20_read_probe(2), DS18B20_read_probe(3), DS18B20_read_probe(4), DS18B20_read_probe(5)]
                    
                except:
                    log.error(NAME, _(u'Unable to load settings from Air Temperature and Humidity Monitor plugin! Is the plugin Air Temperature and Humidity Monitor installed and set up?'))
                    self._sleep(60)

                # regulation
                if plugin_options['enabled_a']:  
                    ds_a_on = temperature_ds[plugin_options['probe_A_on']]    #  pool  
                    ds_a_off = temperature_ds[plugin_options['probe_A_off']]  #  solar
                    station_a = stations.get(plugin_options['control_output_A'])

                    if ds_a_off >= (ds_a_on + plugin_options['temp_a_on']):    # ON
                        a_state = 1
                        if msg_a_on:
                            msg_a_on = False
                            msg_a_off = True
                            regulation_text = datetime_string() + ' ' + _(u'Regulation set ON.') + ' ' + ' (' + _('Output') + ' ' +  str(station_a.index+1) + ').'  
                            log.clear(NAME) 
                            log.info(NAME, regulation_text)  
                            import datetime
                            start = datetime.datetime.now()
                            sid = station_a.index
                            new_schedule = {
                                'active': True,
                                'program': -1,
                                'station': sid,
                                'program_name': _('Pool Heating'),
                                'fixed': True,
                                'cut_off': 0,
                                'manual': True,
                                'blocked': False,
                                'start': start,
                                'original_start': start,
                                'end': start + datetime.timedelta(days=10),
                                'uid': '%s-%s-%d' % (str(start), "Manual", sid),
                                'usage': stations.get(sid).usage
                            }

                            log.start_run(new_schedule)
                            stations.activate(new_schedule['station'])                            

                    if ds_a_off > (ds_a_on + plugin_options['temp_a_off']) and ds_a_off < (ds_a_on + plugin_options['temp_a_on']):   # OFF
                        a_state = 0
                        if msg_a_off:
                            msg_a_off = False
                            msg_a_on = True
                            regulation_text = datetime_string() + ' ' + _(u'Regulation set OFF.') + ' ' + ' (' + _('Output') + ' ' +  str(station_a.index+1) + ').'
                            log.clear(NAME)
                            log.info(NAME, regulation_text)   
                            sid = station_a.index
                            stations.deactivate(sid)
                            active = log.active_runs()
                            for interval in active:
                                if interval['station'] == sid:
                                    log.finish_run(interval)  
  
                else:
                    a_state = -1    


                # footer text
                tempText = ' '

                if a_state == 0:
                    tempText += regulation_text  
                if a_state == 1:
                    tempText += regulation_text      
                if a_state == -1:
                    tempText = _(u'Waiting to turned on or off.')

                temp_sw.val = tempText.encode('utf8')    # value on footer                                                          

                self._sleep(2)

                millis = int(round(time.time() * 1000))
                if (millis - last_millis) > 60000:    # 60 second to clearing status on the webpage
                    last_millis = millis
                    log.clear(NAME)
 
            except Exception:
                log.error(NAME, _(u'Pool Heating plug-in') + ':\n' + traceback.format_exc())
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
        return self.plugin_render.pool_heating(plugin_options, log.events(NAME))

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