#!/usr/bin/env python
# -*- coding: utf-8 -*-
__author__ = 'Martin Pihrt'
# This plugin controls OpenSprinkler OSPy via 8 defined buttons. I2C controller MCP23017 on 0x27 address. 

import time
import traceback
import os
from threading import Thread, Event

import web

from ospy.log import log
from plugins import PluginOptions, plugin_url, plugin_data_dir
from ospy.webpages import ProtectedPage
from ospy.stations import stations
from ospy.scheduler import scheduler
from ospy.programs import programs
from ospy.options import options
from ospy.runonce import run_once
from ospy import helpers
from ospy.helpers import datetime_string

import i18n

NAME = 'Button Control'
LINK = 'settings_page'

plugin_options = PluginOptions(
    NAME,
    {'use_button': False,
     'button0': 'reboot',
     'button1': 'pwrOff',
     'button2': 'stopAll',
     'button3': 'schedEn',
     'button4': 'runP1',
     'button5': 'runP2',
     'button6': 'runP3',
     'button7': 'runP4'
    }
)


################################################################################
# Main function loop:                                                          #
################################################################################

class PluginSender(Thread):
    def __init__(self):
        Thread.__init__(self)
        self.daemon = True
        self._stop = Event()
        
        self.bus = None
        
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

        while not self._stop.is_set():
            try:
                if plugin_options['use_button']:  # if button plugin is enabled
                    disable_text = True
                    actual_buttons = read_buttons()
                    
                    # led_outputs(actual_buttons) # for test

                    for i in range(8):
                       tb = "button" + str(i)    
                       if actual_buttons == i and plugin_options[tb]== "reboot":
                          log.info(NAME, datetime_string() + ': ' + _('System reboot')) 
                          stations.clear()
                          reboot()
                          self._sleep(2)
                       
                       if actual_buttons == i and plugin_options[tb]== "pwrOff":
                          log.info(NAME, datetime_string() + ': ' + _('System shutdown')) 
                          stations.clear()
                          poweroff()
                          self._sleep(2)
                         
                       if actual_buttons == i and plugin_options[tb]== "stopAll":
                          log.info(NAME, datetime_string() + ': ' + _('All stations now stopped')) 
                          log.finish_run(None)       # save log
                          stations.clear()           # set all station to off 
                          self._sleep(2)

                       if actual_buttons == i and plugin_options[tb]== "schedEn":
                          log.info(NAME, datetime_string() + ': ' + _('Scheduler is now enabled')) 
                          options.scheduler_enabled = True
                          self._sleep(2)

                       if actual_buttons == i and plugin_options[tb]== "schedDis":
                          log.info(NAME, datetime_string() + ': ' + _('Scheduler is now disabled')) 
                          options.scheduler_enabled = False
                          self._sleep(2)

                       if actual_buttons == i and plugin_options[tb]== "RunP1":
                          log.info(NAME, datetime_string() + ': ' + _('Run now program 1')) 
                          for program in programs.get():
                             if (program.index == 0):   # Run-now program 1
                                options.manual_mode = False   
                                log.finish_run(None)
                                stations.clear()    
                                programs.run_now(program.index)       
                             program.index+1
                          self._sleep(2)

                       if actual_buttons == i and plugin_options[tb]== "RunP2":
                          log.info(NAME, datetime_string() + ': ' + _('Run now program 2')) 
                          for program in programs.get():
                             if (program.index == 1):   # Run-now program 2  
                                options.manual_mode = False     
                                log.finish_run(None)
                                stations.clear()   
                                programs.run_now(program.index)
                             program.index+1
                          self._sleep(2)

                       if actual_buttons == i and plugin_options[tb]== "RunP3":
                          log.info(NAME, datetime_string() + ': ' + _('Run now program 3')) 
                          for program in programs.get():
                             if (program.index == 2):   # Run-now program 3  
                                options.manual_mode = False     
                                log.finish_run(None)  
                                stations.clear() 
                                programs.run_now(program.index)
                             program.index+1
                          self._sleep(2)
                            
                       if actual_buttons == i and plugin_options[tb]== "RunP4":
                          log.info(NAME, datetime_string() + ': ' + _('Run now program 4')) 
                          for program in programs.get():
                             if (program.index == 3):   # Run-now program 4  
                                options.manual_mode = False   
                                log.finish_run(None)
                                stations.clear()     
                                programs.run_now(program.index)
                             program.index+1
                          self._sleep(2)        
 
                       if actual_buttons == i and plugin_options[tb]== "RunP5":
                          log.info(NAME, datetime_string() + ': ' + _('Run now program 5'))
                          for program in programs.get():
                             if (program.index == 4):   # Run-now program 5
                                options.manual_mode = False
                                log.finish_run(None)
                                stations.clear() 
                                programs.run_now(program.index)
                             program.index+1
                          self._sleep(2)

                       if actual_buttons == i and plugin_options[tb]== "RunP6":
                          log.info(NAME, datetime_string() + ': ' + _('Run now program 6'))
                          for program in programs.get():
                             if (program.index == 5):   # Run-now program 6
                                options.manual_mode = False
                                log.finish_run(None)
                                stations.clear() 
                                programs.run_now(program.index)
                             program.index+1
                          self._sleep(2)

                       if actual_buttons == i and plugin_options[tb]== "RunP7":
                          log.info(NAME, datetime_string() + ': ' + _('Run now program 7'))
                          for program in programs.get():
                             if (program.index == 6):   # Run-now program 7
                                options.manual_mode = False
                                log.finish_run(None)
                                stations.clear() 
                                programs.run_now(program.index)
                             program.index+1
                          self._sleep(2)

                       if actual_buttons == i and plugin_options[tb]== "RunP8":
                          log.info(NAME, datetime_string() + ': ' + _('Run now program 8'))
                          for program in programs.get():
                             if (program.index == 7):   # Run-now program 8
                                options.manual_mode = False
                                log.finish_run(None)
                                stations.clear() 
                                programs.run_now(program.index)
                             program.index+1
                          self._sleep(2)

                    self._sleep(2)

                else:
                    # text on the web if plugin is disabled
                    if disable_text:  
                       log.clear(NAME)
                       log.info(NAME, _('Button plug-in is disabled.'))
                       disable_text = False  
                    self._sleep(1)



            except Exception:
                log.clear(NAME)
                log.error(NAME, _('Button plug-in') + ':\n' + traceback.format_exc())
                self._sleep(60)
                pass
                

