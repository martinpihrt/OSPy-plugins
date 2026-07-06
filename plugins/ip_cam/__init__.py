# -*- coding: utf-8 -*-
__author__ = 'Martin Pihrt'

import json
import time
import datetime
import traceback
import os
from threading import Thread, Event, Lock
from urllib.parse import urljoin, urlparse

import web

from ospy.log import log
from plugins import PluginOptions, plugin_url, plugin_data_dir
from ospy.webpages import ProtectedPage
from ospy.helpers import get_rpi_revision, datetime_string, get_input, verify_csrf
from ospy import helpers
from ospy.options import options

import requests, shutil
from requests.auth import HTTPBasicAuth
import mimetypes

from PIL import Image
from io import BytesIO


NAME = 'IP Cam'
MENU =  _('Package: IP Cam')
LINK = 'settings_page'


plugin_options = PluginOptions(
    NAME,
    {
        'jpg_ip': ['']*options.output_count,       # IP address for jpeg image
        'jpg_que': ['']*options.output_count,      # Query for jpeg image
        'mjpeg_que': ['']*options.output_count,    # Query for mjpeg image        
        'jpg_user': ['']*options.output_count,     # Username for access to jpeg image
        'jpg_pass': ['']*options.output_count,     # Password for access to jpeg image
        'use_jpg': True,                           # first download jpeg from IP address to plugin folder and next show these jpg on webpage
        'use_gif': True,                           # first download jpeg from IP address to plugin folder and next create gif and show these gif on webpage
        'gif_frames': 20,                          # s new gif will be created in 100 seconds (20 frame x 5 sec)
        'download_interval': 5,                     # seconds between camera downloads
        'http_timeout': 15,                         # HTTP timeout in seconds
        'verify_ssl': False,                        # verify HTTPS certificates
        'max_image_kb': 2048,                       # maximum downloaded JPEG size
        'gif_duration': 250,                        # GIF frame duration in ms
     }
)

status_lock = Lock()
camera_status = []


def _ensure_list(name, default=''):
    values = plugin_options[name]
    if not isinstance(values, list):
        values = []
    if len(values) < options.output_count:
        values = values + [default] * (options.output_count - len(values))
    elif len(values) > options.output_count:
        values = values[:options.output_count]
    plugin_options.__setitem__(name, values)
    return values


def _ensure_options():
    for key in ('jpg_ip', 'jpg_que', 'mjpeg_que', 'jpg_user', 'jpg_pass'):
        _ensure_list(key)
    for key, value in {
        'download_interval': 5,
        'http_timeout': 15,
        'verify_ssl': False,
        'max_image_kb': 2048,
        'gif_duration': 250,
    }.items():
        if key not in plugin_options:
            plugin_options.__setitem__(key, value)


def _blank_status(index):
    return {
        'index': index + 1,
        'configured': False,
        'last_download': '',
        'http_status': '',
        'response_ms': '',
        'size': '',
        'resolution': '',
        'success': 0,
        'errors': 0,
        'error': '',
    }


def _ensure_status():
    global camera_status
    with status_lock:
        while len(camera_status) < options.output_count:
            camera_status.append(_blank_status(len(camera_status)))
        if len(camera_status) > options.output_count:
            camera_status = camera_status[:options.output_count]


def _set_camera_status(index, **values):
    _ensure_status()
    with status_lock:
        item = dict(camera_status[index])
        item.update(values)
        camera_status[index] = item


def _camera_statuses():
    _ensure_status()
    with status_lock:
        return [dict(item) for item in camera_status]


def _safe_int(value, default, min_value, max_value):
    try:
        value = int(value)
    except Exception:
        value = default
    return max(min_value, min(max_value, value))


def _camera_configured(index, stream=False):
    query_key = 'mjpeg_que' if stream else 'jpg_que'
    return bool(plugin_options['jpg_ip'][index] and plugin_options[query_key][index])


def _camera_auth(index):
    user = plugin_options['jpg_user'][index]
    password = plugin_options['jpg_pass'][index]
    if user or password:
        return HTTPBasicAuth(user, password)
    return None


def _camera_url(index, stream=False):
    base = (plugin_options['jpg_ip'][index] or '').strip()
    query = (plugin_options['mjpeg_que' if stream else 'jpg_que'][index] or '').strip()
    parsed = urlparse(base)
    if parsed.scheme not in ('http', 'https') or not parsed.netloc:
        raise ValueError(_('IP address and port must start with http:// or https://'))
    query_parsed = urlparse(query)
    if query_parsed.scheme or query_parsed.netloc:
        raise ValueError(_('Camera query must be a relative path, not a full URL.'))
    return urljoin(base.rstrip('/') + '/', query.lstrip('/'))


