# -*- coding: utf-8 -*-
__author__ = u'Martin Pihrt' # www.pihrt.com

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
from ospy.scheduler import predicted_schedule
from ospy.stations import stations
from ospy.webpages import ProtectedPage
from ospy.helpers import get_input
from plugins import PluginOptions, plugin_url


NAME = 'Voice Notification'
MENU =  _(u'Package: Voice Notification')
LINK = 'settings_page'

MP3_FILE_FOLDER = './plugins/voice_notification/static/mp3'

plugin_options = PluginOptions(
    NAME,
    {
        'enabled': False,               # default is OFF
        'voice_start_station': False,   # start message before turning on the station
        'pre_time': 5,                  # sound is played 5 second before turning on the station
        'repeating': 1,                 # how many times to repeat the same message
        'volume': 95,                   # master volume 95%
        'start_hour': 0,                # voice notification only from 0 
        'stop_hour': 23,                # to 23 hours 
        'skip_stations': [],            # skip voice notification if activated stations xxx
        'vs0': ' ',                     # station 1 has select voice1.mp3, voice2.mp3 max is voice20.mp3 etc...
        'vs1': ' ',
        'vs2': ' ', 
        'vs3': ' ', 
        'vs4': ' ', 
        'vs5': ' ', 
        'vs6': ' ', 
        'vs7': ' ', 
        'vs8': ' ',
        'vs9': ' ',
        'vs10': ' ',
        'vs11': ' ',
        'vs12': ' ',
        'vs13': ' ',
        'vs14': ' ',
        'vs15': ' ',
        'vs16': ' ',
        'vs17': ' ', 
        'vs18': ' ',
        'vs19': ' ',
        'vs20': ' ',
        'vs21': ' ',
        'vs22': ' ', 
        'vs23': ' ', 
        'vs24': ' ', 
        'vs25': ' ', 
        'vs26': ' ', 
        'vs27': ' ', 
        'vs28': ' ',
        'vs29': ' ',
        'vs30': ' ',
        'vs31': ' ',
        'vs32': ' ',
        'vs33': ' ',
        'vs34': ' ',
        'vs35': ' ',
        'vs36': ' ',
        'vs37': ' ', 
        'vs38': ' ',
        'vs39': ' ',
        'vs40': ' ',
        'vs41': ' ',
        'vs42': ' ', 
        'vs43': ' ', 
        'vs44': ' ', 
        'vs45': ' ', 
        'vs46': ' ', 
        'vs47': ' ', 
        'vs48': ' ',
        'vs49': ' ',
        'vs50': ' ',
        'vs51': ' ',
        'vs52': ' ',
        'vs53': ' ',
        'vs54': ' ',
        'vs55': ' ',
        'vs56': ' ',
        'vs57': ' ', 
        'vs58': ' ',
        'vs59': ' ',
        'vs60': ' ',
        'vs61': ' ',
        'vs62': ' ', 
        'vs63': ' ', 
        'vs64': ' ', 
        'vs65': ' ', 
        'vs66': ' ', 
        'vs67': ' ', 
        'vs68': ' ',
        'vs69': ' ',
        'vs70': ' ',
        'vs71': ' ',
        'vs72': ' ',
        'vs73': ' ',
        'vs74': ' ',
        'vs75': ' ',
        'vs76': ' ',
        'vs77': ' ', 
        'vs78': ' ',
        'vs79': ' ',
        'vs80': ' ',
        'vs81': ' ',
        'vs82': ' ', 
        'vs83': ' ', 
        'vs84': ' ', 
        'vs85': ' ', 
        'vs86': ' ', 
        'vs87': ' ', 
        'vs88': ' ',
        'vs89': ' ',
        'vs90': ' ',
        'vs91': ' ',
        'vs92': ' ',
        'vs93': ' ',
        'vs94': ' ',
        'vs95': ' ',
        'vs96': ' ',
        'vs97': ' ', 
        'vs98': ' ',
        'vs99': ' ',
        'vs100': ' ',
        'vs101': ' ',
        'vs102': ' ', 
        'vs103': ' ', 
        'vs104': ' ', 
        'vs105': ' ', 
        'vs106': ' ', 
        'vs107': ' ', 
        'vs108': ' ',
        'vs109': ' ',
        'vs110': ' ',
        'vs111': ' ',
        'vs112': ' ',
        'vs113': ' ',
        'vs114': ' ',
        'vs115': ' ',
        'vs116': ' ',
        'vs117': ' ', 
        'vs118': ' ',
        'vs119': ' ',
        'vs120': ' ',
        'vs121': ' ',
        'vs122': ' ', 
        'vs123': ' ', 
        'vs124': ' ', 
        'vs125': ' ', 
        'vs126': ' ', 
        'vs127': ' ', 
        'vs128': ' '
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
            log.info(NAME, _(u'Voice notification is disabled.'))
        else:
            log.info(NAME, _(u'Voice notification is enabled.'))
 
        once_test = True  # for test installing pygame
        play = False      # for enabling play
        last_play = False # for disabling nonstop playing
        post_song  = ' '  # mp3 song filename for vs0 - vs128 (stations song)
    
        while not self._stop.is_set():
            try: 
                if plugin_options['enabled']:     # plugin is enabled
                    try:
                        from pygame import mixer  # https://www.pygame.org/docs/ref/music.html
                     
                    except ImportError:
                        if once_test:             # only once instalation 
                            log.clear(NAME)
                            log.info(NAME, _(u'Pygame is not installed.'))
                            log.info(NAME, _(u'Please wait installing pygame...'))
                            cmd = "sudo apt-get install python-pygame -y"
                            run_command(cmd)
                            once_test = False
                            log.info(NAME, _(u'Pygame is now installed.')) 

                    current_time  = datetime.datetime.now()
                    user_pre_time = current_time + datetime.timedelta(seconds=int(plugin_options['pre_time']))
                    check_start   = current_time - datetime.timedelta(days=1)
                    check_end     = current_time + datetime.timedelta(days=1)

     
                    if plugin_options['voice_start_station'] and current_time.hour >= plugin_options['start_hour'] and current_time.hour <= plugin_options['stop_hour']: # play notifications only from xx hour to yy hour
                        play = False 
                        post_song  = ' '     
                        stat_run_num = -1   
   
                        schedule = predicted_schedule(check_start, check_end)
                        for entry in schedule:
                            if entry['start'] <= user_pre_time < entry['end']:  # is possible program in this interval?
                                if not entry['blocked']: 
                                    for station_num in plugin_options['skip_stations']:
                                        if entry['station'] == station_num:     # station skiping
                                            log.clear(NAME)
                                            log.info(NAME, _(u'Skiping playing on station') + ': ' + str(entry['station']+1) + '.')   
                                            self._sleep(1)
                                            return # not playing skipping
                                  
                                    rain = not options.manual_mode and (rain_blocks.block_end() > datetime.datetime.now() or inputs.rain_sensed())  
                                    ignore_rain = stations.get(entry['station']).ignore_rain

                                    if not rain or ignore_rain: # if station has ignore rain or not rain
                                        play = True  
                                        stat_run_num = entry['station'] 
                                    
 
                        if play != last_play:
                            last_play = play 

                            if stat_run_num != -1:
                                post_song = plugin_options['vs%d' % stat_run_num]
                                #print post_song
                         
                            if last_play: 
                                log.clear(NAME) 
                                play_voice(self, "voice.mp3") # play voice in folder
                                if post_song != ' ':
                                    play_voice(self, post_song) # play post station voice in folder
                                 
                                self._sleep(2)

                                if plugin_options['repeating'] == 2 or plugin_options['repeating'] == 3:
                                    log.info(NAME, _(u'Repeating playing nr. 2...')) 
                                    play_voice(self, "voice.mp3") # play voice in folder
                                    if post_song != ' ':
                                        play_voice(self, post_song) # play post station voice in folder
                                  
                                self._sleep(2)

                                if plugin_options['repeating'] == 3:
                                    log.info(NAME, _(u'Repeating playing nr. 3...')) 
                                    play_voice(self, "voice.mp3") # play voice in folder
                                    if post_song != ' ':
                                        play_voice(self, post_song) # play post station voice in folder

                self._sleep(1)                   
                                             
            except Exception:
                log.error(NAME, _(u'Voice Notification plug-in') + ':\n' + traceback.format_exc())
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


def run_command(cmd):
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
    try:
        from pygame import mixer

        mixer.init()
        log.info(NAME, _(u'Loading: %s...') % song) 

        patch = (os.path.join(MP3_FILE_FOLDER, song)) # ex: /home/pi/OSPy/plugins/voice_notification/static/mp3/voicexx.mp3
        mixer.music.load(patch)

        #log.info(NAME, _('Set pygame volume to 1.0'))
        mixer.music.set_volume(1.0)  # 0.0 min to 1.0 max 

        log.info(NAME, _(u'Set master volume to') + ' ' + str(plugin_options['volume']) + '%')
        try:
            cmd = ["amixer", "sset", "PCM,0", "{}%".format(plugin_options['volume'])]
            run_command(cmd)
        except:            
            cmd = ["amixer", "sset", "Master", "{}%".format(plugin_options['volume'])]
            run_command(cmd)        

        log.info(NAME, _(u'Playing...'))  
        mixer.music.play()

        while mixer.music.get_busy() == True:
            continue                 
       
        mixer.music.stop()
        log.info(NAME, _(u'Stopping...'))

    except Exception:
        log.error(NAME, _(u'Voice Notification plug-in') + ':\n' + traceback.format_exc())

       

################################################################################
# Web pages:                                                                   #
################################################################################
class settings_page(ProtectedPage):
    """Load an html page for entering voice notification adjustments"""

    def GET(self):
        qdict = web.input()
        read_test = None

        if 'test' in qdict:
            read_test = qdict['test']
   
            tsound = ['voice.mp3', 'voice0.mp3', 'voice1.mp3', 'voice2.mp3', 'voice3.mp3', 'voice4.mp3', 'voice5.mp3', 'voice6.mp3', 'voice7.mp3', 'voice8.mp3', 'voice9.mp3', 'voice10.mp3', 'voice11.mp3', 'voice12.mp3', 'voice13.mp3', 'voice14.mp3', 'voice15.mp3', 'voice16.mp3', 'voice17.mp3', 'voice18.mp3', 'voice19.mp3', 'voice20.mp3']
            if read_test in tsound:
                log.clear(NAME)
                log.info(NAME, _(u'Testing button %s...') % read_test)
                play_voice(self, "%s" % read_test) # play for test

        return self.plugin_render.voice_notification(plugin_options, log.events(NAME))

    def POST(self):
        plugin_options.web_update(web.input(**plugin_options)) #for save multiple select

        if checker is not None:
            checker.update()

        raise web.seeother(plugin_url(settings_page), True) 


class upload_page(ProtectedPage):
    
    def GET(self):
        return self.plugin_render.voice_notification(plugin_options, log.events(NAME))

    def POST(self):
        x = web.input(myfile={})

        #web.debug(x['myfile'].filename)    # This is the filename
        #web.debug(x['myfile'].value)       # This is the file contents
        #web.debug(x['myfile'].file.read()) # Or use a file(-like) object

        try:
            name = ''
            name = x['myfile'].filename
            if name in ('voice.mp3', 'voice0.mp3', 'voice1.mp3', 'voice2.mp3', 'voice3.mp3', 'voice4.mp3', 'voice5.mp3', 'voice6.mp3', 'voice7.mp3', 'voice8.mp3', 'voice9.mp3', 'voice10.mp3', 'voice11.mp3', 'voice12.mp3', 'voice13.mp3', 'voice14.mp3', 'voice15.mp3', 'voice16.mp3', 'voice17.mp3', 'voice18.mp3', 'voice19.mp3', 'voice20.mp3'):
                fout = open(os.path.join(MP3_FILE_FOLDER, name),'w') 
                fout.write(x['myfile'].file.read()) 
                fout.close() 
                log.info(NAME, _(u'Saving MP3 %s file OK.') % name) 

            else:
                log.info(NAME, _(u'Error. MP3 file: %s name is not voice.mp3 or voice0.mp3...voice20.mp3') % name) 
        
        except Exception:
                log.error(NAME, _(u'Voice Notification plug-in') + ':\n' + traceback.format_exc())

        raise web.seeother(plugin_url(settings_page), True)


class help_page(ProtectedPage):
    """Load an html page for help page."""

    def GET(self):
        return self.plugin_render.voice_notification_help()        


class settings_json(ProtectedPage):
    """Returns plugin settings in JSON format"""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        return json.dumps(plugin_options)