plugin_sender = None

################################################################################
# Helper functions:                                                            #
################################################################################
def start():
    global plugin_sender
    if plugin_sender is None:
        plugin_sender = PluginSender()


def stop():
    global plugin_sender
    if plugin_sender is not None:
        plugin_sender.stop()
        plugin_sender.join()
        plugin_sender = None

        
def try_io(call, tries=10):
    assert tries > 0
    error = None
    result = None

    while tries:
        try:
            result = call()
        except IOError as e:
            error = e
            tries -= 1
        else:
            break

    if not tries:
        raise error

    return result

def read_buttons():
    try:
        import smbus  

        bus = smbus.SMBus(0 if helpers.get_rpi_revision() == 1 else 1) 
        
        # Set 8 GPA pins as input pull-UP
        try_io(lambda: bus.write_byte_data(0x27,0x0C,0xFF)) #bus.write_byte_data(0x27,0x0C,0xFF)  
     
        # Wait for device
        time.sleep(0.2) 

        # Read state of GPIOA register
        MySwitch = try_io(lambda: bus.read_byte_data(0x27,0x12))  # MySwitch = bus.read_byte_data(0x27,0x12)
               
        inBut = 255-MySwitch; # inversion number for led off if button is not pressed

        led_outputs(inBut)    # switch on actual led if button is pressed

        button_number = -1
        if inBut == 128:
            button_number = 7
            log.debug(NAME, _('Switch 8 pressed'))
        if inBut == 64:
            button_number = 6
            log.debug(NAME, _('Switch 7 pressed'))
        if inBut == 32:
            button_number = 5
            log.debug(NAME, _('Switch 6 pressed'))
        if inBut == 16:
            button_number = 4
            log.debug(NAME, _('Switch 5 pressed'))
        if inBut == 8:
            button_number = 3
            log.debug(NAME, _('Switch 4 pressed'))
        if inBut == 4:
            button_number = 2
            log.debug(NAME, _('Switch 3 pressed'))
        if inBut == 2:
            button_number = 1
            log.debug(NAME, _('Switch 2 pressed'))
        if inBut == 1:
            button_number = 0
            log.debug(NAME, _('Switch 1 pressed'))
        return button_number #if button is not pressed return -1

    except Exception:
        log.clear(NAME)
        log.error(NAME, _('Button plug-in') + ':' + _('Read button - FAULT'))
        log.error(NAME, '\n' + traceback.format_exc())
        pass
        return -1

def led_outputs(led):
    try:
        import smbus  

        bus = smbus.SMBus(0 if helpers.get_rpi_revision() == 1 else 1) 
 
        bus.write_byte_data(0x27,0x01,0x00)
        # Wait for device
        time.sleep(0.1)      
        bus.write_byte_data(0x27,0x13,led)
        # Wait for device
        time.sleep(0.1)
        
    except Exception:
        log.error(NAME, _('Button plug-in') + ':' + _('Set LED - FAULT'))
        log.error(NAME, '\n' + traceback.format_exc())
        pass

################################################################################
# Web pages:                                                                   #
################################################################################

class settings_page(ProtectedPage):
    """Load an html page for entering plugin settings."""

    def GET(self):
        return self.plugin_render.button_control(plugin_options, log.events(NAME))

    def POST(self): 
        plugin_options.web_update(web.input())
        if plugin_sender is not None:
            plugin_sender.update()
        raise web.seeother(plugin_url(settings_page), True)


class settings_json(ProtectedPage):
    """Returns plugin settings in JSON format."""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        return json.dumps(plugin_options)        
