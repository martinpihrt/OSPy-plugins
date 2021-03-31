# -*- coding: utf-8 -*-
__author__ = 'Martin Pihrt'

import json
import traceback

import web
from plugins import PluginOptions, plugin_url
from ospy.webpages import ProtectedPage
from ospy.log import log

NAME = 'Weather Stations'
MENU =  _('Package: Weather Stations')
LINK = 'canvas_page'

plugin_options = PluginOptions(
    NAME,
    {
    'can_or_txt': False,                                            # canvas or text mode showing data
    'can_size_xy': 250,                                             # all canvas x and y size in pixels
    'txt_size_font': 40,                                            # size for font in text mode    

    'use_can1': True,                                               # use canvas 1 or text 1
    'use_can2': True,
    'use_can3': True,
    'use_can4': True,
    'use_can5': True,
    'use_can6': True,
    'use_can7': True,
    'use_can8': True,
    'use_can9': True,

    'can_1_units': _(u'°C'),                                        # canvas 1 units °C or ...
    'can_2_units': _(u'°C'),
    'can_3_units': _(u'°C'),
    'can_4_units': _(u'°C'),
    'can_5_units': _(u'°C'),
    'can_6_units': _(u'°C'),  
    'can_7_units': _(u'%'),
    'can_8_units': _(u'liters'),
    'can_9_units': _(u'm/s'),
                
    'can_1_name': _(u'Canvas DS1'),                                 # canvas 1 name
    'can_2_name': _(u'Canvas DS2'),
    'can_3_name': _(u'Canvas DS3'),
    'can_4_name': _(u'Canvas DS4'),
    'can_5_name': _(u'Canvas DS5'),
    'can_6_name': _(u'Canvas DS6'), 
    'can_7_name': _(u'Percent'),
    'can_8_name': _(u'Volume'), 
    'can_9_name': _(u'Wind'),                

    'can_1_tick': '-10,0,10,20,30,40,50,60',                        # canvas 1 tick scale division
    'can_2_tick': '0,10,20,30,40,50,60,70,80,90,100,110,130',
    'can_3_tick': '0,10,20,30,40,50,60,70,80,90,100,110,130',
    'can_4_tick': '0,10,20,30,40,50,60,70,80,90,100,110,130',
    'can_5_tick': '0,10,20,30,40,50,60,70,80,90,100,110,130',
    'can_6_tick': '0,10,20,30,40,50,60,70,80,90,100,110,130',
    'can_7_tick': '0,10,20,30,40,50,60,70,80,90,100,110,130',
    'can_8_tick': '0,10,20,30,40,50,60,70,80,90,100,110,130',
    'can_9_tick': '0,10,20,30,40,50',

    'can_1_min' : '-10',                                            # canvas 1 minimum value for highlights
    'can_1_max' : '60',                                             # canvas 1 maximum value for highlights
    'can_2_min' : '0',
    'can_2_max' : '130', 
    'can_3_min' : '0',
    'can_3_max' : '130',
    'can_4_min' : '0',
    'can_4_max' : '130',
    'can_5_min' : '0',
    'can_5_max' : '130',
    'can_6_min' : '0',
    'can_6_max' : '130',
    'can_7_min' : '0',
    'can_7_max' : '130',
    'can_8_min' : '0',
    'can_8_max' : '130',
    'can_9_min' : '0',
    'can_9_max' : '50',    

    'can_1_high_fr': 0,                                             # red color on highlights from 
    'can_1_high_to': 15,                                            # red color on highlights to
    'can_1_2_high_fr': 15,                                          # blue color on highlights from 
    'can_1_2_high_to': 30,                                          # blue color on highlights to
    'can_1_3_high_fr': 30,                                          # green color on highlights from 
    'can_1_3_high_to': 45,                                          # green color on highlights to        
    'can_2_high_fr': 5,  
    'can_2_high_to': 25,
    'can_2_2_high_fr': 15,                                          
    'can_2_2_high_to': 30,                                          
    'can_2_3_high_fr': 30,                                          
    'can_2_3_high_to': 45,                                              
    'can_3_high_fr': 30,  
    'can_3_high_to': 40,
    'can_3_2_high_fr': 15,                                          
    'can_3_2_high_to': 30,                                          
    'can_3_3_high_fr': 30,
    'can_3_3_high_to': 45,                                              
    'can_4_high_fr': 50,  
    'can_4_high_to': 60,
    'can_4_2_high_fr': 15,                                           
    'can_4_2_high_to': 30,                                          
    'can_4_3_high_fr': 30,                                          
    'can_4_3_high_to': 45,                                             
    'can_5_high_fr': 70,  
    'can_5_high_to': 80,
    'can_5_2_high_fr': 15,                                           
    'can_5_2_high_to': 30,                                          
    'can_5_3_high_fr': 30,                                          
    'can_5_3_high_to': 45,                                             
    'can_6_high_fr': 90,  
    'can_6_high_to': 100, 
    'can_6_2_high_fr': 15,                                           
    'can_6_2_high_to': 30,                                          
    'can_6_3_high_fr': 30,                                          
    'can_6_3_high_to': 45,                                              
    'can_7_high_fr': 70,  
    'can_7_high_to': 80,
    'can_7_2_high_fr': 15,                                          
    'can_7_2_high_to': 30,                                          
    'can_7_3_high_fr': 30,                                           
    'can_7_3_high_to': 45,                                              
    'can_8_high_fr': 90,  
    'can_8_high_to': 100,           
    'can_8_2_high_fr': 15,                                           
    'can_8_2_high_to': 30,                                          
    'can_8_3_high_fr': 30,                                           
    'can_8_3_high_to': 45,  
    'can_9_high_fr': 10,  
    'can_9_high_to': 50,           
    'can_9_2_high_fr': 0,                                           
    'can_9_2_high_to': 0,                                          
    'can_9_3_high_fr': 0,                                           
    'can_9_3_high_to': 0,                                            
    }
)