def _image_info(content):
    try:
        img = Image.open(BytesIO(content))
        return '{}x{}'.format(img.width, img.height)
    except Exception:
        return ''


def _fetch_camera(index, stream=False):
    url = _camera_url(index, stream)
    timeout = _safe_int(plugin_options['http_timeout'], 15, 1, 120)
    verify = bool(plugin_options['verify_ssl'])
    max_bytes = _safe_int(plugin_options['max_image_kb'], 2048, 64, 10240) * 1024
    started = time.time()
    response = requests.get(url, stream=True, verify=verify, auth=_camera_auth(index), timeout=timeout)
    response_ms = int((time.time() - started) * 1000)
    content = b''
    for chunk in response.iter_content(chunk_size=64 * 1024):
        if chunk:
            content += chunk
            if len(content) > max_bytes:
                raise ValueError(_('Downloaded image is larger than configured maximum size.'))
    return response, content, response_ms


def _test_camera_stream(index):
    url = _camera_url(index, stream=True)
    timeout = _safe_int(plugin_options['http_timeout'], 15, 1, 120)
    verify = bool(plugin_options['verify_ssl'])
    started = time.time()
    response = requests.get(url, stream=True, verify=verify, auth=_camera_auth(index), timeout=timeout)
    response_ms = int((time.time() - started) * 1000)
    content = b''
    try:
        for chunk in response.iter_content(chunk_size=64 * 1024):
            if chunk:
                content = chunk
                break
    finally:
        response.close()
    return response, content, response_ms


def _record_camera_result(index, response=None, content=None, response_ms='', error=''):
    current = _camera_statuses()[index]
    values = {
        'configured': _camera_configured(index),
        'last_download': datetime_string(),
        'response_ms': response_ms,
        'error': error,
    }
    if response is not None:
        values['http_status'] = response.status_code
    if content is not None:
        values['size'] = len(content)
        values['resolution'] = _image_info(content)
    if error:
        values['errors'] = current.get('errors', 0) + 1
    else:
        values['success'] = current.get('success', 0) + 1
    _set_camera_status(index, **values)


def _save_snapshot(index, content):
    helpers.mkdir_p(plugin_data_dir())
    img_path = os.path.join(plugin_data_dir(), '{}.jpg'.format(index + 1))
    with open(img_path, 'wb') as fh:
        fh.write(content)
    return img_path


def _delete_cache():
    deleted = 0
    for filename in os.listdir(plugin_data_dir()) if os.path.isdir(plugin_data_dir()) else []:
        path = os.path.join(plugin_data_dir(), filename)
        if os.path.isfile(path) and (filename.endswith('.jpg') or filename.endswith('.gif')):
            os.remove(path)
            deleted += 1
        elif os.path.isdir(path):
            shutil.rmtree(path)
            deleted += 1
    return deleted


_ensure_options()
_ensure_status()


################################################################################
# Main function loop:                                                          #
################################################################################


