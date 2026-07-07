# -*- coding: utf-8 -*-
__author__ = 'Martin Pihrt'

import json
import time
import datetime
import traceback
import os
import base64
from http import HTTPStatus
from threading import Thread, Event, Lock, RLock
from urllib.parse import urljoin, urlparse

import web

from ospy.log import log
from plugins import PluginOptions, plugin_url, plugin_data_dir
from ospy.webpages import ProtectedPage
from ospy.helpers import get_rpi_revision, datetime_string, get_input, verify_csrf, safe_image_path
from ospy import helpers
from ospy.options import options
from ospy.stations import stations

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
        'enabled': [True]*options.output_count,     # Enable camera
        'use_jpg': True,                           # first download jpeg from IP address to plugin folder and next show these jpg on webpage
        'use_gif': True,                           # first download jpeg from IP address to plugin folder and next create gif and show these gif on webpage
        'show_on_home': True,                       # allow OSPy home page to use plugin images
        'home_image_type': 'jpg',                   # jpg or gif on OSPy home page
        'gif_frames': 20,                          # s new gif will be created in 100 seconds (20 frame x 5 sec)
        'download_interval': 5,                     # seconds between camera downloads
        'http_timeout': 15,                         # HTTP timeout in seconds
        'verify_ssl': False,                        # verify HTTPS certificates
        'max_image_kb': 2048,                       # maximum downloaded JPEG size
        'gif_duration': 250,                        # GIF frame duration in ms
     }
)