################################################################################
# Helper functions:                                                            #
################################################################################
def start():
    pass     

stop = start

################################################################################
# Web pages:                                                                   #
################################################################################

class canvas_page(ProtectedPage):
    """Load an html page for canvas wieving."""

    def GET(self):
        return self.plugin_render.canvas_page(plugin_options)


class help_page(ProtectedPage):
    """Load an html page for help page."""

    def GET(self):
        return self.plugin_render.help_page()        


class settings_page(ProtectedPage):
    """Load an html settings page for canvas options."""

    def GET(self):
        return self.plugin_render.settings_page(plugin_options)


    def POST(self):
        plugin_options.web_update(web.input())
        return self.plugin_render.canvas_page(plugin_options)       


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
        data =  {}

        try:
            from plugins import air_temp_humi
            data['temp_ds0'] = air_temp_humi.DS18B20_read_probe(0)
            data['temp_ds1'] = air_temp_humi.DS18B20_read_probe(1)
            data['temp_ds2'] = air_temp_humi.DS18B20_read_probe(2)
            data['temp_ds3'] = air_temp_humi.DS18B20_read_probe(3)
            data['temp_ds4'] = air_temp_humi.DS18B20_read_probe(4)
            data['temp_ds5'] = air_temp_humi.DS18B20_read_probe(5)
        except: 
            #log.error(NAME, traceback.format_exc())
            data['temp_ds0'] = -127
            data['temp_ds1'] = -127
            data['temp_ds2'] = -127
            data['temp_ds3'] = -127
            data['temp_ds4'] = -127
            data['temp_ds5'] = -127
            pass

        try:    
            from plugins import tank_monitor
            data['water_1'] = tank_monitor.get_all_values()[1]
            data['water_2'] = tank_monitor.get_all_values()[3]
        except: 
            #log.error(NAME, traceback.format_exc())
            data['water_1'] = -127
            data['water_2'] = -127
            pass  

        try:    
            from plugins import wind_monitor
            data['wind_1'] = round(wind_monitor.get_all_values()[0], 2)
        except: 
            #log.error(NAME, traceback.format_exc())
            data['wind_1'] = -127
            pass                      

        return json.dumps(data) 