class Sender(Thread):
    
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
        img_counter = 0
        while not self._stop_event.is_set():
            try:
                if plugin_options['use_jpg']:
                    img_down_state = []
                    for c in range(0, options.output_count):
                        _set_camera_status(c, configured=_camera_configured(c))
                        if _camera_configured(c):
                            try:
                                res, content, response_ms = _fetch_camera(c)
                                if res.status_code == 200:
                                    _save_snapshot(c, content)
                                    img_down_state.append('{}.jpg'.format(c+1))
                                    _record_camera_result(c, res, content, response_ms)
                                else:
                                    _record_camera_result(c, res, b'', response_ms, _('HTTP status') + ': {}'.format(res.status_code))
                            except:
                                error = traceback.format_exc()
                                _record_camera_result(c, error=error.splitlines()[-1] if error else _('Unknown error'))
                                log.error(NAME, _('IP Cam plug-in') + ':\n' + error)

                    log.clear(NAME)
                    log.info(NAME, _('Downloaded images') + ': ' + datetime_string())
                    log.info(NAME, str(img_down_state)[1:-1])

                self._sleep(_safe_int(plugin_options['download_interval'], 5, 1, 3600))

                if plugin_options['use_gif']:
                    for c in range(0, options.output_count):
                        if _camera_configured(c):
                            IMG_FILE = os.path.join(plugin_data_dir(), str(c+1), '{}.jpg'.format(img_counter))
                            SOURCE_FILE = os.path.join(plugin_data_dir(), '{}.jpg'.format(c+1))
                            if not os.path.isdir(os.path.dirname(IMG_FILE)):
                                helpers.mkdir_p(os.path.dirname(IMG_FILE))
                            if os.path.isfile(SOURCE_FILE):
                                shutil.copy(SOURCE_FILE, IMG_FILE)
                    
                    img_counter += 1
                    if img_counter >= int(plugin_options['gif_frames']):
                        img_counter = 0
                        for c in range(0, options.output_count):
                            if _camera_configured(c):
                                frames = []
                                for i in range(0, int(plugin_options['gif_frames'])):
                                    IMG_FILE = os.path.join(plugin_data_dir(), str(c+1), '{}.jpg'.format(i))
                                    if os.path.isfile(IMG_FILE):
                                        frames.append(Image.open(IMG_FILE))
                                if len(frames) > 0:
                                    gif = [image.convert("P", palette=Image.ADAPTIVE) for image in frames]
                                    gif[0].save(os.path.join(plugin_data_dir(), '{}.gif'.format(c+1)), save_all=True, optimize=False, append_images=gif[1:], duration=_safe_int(plugin_options['gif_duration'], 250, 50, 5000), loop=0)
                                    #frame_one = frames[0]
                                    #frame_one.save('plugins/ip_cam/data/{}.gif'.format(c+1), format='GIF', append_images=frames, save_all=True, duration=100, loop=0)
                                    log.info(NAME, _('Creating {}.gif').format(c+1))

                self._sleep(1)

            except Exception:
                log.error(NAME, _('IP Cam plug-in') + ':\n' + traceback.format_exc())
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
       sender.join(15)
       sender = None 


################################################################################
# Web pages:                                                                   #
################################################################################

class settings_page(ProtectedPage):
    """Main html page"""

    def GET(self):
        try:
            global sender
            qdict = web.input()

            cam = get_input(qdict, 'cam', False, lambda x: True)
            cam_foto = get_input(qdict, 'cam_foto', False, lambda x: True)
            cam_gif = get_input(qdict, 'cam_gif', False, lambda x: True)
            cam_stream = get_input(qdict, 'cam_stream', False, lambda x: True)
            snapshot = get_input(qdict, 'snapshot', False, lambda x: True)
            test_jpeg = get_input(qdict, 'test_jpeg', False, lambda x: True)
            test_mjpeg = get_input(qdict, 'test_mjpeg', False, lambda x: True)
            delete_cache = get_input(qdict, 'delete_cache', False, lambda x: True)

            if cam:
                cam_nr = int(qdict['cam'])
                return self.plugin_render.ip_cam_gif(plugin_options, cam_nr)

            if delete_cache:
                verify_csrf(qdict)
                deleted = _delete_cache()
                log.info(NAME, datetime_string() + ' ' + _('Deleted cached camera files') + ': {}'.format(deleted))
                raise web.seeother(plugin_url(settings_page), True)

            for action_name, action_value, stream in (
                ('snapshot', snapshot, False),
                ('test_jpeg', test_jpeg, False),
                ('test_mjpeg', test_mjpeg, True),
            ):
                if action_value:
                    verify_csrf(qdict)
                    cam_index = int(action_value) - 1
                    try:
                        if stream:
                            res, content, response_ms = _test_camera_stream(cam_index)
                        else:
                            res, content, response_ms = _fetch_camera(cam_index)
                        if res.status_code == 200:
                            if not stream or action_name == 'snapshot':
                                _save_snapshot(cam_index, content)
                            _record_camera_result(cam_index, res, content, response_ms)
                            log.info(NAME, datetime_string() + ' ' + _('Camera {} test OK').format(cam_index + 1))
                        else:
                            _record_camera_result(cam_index, res, b'', response_ms, _('HTTP status') + ': {}'.format(res.status_code))
                            log.error(NAME, datetime_string() + ' ' + _('Camera {} test failed').format(cam_index + 1))
                    except:
                        error = traceback.format_exc()
                        _record_camera_result(cam_index, error=error.splitlines()[-1] if error else _('Unknown error'))
                        log.error(NAME, _('IP Cam plug-in') + ':\n' + error)
                    raise web.seeother(plugin_url(settings_page), True)

            if cam_foto:
                cam_nr = qdict['cam_foto']
                download_name = os.path.join(plugin_data_dir(), '{}.jpg'.format(cam_nr))
            elif cam_gif:
                cam_nr = qdict['cam_gif']
                download_name = os.path.join(plugin_data_dir(), '{}.gif'.format(cam_nr))
            elif cam_stream:
                cam_nr = int(qdict['cam_stream'])
                return self.plugin_render.ip_cam_mjpeg(plugin_options, cam_nr, plugin_url(stream_page) + '?cam={}'.format(cam_nr))
            else:
                return self.plugin_render.ip_cam(plugin_options, log.events(NAME), _camera_statuses())

            if os.path.isfile(download_name):     # exists image?
                content = mimetypes.guess_type(download_name)[0]
                web.header('Content-type', content)
                web.header('Content-Length', os.path.getsize(download_name))
                web.header('Content-Disposition', 'attachment; filename={}'.format(os.path.basename(download_name)))
                with open(download_name, 'rb') as img:
                    return img.read()
            return None
        except web.HTTPError:
            raise
        except:
            log.error(NAME, _('IP Cam plug-in') + ':\n' + traceback.format_exc())
            msg = _('An internal error was found in the system, see the error log for more information. The error is in part:') + ' '
            msg += _('ip_cam -> settings_page GET')
            return self.core_render.notice('/', msg)

    def POST(self):
        try:
            qdict = web.input()
            verify_csrf(qdict)
            return self.plugin_render.ip_cam(plugin_options, log.events(NAME), _camera_statuses())
        except:
            log.error(NAME, _('IP Cam plug-in') + ':\n' + traceback.format_exc())
            msg = _('An internal error was found in the system, see the error log for more information. The error is in part:') + ' '
            msg += _('ip_cam -> settings_page POST')
            return self.core_render.notice('/', msg)


