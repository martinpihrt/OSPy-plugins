# -*- coding: utf-8 -*-
__author__ = 'Martin Pihrt'

import json
import time
import traceback
import web


from blinker import signal ### for this example ###

from ospy.helpers import datetime_string 
from ospy.log import log
from threading import Thread, Event
from plugins import plugin_url
from ospy.webpages import ProtectedPage

NAME = 'Signaling Examples'
MENU =  _('Package: Signaling Examples')
LINK = 'settings_page'


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
        #while not self._stop_event.is_set(): ### delete hashtag for loop ###
            ### here is main loop for this plugin ###
            loggedin = signal('loggedin') ### associations with signal ###
            loggedin.connect(notify_login)### define which subroutine will be triggered in helper ###
            value_change = signal('value_change')
            value_change.connect(notify_value_change)
            option_change = signal('option_change')
            option_change.connect(notify_option_change)
            rebooted = signal('rebooted')
            rebooted.connect(notify_rebooted)
            restarted = signal('restarted')
            restarted.connect(notify_restarted)
            station_names = signal('station_names')
            station_names.connect(notify_station_names)
            program_change = signal('program_change')
            program_change.connect(notify_program_change)
            program_deleted = signal('program_deleted')
            program_deleted.connect(notify_program_deleted)
            program_toggled = signal('program_toggled')
            program_toggled.connect(notify_program_toggled)
            program_runnow = signal('program_runnow')
            program_runnow.connect(notify_program_runnow)
            zone_change = signal('zone_change')
            zone_change.connect(notify_zone_change)
            rain_active = signal('rain_active')
            rain_active.connect(notify_rain_active)
            rain_not_active = signal('rain_not_active')
            rain_not_active.connect(notify_rain_not_active)
            master_one_on = signal('master_one_on')
            master_one_on.connect(notify_master_one_on)
            master_one_off = signal('master_one_off')
            master_one_off.connect(notify_master_one_off)
            master_two_on = signal('master_two_on')
            master_two_on.connect(notify_master_two_on)
            master_two_off = signal('master_two_off')
            master_two_off.connect(notify_master_two_off)
            pressurizer_master_relay_on = signal('pressurizer_master_relay_on')
            pressurizer_master_relay_on.connect(notify_pressurizer_master_relay_on)
            pressurizer_master_relay_off = signal('pressurizer_master_relay_off')
            pressurizer_master_relay_off.connect(notify_pressurizer_master_relay_off)
            poweroff = signal('poweroff')
            poweroff.connect(notify_poweroff)
            ospyupdate = signal('ospyupdate')
            ospyupdate.connect(notify_ospyupdate)
            station_on = signal('station_on')
            station_on.connect(notify_station_on)
            station_off = signal('station_off')
            station_off.connect(notify_station_off)
            station_clear = signal('station_clear')
            station_clear.connect(notify_station_clear)
            internet_available = signal('internet_available')
            internet_available.connect(notify_internet_available)
            internet_not_available = signal('internet_not_available')
            internet_not_available.connect(notify_internet_not_available)
            rain_delay_set = signal('rain_delay_set')
            rain_delay_set.connect(notify_rain_delay_setuped) 
            rain_delay_remove = signal('rain_delay_remove')
            rain_delay_remove.connect(notify_rain_delay_expired)
            hass_plugin_update = signal('hass_plugin_update')
            hass_plugin_update.connect(notify_hass_update)
            core_30_sec_tick = signal('core_30_sec_tick')
            core_30_sec_tick.connect(notify_core_30_sec_tick)
            air_temp_humi_plugin_update = signal('air_temp_humi_plugin_update')
            air_temp_humi_plugin_update.connect(notify_air_temp_humi_plugin_update)

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

### login ###
def notify_login(name, **kw):
    log.info(NAME, datetime_string() + ': ' + _('Someone logged in'))
    
### System settings ###
def notify_value_change(name, **kw):
    log.info(NAME, datetime_string() + ': ' + _('Value_change'))

### Option settings ###
def notify_option_change(name, **kw):
    log.info(NAME, datetime_string() + ': ' + _('Options settings changed'))

### Reboot ###
def notify_rebooted(name, **kw):
    log.info(NAME, datetime_string() + ': ' + _('System rebooted'))

### Restarted ###
def notify_restarted(name, **kw):
    log.info(NAME, datetime_string() + ': ' + _('System restarted'))

### station names ###
def notify_station_names(name, **kw):
    log.info(NAME, datetime_string() + ': ' + _('Station names changed'))

### program change ##
def notify_program_change(name, **kw):
    log.info(NAME, datetime_string() + ': ' + _('Programs changed'))

### program deleted ###
def notify_program_deleted(name, **kw):
    log.info(NAME, datetime_string() + ': ' + _('Program deleted'))

