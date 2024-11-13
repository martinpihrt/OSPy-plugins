# -*- coding: utf-8 -*-
__author__ = 'Martin Pihrt' # www.pihrt.com

# System imports
import datetime
import time
from threading import Thread, Event
import traceback
import json
import os
import sys
import subprocess
import web

# Local imports
from ospy.log import log
from ospy.options import options
from ospy.webpages import ProtectedPage
from ospy.helpers import datetime_string
from ospy import helpers
from plugins import PluginOptions, plugin_url, plugin_data_dir

from blinker import signal


NAME = 'Voice Station'
MENU =  _('Package: Voice Station')
LINK = 'settings_page'

plugin_options = PluginOptions(
    NAME,
    {
        'enabled': False,                 # default is OFF
        'volume': 90,                     # master volume %
        'start_hour': 6,                  # voice notification only from 6 
        'stop_hour': 20,                  # to 20 hours
        'on':  [-1]*options.output_count, # song name for station 1-8 if ON
        'off': [-1]*options.output_count, # song name for station 1-8 if OFF
        'sounds': [],                     # a list of all songs names in the plugin data directory
        'sounds_inserted': [],            # date time inserted songs (sorted by last upload)
        'sounds_size': [],                # songs size in bytes
        'core': 1,                        # 0=alsa, 1=pydub
    })

must_stop = False                         # stopping play from webpage

################################################################################
# Main function loop:                                                          #
################################################################################
class VoiceChecker(Thread):
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
        station_on = signal('station_on')
        station_on.connect(notify_station_on)
        station_off = signal('station_off')
        station_off.connect(notify_station_off)

        log.clear(NAME)

        if not plugin_options['enabled']:
            log.info(NAME, _('Voice Station is disabled.'))
        else:
            log.info(NAME, _('Voice Station is enabled.'))

        read_folder()                             # read name from file in data folder and add to plugin_options "sound"

        while not self._stop_event.is_set():
            try: 
                if plugin_options['enabled']:     # plugin is enabled
                    play_voice()
                    self._sleep(1)

            except Exception:
                log.error(NAME, _('Voice Station plug-in') + ':\n' + traceback.format_exc())
                self._sleep(60)

checker = None

################################################################################
# Helper functions:                                                            #
################################################################################

### Stations ON ###
def notify_station_on(name, **kw):
    if plugin_options['enabled']:
        current_time  = datetime.datetime.now()
        try:
            if int(current_time.hour) >= int(plugin_options['start_hour']) and int(current_time.hour) <= int(plugin_options['stop_hour']):
                st_nr = int(kw["txt"])
                log.clear(NAME)
                log.info(NAME, datetime_string() + ': ' + _('Stations {} ON').format(str(st_nr + 1)))
                data = {}
                if len(plugin_options['sounds']) > 0:
                    data['song'] = plugin_options['sounds'][int(plugin_options['on'][st_nr])]
                    path = os.path.join(plugin_data_dir(), data['song'])
                    if os.path.isfile(path):
                        update_song_queue(data) # save song name to song queue
                    else:
                        log.info(NAME, datetime_string() + ': ' + _('File not exists!'))
        except Exception:
            log.error(NAME, _('Voice Station plug-in') + ':\n' + traceback.format_exc())

### Stations OFF ###
def notify_station_off(name, **kw):
    if plugin_options['enabled']:
        current_time  = datetime.datetime.now()
        try:
            if int(current_time.hour) >= int(plugin_options['start_hour']) and int(current_time.hour) <= int(plugin_options['stop_hour']):
                st_nr = int(kw["txt"])
                log.clear(NAME)
                log.info(NAME, datetime_string() + ': ' + _('Stations {} OFF').format(str(st_nr + 1)))
                data = {}
                if len(plugin_options['sounds']) > 0:
                    data['song'] = plugin_options['sounds'][int(plugin_options['off'][st_nr])]
                    path = os.path.join(plugin_data_dir(), data['song'])
                    if os.path.isfile(path):
                        update_song_queue(data) # save song name to song queue
                    else:
                        log.info(NAME, datetime_string() + ': ' + _('File not exists!'))
        except Exception:
            log.error(NAME, _('Voice Station plug-in') + ':\n' + traceback.format_exc())

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

