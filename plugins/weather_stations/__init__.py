# -*- coding: utf-8 -*-
__author__ = u'Martin Pihrt'

import json
import time
import traceback
import web

from ospy.log import log
from threading import Thread, Event
from plugins import PluginOptions, plugin_url
from ospy.webpages import ProtectedPage
from ospy.sensors import sensors

NAME = 'Weather Stations'
MENU =  _(u'Package: Weather Stations')
LINK = 'canvas_page'

plugin_options = PluginOptions(
    NAME,
    {
    'can_or_txt': False,                                             # canvas or text mode showing data
    'can_size_xy': 250,                                              # all canvas x and y size in pixels
    'txt_size_font': 40,                                             # size for font in text mode    

    # for airtemp, watertank, wind plugins and OSPy sensors Wi-Fi/LAN...
    's_use':    [False]*30,                 # show or disbale sensor in canvas/text mode
    's_unit':   ['']*30,                    # sensor units
    's_name':   ['']*30,                    # sensor name
    's_tick':   ['0,10,20,30']*30,          # sensor canvas tick scale division
    's_min':    ['0']*30,                   # sensor canvas minimum value for highlights
    's_max':    ['30']*30,                  # sensor canvas maximum value for highlights
    's_a_high_fr': [5]*30,                  # sensor red color on highlights from
    's_a_high_to': [10]*30,                 # sensor red color on highlights to
    's_b_high_fr': [10]*30,                 # sensor blue color on highlights from
    's_b_high_to': [20]*30,                 # sensor blue color on highlights to
    's_c_high_fr': [20]*30,                 # sensor green color on highlights from
    's_c_high_to': [30]*30,                 # sensor green color on highlights to
    }
)

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

    def run(self):
        log.clear(NAME)
        log.info(NAME, _(u'Weather stations plug-in is enabled.'))
         
sender = None

################################################################################
# Helper functions:                                                            #
################################################################################
### start ###
def start():
    global sender
    if sender is None:
        sender = Sender()
 
### stop ###
def stop():
    global sender
    if sender is not None:
       sender.stop()
       sender.join()
       sender = None 

### clear plugin settings to default ###
def set_to_default():
    plugin_options.__setitem__('s_use', [False]*30)
    plugin_options.__setitem__('s_unit', ['']*30)
    plugin_options.__setitem__('s_name', ['']*30)
    plugin_options.__setitem__('s_tick', ['0,10,20,30']*30)
    plugin_options.__setitem__('s_min', ['0']*30)
    plugin_options.__setitem__('s_max', ['30']*30)
    plugin_options.__setitem__('s_a_high_fr', [5]*30)
    plugin_options.__setitem__('s_a_high_to', [10]*30)
    plugin_options.__setitem__('s_b_high_fr', [10]*30)
    plugin_options.__setitem__('s_b_high_to', [20]*30)
    plugin_options.__setitem__('s_c_high_fr', [20]*30)
    plugin_options.__setitem__('s_c_high_to', [30]*30)
    log.clear(NAME)
    log.info(NAME, _(u'Weather stations plug-in has any error, clear plugin settings to default.'))

################################################################################
# Web pages:                                                                   #
################################################################################

class canvas_page(ProtectedPage):
    """Load an html page for canvas wieving."""

    def GET(self):
        try:
            return self.plugin_render.canvas_page(plugin_options)
        except:
            set_to_default()    
            return self.plugin_render.canvas_page(plugin_options)

class help_page(ProtectedPage):
    """Load an html page for help page."""

    def GET(self):
        return self.plugin_render.help_page()


