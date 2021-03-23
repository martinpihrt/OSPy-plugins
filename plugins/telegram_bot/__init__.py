from __future__ import print_function
# -*- coding: utf-8 -*-
__author__ = 'Martin Pihrt'

import json
import time
import datetime
import sys
import traceback
import os
import subprocess
from threading import Thread, Event

import web

from ospy.log import log
from plugins import PluginOptions, plugin_url, plugin_data_dir
from ospy.webpages import ProtectedPage
from ospy.helpers import get_rpi_revision
from ospy.helpers import datetime_string
from ospy import helpers, options

from ospy.webpages import showInFooter # Enable plugin to display readings in UI footer

NAME = 'Telegram Bot'
MENU =  _(u'Package: Telegram Bot')
LINK = 'settings_page'

plugin_options = PluginOptions(
    NAME,
    {'use_plugin': False, 
     'botToken': '',
     'botAccessKey': '',
     'zoneChange': False,
     'stationScheduled': False,
     'info_cmd': u'info',
     'enable_cmd': u'enable',
     'disable_cmd': u'disable',
     'runOnce_cmd': u'runOnce',
     'currentChats': [] 
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
        self.bot = None
        self._currentTxt = ''
        self._latest_message_id = 0

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
        telegram_ftr = showInFooter()                         # instantiate class to enable data in footer
        telegram_ftr.button = "telegram_bot/settings"         # button redirect on footer
        telegram_ftr.label =  _(u'Telegram Bot')              # label on footer
        
        telegram_bad_import_test = False

        try:
            import telegram
        except:
            telegram_bad_import_test = True
            pass

        if telegram_bad_import_test:
            log.clear(NAME)
            log.error(NAME, _(u'Telegram not found, installing. Please wait...'))
            # https://pypi.org/project/python-telegram-bot/2.4/
            cmd = "sudo pip install python-telegram-bot==2.4"       # python 2.7 end telegram support
            #cmd = "sudo pip install python-telegram-bot --upgrade" # python 3+
            proc = subprocess.Popen(cmd,stderr=subprocess.STDOUT,stdout=subprocess.PIPE,shell=True)
            output = proc.communicate()[0]
            log.debug(NAME, u'{}'.format(output))
        
        try:
            import telegram
        except:
            telegram_bad_import_test = True
            pass

        try:
            # https://www.toptal.com/python/telegram-bot-tutorial-python
            if plugin_options['use_plugin'] and plugin_options['botToken'] != "" and not telegram_bad_import_test:
                log.clear(NAME)
                self._currentChats = plugin_options['currentChats']
                self.bot = telegram.Bot(token = plugin_options['botToken'])
                log.debug(NAME, u'{}'.format(self.bot.getMe()))  
        except Exception:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            err_string = u"".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
            log.error(NAME, _(u'Telegram Bot plug-in') + ':\n' + err_string)

        while not self._stop.is_set() and self.bot is not None:
            try:
                updates = self.bot.getUpdates()
                if updates:
                    log.clear(NAME)
                    for update in updates:
                        if update.message:
                            message = update.message
                        else:
                            message = None
  
                        if message is not None:
                            print(message)

                self._sleep(2)
 
            except Exception:
                exc_type, exc_value, exc_traceback = sys.exc_info()
                err_string = u"".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
                log.error(NAME, _(u'Telegram Bot plug-in') + ':\n' + err_string) 
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
        return self.plugin_render.telegram_bot(plugin_options, log.events(NAME))

    def POST(self):
        global sender
        plugin_options.web_update(web.input())

        if sender is not None:
            sender.update()                
        raise web.seeother(plugin_url(settings_page), True)

class help_page(ProtectedPage):
    """Load an html page for help"""

    def GET(self):
        return self.plugin_render.telegram_bot_help()


class settings_json(ProtectedPage):
    """Returns plugin settings in JSON format."""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        return json.dumps(plugin_options)