def set_to_default():
    plugin_options.__setitem__('enabled', False)
    plugin_options.__setitem__('volume', 90)
    plugin_options.__setitem__('start_hour', 6)
    plugin_options.__setitem__('stop_hour', 20)
    plugin_options.__setitem__('on', [-1]*options.output_count)
    plugin_options.__setitem__('off', [-1]*options.output_count)
    plugin_options.__setitem__('sounds', [])
    plugin_options.__setitem__('sounds_inserted', [])
    plugin_options.__setitem__('sounds_size', [])
    log.clear(NAME)
    log.info(NAME, _('Voice Station plug-in has any error, clear plugin settings to default.'))
    read_folder()

### Run any cmd ###
def run_command(cmd):
    try:
        proc = subprocess.Popen(
        cmd,
        stderr=subprocess.STDOUT, # merge stdout and stderr
        stdout=subprocess.PIPE,
        shell=True)
        output = proc.communicate()[0].decode('utf-8')
        log.info(NAME, output)

    except Exception:
        log.error(NAME, _('Voice Station plug-in') + ':\n' + traceback.format_exc())

### Read all songs in folder ###
def read_folder():
    try:
        import os
        import time

        dir_name =  plugin_data_dir() + '/'
        # Get list of all files only in the given directory
        list_of_files = filter( lambda x: os.path.isfile(os.path.join(dir_name, x)), os.listdir(dir_name) )
        # Sort list of files based on last modification time in ascending order
        list_of_files = sorted( list_of_files, key = lambda x: os.path.getmtime(os.path.join(dir_name, x)))
        # Along with last modification time of file
        e = []
        f = []
        g = []

        for file_name in list_of_files:
            file_path = os.path.join(dir_name, file_name)
            timestamp_str = time.strftime('%d/%m/%Y - %H:%M:%S', time.gmtime(os.path.getmtime(file_path)))
            size = os.path.getsize(file_path)
            e.append(timestamp_str)
            f.append(file_name)
            g.append(round(size, 2))

        plugin_options.__setitem__('sounds_inserted', e)
        plugin_options.__setitem__('sounds', f)
        plugin_options.__setitem__('sounds_size', g)

    except Exception:
        log.error(NAME, _('Voice Station plug-in') + ':\n' + traceback.format_exc())

### Read song queue from json file ###
def read_song_queue():
    try:
        with open(os.path.join(plugin_data_dir(), 'json', 'song_queue.json')) as song_queue:
            return json.load(song_queue)
    except IOError:
        return []

### Write song queue to json file ###
def write_song_queue(json_data):
    try:
        _dir = os.path.join(plugin_data_dir(), 'json') 
        if not os.path.exists(_dir):
            os.makedirs(_dir)
        with open(os.path.join(plugin_data_dir(), 'json', 'song_queue.json'), 'w') as song_queue:
            json.dump(json_data, song_queue)
    except Exception:
        log.error(NAME, _('Voice Station plug-in') + ':\n' + traceback.format_exc())

### Update song queue in json file ### 
def update_song_queue(data):
    try:                                 # exists file: saved_song_queue.json?
        song_queue = read_song_queue()
    except:                              # no! create empty file
        _dir = os.path.join(plugin_data_dir(), 'json') 
        if not os.path.exists(_dir):
            os.makedirs(_dir)
        write_song_queue([])
        song_queue = read_song_queue()

    song_queue.insert(0, data)
    write_song_queue(song_queue)

### Convert percent to db
def set_volume(audio, percent):
    import math
    dB_change = 20 * math.log10(percent / 100.0)
    return audio.apply_gain(dB_change)