class settings_page(ProtectedPage):
    """Load an html settings page for canvas options."""

    def GET(self):
        try:
            return self.plugin_render.settings_page(plugin_options)
        except:
            set_to_default()
        
        return self.plugin_render.settings_page(plugin_options)

    def POST(self):
        qdict = web.input()

        try:
            commands = {
                's_use' : [],
                's_name': [],
                's_unit': [],
                's_tick': [],
                's_min' : [],
                's_max' : [],
                's_a_high_fr': [],
                's_a_high_to': [],
                's_b_high_fr': [],
                's_b_high_to': [],
                's_c_high_fr': [],
                's_c_high_to': [],
                }

            if 'can_or_txt' in qdict:
                if qdict['can_or_txt']=='on':
                    plugin_options.__setitem__('can_or_txt', True)
            else:  
                plugin_options.__setitem__('can_or_txt', False)

            if 'can_size_xy' in qdict:
                plugin_options.__setitem__('can_size_xy', qdict['can_size_xy'])

            if 'txt_size_font' in qdict:
                plugin_options.__setitem__('txt_size_font', qdict['txt_size_font'])

            plug_air_temp  = 6
            plug_tank_moni = 2
            plug_wind_moni = 1
            sensor_count   = sensors.count()
            sum_canvas = plug_air_temp + plug_tank_moni + plug_wind_moni + sensor_count # numbers for all canvas from plugins and sensors

            for i in range(0, sum_canvas+2):
                if 's_use'+str(i) in qdict:
                    if qdict['s_use'+str(i)]=='on':
                        commands['s_use'].append(True)
                else:
                        commands['s_use'].append(False)
                if 's_name'+str(i) in qdict:
                    commands['s_name'].append(qdict['s_name'+str(i)])
                else:
                    commands['s_name'].append(u'')    
                if 's_unit'+str(i) in qdict:
                    commands['s_unit'].append(qdict['s_unit'+str(i)])
                else:
                    commands['s_unit'].append(u'')    
                if 's_tick'+str(i) in qdict:
                    commands['s_tick'].append(qdict['s_tick'+str(i)])
                else:
                    commands['s_tick'].append(u'0,10,20,30')    
                if 's_min'+str(i) in qdict:
                    commands['s_min'].append(qdict['s_min'+str(i)])
                else:
                    commands['s_min'].append(u'0')    
                if 's_max'+str(i) in qdict:
                    commands['s_max'].append(qdict['s_max'+str(i)])
                else:
                    commands['s_max'].append(u'30')    
                if 's_a_high_fr'+str(i) in qdict:
                    commands['s_a_high_fr'].append(qdict['s_a_high_fr'+str(i)])
                else:
                    commands['s_a_high_fr'].append(5)    
                if 's_a_high_to'+str(i) in qdict:
                    commands['s_a_high_to'].append(qdict['s_a_high_to'+str(i)])
                else:
                    commands['s_a_high_to'].append(10)    
                if 's_b_high_fr'+str(i) in qdict:
                	commands['s_b_high_fr'].append(qdict['s_b_high_fr'+str(i)])
                else:
                    commands['s_b_high_fr'].append(10)    
                if 's_b_high_to'+str(i) in qdict:
                    commands['s_b_high_to'].append(qdict['s_b_high_to'+str(i)])
                else:
                    commands['s_b_high_to'].append(20)    
                if 's_c_high_fr'+str(i) in qdict:
                    commands['s_c_high_fr'].append(qdict['s_c_high_fr'+str(i)])
                else:
                    commands['s_c_high_fr'].append(20)    
                if 's_c_high_to'+str(i) in qdict:
                    commands['s_c_high_to'].append(qdict['s_c_high_to'+str(i)])
                else:
                    commands['s_c_high_to'].append(30)

            plugin_options.__setitem__('s_use', commands['s_use'])
            plugin_options.__setitem__('s_name', commands['s_name'])
            plugin_options.__setitem__('s_unit', commands['s_unit'])
            plugin_options.__setitem__('s_tick', commands['s_tick'])
            plugin_options.__setitem__('s_min', commands['s_min'])
            plugin_options.__setitem__('s_max', commands['s_max'])
            plugin_options.__setitem__('s_a_high_fr', commands['s_a_high_fr'])
            plugin_options.__setitem__('s_a_high_to', commands['s_a_high_to'])
            plugin_options.__setitem__('s_b_high_fr', commands['s_b_high_fr'])
            plugin_options.__setitem__('s_b_high_to', commands['s_b_high_to'])
            plugin_options.__setitem__('s_c_high_fr', commands['s_c_high_fr'])
            plugin_options.__setitem__('s_c_high_to', commands['s_c_high_to'])
            
            if sender is not None:
                sender.update()

        except Exception:
           log.error(NAME, _(u'Weather stations plug-in') + ':\n' + traceback.format_exc())
           pass

        raise web.seeother(plugin_url(canvas_page), True)



