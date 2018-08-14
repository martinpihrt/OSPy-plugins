#!/usr/bin/env python
# -*- coding: utf-8 -*-
__author__ = 'Martin Pihrt'

import json
import time
import traceback
import web

import i18n

from blinker import signal ### for this example ###

from ospy.helpers import datetime_string 
from ospy.log import log
from threading import Thread, Event
from plugins import PluginOptions, plugin_url
from ospy.webpages import ProtectedPage

NAME = 'Signaling Examples'  ### name for plugin in plugin manager ###
LINK = 'settings_page'       ### link for page in plugin manager ###
 
plugin_options = PluginOptions(
    NAME,
    {'use_signaling': False        ### for example ###
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

class settings_json(ProtectedPage):            ### return plugin_options as JSON data ###
    """Returns plugin settings in JSON format."""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        return json.dumps(plugin_options)
