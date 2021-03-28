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
from ospy import helpers
from ospy.options import options
from ospy.stations import stations
from ospy.runonce import run_once
from ospy.programs import programs

from blinker import signal

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
     'help_cmd': _(u'help'),     
     'info_cmd': _(u'info'),
     'enable_cmd': _(u'enable'),
     'disable_cmd': _(u'disable'),
     'runOnce_cmd': _(u'runOnce'),
     'stop_cmd': _(u'stop'),
     'currentChats': [],
     'lastChatDate': [],
     'use_footer': True
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
        self._currentChats = []
        self._lastMsgID = 0
        self._lastChatDate = []
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

    def _botCmd_start_chat(self, bot, update):
        txt= _(u'Hi! I am a Bot to interface with {}. /{}').format(options.name, plugin_options['help_cmd'])
        txt= unicode(txt).encode('utf-8')
        bot.sendMessage(update.message.chat.id, text=txt)

    def _botCmd_subscribe(self, bot, update):
        chats = self._currentChats
        txt=''
        if update.message.chat.id not in chats:
            chats.append(update.message.chat.id)
            self._currentChats = chats
            plugin_options['currentChats'] = chats
            txt= _(u'Hi! you are now added to the {} announcement.').format(options.name),
            txt= unicode(txt).encode('utf-8')
            bot.sendMessage(update.message.chat.id, text=txt)
            log.info(NAME, txt)
        else:
            txt= _(u'Sorry, please enter the correct AccessKey!')
            txt= unicode(txt).encode('utf-8')
            bot.sendMessage(update.message.chat.id, text=txt)
            log.info(NAME, txt)

    def _echo(self, bot, update):
        txt= _(u'You write: {}').format(update.message.text)
        txt= unicode(txt).encode('utf-8')
        bot.sendMessage(update.message.chat.id, text=txt)

    def _announce(self, txt):
        bot = self.bot
        for chat_id in self._currentChats:
            txt= unicode(txt).encode('utf-8')
            try:
                bot.sendMessage(chat_id, text=txt)
            except:
                pass    

    def _botCmd_help(self, bot, update):
        chat_id = update.message.chat.id
        if chat_id in self._currentChats:
            txt = _(u'Help: /{}\n Info Command: /{}\n Enable Command: /{}\n Disable Command: /{}\n Stop Command: /{}\n Run Once Command: /{}\n (use program number as argument).\n /subscribe Subscribe to the Announcement list, need an access Key.').format(
                plugin_options['help_cmd'],
                plugin_options['info_cmd'],
                plugin_options['enable_cmd'],
                plugin_options['disable_cmd'],
                plugin_options['stop_cmd'],
                plugin_options['runOnce_cmd']
            )
        else:
            txt = _(u'Sorry I can not do that.')
        txt= unicode(txt).encode('utf-8')
        bot.sendMessage(chat_id, text=txt)

    def _botCmd_info(self, bot, update):
        chat_id = update.message.chat.id
        if chat_id in self._currentChats:
            txt =  _(u'Info from {}\n').format(options.name)
            for station in stations.get():
                txt += _(u'Station: {} State: ').format(station.name)
                if station.active:
                    txt += _(u'ON') + u' ('
                    if(station.remaining_seconds == -1):
                        txt += _(u'Forever') + u')'
                    else:    
                        txt += _(u'{}').format(str(int(station.remaining_seconds))) + u')'
                else:
                    txt += _(u'OFF')
                txt += '\n'    
            txt += _(u'Scheduler is {}.\n').format( _(u'enabled') if options.scheduler_enabled else _(u'disabled'))    
        else:
            txt = _(u'Sorry I can not do that.')

        txt = unicode(txt).encode('utf-8')
        bot.sendMessage(chat_id, text=txt)

    def _botCmd_enable(self, bot, update):                    # msg for switch scheduler to on
        chat_id = update.message.chat.id
        if chat_id in self._currentChats:
            txt = _(u'{} System - scheduler ON.').format(options.name)
            options.scheduler_enabled = True 
        else:
            txt = _(u'Sorry I can not do that.')
        txt = unicode(txt).encode('utf-8')    
        bot.sendMessage(chat_id, text=txt)

    def _botCmd_disable(self, bot, update):                   # msg for switch scheduler to off
        chat_id = update.message.chat.id
        if chat_id in self._currentChats:
            txt = _(u'{} System - scheduler OFF.').format(options.name)
            options.scheduler_enabled = False 
        else:
            txt = _(u'Sorry I can not do that.')
        txt = unicode(txt).encode('utf-8')    
        bot.sendMessage(chat_id, text=txt)

    def _botCmd_stop(self, bot, update):                      # msg for stop all station and disable scheduler
        chat_id = update.message.chat.id
        if chat_id in self._currentChats:
            txt = _(u'{} System - scheduler OFF. All stations OFF.').format(options.name)
            programs.run_now_program = None
            run_once.clear()
            log.finish_run(None)
            stations.clear() 
        else:
            txt = _(u'Sorry I can not do that.')
        txt = unicode(txt).encode('utf-8')    
        bot.sendMessage(chat_id, text=txt)        

    def _botCmd_runOnce(self, bot, update, args):             # run-now program xx
        chat_id = update.message.chat.id
        if chat_id in self._currentChats:
            txt = _(u'{} RunOnce: program {}.').format(options.name, args)
            for program in programs.get():
                if (program.index == int(args-1)):   
                    options.manual_mode = False   
                    log.finish_run(None)
                    stations.clear()    
                    programs.run_now(program.index)
                    break       
                program.index+1
        else:
            txt = _(u'Sorry I can not do that.')
        txt = unicode(txt).encode('utf-8')    
        bot.sendMessage(chat_id, text=txt)

    def run(self):
        tempText = ''
        if plugin_options['use_footer']:
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
            log.info(NAME, u'{}'.format(output))
        
        try:
            import telegram
        except:
            telegram_bad_import_test = True
            pass

        try:
            # https://www.toptal.com/python/telegram-bot-tutorial-python
            if plugin_options['use_plugin'] and plugin_options['botToken'] != "" and plugin_options['botAccessKey'] != "" and not telegram_bad_import_test:
                log.clear(NAME)
                self._currentChats = plugin_options['currentChats']
                self._lastChatDate = plugin_options['lastChatDate']

                self.bot = telegram.Bot(token = plugin_options['botToken'])
                getbot = self.bot.getMe()
                info_id = getbot.id
                info_username = getbot.username
                info_first_name = getbot.first_name
                log.info(NAME, _(u'Hi connect is OK my ID: {}, User Name: {}, First Name: {}.').format(info_id, info_username, info_first_name))
                
                if plugin_options['use_footer']:
                    tempText = _(u'Hi connect is OK my Name: {}.').format(info_username)
                    telegram_ftr.val = tempText.encode('utf8')

                self._announce(_(u'Bot on {} has just started!').format(options.name))

        except Exception:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            err_string = u"".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
            log.error(NAME, _(u'Telegram Bot plug-in') + ':\n' + err_string)
            if plugin_options['use_footer']:
                tempText = _(u'Telegram Bot has error, check in plugin status!')
                telegram_ftr.val = tempText.encode('utf8')

        zone_change = signal('zone_change')
        zone_change.connect(notify_zone_change)

        while not self._stop.is_set() and self.bot is not None:
            try:
                updates = self.bot.getUpdates()
                if updates:
                    for update in updates:
                        if update.message:
                            message = update.message
                        else:
                            message = None
  
                        if message is not None:
                            chat_date = message.date      # time stamp
                            chat_id = message.chat.id     # chat ID
                            msg_id = message.message_id   # msg ID
                            msg_text = message.text       # msg text
                            msg_from = u'{} {}'.format(message.chat.first_name, message.chat.last_name) # from user: first name last name

                            if msg_id != self._lastMsgID and chat_date not in self._lastChatDate:
                                self._lastMsgID = msg_id
                                self._lastChatDate.append(chat_date)
                                plugin_options['lastChatDate'] = self._lastChatDate

                                log.clear(NAME)
                                log.info(NAME, _(u'New message: {} ID: {}.').format(msg_text, msg_id))
                                log.info(NAME, _(u'From: {} ID: {}.').format(msg_from, chat_id))
                                
                                self._echo(self.bot, update)

                                if msg_text == u'/start':
                                    self._botCmd_start_chat(self.bot, update)                                    
                                    tempText = _(u'Last msg: /start')
                                    log.info(NAME, tempText)
                                    #plugin_options['lastChatDate'] = []
                                elif msg_text == u'/{}'.format(plugin_options['help_cmd']):
                                    self._botCmd_help(self.bot, update)
                                    tempText = _(u'Last msg: /{}').format(plugin_options['help_cmd'])
                                    log.info(NAME, tempText)
                                elif msg_text == u'/{}'.format(plugin_options['info_cmd']):
                                    self._botCmd_info(self.bot, update)
                                    tempText = _(u'Last msg: /{}').format(plugin_options['info_cmd'])
                                    log.info(NAME, tempText)
                                elif msg_text == u'/{}'.format(plugin_options['enable_cmd']):
                                    self._botCmd_enable(self.bot, update)
                                    tempText = _(u'Last msg: /{}').format(plugin_options['enable_cmd'])
                                    log.info(NAME, tempText)
                                elif msg_text == u'/{}'.format(plugin_options['disable_cmd']):
                                    self._botCmd_disable(self.bot, update)
                                    tempText = _(u'Last msg: /{}').format(plugin_options['disable_cmd'])
                                    log.info(NAME, tempText)
                                elif msg_text == u'/{}'.format(plugin_options['stop_cmd']):
                                    self._botCmd_stop(self.bot, update)
                                    tempText = _(u'Last msg: /{}').format(plugin_options['stop_cmd'])
                                    log.info(NAME, tempText)                                    
                                elif u'/{}'.format(plugin_options['runOnce_cmd']) in msg_text:
                                    runlen = len(u'/{}'.format(plugin_options['runOnce_cmd']))
                                    pgmid = int(msg_text[runlen:])
                                    args = pgmid
                                    self._botCmd_runOnce(self.bot, update, args)
                                    tempText = _(u'Last msg: /{} arg: {}').format(plugin_options['runOnce_cmd'], args)
                                    log.info(NAME, tempText)
                                elif u'{}'.format(plugin_options['botAccessKey']) in msg_text:
                                    self._botCmd_subscribe(self.bot, update)
                                    tempText = _(u'Last msg: /subscribe')
                                    log.info(NAME, tempText)                                    
                                else:
                                    txt= _(u'Sorry command is not supported!')
                                    txt = unicode(txt).encode('utf-8')
                                    self.bot.sendMessage(update.message.chat.id, text= txt)
                                    log.info(NAME, txt)
                                    tempText = txt
                                
                                if plugin_options['use_footer']:
                                    telegram_ftr.val = tempText.encode('utf8')                                       

                self._sleep(5)
 
            except Exception:
                exc_type, exc_value, exc_traceback = sys.exc_info()
                err_string = u"".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
                log.error(NAME, _(u'Telegram Bot plug-in') + ':\n' + err_string) 
                self._sleep(30)
          
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

def notify_zone_change(name, **kw):
    if plugin_options['zoneChange']:
        txt =  _(u'There has been a Station Change.\n')
        for station in stations.get():
            txt += _(u'Station: {} State: ').format(station.name)
            if station.active:
                txt += _(u'ON') + u' ('
                if(station.remaining_seconds == -1):
                    txt += _(u'Forever') + u')'
                else:    
                    txt += _(u'{}').format(str(int(station.remaining_seconds))) + u')'
            else:
                txt += _(u'OFF')
            txt += '\n'    
        sender._announce(txt)                   

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