### Play a song ###
def play_voice():
    global must_stop
    try:
        if plugin_options['core'] == 0:
            from pygame import mixer
        if plugin_options['core'] == 1:
            from .pydub.audio_segment import AudioSegment
            from .pydub.playback import play

        try:                                    # exists file: song_queue.json?
            song_queue = read_song_queue()      # read from file
        except:                                 # no! create empty file
            write_song_queue([])                # create empty file
            song_queue = read_song_queue()      # read from file

        song = ''
        if len(song_queue) > 0:                 # if there is something in json
            song = song_queue[0]['song']
            path = os.path.join(plugin_data_dir(), song)
            if os.path.isfile(path):
                if plugin_options['core'] == 0:
                    mixer.init()
                    if mixer.music.get_busy() == False:
                        log.info(NAME, datetime_string() + ': ' + _('Songs in queue {}').format(len(song_queue)))
                        for i in range(0, len(song_queue)):
                            log.info(NAME, _('Nr. {} -> {}').format(str(i+1), song_queue[i]['song']))
                        log.info(NAME, datetime_string() + ': ' + _('Loading: {}').format(song))
                        mixer.music.load(path)
                        mixer.music.set_volume(1.0)  # 0.0 min to 1.0 max 
                        log.info(NAME, datetime_string() + ': ' + _('Set master volume to {}%').format(str(plugin_options['volume'])))
                        try:
                            cmd = ["amixer", "sset", "PCM,0", "{}%".format(plugin_options['volume'])]
                            run_command(cmd)
                        except:
                            cmd = ["amixer", "sset", "Master", "{}%".format(plugin_options['volume'])]
                            run_command(cmd)
                        mixer.music.play()
                        log.info(NAME, datetime_string() + ': ' + _('Playing.'))

                if plugin_options['core'] == 1:
                    log.info(NAME, datetime_string() + ': ' + _('Songs in queue {}').format(len(song_queue)))
                    for i in range(0, len(song_queue)):
                        log.info(NAME, _('Nr. {} -> {}').format(str(i+1), song_queue[i]['song']))
                    log.info(NAME, datetime_string() + ': ' + _('Loading: {}').format(song))
                    log.info(NAME, datetime_string() + ': ' + _('Set master volume to {}%').format(str(plugin_options['volume'])))          
                    try:
                        #song = AudioSegment.from_mp3(path)
                        song = AudioSegment.from_file(path, format="mp3")
                    except:
                        #song = AudioSegment.from_wav(path)
                        song = AudioSegment.from_file(path, format="wav")
                    song = set_volume(song, plugin_options['volume'])
                    play(song)
                    log.info(NAME, datetime_string() + ': ' + _('Playing.'))
            else:
                del song_queue[0]
                write_song_queue(song_queue)

            if plugin_options['core'] == 0:
                while mixer.music.get_busy() == True and not must_stop:
                    continue 
                mixer.music.stop()

            log.info(NAME, datetime_string() + ': ' + _('Stopping.'))
            del song_queue[0]                   # delete song queue in file
            write_song_queue(song_queue)        # save to file after deleting an item
            must_stop = False

    except Exception:
        log.error(NAME, _('Voice Station plug-in') + ':\n' + traceback.format_exc())


################################################################################
# Web pages:                                                                   #
################################################################################
class settings_page(ProtectedPage):
    """Load an html page for entering voice station adjustments"""

    def GET(self):
        global must_stop
        qdict = web.input()

        if checker is not None:
            stop = helpers.get_input(qdict, 'stop', False, lambda x: True)
            clear = helpers.get_input(qdict, 'clear', False, lambda x: True)

            if 'test' in qdict:
                command = -1
                data = {}
                if 'state' in qdict and int(qdict['state']) == 1:
                    command = plugin_options['on'][int(qdict['test'])]
                if 'state' in qdict and int(qdict['state']) == 0:
                    command = plugin_options['off'][int(qdict['test'])]

                if len(plugin_options['sounds']) > 0 and command != -1:
                    data['song'] = plugin_options['sounds'][command]
                    path = os.path.join(plugin_data_dir(), data['song'])
                    if os.path.isfile(path):
                        log.info(NAME, datetime_string() + ': ' + _('Button test, song {}.').format(data['song']))
                        update_song_queue(data) # save song name to song queue
                    else:
                        log.info(NAME, datetime_string() + ': ' + _('File not exists!'))
                else:
                    log.info(NAME, datetime_string() + ': ' + _('File not exists!'))

            if stop:
                must_stop = True
                log.info(NAME, datetime_string() + ': ' + _('Button Stop.'))

            if clear:
                must_stop = True
                song_queue = read_song_queue()
                while len(song_queue) > 0:
                    song_queue = read_song_queue()
                    del song_queue[0]
                    write_song_queue(song_queue)
                log.clear(NAME)
                log.info(NAME, datetime_string() + ': ' + _('Button clear playlist.'))

        try:
            return self.plugin_render.voice_station(plugin_options, log.events(NAME))
        except Exception:
            log.error(NAME, _('Voice Station plug-in') + ':\n' + traceback.format_exc())
            set_to_default()
            return self.plugin_render.voice_station(plugin_options, log.events(NAME))

    def POST(self):
        qdict = web.input()
        try:
            if 'enabled' in qdict:
                if qdict['enabled']=='on':
                    plugin_options.__setitem__('enabled', True)
            else:
                plugin_options.__setitem__('enabled', False)

            if 'volume' in qdict:
                plugin_options.__setitem__('volume', qdict['volume'])

            if 'core' in qdict:
                plugin_options.__setitem__('core', qdict['core'])

            if 'start_hour' in qdict:
                plugin_options.__setitem__('start_hour', qdict['start_hour'])

            if 'stop_hour' in qdict:
                plugin_options.__setitem__('stop_hour', qdict['stop_hour'])

            commands = {'on': [], 'off': []} 
            for i in range(0, options.output_count):
                if 'con'+str(i) in qdict:
                    commands['on'].append(int(qdict['con'+str(i)]))
                else:
                    commands['on'].append(-1)
                if 'coff'+str(i) in qdict: 
                    commands['off'].append(int(qdict['coff'+str(i)]))
                else:
                    commands['off'].append(-1)

            plugin_options.__setitem__('on', commands['on'])
            plugin_options.__setitem__('off', commands['off'])

            if checker is not None:
                checker.update()

        except Exception:
            log.error(NAME, _('Voice Station plug-in') + ':\n' + traceback.format_exc())

        raise web.seeother(plugin_url(settings_page), True)