status_lock = Lock()
cache_lock = RLock()
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
    _ensure_list('enabled', True)
    for key, value in {
        'show_on_home': True,
        'home_image_type': 'jpg',
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
        'http_message': '',
        'http_hint': '',
        'gif_frames': 0,
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
    return bool(plugin_options['enabled'][index] and plugin_options['jpg_ip'][index] and plugin_options[query_key][index])


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


def _http_message(status_code):
    try:
        return HTTPStatus(int(status_code)).phrase
    except Exception:
        return ''


def _http_hint(status_code):
    hints = {
        0: _('No HTTP response was received. Check camera address, port, network and timeout.'),
        200: _('OK'),
        301: _('Moved permanently. Check whether the camera path or protocol has changed.'),
        302: _('Redirected. Check whether the camera redirects to another path.'),
        400: _('Bad request. Check the JPEG or MJPEG query path.'),
        401: _('Unauthorized. Check username/password and try enabling Basic or Digest authentication in the camera.'),
        403: _('Forbidden. The user may not have permission to view the stream.'),
        404: _('Not found. The camera path is probably wrong for this model.'),
        408: _('Request timeout. Increase the timeout or check the network.'),
        500: _('Camera/server error. Check the camera firmware and stream settings.'),
        503: _('Service unavailable. The camera may be overloaded or already serving too many streams.'),
    }
    try:
        return hints.get(int(status_code), _('Check camera address, authentication and selected path.'))
    except Exception:
        return hints[0]


def _fetch_camera(index, stream=False):
    url = _camera_url(index, stream)
    timeout = _safe_int(plugin_options['http_timeout'], 15, 1, 120)
    verify = bool(plugin_options['verify_ssl'])
    max_bytes = _image_limit_bytes()
    hard_limit = max(max_bytes * 8, 25 * 1024 * 1024)
    started = time.time()
    response = requests.get(url, stream=True, verify=verify, auth=_camera_auth(index), timeout=timeout)
    response_ms = int((time.time() - started) * 1000)
    content = b''
    for chunk in response.iter_content(chunk_size=64 * 1024):
        if chunk:
            content += chunk
            if len(content) > hard_limit:
                raise ValueError(_('Downloaded image is larger than configured maximum size.'))
    if not stream:
        content = _fit_image_to_limit(content, max_bytes)
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


def _run_camera_action(action_name, cam_index):
    stream = action_name == 'test_mjpeg'
    msg = 'test_failed'
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
            msg = 'snapshot_ok' if action_name == 'snapshot' else 'test_ok'
        else:
            _record_camera_result(cam_index, res, b'', response_ms, _('HTTP status') + ': {}'.format(res.status_code))
            log.error(NAME, datetime_string() + ' ' + _('Camera {} test failed').format(cam_index + 1))
    except Exception:
        error = traceback.format_exc()
        _record_camera_result(cam_index, error=error.splitlines()[-1] if error else _('Unknown error'))
        log.error(NAME, _('IP Cam plug-in') + ':\n' + error)
    return msg


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
        values['http_message'] = _http_message(response.status_code)
        values['http_hint'] = _http_hint(response.status_code)
    if content is not None:
        values['size'] = len(content)
        values['resolution'] = _image_info(content)
    if error:
        values['errors'] = current.get('errors', 0) + 1
    else:
        values['success'] = current.get('success', 0) + 1
    _set_camera_status(index, **values)


def _save_snapshot(index, content):
    with cache_lock:
        helpers.mkdir_p(plugin_data_dir())
        img_path = os.path.join(plugin_data_dir(), '{}.jpg'.format(index + 1))
        with open(img_path, 'wb') as fh:
            fh.write(content)
        return img_path


def _camera_image_path(index, image_type):
    return os.path.join(plugin_data_dir(), '{}.{}'.format(index + 1, image_type))


def _snapshot_file_path(filename):
    if isinstance(filename, bytes):
        filename = filename.decode('utf8', 'ignore')
    if not isinstance(filename, str):
        return ''
    filename = os.path.basename(filename or '')
    parts = filename.split('.')
    if len(parts) != 2 or not parts[0].isdigit() or parts[1].lower() not in ('jpg', 'gif'):
        return ''
    index = int(parts[0])
    if index < 1 or index > options.output_count:
        return ''
    return _camera_image_path(index - 1, parts[1].lower())


def _ensure_cached_gif_limit(index):
    path = _camera_image_path(index, 'gif')
    if os.path.isfile(path) and os.path.getsize(path) > _image_limit_bytes() and len(_gif_frame_files(index)) >= 2:
        try:
            _create_gif(index)
        except Exception:
            log.error(NAME, _('IP Cam plug-in') + ':\n' + traceback.format_exc())
    return path


def _snapshot_items():
    items = []
    with cache_lock:
        for index in range(0, options.output_count):
            for image_type in ('jpg', 'gif'):
                if image_type == 'gif':
                    _ensure_cached_gif_limit(index)
                path = _camera_image_path(index, image_type)
                if os.path.isfile(path):
                    try:
                        content_type = mimetypes.guess_type(path)[0] or 'application/octet-stream'
                        with open(path, 'rb') as image_file:
                            data_uri = 'data:{};base64,{}'.format(
                                content_type,
                                base64.b64encode(image_file.read()).decode('ascii')
                            )
                        items.append({
                            'index': index + 1,
                            'station': stations[index].name if index < len(stations.get()) else _('Camera') + ' {}'.format(index + 1),
                            'type': image_type.upper(),
                            'filename': os.path.basename(path),
                            'size': os.path.getsize(path),
                            'modified': datetime.datetime.fromtimestamp(os.path.getmtime(path)).strftime('%Y-%m-%d %H:%M:%S'),
                            'data_uri': data_uri,
                        })
                    except IOError:
                        pass
    return items


def _gif_dir(index):
    return os.path.join(plugin_data_dir(), str(index + 1))


def _gif_frame_files(index):
    frame_dir = _gif_dir(index)
    if not os.path.isdir(frame_dir):
        return []
    files = []
    for filename in os.listdir(frame_dir):
        if filename.lower().endswith('.jpg'):
            path = os.path.join(frame_dir, filename)
            try:
                if os.path.isfile(path):
                    files.append((os.path.getmtime(path), path))
            except OSError:
                pass
    return [path for _mtime, path in sorted(files)]


def _image_limit_bytes():
    return _safe_int(plugin_options['max_image_kb'], 2048, 64, 10240) * 1024


def _save_jpeg_to_bytes(image, quality=85):
    output = BytesIO()
    image.save(output, format='JPEG', quality=quality, optimize=True)
    return output.getvalue()


def _fit_image_to_limit(content, max_bytes):
    if len(content) <= max_bytes:
        return content

    with Image.open(BytesIO(content)) as image:
        image = image.convert('RGB')

        for quality in (90, 82, 74, 66, 58, 50):
            resized = _save_jpeg_to_bytes(image, quality=quality)
            if len(resized) <= max_bytes:
                return resized

        scale = 0.85
        for _ in range(14):
            width = max(1, int(image.size[0] * scale))
            height = max(1, int(image.size[1] * scale))
            resized_image = image.resize((width, height), Image.LANCZOS)
            for quality in (82, 74, 66, 58, 50):
                resized = _save_jpeg_to_bytes(resized_image, quality=quality)
                if len(resized) <= max_bytes:
                    return resized
            scale *= 0.85

    raise ValueError(_('Downloaded image is larger than configured maximum size.'))


def _save_gif_frame(index, content):
    with cache_lock:
        frame_dir = _gif_dir(index)
        helpers.mkdir_p(frame_dir)
        frame_path = os.path.join(frame_dir, '{}.jpg'.format(int(time.time() * 1000)))
        with open(frame_path, 'wb') as fh:
            fh.write(content)

        keep = _safe_int(plugin_options['gif_frames'], 20, 3, 50)
        frame_files = _gif_frame_files(index)
        for old_file in frame_files[:-keep]:
            try:
                os.remove(old_file)
            except Exception:
                pass
        return frame_path


def _open_gif_frame(frame_file, target_size=None):
    with Image.open(frame_file) as image:
        frame = image.convert("RGB")
        if target_size and frame.size != target_size:
            frame = frame.resize(target_size, Image.LANCZOS)
        return frame


def _build_gif_bytes(frame_files, scale=1.0):
    if not frame_files:
        return b'', 0

    first = None
    for frame_file in frame_files:
        try:
            first = _open_gif_frame(frame_file)
            break
        except IOError:
            pass
    if first is None:
        return b'', 0

    width = max(1, int(first.size[0] * scale))
    height = max(1, int(first.size[1] * scale))
    target_size = (width, height)

    frames = []
    for frame_file in frame_files:
        try:
            frame = _open_gif_frame(frame_file, target_size)
            frames.append(frame.convert("P", palette=Image.ADAPTIVE))
        except IOError:
            pass

    if len(frames) < 2:
        return b'', len(frames)

    output = BytesIO()
    frames[0].save(
        output,
        format='GIF',
        save_all=True,
        optimize=True,
        append_images=frames[1:],
        duration=_safe_int(plugin_options['gif_duration'], 250, 50, 5000),
        loop=0,
        disposal=2
    )
    return output.getvalue(), len(frames)


def _create_gif(index):
    with cache_lock:
        frame_files = _gif_frame_files(index)
        if len(frame_files) < 2:
            _set_camera_status(index, gif_frames=len(frame_files))
            return False

        max_bytes = _image_limit_bytes()
        gif_data = b''
        frame_count = 0
        scale = 1.0
        for _ in range(12):
            gif_data, frame_count = _build_gif_bytes(frame_files, scale)
            if len(gif_data) <= max_bytes:
                break
            scale *= 0.82

        if not gif_data:
            _set_camera_status(index, gif_frames=frame_count, error=_('Could not create GIF.'))
            return False

        gif_path = os.path.join(plugin_data_dir(), '{}.gif'.format(index + 1))
        with open(gif_path, 'wb') as fh:
            fh.write(gif_data)
        values = {'gif_frames': frame_count}
        if len(gif_data) > max_bytes:
            values['error'] = _('Generated GIF is still larger than configured maximum size.')
        _set_camera_status(index, **values)
        return True


def _fallback_station_image(cam_nr, thumbnail=True):
    station_name = 'station{}_thumbnail.png'.format(cam_nr) if thumbnail else 'station{}.png'.format(cam_nr)
    station_path = safe_image_path(station_name, station_folder=True)
    if station_path and os.path.isfile(station_path):
        return station_path
    default_name = 'no_image_thumbnail.png' if thumbnail else 'no_image.png'
    return safe_image_path(default_name)


def _serve_image_file(path, attachment=False):
    if not path or not os.path.isfile(path):
        return None
    content = mimetypes.guess_type(path)[0] or 'application/octet-stream'
    web.header('Content-type', content)
    web.header('Content-Length', os.path.getsize(path))
    if attachment:
        web.header('Content-Disposition', 'attachment; filename={}'.format(os.path.basename(path)))
    else:
        web.header('Cache-Control', 'no-store')
    with open(path, 'rb') as fh:
        return fh.read()


def _delete_cache():
    with cache_lock:
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
                                    if plugin_options['use_gif']:
                                        _save_gif_frame(c, content)
                                        if _create_gif(c):
                                            log.info(NAME, _('Creating {}.gif').format(c+1))
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
            return_to = get_input(qdict, 'return_to', 'settings', lambda x: x in ('settings', 'setup'))

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
                    if cam_index < 0 or cam_index >= options.output_count:
                        raise ValueError(_('Unknown camera.'))
                    msg = _run_camera_action(action_name, cam_index)
                    if return_to == 'setup':
                        raise web.seeother(plugin_url(setup_page) + '?cam={}&msg={}'.format(cam_index + 1, msg), True)
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
            return _serve_image_file(download_name)
        except:
            log.error(NAME, _('IP Cam plug-in') + ':\n' + traceback.format_exc())
            return None


class home_image_page(ProtectedPage):
    """Returns IP Cam image for OSPy home page, with station image fallback."""

    def GET(self):
        try:
            qdict = web.input()
            cam_nr = int(qdict.get('cam', 1))
            image_type = qdict.get('type', plugin_options['home_image_type'])
            if cam_nr < 1 or cam_nr > options.output_count:
                raise ValueError(_('Unknown camera.'))

            index = cam_nr - 1
            download_name = ''
            if plugin_options['enabled'][index]:
                if image_type == 'gif':
                    download_name = _ensure_cached_gif_limit(index)
                else:
                    download_name = os.path.join(plugin_data_dir(), '{}.jpg'.format(cam_nr))

            if not download_name or not os.path.isfile(download_name):
                download_name = _fallback_station_image(cam_nr, thumbnail=True)

            return _serve_image_file(download_name)
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
            msg = qdict.get('msg', 'none')
            selected_camera = int(qdict.get('cam', 1)) - 1
            selected_camera = max(0, min(options.output_count - 1, selected_camera))
            _ensure_options()
            return self.plugin_render.ip_cam_setup(plugin_options, msg, selected_camera)
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
            commands = {'mjpeg_que': [], 'jpg_ip': [], 'jpg_que': [], 'jpg_user': [], 'jpg_pass': [], 'enabled': []}
            for i in range(0, options.output_count):
                commands['enabled'].append(qdict.get('enabled'+str(i)) == 'on')
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
            plugin_options.__setitem__('show_on_home', True)
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
            plugin_options.__setitem__('enabled', commands['enabled'])

            if sender is not None:
                sender.update()

            msg = 'saved'
            selected_camera = _safe_int(qdict.get('selected_camera', 1), 1, 1, options.output_count) - 1
            action = qdict.get('action', '')
            if action in ('snapshot', 'test_jpeg', 'test_mjpeg'):
                msg = _run_camera_action(action, selected_camera)
            return self.plugin_render.ip_cam_setup(plugin_options, msg, selected_camera)

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


class snapshots_page(ProtectedPage):
    """Manage cached snapshots and GIF files."""

    def GET(self):
        try:
            qdict = web.input()
            preview = get_input(qdict, 'preview', False, lambda x: True)
            download = get_input(qdict, 'download', False, lambda x: True)
            file_download = qdict.get('file', '')
            delete = get_input(qdict, 'delete', False, lambda x: True)
            delete_all = get_input(qdict, 'delete_all', False, lambda x: True)
            file_type = get_input(qdict, 'type', 'jpg', lambda x: x in ('jpg', 'gif'))

            if delete_all:
                verify_csrf(qdict)
                deleted = _delete_cache()
                log.info(NAME, datetime_string() + ' ' + _('Deleted cached camera files') + ': {}'.format(deleted))
                raise web.seeother(plugin_url(snapshots_page), True)

            if delete:
                verify_csrf(qdict)
                index = int(delete) - 1
                if index < 0 or index >= options.output_count:
                    raise ValueError(_('Unknown camera.'))
                if file_type == 'gif':
                    _ensure_cached_gif_limit(index)
                path = _camera_image_path(index, file_type)
                if os.path.isfile(path):
                    os.remove(path)
                    log.info(NAME, datetime_string() + ' ' + _('Deleted cached camera file') + ': {}'.format(os.path.basename(path)))
                raise web.seeother(plugin_url(snapshots_page), True)

            if file_download:
                path = _snapshot_file_path(file_download)
                if path and os.path.isfile(path):
                    return _serve_image_file(path, attachment=True)
                return self.core_render.notice(
                    plugin_url(snapshots_page),
                    _('Snapshot file is not available yet. Use Snapshot now or wait for a successful automatic camera download.')
                )

            if preview or download:
                index = int(preview or download) - 1
                if index < 0 or index >= options.output_count:
                    raise ValueError(_('Unknown camera.'))
                path = _camera_image_path(index, file_type)
                if not os.path.isfile(path):
                    if preview:
                        raise web.notfound(_('Snapshot file is not available yet.'))
                    return self.core_render.notice(
                        plugin_url(snapshots_page),
                        _('Snapshot file is not available yet. Use Snapshot now or wait for a successful automatic camera download.')
                    )
                return _serve_image_file(path, attachment=bool(download))

            return self.plugin_render.ip_cam_snapshots(plugin_options, _snapshot_items())
        except web.HTTPError:
            raise
        except:
            log.error(NAME, _('IP Cam plug-in') + ':\n' + traceback.format_exc())
            msg = _('An internal error was found in the system, see the error log for more information. The error is in part:') + ' '
            msg += _('ip_cam -> snapshots_page GET')
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