class image_page(ProtectedPage):
    """Returns one cached camera snapshot."""

    def GET(self):
        try:
            qdict = web.input()
            cam_nr = int(qdict.get('cam', 1))
            if cam_nr < 1 or cam_nr > options.output_count:
                raise ValueError(_('Unknown camera.'))
            download_name = os.path.join(plugin_data_dir(), '{}.jpg'.format(cam_nr))
            if not os.path.isfile(download_name):
                return None
            content = mimetypes.guess_type(download_name)[0] or 'image/jpeg'
            web.header('Content-type', content)
            web.header('Content-Length', os.path.getsize(download_name))
            web.header('Cache-Control', 'no-store')
            with open(download_name, 'rb') as img:
                return img.read()
        except:
            log.error(NAME, _('IP Cam plug-in') + ':\n' + traceback.format_exc())
            return None


class stream_page(ProtectedPage):
    """Proxies one MJPEG stream without exposing camera credentials in HTML."""

    def GET(self):
        try:
            qdict = web.input()
            cam_nr = int(qdict.get('cam', 1))
            if cam_nr < 1 or cam_nr > options.output_count:
                raise ValueError(_('Unknown camera.'))
            index = cam_nr - 1
            url = _camera_url(index, stream=True)
            response = requests.get(
                url,
                stream=True,
                verify=bool(plugin_options['verify_ssl']),
                auth=_camera_auth(index),
                timeout=_safe_int(plugin_options['http_timeout'], 15, 1, 120)
            )
            web.header('Content-type', response.headers.get('content-type', 'multipart/x-mixed-replace'))
            web.header('Cache-Control', 'no-store')

            def stream():
                try:
                    for chunk in response.iter_content(chunk_size=64 * 1024):
                        if chunk:
                            yield chunk
                finally:
                    response.close()
            return stream()
        except:
            log.error(NAME, _('IP Cam plug-in') + ':\n' + traceback.format_exc())
            return None

