#!/usr/bin/env python
# this plugins check water level in tank via ultrasonic sensor
__author__ = 'Martin Pihrt'

import json
import time
import datetime
import sys
import traceback

from threading import Thread, Event

import web
from ospy.stations import stations
from ospy.options import options
from ospy.log import log, logEM
from plugins import PluginOptions, plugin_url
from ospy.helpers import get_rpi_revision
from ospy.webpages import ProtectedPage
from ospy.helpers import datetime_string

import i18n

NAME = 'Water Tank Monitor'
LINK = 'settings_page'

tank_options = PluginOptions(
    NAME,
    {
       'use_sonic': True,      # use sonic sensor
       'distance_bottom': 179, # sensor <-> bottom tank
       'distance_top': 86,     # sensor <-> top tank
       'water_minimum': 40,    # water level <-> bottom tank
       'diameter': 98,         # cylinder diameter for volume calculation
       'use_stop':      False, # not stop water system
       'use_send_email': False,# not send email
       'emlsubject': _('Report from OSPy TANK plugin'),
	'address_ping': 0x04    # device address for sonic ping HW board
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
        once_text = True
        two_text = True
        send = False
        mini = True
        
        while not self._stop.is_set():
            try:
                if tank_options['use_sonic']: 
                    if two_text:
                        log.clear(NAME)
                        log.info(NAME, _('Water tank monitor is enabled.'))
                        once_text = True
                        two_text = False

                    level_in_tank = get_sonic_tank_cm()
                    
                    if level_in_tank >= 0: # if I2C device exists
                        log.info(NAME, datetime_string() + ' ' + _('Water level') + ': ' + str(level_in_tank) + ' ' + _('cm') + ' (' + str(get_tank()) + ' ' + ('%).'))
                        log.info(NAME, _('Ping') + ': ' + str(get_sonic_cm()) + ' ' + _('cm') + ', ' + _('Volume') + ': ' + str(get_volume()) + ' ' + _('m3.'))

                        if level_in_tank <= int(tank_options['water_minimum']) and mini and not options.manual_mode and level_in_tank > -1:
                        
                            if tank_options['use_send_email']: 
                               send = True
                               mini = False 
    
                            log.info(NAME, datetime_string() + ' ' + _('ERROR: Water in Tank') + ' < ' + str(tank_options['water_minimum']) + ' ' + _('cm') + '!')
                            if tank_options['use_stop']:                            
                               options.scheduler_enabled = False                  # disable scheduler
                               log.finish_run(None)                               # save log
                               stations.clear()                                   # set all station to off  
                                          

                        if level_in_tank > int(tank_options['water_minimum']) + 5 and not mini: 
                            mini = True
                    else:
                        log.info(NAME, datetime_string() + ' ' + _('Water level: Error I2C device not found.'))
                
                else:
                    if once_text:
                       log.info(NAME, 'Water tank monitor is disabled.')
                       once_text = False
                       two_text = True
                       last_level = 0
                
                if send:
                    msg = '<b>' + _('Water Tank Monitor plug-in') + '</b> ' + '<br><p style="color:red;">' + _('System detected error: Water Tank has minimum Water Level') +  ': ' + str(tank_options['water_minimum']) + _('cm') + '.\n' + '</p>'
                    msglog = _('Water Tank Monitor plug-in') + ': ' + _('System detected error: Water Tank has minimum Water Level') +  ': ' + str(tank_options['water_minimum']) + _('cm') + '. '  
                    try:
                        send_email(msg, msglog)
                        send = False
                    except Exception as err:
                        log.error(NAME, _('Email was not sent') + '! ' + str(err))

                self._sleep(10) 
                log.clear(NAME)

            except Exception:
                log.error(NAME, _('Water Tank Monitor plug-in') + ':\n' + traceback.format_exc())
                self._sleep(10)


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


def get_sonic_cm():
    try:
        import smbus
        bus = smbus.SMBus(1 if get_rpi_revision() >= 2 else 0)

        data = [2]
        data = try_io(lambda: bus.read_i2c_block_data(tank_options['address_ping'],2))
        cm = data[1] + data[0]*255
        return cm
    except:
        return -1   


def get_sonic_tank_cm():
    try:
        cm = get_sonic_cm()
        if cm < 0:
           return -1
 
        tank_cm = maping(cm,int(tank_options['distance_bottom']),int(tank_options['distance_top']),int(tank_options['distance_top']),int(tank_options['distance_bottom']))
        if tank_cm >= 0:
           return tank_cm

        else:
           return 0 
    except:
        return -1 # if I2C device not exists


def get_tank(): # return water tank level 0-100%, -1 is error i2c not found
    tank_lvl = get_sonic_tank_cm()
    if tank_lvl >= 0:
       tank_proc = maping(tank_lvl,int(tank_options['distance_top']),int(tank_options['distance_bottom']),0,100) 
       return tank_proc
    else:
       return -1


def get_volume(): # return volume calculation from cylinder diameter and water column height in m3
    tank_lvl = get_sonic_tank_cm()
    if tank_lvl >= 0:
       
       try:       
          import math
          r = tank_options['diameter']/2
          area = math.pi*r*r               # calculate area of circle
          volume = area*tank_lvl           # volume in cm3
          volume = volume/1000000          # convert from cm3 to m3
          volume = round(volume,2)         # round only two decimals
          return volume
       except:
          return -1
    else:
       return -1


def maping(x, in_min, in_max, out_min, out_max):
    # return value from map. example (x=1023,0,1023,0,100) -> x=1023 return 100
    return (x - in_min) * (out_max - out_min) / (in_max - in_min) + out_min

 
def send_email(msg, msglog):
    """Send email"""
    message = datetime_string() + ': ' + msg
    try:
        from plugins.email_notifications import email

        Subject = tank_options['emlsubject']

        email(message, subject=Subject)

        if not options.run_logEM:
           log.info(NAME, _('Email logging is disabled in options...'))
        else:        
           logEM.save_email_log(Subject, msglog, _('Sent'))

        log.info(NAME, _('Email was sent') + ': ' + msglog)

    except Exception:
        if not options.run_logEM:
           log.info(NAME, _('Email logging is disabled in options...'))
        else:
           logEM.save_email_log(Subject, msglog, _('Email was not sent'))

        log.info(NAME, _('Email was not sent') + '! ' + traceback.format_exc())


################################################################################
# Web pages:                                                                   #
################################################################################

class settings_page(ProtectedPage):
    """Load an html page for entering adjustments."""

    def GET(self):
        return self.plugin_render.tank_monitor(tank_options, log.events(NAME))

    def POST(self):
        tank_options.web_update(web.input())

        if sender is not None:
            sender.update()
        raise web.seeother(plugin_url(settings_page), True)


class settings_json(ProtectedPage):
    """Returns plugin settings in JSON format."""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        return json.dumps(tank_options)

