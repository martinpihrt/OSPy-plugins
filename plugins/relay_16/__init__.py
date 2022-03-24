# -*- coding: utf-8 -*-
__author__ = u'Martin Pihrt' 

import datetime
import time

from threading import Thread, Event
import traceback
import json

import web
from ospy.log import log
from ospy.options import options
from ospy.webpages import ProtectedPage
from ospy.helpers import determine_platform, get_rpi_revision, datetime_string
from ospy.stations import stations
from plugins import PluginOptions, plugin_url


NAME = 'Direct 16 Relay Outputs'
MENU =  _(u'Package: Direct 16 Relay Outputs')
LINK = 'settings_page'

plugin_options = PluginOptions(
    NAME,
    {
        'enabled': False,  # default is OFF
        'relays': 1,       # default 1 relay
        'active': 'high'   # default is normal logic   
    })


################################################################################
# Main function loop:                                                          #
################################################################################
class Relay16Checker(Thread):
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
        error_check = False # error signature
        relay_pins = [0]
        relay_count = -1
        msg_debug_err = True
        msg_debug_on = [True,True,True,True,True,True,True,True,True,True,True,True,True,True,True,True]
        msg_debug_off = [True,True,True,True,True,True,True,True,True,True,True,True,True,True,True,True]
        time_cleaner = 0
 
        if not plugin_options['enabled']:
           log.info(NAME, _('Relay 16 plug-in') + ': ' +  _('is disabled.'))

        while not self._stop_event.is_set():
            try: 
                if relay_count != plugin_options['relays'] and plugin_options['enabled']:
                  relay_count = plugin_options['relays']
                  log.clear(NAME)
                  log.info(NAME, _('Relay 16 plug-in') + ': ' + datetime_string() + ' ' + str(plugin_options['relays']) + ' ' + _('Outputs set.')) 

                  #### define the GPIO pins that will be used ####
                  try:
                     if determine_platform() == 'pi': # If this will run on Raspberry Pi:

                        import RPi.GPIO as GPIO  # RPi hardware
                        GPIO.setmode(GPIO.BOARD) #IO channels are identified by header connector pin numbers. Pin numbers are 
                        
                        if get_rpi_revision() >= 2: 
                                     
                           relay_pins = [22,24,26,32,36,38,40,21,23,29,31,33,35,37,18,19] ### associations for outputs HW connector PINs 

                           log.info(NAME, _('Relay 16 plug-in') + ': ' + _('Possible GPIO pins') + str(relay_pins) + '.') 
                           for i in range(plugin_options['relays']):   # count 1 or 2, 4, 8, 16 outputs
                               try:
                                   GPIO.setup(relay_pins[i], GPIO.OUT) # set pin as outputs
                               except:
                                   error_check = True                  # not set pins -> this is error
                                   log.error(NAME, _('Relay 16 plug-in') + ':\n' + traceback.format_exc())
                        else:
                           log.info(NAME, _('Relay 16 plug-in') + ': ' + _('Sorry Raspberry Pi 1 is old version.'))
                           error_check = True
                     else:
                        log.info(NAME, _('Relay 16 plug-in') + ': ' + _('Relay board plugin only supported on Raspberry Pi.'))

                  except:
                     if msg_debug_err:
                        log.error(NAME, _('Relay 16 plug-in') + ':\n' + traceback.format_exc())
                        msg_debug_err = False
                     error_check = False
                     pass

                #### plugin 
                if plugin_options['enabled']:                   # if plugin is enabled
                  if error_check == False:                      # if not check error
                    for station in stations.get():              
                      if station.index+1 <= plugin_options['relays']:  # only if station count is < count relay outputs

                         ### ON
                         if station.active:                            # stations is on 
                            if plugin_options['active'] == 'high':     # normal high logic
                               # relay output on to 3.3V 
                               GPIO.output(relay_pins[station.index], GPIO.HIGH)
                               if msg_debug_on[station.index]:
                                  log.info(NAME, _('Relay 16 plug-in') + ': ' + datetime_string() + ' ' + _('Setings Relay Output') + ' ' + str(relay_pins[station.index]) + ' ' + _('to HIGH') + ' (' + _('Station') + ' ' + str(station.index+1) + ' ' + _('ON') + ').')
                                  msg_debug_on[station.index] = False
                                  msg_debug_off[station.index] = True 
                            else:                                      # inversion low logic
                               # relay output on to 0V 
                               GPIO.output(relay_pins[station.index], GPIO.LOW)
                               if msg_debug_on[station.index]:
                                  log.info(NAME, _('Relay 16 plug-in') + ': ' + datetime_string() + ' ' + _('Setings Relay Output') + ' ' + str(relay_pins[station.index]) + ' ' + _('to LOW') + ' (' + _('Station') + ' ' + str(station.index+1) + ' ' + _('ON') + ').') 
                                  msg_debug_on[station.index] = False
                                  msg_debug_off[station.index] = True

                         ### OFF
                         else:                                         # stations is off
                            if plugin_options['active'] == 'high':     # normal high logic
                               # relay output off to 0V
                               GPIO.output(relay_pins[station.index], GPIO.LOW)
                               if msg_debug_off[station.index]:
                                  log.info(NAME, _('Relay 16 plug-in') + ': ' + datetime_string() + ' ' + _('Setings Relay Output') + ' ' + str(relay_pins[station.index]) + ' ' + _('to LOW') + ' (' + _('Station') + ' ' + str(station.index+1) +  ' ' + _('OFF') + ').')
                                  msg_debug_off[station.index] = False
                                  msg_debug_on[station.index] = True
                            else:                                      # inversion low logic
                               # relay output off to 3.3V   
                               GPIO.output(relay_pins[station.index], GPIO.HIGH)
                               if msg_debug_off[station.index]:
                                  log.info(NAME, _('Relay 16 plug-in') + ': ' + datetime_string() + ' ' + _('Setings Relay Output') + ' ' + str(relay_pins[station.index]) + ' ' + _('to HIGH') + ' (' + _('Station') + ' ' + str(station.index+1)  + ' ' + _('OFF') + ').')
                                  msg_debug_off[station.index] = False
                                  msg_debug_on[station.index] = True

                time.sleep(0.5)

                time_cleaner += 1                 

                if time_cleaner >= 120: # 60 sec timer (ex: 120 * time.sleep(0.5) is 60 sec)
                   time_cleaner = 0
                   relay_count = -1
                   msg_debug_err = True
                   msg_debug_on = [True,True,True,True,True,True,True,True,True,True,True,True,True,True,True,True]
                   msg_debug_off = [True,True,True,True,True,True,True,True,True,True,True,True,True,True,True,True]

              

            except Exception:
                log.error(NAME, _('Relay 16 plug-in') + ':\n' + traceback.format_exc())
                msg = -1
                self._sleep(60)


checker = None


################################################################################
# Helper functions:                                                            #
################################################################################
  
def start():
    global checker
    if checker is None:
        checker = Relay16Checker()


def stop():
    global checker
    if checker is not None:
        checker.stop()
        checker.join()
        checker = None

################################################################################
# Web pages:                                                                   #
################################################################################
class settings_page(ProtectedPage):
    """Load an html page for entering relay 16 adjustments"""

    def GET(self):
        return self.plugin_render.relay_16(plugin_options, log.events(NAME))

    def POST(self):
        plugin_options.web_update(web.input())
        if checker is not None:
            checker.update()
        raise web.seeother(plugin_url(settings_page), True)


class help_page(ProtectedPage):
    """Load an html page for help"""

    def GET(self):
        return self.plugin_render.relay_16_help()        


class settings_json(ProtectedPage):
    """Returns plugin settings in JSON format"""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        return json.dumps(plugin_options)