class upload_page(ProtectedPage):

    def GET(self):
        return self.plugin_render.voice_station(plugin_options, 'none')

    def POST(self):
        qdict = web.input(myfile={})
        errorCode = qdict.get('errorCode', 'none')

        #web.debug(qdict['myfile'].filename)    # This is the filename
        #web.debug(qdict['myfile'].value)       # This is the file contents
        #web.debug(qdict['myfile'].file.read()) # Or use a file(-like) object

        try:
            fname = qdict['myfile'].filename
            upload_type = fname[-4:len(fname)]
            types = ['.mp3','.wav']
            if upload_type not in types:        # check file type is ok
                log.info(NAME, datetime_string() + ': ' + _('Error. File must be in mp3 or wav format!'))
                errorCode = qdict.get('errorCode', 'Etype')
                return self.plugin_render.voice_station_sounds(plugin_options, errorCode)
            else:
                fout = open(os.path.join(plugin_data_dir(), fname),'wb') # ASCI_convert(fname)
                fout.write(qdict['myfile'].file.read()) 
                fout.close() 
                log.info(NAME, datetime_string() + ': ' + _('Uploading file sucesfully.'))
                errorCode = qdict.get('errorCode', 'UplOK')
                read_folder()
                return self.plugin_render.voice_station_sounds(plugin_options, errorCode)

        except Exception:
                log.error(NAME, _('Voice Station plug-in') + ':\n' + traceback.format_exc())
                errorCode = qdict.get('errorCode', 'Eupl')
                return self.plugin_render.voice_station_sounds(plugin_options, errorCode)

        raise web.seeother(plugin_url(sound_page), True)


class help_page(ProtectedPage):
    """Load an html page for help page."""

    def GET(self):
        return self.plugin_render.voice_station_help()

class sound_page(ProtectedPage):
    """Load an html page for sound page."""

    def GET(self):
        qdict = web.input()
        errorCode = qdict.get('errorCode', 'none')

        if 'delete' in qdict:
            delete = qdict['delete']
            if len(plugin_options['sounds']) > 0:
                del_file = os.path.join(plugin_data_dir(), plugin_options['sounds'][int(delete)] )
                if os.path.isfile(del_file):
                    os.remove(del_file)
                    errorCode = qdict.get('errorCode', 'DelOK')
                    read_folder()
                    log.debug(NAME, datetime_string() + ': ' + _('Deleting file has sucesfully.'))
                else:
                    errorCode = qdict.get('errorCode', 'DelNex')
                    log.error(NAME, datetime_string() + ': ' + _('File for deleting not found!'))

        return self.plugin_render.voice_station_sounds(plugin_options, errorCode)


class settings_json(ProtectedPage):
    """Returns plugin settings in JSON format"""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        return json.dumps(plugin_options)