class settings_json(ProtectedPage):
    """Returns plugin settings in JSON format."""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        return json.dumps(plugin_options)


class data_json(ProtectedPage):
    """Returns measured data in JSON format."""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        data = []

        try:
            from plugins import air_temp_humi
            data.append(air_temp_humi.DS18B20_read_probe(0))
            data.append(air_temp_humi.DS18B20_read_probe(1))
            data.append(air_temp_humi.DS18B20_read_probe(2))
            data.append(air_temp_humi.DS18B20_read_probe(3))
            data.append(air_temp_humi.DS18B20_read_probe(4))
            data.append(air_temp_humi.DS18B20_read_probe(5))
        except:
            data.append(-127)
            data.append(-127)
            data.append(-127)
            data.append(-127)
            data.append(-127)
            data.append(-127)
            pass

        try:
            from plugins import tank_monitor
            data.append(tank_monitor.get_all_values()[1])
            data.append(tank_monitor.get_all_values()[3])
        except:
            data.append(-127)
            data.append(-127)
            pass

        try:
            from plugins import wind_monitor
            data.append(round(wind_monitor.get_all_values()[0], 2))
        except: 
            data.append(-127)
            pass

        if sensors.count()>0:
            for sensor in sensors.get():
                try:
                    if sensor.sens_type > 0 and sensor.sens_type < 6:        # 1-5 is sensor (Dry Contact, Leak Detector, Moisture, Motion, Temperature)
                        if sensor.sens_type == 1:
                            data.append(sensor.last_read_value[4])
                        elif sensor.sens_type == 2:
                            data.append(sensor.last_read_value[5])
                        elif sensor.sens_type == 3:
                            data.append(sensor.last_read_value[6])
                        elif sensor.sens_type == 4:
                            data.append(sensor.last_read_value[7])
                        elif sensor.sens_type == 5:
                            data.append(sensor.last_read_value[0])
                        else:
                            data.append(-127)
                    elif sensor.sens_type == 6:                              # 6 is multisensor
                        if sensor.multi_type >= 0 and sensor.multi_type <4:  # multisensor temperature DS1-DS4
                            data.append(sensor.last_read_value[sensor.multi_type])
                        elif sensor.multi_type == 4:                         # multisensor Dry Contact
                            data.append(sensor.last_read_value[4])
                        elif sensor.multi_type == 5:                         # multisensor Leak Detector
                            data.append(sensor.last_read_value[5])
                        elif sensor.multi_type == 6:                         # multisensor Moisture
                            data.append(sensor.last_read_value[6])
                        elif sensor.multi_type == 7:                         # multisensor Motion
                            data.append(sensor.last_read_value[7])
                        elif sensor.multi_type == 8:                         # multisensor Ultrasonic
                            data.append(sensor.last_read_value[8])
                        else:
                            data.append(-127)                                # any errors
                    else:                                                    # any errors
                        data.append(-127)
                except:
                    log.error(NAME, _(u'Weather stations plug-in') + ':\n' + traceback.format_exc())
                    data.append(-127)                                        # any errors
                    pass

        return json.dumps(data) # example data list [-127, -127, -127, -127, -127, -127, -127, -127, -127, 25]