class setup_page(ProtectedPage):
    """Load an html setup page."""

    def GET(self):
        try:
            qdict = web.input()
            msg = 'none'
  
            try:
                return self.plugin_render.ip_cam_setup(plugin_options, msg)
            except:
                plugin_options.__setitem__('jpg_ip', ['']*options.output_count)
                plugin_options.__setitem__('jpg_que', ['']*options.output_count)
                plugin_options.__setitem__('mjpeg_que', ['']*options.output_count)
                plugin_options.__setitem__('jpg_user', ['']*options.output_count)
                plugin_options.__setitem__('jpg_pass', ['']*options.output_count)
                plugin_options.__setitem__('gif_frames', 20)
                plugin_options.__setitem__('use_jpg', True)
                plugin_options.__setitem__('use_gif', True)
                plugin_options.__setitem__('download_interval', 5)
                plugin_options.__setitem__('http_timeout', 15)
                plugin_options.__setitem__('verify_ssl', False)
                plugin_options.__setitem__('max_image_kb', 2048)
                plugin_options.__setitem__('gif_duration', 250)
                return self.plugin_render.ip_cam_setup(plugin_options, msg)
        except:
            log.error(NAME, _('IP Cam plug-in') + ':\n' + traceback.format_exc())
            msg = _('An internal error was found in the system, see the error log for more information. The error is in part:') + ' '
            msg += _('ip_cam -> setup_page GET')
            return self.core_render.notice('/', msg)

    def POST(self):
        global sender
        try:
            qdict = web.input()
            verify_csrf(qdict)
            commands = {'mjpeg_que': [], 'jpg_ip': [], 'jpg_que': [], 'jpg_user': [], 'jpg_pass': []}
            for i in range(0, options.output_count):
                if 'mjpeg_que'+str(i) in qdict:
                    commands['mjpeg_que'].append(qdict['mjpeg_que'+str(i)])
                else:
                    commands['mjpeg_que'].append('')

                if 'jpg_ip'+str(i) in qdict:
                    commands['jpg_ip'].append(qdict['jpg_ip'+str(i)])
                else:
                    commands['jpg_ip'].append('')

                if 'jpg_que'+str(i) in qdict:
                    commands['jpg_que'].append(qdict['jpg_que'+str(i)])
                else:
                    commands['jpg_que'].append('')

                if 'jpg_user'+str(i) in qdict:
                    commands['jpg_user'].append(qdict['jpg_user'+str(i)])
                else:
                    commands['jpg_user'].append('')

                if 'jpg_pass'+str(i) in qdict:
                    commands['jpg_pass'].append(qdict['jpg_pass'+str(i)])
                else:
                    commands['jpg_pass'].append('')

            plugin_options.__setitem__('use_jpg', qdict.get('use_jpg') == 'on')
            plugin_options.__setitem__('use_gif', qdict.get('use_gif') == 'on')
            plugin_options.__setitem__('verify_ssl', qdict.get('verify_ssl') == 'on')

            if 'gif_frames' in qdict:
                plugin_options.__setitem__('gif_frames', _safe_int(qdict['gif_frames'], 20, 3, 50))
            if 'download_interval' in qdict:
                plugin_options.__setitem__('download_interval', _safe_int(qdict['download_interval'], 5, 1, 3600))
            if 'http_timeout' in qdict:
                plugin_options.__setitem__('http_timeout', _safe_int(qdict['http_timeout'], 15, 1, 120))
            if 'max_image_kb' in qdict:
                plugin_options.__setitem__('max_image_kb', _safe_int(qdict['max_image_kb'], 2048, 64, 10240))
            if 'gif_duration' in qdict:
                plugin_options.__setitem__('gif_duration', _safe_int(qdict['gif_duration'], 250, 50, 5000))

            plugin_options.__setitem__('mjpeg_que', commands['mjpeg_que'])
            plugin_options.__setitem__('jpg_ip', commands['jpg_ip'])
            plugin_options.__setitem__('jpg_que', commands['jpg_que'])
            plugin_options.__setitem__('jpg_user', commands['jpg_user'])
            plugin_options.__setitem__('jpg_pass', commands['jpg_pass'])

            if sender is not None:
                sender.update()

            msg = 'saved'
            return self.plugin_render.ip_cam_setup(plugin_options, msg)

        except:
            log.error(NAME, _('IP Cam plug-in') + ':\n' + traceback.format_exc())
            msg = _('An internal error was found in the system, see the error log for more information. The error is in part:') + ' '
            msg += _('ip_cam -> setup_page POST')
            return self.core_render.notice('/', msg)


class help_page(ProtectedPage):
    """Load an html page for help page."""

    def GET(self):
        try:
            return self.plugin_render.ip_cam_help()
        except:
            log.error(NAME, _('IP Cam plug-in') + ':\n' + traceback.format_exc())
            msg = _('An internal error was found in the system, see the error log for more information. The error is in part:') + ' '
            msg += _('ip_cam -> help_page GET')
            return self.core_render.notice('/', msg)

class settings_json(ProtectedPage):
    """Returns plugin settings in JSON format."""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        try:
            return json.dumps(plugin_options)
        except:
            return {}


class status_json(ProtectedPage):
    """Returns camera status data in JSON format."""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        try:
            return json.dumps({
                'events': log.events(NAME),
                'cameras': _camera_statuses(),
            })
        except:
            return {}
