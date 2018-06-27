# !/usr/bin/env python
# -*- coding: utf-8 -*-
__author__ = 'Martin Pihrt' # www.pihrt.com

# System imports
import datetime
import time
from threading import Thread, Event
import traceback
import json
import os
import subprocess
import web

# Local imports
from ospy.log import log
from ospy.options import options
from ospy.options import rain_blocks
from ospy.inputs import inputs
from ospy.programs import programs
from ospy.stations import stations
from ospy.webpages import ProtectedPage
from plugins import PluginOptions, plugin_url

import i18n

NAME = 'Voice Notification'
LINK = 'settings_page'

plugin_options = PluginOptions(
    NAME,
    {
        'enabled': False,               # default is OFF
        'voice_start_station': False,   # start message before turning on the station
        'pre_time': 5,                  # sound is played 5 second before turning on the station
        'repeating': 1,                 # how many times to repeat the same message
        'volume': 80,                   # master volume 80%
        'start_hour': 7,                # voice notification only from 7 
        'stop_hour': 20                 # to 20 hours 
    })


################################################################################
# Main function loop:                                                          #
################################################################################
class VoiceChecker(Thread):
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
        log.clear(NAME)
      
        if not plugin_options['enabled']:
           log.info(NAME, _('Voice notification is disabled.'))
        else:
           log.info(NAME, _('Voice notification is enabled.'))
 
        once_test = True  # for test installing pygame
        play = False      # for enabling play
        last_play = False # for disabling nonstop playing
   
        while not self._stop.is_set():
            try: 
                if plugin_options['enabled']:   # plugin is enabled
                   try:
                      from pygame import mixer  # https://www.pygame.org/docs/ref/music.html
                     
                   except ImportError:
                      if once_test:             # only once instalation 
                         log.clear(NAME)
                         log.info(NAME, _('Pygame is not installed.'))
                         log.info(NAME, _('Please wait installing pygame...'))
                         cmd = "sudo apt-get install python-pygame -y"
                         run_command(self, cmd)
                         once_test = False
                         log.info(NAME, _('Pygame is now installed.')) 

                   if plugin_options['voice_start_station']: # start notifications

                      current_time = datetime.datetime.now()
                      pre_datetime = current_time - datetime.timedelta(seconds=int(plugin_options['pre_time']))

                      if current_time.hour >= plugin_options['start_hour'] and current_time.hour <= plugin_options['stop_hour']: # play notifications only from xx hour to yy hour

                         play = False 
                                                 
                         rain = not options.manual_mode and (rain_blocks.block_end() > datetime.datetime.now() or inputs.rain_sensed())
                         active = log.active_runs()
                         

                         #for entry in active:
                         #   ignore_rain = stations.get(entry['station']).ignore_rain
                         #   if entry['start'] > pre_datetime  and (not rain or ignore_rain) and not entry['blocked']:
                         #      play = True
                                   
 
                         if play != last_play:
                            last_play = play 
                         
                            if last_play: 
                               log.clear(NAME) 
                               play_voice(self, "voice.mp3") # play voice in folder
                               while mixer.music.get_busy() == True:
                                 continue
                               self._sleep(2)

                               if plugin_options['repeating'] == 2:
                                 log.info(NAME, _('Repeating playing nr. 2...')) 
                                 play_voice(self, "voice.mp3") # play voice in folder
                                 while mixer.music.get_busy() == True:
                                   continue
                               self._sleep(2)

                               if plugin_options['repeating'] == 3:
                                 log.info(NAME, _('Repeating playing nr. 3...')) 
                                 play_voice(self, "voice.mp3") # play voice in folder
                                 while mixer.music.get_busy() == True:
                                   continue

                               mixer.music.stop()
                               log.info(NAME, _('Stopping...'))
     
                                   
            except Exception:
                log.error(NAME, _('Voice Notification plug-in') + ':\n' + traceback.format_exc())
                self._sleep(60)


checker = None


################################################################################
# Helper functions:                                                            #
################################################################################
  
def start():
    global checker
    if checker is None:
        checker = VoiceChecker()


def stop():
    global checker
    if checker is not None:
        checker.stop()
        checker.join()
        checker = None


def run_command(self, cmd):
    """run command"""
    proc = subprocess.Popen(
    cmd,
    stderr=subprocess.STDOUT, # merge stdout and stderr
    stdout=subprocess.PIPE,
    shell=True)
    output = proc.communicate()[0]
    log.info(NAME, output) 


def play_voice(self, song):
    """play song"""
    from pygame import mixer

    mixer.init()
    log.info(NAME, _('Loading...')) 
    mixer.music.load(os.path.join("/home/pi/OSPy/plugins/voice_notification/static/mp3", song))
    log.info(NAME, _('Set pygame volume to 1.0'))
    mixer.music.set_volume(1.0)  # 0.0 min to 1.0 max 
    log.info(NAME, _('Set master volume to') + ' ' + str(plugin_options['volume']) + '%')
    cmd = "sudo amixer  sset PCM,0 " + str(plugin_options['volume']) + "%"
    run_command(self, cmd)
    log.info(NAME, _('Playing...'))  
    mixer.music.play()
       

################################################################################
# Web pages:                                                                   #
################################################################################
class settings_page(ProtectedPage):
    """Load an html page for entering voice notification adjustments"""

    def GET(self):
        return self.plugin_render.voice_notification(plugin_options, log.events(NAME))

    def POST(self):
        plugin_options.web_update(web.input())
        if checker is not None:
            checker.update()
        raise web.seeother(plugin_url(settings_page), True)


class upload_page(ProtectedPage):
    """Upload mp3 file to static/mp3/xxx"""

    def POST(self):
# todo upload mp3 file  
        raise web.seeother(plugin_url(settings_page), True)


class settings_json(ProtectedPage):
    """Returns plugin settings in JSON format"""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        return json.dumps(plugin_options)
