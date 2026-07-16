# -*- coding: utf-8 -*-
__author__ = 'Martin Pihrt' # www.pihrt.com

# System imports
import datetime
import time
from threading import Thread, Lock
import traceback
import json
import os
import subprocess
import web

# Local imports
from ospy.log import log
from ospy.options import options
from ospy.webpages import ProtectedPage
from ospy.helpers import datetime_string
from ospy import helpers
from plugins import PluginOptions, plugin_url, plugin_data_dir, get_runtime
from ospy.helpers import verify_csrf

from blinker import signal


NAME = 'Voice Station'
MENU =  _('Package: Voice Station')
LINK = 'settings_page'
MAX_UPLOAD_SIZE = 20 * 1024 * 1024
MAX_QUEUE_ITEMS = 100
COMMAND_TIMEOUT = 60
ERROR_LOG_THROTTLE = 300

plugin_options = PluginOptions(
    NAME,
    {
        'enabled': False,                 # default is OFF
        'volume': 95,                     # master volume %
        'start_hour': 6,                  # voice notification only from 6 
        'stop_hour': 20,                  # to 20 hours
        'on':  [-1]*options.output_count, # song name for station 1-8 if ON
        'off': [-1]*options.output_count, # song name for station 1-8 if OFF
        'sounds': [],                     # a list of all songs names in the plugin data directory
        'sounds_inserted': [],            # date time inserted songs (sorted by last upload)
        'sounds_size': [],                # songs size in bytes
    })
runtime = get_runtime()
process_lock = Lock()
health_lock = Lock()
active_process = None
health_state = {
    'last_cycle': 0,
    'last_playback': 0,
    'last_station_event': 0,
    'last_error': 0,
    'last_error_message': '',
}


################################################################################
# Main function loop:                                                          #
################################################################################
class VoiceChecker(Thread):
    def __init__(self):
        Thread.__init__(self)
        self.daemon = True
        self._stop_event = runtime.stop_event

        self._sleep_time = 0
        self._last_error_log = 0
        self.start()
        runtime.register_thread(self)

    def stop(self):
        self._stop_event.set()

    def update(self):
        self._sleep_time = 0

    def _sleep(self, secs):
        self._sleep_time = secs
        while self._sleep_time > 0 and not self._stop_event.is_set():
            time.sleep(1)
            self._sleep_time -= 1

    def _log_problem(self, message):
        now = time.time()
        with health_lock:
            health_state['last_error'] = now
            health_state['last_error_message'] = str(message).splitlines()[-1]
        if now - self._last_error_log >= ERROR_LOG_THROTTLE:
            log.error(NAME, message)
            self._last_error_log = now

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

        try:
            while not self._stop_event.is_set():
                try:
                    if plugin_options['enabled']:     # plugin is enabled
                        play_voice()
                    with health_lock:
                        health_state['last_cycle'] = time.time()
                    self._sleep(1)

                except Exception:
                    self._log_problem(_('Voice Station plug-in') + ':\n' + traceback.format_exc())
                    self._sleep(60)
        finally:
            station_on.disconnect(notify_station_on)
            station_off.disconnect(notify_station_off)

checker = None

################################################################################
# Helper functions:                                                            #
################################################################################

### Stations ON ###
def notify_station_on(name, **kw):
    if plugin_options['enabled']:
        current_time  = datetime.datetime.now()
        try:
            normalize_options()
            if int(current_time.hour) >= int(plugin_options['start_hour']) and int(current_time.hour) <= int(plugin_options['stop_hour']):
                st_nr = safe_int(kw.get("txt"), -1)
                if st_nr < 0 or st_nr >= options.output_count:
                    return
                with health_lock:
                    health_state['last_station_event'] = time.time()
                log.clear(NAME)
                log.info(NAME, datetime_string() + ': ' + _('Stations {} ON').format(str(st_nr + 1)))
                data = {}
                if len(plugin_options['sounds']) > 0:
                    sound_index = safe_int(plugin_options['on'][st_nr], -1)
                    if sound_index < 0 or sound_index >= len(plugin_options['sounds']):
                        return
                    data['song'] = plugin_options['sounds'][sound_index]
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
            normalize_options()
            if int(current_time.hour) >= int(plugin_options['start_hour']) and int(current_time.hour) <= int(plugin_options['stop_hour']):
                st_nr = safe_int(kw.get("txt"), -1)
                if st_nr < 0 or st_nr >= options.output_count:
                    return
                with health_lock:
                    health_state['last_station_event'] = time.time()
                log.clear(NAME)
                log.info(NAME, datetime_string() + ': ' + _('Stations {} OFF').format(str(st_nr + 1)))
                data = {}
                if len(plugin_options['sounds']) > 0:
                    sound_index = safe_int(plugin_options['off'][st_nr], -1)
                    if sound_index < 0 or sound_index >= len(plugin_options['sounds']):
                        return
                    data['song'] = plugin_options['sounds'][sound_index]
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
        runtime.request_stop()
        terminate_active_process()
        checker.join(15)
        if not checker.is_alive():
            checker = None


def safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def normalize_options():
    plugin_options['volume'] = max(0, min(100, safe_int(plugin_options.get('volume', 95), 95)))
    plugin_options['start_hour'] = max(0, min(23, safe_int(plugin_options.get('start_hour', 6), 6)))
    plugin_options['stop_hour'] = max(0, min(23, safe_int(plugin_options.get('stop_hour', 20), 20)))
    for key in ('on', 'off'):
        values = list(plugin_options.get(key, []))
        while len(values) < options.output_count:
            values.append(-1)
        plugin_options[key] = values[:options.output_count]

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
        log.debug(NAME, _('Voice Station plug-in') + ':\n' + traceback.format_exc())

### Read song queue from json file ###
def read_song_queue():
    try:
        with open(os.path.join(plugin_data_dir(), 'json', 'song_queue.json')) as song_queue:
            return json.load(song_queue)
    except (IOError, ValueError):
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
    song_queue = song_queue[:MAX_QUEUE_ITEMS]
    write_song_queue(song_queue)


def run_audio_command(command, timeout):
    global active_process
    process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    with process_lock:
        active_process = process
    try:
        deadline = time.time() + timeout
        while process.poll() is None:
            if runtime.stop_event.wait(0.1):
                process.terminate()
                try:
                    process.wait(3)
                except subprocess.TimeoutExpired:
                    process.kill()
                return False
            if time.time() >= deadline:
                process.kill()
                raise subprocess.TimeoutExpired(command, timeout)
        if process.returncode:
            raise subprocess.CalledProcessError(process.returncode, command)
        return True
    finally:
        with process_lock:
            if active_process is process:
                active_process = None


def terminate_active_process():
    with process_lock:
        process = active_process
    if process is not None and process.poll() is None:
        process.terminate()


def play_audio(path):
    read_folder()
    if os.path.exists(path):
        if path.endswith('.wav'):
            log.info(NAME, datetime_string() + ': ' + _('Playing WAV file.'))
            log.info(NAME, datetime_string() + ': ' + _('Set master volume to {}%').format(str(plugin_options['volume'])))
            if not run_audio_command(["/usr/bin/amixer", "sset", "PCM,0", "{}%".format(plugin_options['volume'])], 10):
                return
            cmd = ["aplay", path]
            run_audio_command(cmd, COMMAND_TIMEOUT)
        elif path.endswith('.mp3'):
            wav_path = os.path.splitext(path)[0] + '.wav'
            if not os.path.exists(wav_path):
                log.info(NAME, datetime_string() + ': ' + _('Converting mp3 to wav.'))
                ffmpeg_cmd = ["ffmpeg", "-i", path, wav_path]
                if not run_audio_command(ffmpeg_cmd, COMMAND_TIMEOUT):
                    return
            else:
                log.info(NAME, datetime_string() + ': ' + _('WAV file already exists, skipping conversion.'))

            log.info(NAME, datetime_string() + ': ' + _('Playing WAV file.'))
            log.info(NAME, datetime_string() + ': ' + _('Set master volume to {}%').format(str(plugin_options['volume'])))
            if not run_audio_command(["/usr/bin/amixer", "sset", "PCM,0", "{}%".format(plugin_options['volume'])], 10):
                return
            cmd = ["aplay", wav_path]
            run_audio_command(cmd, COMMAND_TIMEOUT)
        else:
            log.info(NAME, datetime_string() + ': ' + _('File {} not suported.').format(path))
    else:
        log.info(NAME, datetime_string() + ': ' + _('File {} not exist.').format(path))

### Queue songs ###
def play_voice():
    try:
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
                try:
                    log.info(NAME, datetime_string() + ': ' + _('Songs in queue {}').format(len(song_queue)))
                    for i in range(0, len(song_queue)):
                        log.info(NAME, _('Nr. {} -> {}').format(str(i+1), song_queue[i]['song']))
                    log.info(NAME, datetime_string() + ': ' + _('Loading: {}').format(song))
                    play_audio(path)
                except Exception:
                    log.debug(NAME, _('Voice Station plug-in') + ':\n' + traceback.format_exc())
            else:
                del song_queue[0]
                write_song_queue(song_queue)

            log.info(NAME, datetime_string() + ': ' + _('Stopping.'))
            del song_queue[0]                   # delete song queue in file
            write_song_queue(song_queue)        # save to file after deleting an item
            with health_lock:
                health_state['last_playback'] = time.time()

    except Exception:
        log.debug(NAME, _('Voice Station plug-in') + ':\n' + traceback.format_exc())


