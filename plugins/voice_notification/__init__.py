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
from ospy.helpers import get_input, datetime_string
from plugins import PluginOptions, plugin_url, plugin_data_dir


NAME = 'Voice Notification'
MENU =  _(u'Package: Voice Notification')
LINK = 'settings_page'

plugin_options = PluginOptions(
    NAME,
    {
        'enabled': False,               # default is OFF
        'pre_time': 15,                 # sound is played 5 second before turning on the station
        'repeating': 1,                 # how many times to repeat the same message
        'volume': 95,                   # master volume 95%
        'start_hour': 0,                # voice notification only from 0 
        'stop_hour': 23,                # to 23 hours 
        'skip_stations': [],            # skip voice notification if activated stations xxx
        'on':  [-1]*8,                  # song name for station 1-8 if ON (8 stations is default)
        'sounds': [],                   # a list of all songs names in the plugin data directory
        'sounds_inserted': [],          # date time inserted songs (sorted by last upload)
        'sounds_size': [],              # songs size in bytes
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
        log.clear(NAME)
      
        if not plugin_options['enabled']:
            log.info(NAME, _(u'Voice notification is disabled.'))
        else:
            log.info(NAME, _(u'Voice notification is enabled.'))
 
        read_folder()       # read name from file in data folder and add to plugin_options "sound"
        once_test = True    # for test installing pygame
        is_installed = True # if pygame is installed
        last_station_on = -1
    
        while not self._stop_event.is_set():
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
                            is_installed = False

                    current_time  = datetime.datetime.now()
                    user_pre_time = current_time + datetime.timedelta(seconds=int(plugin_options['pre_time']))
                    check_start   = current_time - datetime.timedelta(days=1)
                    check_end     = current_time + datetime.timedelta(days=1)

                    if int(current_time.hour) >= int(plugin_options['start_hour']) and int(current_time.hour) <= int(plugin_options['stop_hour']) and is_installed: # play notifications only from xx hour to yy hour   
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
                                        stat_num = int(entry['station'])
                                        if len(plugin_options['sounds']) > 0:
                                            log.clear(NAME)
                                            data = {}
                                            data['song'] = plugin_options['sounds'][int(plugin_options['on'][stat_num])]
                                            path = os.path.join(plugin_data_dir(), data['song'])
                                            if os.path.isfile(path):
                                                if last_station_on != stat_num:
                                                    last_station_on = stat_num
                                                    log.info(NAME, _(u'Add song {} to queue.').format(data['song']))
                                                    update_song_queue(data)     # save song name to song queue
                                                    if plugin_options['repeating'] == 2 or plugin_options['repeating'] == 3:
                                                        log.info(NAME, _(u'Add 2. repeating for song.'))
                                                        song_queue = read_song_queue()
                                                        song_queue.insert(1, data)
                                                        write_song_queue(song_queue)
                                                    if plugin_options['repeating'] == 3:
                                                        log.info(NAME, _(u'Add 3. repeating for song.'))
                                                        song_queue = read_song_queue()
                                                        song_queue.insert(2, data)
                                                        write_song_queue(song_queue)
                if is_installed:
                    play_voice()

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
        log.error(NAME, _(u'Voice Notification plug-in') + ':\n' + traceback.format_exc())


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
        log.error(NAME, _(u'Voice Notification plug-in') + ':\n' + traceback.format_exc())

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
        log.error(NAME, _(u'Voice Notification plug-in') + ':\n' + traceback.format_exc())

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

### Play a song ###
def play_voice():
    global must_stop

    try:
        from pygame import mixer

        try:                                    # exists file: song_queue.json?
            song_queue = read_song_queue()      # read from file
        except:                                 # no! create empty file
            write_song_queue([])                # create file
            song_queue = read_song_queue()      # read from file

        song = ''
        if len(song_queue) > 0:                 # if there is something in json
            song = song_queue[0]['song']
            path = os.path.join(plugin_data_dir(), song)
            mixer.init()
            if os.path.isfile(path):
                if mixer.music.get_busy() == False:
                    log.info(NAME, datetime_string() + u': ' + _(u'Songs in queue {}').format(len(song_queue)))
                    for i in range(0, len(song_queue)):
                        log.info(NAME, _(u'Nr. {} -> {}').format(str(i+1), song_queue[i]['song']))
                    log.info(NAME, datetime_string() + u': ' + _(u'Loading: {}').format(song))
                    mixer.music.load(path)
                    mixer.music.set_volume(1.0)  # 0.0 min to 1.0 max 
                    log.info(NAME, datetime_string() + u': ' + _(u'Set master volume to {}%').format(str(plugin_options['volume'])))
                    try:
                        cmd = ["amixer", "sset", "PCM,0", "{}%".format(plugin_options['volume'])]
                        run_command(cmd)
                    except:
                        cmd = ["amixer", "sset", "Master", "{}%".format(plugin_options['volume'])]
                        run_command(cmd)
                    mixer.music.play()
                    log.info(NAME, datetime_string() + u': ' + _(u'Playing.'))
            else:
                del song_queue[0]
                write_song_queue(song_queue)

            while mixer.music.get_busy() == True and not must_stop:
                continue 

            mixer.music.stop()
            log.info(NAME, datetime_string() + u': ' + _(u'Stopping.'))
            del song_queue[0]                   # delete song queue in file
            write_song_queue(song_queue)        # save to file after deleting an item
            must_stop = False

    except Exception:
        log.error(NAME, _(u'Voice Notification plug-in') + ':\n' + traceback.format_exc())


################################################################################
# Web pages:                                                                   #
################################################################################
class settings_page(ProtectedPage):
    """Load an html page for entering voice notification adjustments"""

    def GET(self):
        global must_stop
        qdict = web.input()
    
        if checker is not None:
            stop = get_input(qdict, 'stop', False, lambda x: True)
            clear = get_input(qdict, 'clear', False, lambda x: True)

            if 'test' in qdict:
                command = -1
                data = {}
                if 'state' in qdict and int(qdict['state']) == 1:
                    command = plugin_options['on'][int(qdict['test'])]
                if len(plugin_options['sounds']) > 0 and command != -1:
                    data['song'] = plugin_options['sounds'][command]
                    path = os.path.join(plugin_data_dir(), data['song'])
                    if os.path.isfile(path):
                        log.clear(NAME)
                        log.info(NAME, datetime_string() + u': ' + _(u'Button test, song {}.').format(data['song']))
                        update_song_queue(data) # save song name to song queue
                    else:
                        log.clear(NAME)
                        log.info(NAME, datetime_string() + u': ' + _(u'File not exists!'))
                else:
                    log.clear(NAME)                    
                    log.info(NAME, datetime_string() + u': ' + _(u'File not exists!'))

            if stop:
                must_stop = True
                log.clear(NAME)
                log.info(NAME, datetime_string() + u': ' + _(u'Button Stop.'))
            
            if clear:
                must_stop = True
                song_queue = read_song_queue()
                while len(song_queue) > 0:
                    song_queue = read_song_queue()
                    del song_queue[0]
                    write_song_queue(song_queue)
                log.clear(NAME)
                log.info(NAME, datetime_string() + u': ' + _(u'Button clear playlist.'))


        return self.plugin_render.voice_notification(plugin_options, log.events(NAME))

    def POST(self):
        qdict = web.input(skip_stations=[]) # skip_stations [] for multiple select
        try:
            if 'enabled' in qdict:
                if qdict['enabled']=='on':
                    plugin_options.__setitem__('enabled', True)
            else:
                plugin_options.__setitem__('enabled', False)

            if 'voice_start_station' in qdict:
                plugin_options.__setitem__('voice_start_station', qdict['voice_start_station'])

            if 'pre_time' in qdict:
                plugin_options.__setitem__('pre_time', qdict['pre_time'])

            if 'repeating' in qdict:
                plugin_options.__setitem__('repeating', qdict['repeating'])

            if 'skip_stations' in qdict:
                plugin_options.__setitem__('skip_stations', qdict['skip_stations'])

            if 'volume' in qdict:
                plugin_options.__setitem__('volume', qdict['volume'])

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

            plugin_options.__setitem__('on', commands['on'])

            if checker is not None:
                checker.update()

        except Exception:
            log.error(NAME, _(u'Voice Notification plug-in') + ':\n' + traceback.format_exc())

        raise web.seeother(plugin_url(settings_page), True) 


class upload_page(ProtectedPage):

    def GET(self):
        return self.plugin_render.voice_notification(plugin_options, 'none')

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
                log.info(NAME, datetime_string() + ': ' + _(u'Error. File must be in mp3 or wav format!'))
                errorCode = qdict.get('errorCode', 'Etype')
                return self.plugin_render.voice_notification_sounds(plugin_options, errorCode)
            else:
                fout = open(os.path.join(plugin_data_dir(), fname),'wb') # ASCI_convert(fname)
                fout.write(qdict['myfile'].file.read()) 
                fout.close() 
                log.info(NAME, datetime_string() + ': ' + _(u'Uploading file sucesfully.'))
                errorCode = qdict.get('errorCode', 'UplOK')
                read_folder()
                return self.plugin_render.voice_notification_sounds(plugin_options, errorCode)

        except Exception:
                log.error(NAME, _(u'Voice Station plug-in') + ':\n' + traceback.format_exc())
                errorCode = qdict.get('errorCode', 'Eupl')
                return self.plugin_render.voice_notification_sounds(plugin_options, errorCode)

        raise web.seeother(plugin_url(sound_page), True)


class help_page(ProtectedPage):
    """Load an html page for help page."""

    def GET(self):
        return self.plugin_render.voice_notification_help()

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
                    log.clear(NAME)
                    log.debug(NAME, datetime_string() + ': ' + _(u'Deleting file has sucesfully.'))
                else:
                    errorCode = qdict.get('errorCode', 'DelNex')
                    log.clear(NAME)
                    log.error(NAME, datetime_string() + ': ' + _(u'File for deleting not found!'))

        return self.plugin_render.voice_notification_sounds(plugin_options, errorCode)


class settings_json(ProtectedPage):
    """Returns plugin settings in JSON format"""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        return json.dumps(plugin_options)
