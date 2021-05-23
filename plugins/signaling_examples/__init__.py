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
from plugins import PluginOptions, plugin_url
from ospy.webpages import ProtectedPage

NAME = 'Signaling Examples'  ### name for plugin in plugin manager ###
MENU =  _(u'Package: Signaling Examples')
LINK = 'settings_page'       ### link for page in plugin manager ###
 
plugin_options = PluginOptions(
    NAME,
    {#'use_signaling': False        ### for example ###
    ### here is your plugin options ### 
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

        self.status = {}

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
        #while not self._stop.is_set(): ### delete hashtag for loop ###

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
    log.info(NAME, datetime_string() + ': ' + _(u'Someone logged in'))
    
### System settings ###
def notify_value_change(name, **kw):
    log.info(NAME, datetime_string() + ': ' + _(u'Value_change'))

### Option settings ###
def notify_option_change(name, **kw):
    log.info(NAME, datetime_string() + ': ' + _(u'Options settings changed'))

### Reboot ###
def notify_rebooted(name, **kw):
    log.info(NAME, datetime_string() + ': ' + _(u'System rebooted'))

### Restarted ###
def notify_restarted(name, **kw):
    log.info(NAME, datetime_string() + ': ' + _(u'System restarted'))

### station names ###
def notify_station_names(name, **kw):
    log.info(NAME, datetime_string() + ': ' + _(u'Station names changed'))

### program change ##
def notify_program_change(name, **kw):
    log.info(NAME, datetime_string() + ': ' + _(u'Programs changed'))

### program deleted ###
def notify_program_deleted(name, **kw):
    log.info(NAME, datetime_string() + ': ' + _(u'Program deleted'))

### program toggled ###
def notify_program_toggled(name, **kw):
    log.info(NAME, datetime_string() + ': ' + _(u'Program toggled on or off'))

### program runnow ###
def notify_program_runnow(name, **kw):
    log.info(NAME, datetime_string() + ': ' + _(u'Program runnow'))

### zone change ###
def notify_zone_change(name, **kw):
    log.info(NAME, datetime_string() + ': ' + _(u'Zone change'))

### rain ###
def notify_rain_active(name, **kw):
    log.info(NAME, datetime_string() + ': ' + _(u'Rain active'))

### not rain ###
def notify_rain_not_active(name, **kw):
    log.info(NAME, datetime_string() + ': ' + _(u'Rain not active'))    

### master 1 on ###
def notify_master_one_on(name, **kw):
    log.info(NAME, datetime_string() + ': ' + _(u'Master one on'))    

### master 1 off ###
def notify_master_one_off(name, **kw):
    log.info(NAME, datetime_string() + ': ' + _(u'Master one off'))    

### master 2 on ###
def notify_master_two_on(name, **kw):
    log.info(NAME, datetime_string() + ': ' + _(u'Master two on'))    

### master 2 off ###
def notify_master_two_off(name, **kw):
    log.info(NAME, datetime_string() + ': ' + _(u'Master two off'))  

### pressurizer plugin master relay on ###
def notify_pressurizer_master_relay_on(name, **kw):
    log.info(NAME, datetime_string() + ': ' + _(u'Pressurizer plugin master relay on')) 

### pressurizer plugin master relay off ###
def notify_pressurizer_master_relay_off(name, **kw):
    log.info(NAME, datetime_string() + ': ' + _(u'Pressurizer plugin master relay off')) 

### Linux system power off ###
def notify_poweroff(name, **kw):
    log.info(NAME, datetime_string() + ': ' + _(u'Linux system now powering off')) 

### OSPy system update available ###
def notify_ospyupdate(name, **kw):
    log.info(NAME, datetime_string() + ': ' + _(u'OSPy system update available'))

### Stations ON ###
def notify_station_on(name, **kw):
    log.info(NAME, datetime_string() + ': ' + _(u'OSPy stations ON, index: {}').format(kw[u"txt"]))
    #print(u"Messge from {}!: {}".format(name, kw[u"txt"]))

### Stations OFF ###
def notify_station_off(name, **kw):
    log.info(NAME, datetime_string() + ': ' + _(u'OSPy stations OFF, index: {}').format(kw[u"txt"]))
    #print(u"Messge from {}!: {}".format(name, kw[u"txt"]))

### All stations set to OFF ###
def notify_station_clear(name, **kw):
    log.info(NAME, datetime_string() + ': ' + _(u'OSPy all stations OFF'))


################################################################################
# Web pages:                                                                   #
################################################################################

class settings_page(ProtectedPage):
    """Load an html page for entering adjustments."""

    def GET(self):
        return self.plugin_render.signaling_examples(plugin_options, log.events(NAME))

    def POST(self):
        plugin_options.web_update(web.input()) ### update options from web ###

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