################################################################################
# Web pages:                                                                   #
################################################################################
class settings_page(ProtectedPage):
    """Load an html page for entering voice station adjustments"""

    def GET(self):
        normalize_options()
        qdict = web.input()

        if checker is not None:
            clear = helpers.get_input(qdict, 'clear', False, lambda x: True)

            if 'test' in qdict:
                verify_csrf(qdict)
                command = -1
                data = {}
                test_index = safe_int(qdict.get('test'), -1)
                if 'state' in qdict and safe_int(qdict['state'], 0) == 1 and 0 <= test_index < len(plugin_options['on']):
                    command = safe_int(plugin_options['on'][test_index], -1)
                if 'state' in qdict and safe_int(qdict['state'], 0) == 0 and 0 <= test_index < len(plugin_options['off']):
                    command = safe_int(plugin_options['off'][test_index], -1)

                if len(plugin_options['sounds']) > 0 and 0 <= command < len(plugin_options['sounds']):
                    data['song'] = plugin_options['sounds'][command]
                    path = os.path.join(plugin_data_dir(), data['song'])
                    if os.path.isfile(path):
                        log.info(NAME, datetime_string() + ': ' + _('Button test, song {}.').format(data['song']))
                        update_song_queue(data) # save song name to song queue
                    else:
                        log.info(NAME, datetime_string() + ': ' + _('File not exists!'))
                else:
                    log.info(NAME, datetime_string() + ': ' + _('File not exists!'))

            if clear:
                verify_csrf(qdict)
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
            return self.plugin_render.voice_station(plugin_options, log.events(NAME))

    def POST(self):
        qdict = web.input()
        verify_csrf(qdict)
        try:
            if 'enabled' in qdict:
                if qdict['enabled']=='on':
                    plugin_options.__setitem__('enabled', True)
            else:
                plugin_options.__setitem__('enabled', False)

            if 'volume' in qdict:
                plugin_options.__setitem__('volume', safe_int(qdict['volume'], 95))

            if 'start_hour' in qdict:
                plugin_options.__setitem__('start_hour', safe_int(qdict['start_hour'], 6))

            if 'stop_hour' in qdict:
                plugin_options.__setitem__('stop_hour', safe_int(qdict['stop_hour'], 20))

            commands = {'on': [], 'off': []} 
            for i in range(0, options.output_count):
                if 'con'+str(i) in qdict:
                    commands['on'].append(safe_int(qdict['con'+str(i)], -1))
                else:
                    commands['on'].append(-1)
                if 'coff'+str(i) in qdict: 
                    commands['off'].append(safe_int(qdict['coff'+str(i)], -1))
                else:
                    commands['off'].append(-1)

            plugin_options.__setitem__('on', commands['on'])
            plugin_options.__setitem__('off', commands['off'])
            normalize_options()

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
        verify_csrf(qdict)
        errorCode = qdict.get('errorCode', 'none')

        #web.debug(qdict['myfile'].filename)    # This is the filename
        #web.debug(qdict['myfile'].value)       # This is the file contents
        #web.debug(qdict['myfile'].file.read()) # Or use a file(-like) object

        try:
            fname = os.path.basename((qdict['myfile'].filename or '').replace('\\', '/'))
            upload_type = os.path.splitext(fname)[1].lower()
            types = ['.mp3','.wav']
            upload_data = qdict['myfile'].file.read(MAX_UPLOAD_SIZE + 1)
            if upload_type not in types or not fname:        # check file type is ok
                log.info(NAME, datetime_string() + ': ' + _('Error. File must be in mp3 or wav format!'))
                errorCode = qdict.get('errorCode', 'Etype')
                return self.plugin_render.voice_station_sounds(plugin_options, errorCode)
            elif len(upload_data) > MAX_UPLOAD_SIZE:
                log.info(NAME, datetime_string() + ': ' + _('Uploaded file is too large.'))
                errorCode = qdict.get('errorCode', 'Eupl')
                return self.plugin_render.voice_station_sounds(plugin_options, errorCode)
            else:
                with open(os.path.join(plugin_data_dir(), fname), 'wb') as fout:
                    fout.write(upload_data)
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
            verify_csrf(qdict)
            delete = safe_int(qdict['delete'], -1)
            if 0 <= delete < len(plugin_options['sounds']):
                del_file = os.path.join(plugin_data_dir(), plugin_options['sounds'][delete])
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


def health():
    """Return a compact status for the OSPy diagnostics page."""
    worker_alive = checker is not None and checker.is_alive()
    with process_lock:
        playing = active_process is not None and active_process.poll() is None
    with health_lock:
        state = dict(health_state)

    details = {
        'worker': _('Running') if worker_alive else _('Stopped'),
        'enabled': bool(plugin_options.get('enabled', False)),
        'sound_files': len(plugin_options.get('sounds', [])),
        'queued_sounds': len(read_song_queue()),
        'playing': playing,
        'last_cycle': state['last_cycle'],
        'last_playback': state['last_playback'],
        'last_station_event': state['last_station_event'],
        'last_error': state['last_error'],
    }
    if state['last_error_message']:
        details['error'] = state['last_error_message']

    if not worker_alive:
        status = 'error'
        summary = _('Voice Station worker is not running.')
    elif not plugin_options.get('enabled', False):
        status = 'unknown'
        summary = _('Voice Station is disabled.')
    elif state['last_error'] and state['last_error'] > state['last_cycle']:
        status = 'warning'
        summary = _('Voice Station reported an error.')
    else:
        status = 'ok'
        summary = _('Voice Station is ready.')
    return {'status': status, 'summary': summary, 'details': details}