### program toggled ###
def notify_program_toggled(name, **kw):
    log.info(NAME, datetime_string() + ': ' + _('Program toggled on or off'))

### program runnow ###
def notify_program_runnow(name, **kw):
    log.info(NAME, datetime_string() + ': ' + _('Program runnow'))

### zone change ###
def notify_zone_change(name, **kw):
    log.info(NAME, datetime_string() + ': ' + _('Zone change'))

### rain ###
def notify_rain_active(name, **kw):
    log.info(NAME, datetime_string() + ': ' + _('Rain active'))

### not rain ###
def notify_rain_not_active(name, **kw):
    log.info(NAME, datetime_string() + ': ' + _('Rain not active'))    

### master 1 on ###
def notify_master_one_on(name, **kw):
    log.info(NAME, datetime_string() + ': ' + _('Master one on'))    

### master 1 off ###
def notify_master_one_off(name, **kw):
    log.info(NAME, datetime_string() + ': ' + _('Master one off'))    

### master 2 on ###
def notify_master_two_on(name, **kw):
    log.info(NAME, datetime_string() + ': ' + _('Master two on'))    

### master 2 off ###
def notify_master_two_off(name, **kw):
    log.info(NAME, datetime_string() + ': ' + _('Master two off'))  

### pressurizer plugin master relay on ###
def notify_pressurizer_master_relay_on(name, **kw):
    log.info(NAME, datetime_string() + ': ' + _('Pressurizer plugin master relay on')) 

### pressurizer plugin master relay off ###
def notify_pressurizer_master_relay_off(name, **kw):
    log.info(NAME, datetime_string() + ': ' + _('Pressurizer plugin master relay off')) 

### Linux system power off ###
def notify_poweroff(name, **kw):
    log.info(NAME, datetime_string() + ': ' + _('Linux system now powering off')) 

### OSPy system update available ###
def notify_ospyupdate(name, **kw):
    log.info(NAME, datetime_string() + ': ' + _('OSPy system update available'))

### Stations ON ###
def notify_station_on(name, **kw):
    log.info(NAME, datetime_string() + ': ' + _('OSPy stations ON, index: {}').format(kw[u"txt"]))
    #print(u"Messge from {}!: {}".format(name, kw[u"txt"]))

### Stations OFF ###
def notify_station_off(name, **kw):
    log.info(NAME, datetime_string() + ': ' + _('OSPy stations OFF, index: {}').format(kw[u"txt"]))
    #print(u"Messge from {}!: {}".format(name, kw[u"txt"]))

### All stations set to OFF ###
def notify_station_clear(name, **kw):
    log.info(NAME, datetime_string() + ': ' + _('OSPy all stations OFF'))

### Internet available ###
def notify_internet_available(name, **kw):
    log.info(NAME, datetime_string() + ': ' + _('Internet is available (external IP)'))

### Internet not available ###
def notify_internet_not_available(name, **kw):
    log.info(NAME, datetime_string() + ': ' + _('Internet is not available (external IP)'))

### Rain delay has setuped ###
def notify_rain_delay_setuped(name, **kw):
    log.info(NAME, datetime_string() + ': ' + _('Rain delay is now set a delay {} hours').format(kw[u"txt"]))

### Rain delay has expired ###
def notify_rain_delay_expired(name, **kw):
    log.info(NAME, datetime_string() + ': ' + _('Rain delay has now been removed'))

### HASS plugin update ###
def notify_hass_update(name, **kw):
    log.info(NAME, datetime_string() + ': ' + _('Home Assistant update'))

### OSPy core tick in loop 30 second ###
def notify_core_30_sec_tick(name, **kw):
    log.clear(NAME)
    log.info(NAME, datetime_string() + ': ' + _('Core tick interval 30 second'))

### Airtemp humi plugin update ###
def notify_air_temp_humi_plugin_update(name, **kw):
    log.info(NAME, datetime_string() + ': ' + _('Air Temperature and Humidity Monitor update'))

################################################################################
# Web pages:                                                                   #
################################################################################

class settings_page(ProtectedPage):
    """Load an html page for entering adjustments."""

    def GET(self):
        return self.plugin_render.signaling_examples()

    def POST(self):
        if sender is not None:
            sender.update()                
        raise web.seeother(plugin_url(settings_page), True)


class help_page(ProtectedPage):
    """Load an html page for help"""

    def GET(self):
        return self.plugin_render.signaling_examples_help()


class settings_json(ProtectedPage):            ### return plugin_options as JSON data ###
    """Returns plugin settings in JSON format."""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        return json.dumps(plugin_options)


class signal_json(ProtectedPage):
    """Returns log info state in JSON format."""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        data = {}
        data['loginfo'] = '{}'.format(log.events(NAME))
        return json.dumps(data)

