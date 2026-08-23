# -*- coding: utf-8 -*-
__author__ = u'Martin Pihrt'

import json
import time
import traceback
import web
import os
import mimetypes
import uuid
import datetime
from collections import deque

from ospy.helpers import datetime_string, verify_csrf
from ospy import helpers 
from ospy.log import log
from ospy.sensors import sensors
from ospy.programs import programs
from threading import Thread, Lock
from plugins import PluginOptions, plugin_url, plugin_data_dir, get_runtime
from ospy.webpages import ProtectedPage

from ospy.webpages import showInFooter # Enable plugin to display readings in UI footer

from urllib.request import urlopen
from urllib.parse import quote_plus
from urllib.parse import urlparse

from .blind_model import aggregate_blind_states, command_url, default_blind, in_time_window, parse_status, position_state, run_now_deadline, sensor_temperature, status_url, stored_blinds, wind_window_state

NAME = 'Venetian blind'      ### name for plugin in plugin manager ###
MENU =  _(u'Package: Venetian blind')
LINK = 'home_page'           ### link for page in plugin manager ###
HTTP_TIMEOUT = 5
STATUS_INTERVAL = 10
ERROR_LOG_THROTTLE = 300
MAX_LOG_RECORDS = 200

plugin_options = PluginOptions(
    NAME,
    {
        'use_control': False,
        'use_log': False, 
        'use_footer': True,
        # PluginOptions restores values only when their type matches the default.
        # This must stay a list so profiles and tilt settings survive a reload.
        'blinds': [],
        'view_mode': 'cards',
        'automation_enabled': False,
        'temperature_sensor': -1,
        'temperature_limit': 30.0,
        'wind_limit': 10.0,
        'safe_wind_samples': 50,
        'strong_wind_samples': 2,
        'strong_wind_interval': 5,
        'automation_start': '08:00',
        'automation_end': '20:00',
        'close_programs': [],
        'open_programs': [],
     }
)
runtime = get_runtime()
health_lock = Lock()
health_state = {
    'last_status': 0,
    'last_command': 0,
    'last_error': 0,
    'last_error_message': '',
}


################################################################################
# Main function loop:                                                          #
################################################################################

class Sender(Thread):
    def __init__(self):
        Thread.__init__(self)
        self.daemon = True
        self._stop_event = runtime.stop_event

        self.status = {}
        self.status['bstatus'] = {}

        self._sleep_time = 0
        self._last_error_log = 0
        self._wind_samples = deque(maxlen=10000)
        self._last_wind_measurement = None
        self._wind_action_sent = False
        self._temperature_action_sent = False
        self._last_active_programs = set()
        self._program_queue = deque()
        self._program_reason = ''
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
        last_msg = ''
        act_msg = ''
        ven_blind = None
        
        if plugin_options['use_footer']:
            ven_blind = showInFooter()                        #  instantiate class to enable data in footer
            ven_blind.button = "venetian_blind/home"          # button redirect on footer
            ven_blind.label =  _(u'Venetian blind')           # label on footer
        
        while not self._stop_event.is_set():
            try:
                if plugin_options['use_control']:             # if plugin is enabled
                    show_msg = read_blinds_status()
                    automation_cycle(self)
                    if plugin_options['use_footer']:          # if footer is enabled
                        if ven_blind is not None:
                            ven_blind.val = show_msg.encode('utf8').decode('utf8')       # value on footer                    
                else:
                    act_msg = _('Venetian blind is disabled.')
                    if act_msg != last_msg:
                        log.clear(NAME)
                        log.info(NAME, act_msg)
                        last_msg = act_msg
                        if plugin_options['use_footer']:
                            if ven_blind is not None:
                                ven_blind.val = act_msg.encode('utf8').decode('utf8')    # value on footer                            
                
                self._sleep(STATUS_INTERVAL)

            except Exception:
                self._log_problem(_('Venetian blind plug-in') + ':\n' + traceback.format_exc())
                self._sleep(60)

sender = None

################################################################################
# Helper functions:                                                            #
################################################################################

### start ###
def start():
    global sender
    if sender is None:
        normalize_options()
        sender = Sender()
 
### stop ###
def stop():
    global sender
    if sender is not None:
        sender.stop()
        sender.join(15)
        if sender.is_alive():
            log.error(NAME, _('The plug-in worker did not stop within the timeout.'))
        else:
            sender = None


def health():
    """Return configured blind, reachability and worker state."""
    with health_lock:
        state = dict(health_state)
    worker_running = sender is not None and sender.is_alive()
    configured = [blind for blind in get_blinds() if blind.get('enabled', True)]
    status_details = sender.status.get('details', {}) if sender is not None else {}
    automation = sender.status.get('automation', {}) if sender is not None else {}
    reachable = sum(1 for value in status_details.values() if value.get('reachable'))
    details = {
        _('Worker thread'): _('Running') if worker_running else _('Stopped'),
        _('Blind control enabled'): _('Yes') if plugin_options['use_control'] else _('No'),
        _('Configured blinds'): len(configured),
        _('Reachable blinds'): reachable,
        _('Last successful status update'): (
            datetime_string(time.localtime(state['last_status']))
            if state['last_status'] else _('Not available')
        ),
        _('Last command sent'): (
            datetime_string(time.localtime(state['last_command']))
            if state['last_command'] else _('Not available')
        ),
        _('Automation enabled'): _('Yes') if plugin_options.get('automation_enabled') else _('No'),
    }
    if plugin_options.get('automation_enabled'):
        details[_('Automation temperature')] = '{} °C'.format(automation['temperature']) if automation.get('temperature') is not None else _('Not available')
        details[_('Automation wind speed')] = '{} m/s'.format(automation['wind']) if automation.get('wind') is not None else _('Not available')
        details[_('Consecutive safe wind measurements')] = '{}/{}'.format(automation.get('safe_count', 0), plugin_options['safe_wind_samples'])
        details[_('Strong wind exceedances')] = '{}/{} ({} min)'.format(automation.get('exceedances', 0), plugin_options['strong_wind_samples'], plugin_options['strong_wind_interval'])
        details[_('Confirmed blind states')] = '{}/{}'.format(automation.get('known_blinds', 0), automation.get('enabled_blinds', len(configured)))
    if state['last_error_message']:
        details[_('Last error')] = state['last_error_message']
    if not worker_running:
        return {
            'status': 'error',
            'summary': _('Venetian Blind worker is not running.'),
            'details': details,
        }
    if not plugin_options['use_control']:
        return {
            'status': 'unknown',
            'summary': _('Venetian blind control is disabled.'),
            'details': details,
        }
    if state['last_error'] and state['last_error'] >= max(
            state['last_status'], state['last_command']):
        return {
            'status': 'error',
            'summary': state['last_error_message'],
            'details': details,
        }
    if not state['last_status']:
        return {
            'status': 'unknown',
            'summary': _('Venetian Blind is waiting for its first status update.'),
            'details': details,
        }
    if reachable < len(configured):
        return {
            'status': 'warning',
            'summary': _('One or more configured blinds are not reachable.'),
            'details': details,
        }
    return {
        'status': 'ok',
        'summary': _('Venetian Blind is responding.'),
        'details': details,
    }


def mobile_status():
    """Return the cached plug-in state without polling the blinds again."""
    result = health()
    with health_lock:
        updated = health_state['last_status']
    return {
        'status': result.get('status', 'unknown'),
        'title': _('Venetian blind'),
        'summary': result.get('summary', ''),
        'updated': updated,
    }


def mobile_cards(**_kwargs):
    """Return one native mobile status card for every configured blind."""
    blinds = get_blinds()
    details = sender.status.get('details', {}) if sender is not None else {}
    statuses = sender.status.get('bstatus', {}) if sender is not None else {}
    cards = []
    action_labels = {
        'open': _('open'), 'stop': _('stop'), 'closed': _('close'),
        'tilt1': _('tilt 1'), 'tilt2': _('tilt 2'),
        'tilt3': _('tilt 3'), 'tilt4': _('tilt 4'),
    }
    for index, blind in enumerate(blinds):
        detail = details.get(index, {})
        reachable = bool(detail.get('reachable'))
        position = detail.get('position')
        metrics = [
            {'id': 'state', 'label': _('State'),
             'value': statuses.get(index, _('unknown state')), 'unit': ''},
            {'id': 'position', 'label': _('Position'),
             'value': round(position, 1) if position is not None else None,
             'unit': '%'},
            {'id': 'connection', 'label': _('Connection'),
             'value': _('Available') if reachable else _('Unavailable'),
             'unit': ''},
            {'id': 'profile', 'label': _('Profile'),
             'value': blind.get('profile', 'custom'), 'unit': ''},
        ]
        actions = [
            {'id': target, 'label': label,
             'payload': {'blind_uid': blind['uid']}}
            for target, label in action_labels.items()
        ] if blind.get('enabled', True) and plugin_options.get('use_control') else []
        cards.append({
            'id': 'blind_{}'.format(blind['uid']),
            'kind': 'metrics',
            'title': blind.get('label') or _('Venetian blind'),
            'status': ('disabled' if not blind.get('enabled', True) else
                       'ok' if reachable else 'unavailable'),
            'metrics': metrics,
            'actions': actions,
        })
    return cards


def mobile_action(action, payload):
    """Execute a declared manual blind command from Mobile API v1."""
    targets = ('open', 'stop', 'closed', 'tilt1', 'tilt2', 'tilt3', 'tilt4')
    if action not in targets:
        raise ValueError(_('Unknown command.'))
    if not plugin_options.get('use_control'):
        raise RuntimeError(_('Venetian blind is disabled.'))
    if not isinstance(payload, dict):
        raise ValueError(_('Blind index is invalid.'))
    uid = str(payload.get('blind_uid', ''))
    blinds = get_blinds()
    index = next((i for i, blind in enumerate(blinds)
                  if blind['uid'] == uid and blind.get('enabled', True)), -1)
    if index < 0:
        raise ValueError(_('Blind index is invalid.'))
    message = send_cmd_to_blind(index, action)
    success = message == _('The command has been executed.')
    return {
        'status': 'ok' if success else 'error',
        'message': message,
        'blind_uid': uid,
        'target': action,
    }


def fetch_json(url):
    with urlopen(url, timeout=HTTP_TIMEOUT) as response:
        charset = response.info().get_content_charset('utf-8')
        return json.loads(response.read().decode(charset))

def uri_validator(x):
    try:
        result = urlparse(x)
        return result.scheme in ('http', 'https') and bool(result.netloc)
    except Exception:
        return False

def valid_blind_index(index):
    return 0 <= index < len(get_blinds())

def send_cmd_to_blind(button, position):
    """Send command via REST API to blinds."""
    try:
        if not valid_blind_index(button):
            return _('Blind index is invalid.')
        blind = get_blinds()[button]
        target = {-1: 'closed', 0: 'stop', 1: 'open'}.get(position, position)
        url = command_url(blind, target)
        target_labels = {'open': _('open'), 'stop': _('stop'), 'closed': _('close'), 'tilt1': _('tilt 1'), 'tilt2': _('tilt 2'), 'tilt3': _('tilt 3'), 'tilt4': _('tilt 4')}
        pos_msg = target_labels.get(target, _('unknown state'))
        if url is not None:
            if uri_validator(url):
                try:
                    data = fetch_json(url)
                    with health_lock:
                        health_state['last_command'] = time.time()
                        health_state['last_error_message'] = ''
                    msg_log = '{}: {}'.format(_('Answer ok'), data)
                    update_log(pos_msg, msg_log)
                    if target != 'stop' and sender is not None:
                        sender.status.setdefault('desired', {})[button] = target
                    return _('The command has been executed.')
                except OSError:
                    update_log(pos_msg, _('No route to host {}.').format(url))
                    log.debug(NAME, _('No route to host {}.').format(url))
                    return _('No route to host {}.').format(url) 
            else:
                log.error(NAME, _('URL {} is invalid.').format(url))
                update_log(pos_msg, _('URL {} is invalid.').format(url))
                return _('URL {} is invalid.').format(url)
    except Exception:
        log.error(NAME, _('Venetian blind plug-in') + ':\n' + traceback.format_exc())
        return _('Any error.')

def read_blinds_status():
    """Read status json data from blinds via REST API."""
    global sender
    footer_msg = ''
    try:
        from datetime import datetime
        today =  datetime.today()
        footer_msg += '{} '.format(today.strftime("%H:%M:%S"))

        blinds = get_blinds()
        sender.status['details'] = {}
        for i, blind in enumerate(blinds):
            if not blind.get('enabled', True):
                sender.status['bstatus'][i] = _('disabled')
                continue
            status_address = status_url(blind)
            if status_address != '':
                if uri_validator(status_address):
                    try:
                        data = fetch_json(status_address)
                        if len(data) > 0:
                            parsed = parse_status(data, blind['profile'])
                            state_key = position_state(parsed['position'], blind['tilt_positions'])
                            labels = {'closed': blind['closed_label'] or _('Closed blind'), 'open': blind['open_label'] or _('Open blind')}
                            labels.update({'tilt{}'.format(n + 1): blind['tilt_labels'][n] or _('Tilt {}').format(n + 1) for n in range(4)})
                            state_labels = {'open': _('opening'), 'opening': _('opening'), 'close': _('closing'), 'closing': _('closing'), 'stop': _('stopped'), 'stopped': _('stopped'), 'closed': _('closed')}
                            movement = state_labels.get(parsed['state'], _('unknown state'))
                            position_label = labels.get(state_key, _('position') + ': {}%'.format(round(parsed['position'], 1)) if parsed['position'] is not None else _('unknown position'))
                            sender.status['bstatus'][i] = '{} ({})'.format(movement, position_label)
                            sender.status.setdefault('details', {})[i] = {'state': state_key, 'position': parsed['position'], 'movement': parsed['state'], 'reachable': True}
                            footer_msg += '{}: {} '.format(blind['label'], sender.status['bstatus'][i])
                        with health_lock:
                            health_state['last_status'] = time.time()
                            health_state['last_error_message'] = ''
                    except Exception:
                        with health_lock:
                            health_state['last_error'] = time.time()
                            health_state['last_error_message'] = _('No route to a configured blind.')
                        log.debug(NAME, _('No route to host {}.').format(status_address))
                        sender.status['bstatus'][int(i)] = '{}'.format(_('No route to host.'))
                        sender.status.setdefault('details', {})[i] = {'state': 'unknown', 'position': None, 'reachable': False}
                        footer_msg += '{}: {} '.format(blind['label'], sender.status['bstatus'][int(i)])
                else:
                    log.error(NAME, _('URL {} is invalid.').format(status_address))
                    sender.status['bstatus'][int(i)] = '{} {}'.format(datetime_string(), _('URL invalid.'))
                    sender.status['details'][i] = {'state': 'unknown', 'position': None, 'reachable': False}
                    footer_msg += '{}: {} '.format(blind['label'], sender.status['bstatus'][int(i)])
            else:
                sender.status['bstatus'][int(i)] = '{} {}'.format(datetime_string(), _('URL is not setuped.'))
                sender.status['details'][i] = {'state': 'unknown', 'position': None, 'reachable': False}
                footer_msg += '{}: {} '.format(blind['label'], sender.status['bstatus'][int(i)])
        
        return footer_msg

    except Exception:
        log.error(NAME, _('Venetian blind plug-in') + ':\n' + traceback.format_exc())
        return _('Any error.')

def read_log():
    """Read log data from json file."""
    try:
        with open(os.path.join(plugin_data_dir(), 'log.json')) as logf:
            return json.load(logf)
    except (IOError, ValueError):
        return []

def write_log(json_data):
    """Write data to log json file."""
    with open(os.path.join(plugin_data_dir(), 'log.json'), 'w') as outfile:
        json.dump(json_data, outfile)

def update_log(cmd, status):
    """Update data in json files."""
    try:
        log_data = read_log()
    except:   
        write_log([])
        log_data = read_log()

    from datetime import datetime 

    data = {}
    data['cmd'] = cmd
    data['status'] = status
    data['datetime'] = datetime_string()

    log_data.insert(0, data)
    log_data = log_data[:MAX_LOG_RECORDS]
    write_log(log_data)
    if plugin_options['use_log']:
        log.info(NAME, _('Saving to log files OK'))

def safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default

def safe_float(value, default=0.0):
    try:
        return float(str(value).replace(',', '.'))
    except (TypeError, ValueError):
        return default

def get_blinds():
    blinds = stored_blinds(dict(plugin_options), lambda: uuid.uuid4().hex)
    if plugin_options.get('blinds') != blinds:
        plugin_options['blinds'] = blinds
    return blinds

def normalize_options():
    get_blinds()
    plugin_options['temperature_sensor'] = safe_int(plugin_options.get('temperature_sensor', -1), -1)
    plugin_options['temperature_limit'] = max(-50.0, min(100.0, safe_float(plugin_options.get('temperature_limit', 30), 30)))
    plugin_options['wind_limit'] = max(0.1, min(100.0, safe_float(plugin_options.get('wind_limit', 10), 10)))
    plugin_options['safe_wind_samples'] = max(1, min(500, safe_int(plugin_options.get('safe_wind_samples', 50), 50)))
    plugin_options['strong_wind_samples'] = max(1, min(20, safe_int(plugin_options.get('strong_wind_samples', 2), 2)))
    plugin_options['strong_wind_interval'] = max(1, min(1440, safe_int(plugin_options.get('strong_wind_interval', 5), 5)))
    plugin_options['close_programs'] = [safe_int(value, -1) for value in plugin_options.get('close_programs', []) if safe_int(value, -1) >= 0]
    plugin_options['open_programs'] = [safe_int(value, -1) for value in plugin_options.get('open_programs', []) if safe_int(value, -1) >= 0]
    plugin_options['view_mode'] = plugin_options.get('view_mode') if plugin_options.get('view_mode') in ('cards', 'list') else 'cards'

def _time_minutes(text, default):
    try:
        hour, minute = str(text).split(':', 1)
        return max(0, min(1439, int(hour) * 60 + int(minute)))
    except (TypeError, ValueError):
        return default

def _temperature_value():
    index = plugin_options.get('temperature_sensor', -1)
    if index < 0:
        return None
    try:
        return sensor_temperature(sensors.get(index))
    except Exception:
        return None

def _wind_reading():
    try:
        from plugins import wind_monitor
        if wind_monitor.wind_sender is None:
            return None
        status = wind_monitor.wind_sender.status
        value = float(status.get('meter'))
        with wind_monitor.health_lock:
            timestamp = float(wind_monitor.health_state.get('last_reading', 0) or 0)
        measurement_key = (timestamp, str(status.get('last_measurement', '')))
        return value, timestamp, measurement_key
    except Exception:
        return None

def _active_run_now_index():
    """Return an active Run-Now index and discard OSPy's completed object."""
    active = programs.run_now_program
    if active is None:
        return -1
    deadline = run_now_deadline(active)
    if deadline is None or deadline <= datetime.datetime.now():
        programs.run_now_program = None
        return -1
    return getattr(active, 'index', -1)


def _start_next_program(worker):
    if not worker._program_queue or _active_run_now_index() >= 0:
        return
    index = worker._program_queue.popleft()
    programs.run_now(index)
    update_log(worker._program_reason, _('Program {} started.').format(index + 1))

def _run_programs(worker, indices, reason, priority=False):
    available = {program.index for program in programs.get()}
    if priority:
        _cancel_lowering_actions(worker)
    scheduled = False
    active_index = _active_run_now_index()
    for index in indices:
        if index not in available:
            continue
        scheduled = True
        if index != active_index and index not in worker._program_queue:
            worker._program_queue.append(index)
    worker._program_reason = reason
    _start_next_program(worker)
    return scheduled

def _cancel_lowering_actions(worker):
    closing = set(plugin_options.get('close_programs', []))
    worker._program_queue = deque(index for index in worker._program_queue if index not in closing)
    active = programs.run_now_program
    if active is not None and _active_run_now_index() in closing:
        programs.run_now_program = None

def automation_cycle(worker):
    if not plugin_options.get('automation_enabled', False):
        worker._program_queue.clear()
        worker._wind_samples.clear()
        worker._last_wind_measurement = None
        worker._wind_action_sent = False
        worker._temperature_action_sent = False
        return
    _start_next_program(worker)
    normalize_options()
    now_timestamp = time.time()
    reading = _wind_reading()
    if reading is not None:
        wind, measurement_timestamp, measurement_key = reading
        if measurement_timestamp > 0 and measurement_key != worker._last_wind_measurement:
            worker._wind_samples.append((measurement_timestamp, wind))
            worker._last_wind_measurement = measurement_key
    retention = max(plugin_options['strong_wind_interval'] * 60, plugin_options['safe_wind_samples'] * STATUS_INTERVAL * 2, 600)
    while worker._wind_samples and now_timestamp - worker._wind_samples[0][0] > retention:
        worker._wind_samples.popleft()
    wind_state = wind_window_state(
        worker._wind_samples,
        now_timestamp,
        plugin_options['wind_limit'],
        plugin_options['safe_wind_samples'],
        plugin_options['strong_wind_samples'],
        plugin_options['strong_wind_interval'] * 60,
        STATUS_INTERVAL * 3,
    )
    active_programs = {entry.get('program') for entry in log.active_runs() if entry.get('program') is not None and entry.get('program') >= 0}
    run_now_index = _active_run_now_index()
    if run_now_index >= 0:
        active_programs.add(run_now_index)
    if active_programs != worker._last_active_programs:
        if active_programs.intersection(plugin_options['open_programs']):
            worker._wind_action_sent = True
        elif active_programs.intersection(plugin_options['close_programs']):
            worker._temperature_action_sent = True
        worker._last_active_programs = active_programs
    details = worker.status.get('details', {})
    enabled_indices = [index for index, blind in enumerate(get_blinds()) if blind.get('enabled', True)]
    blind_state = aggregate_blind_states(details, enabled_indices)
    all_open = blind_state['all_open']
    all_closed = blind_state['all_closed']
    worker.status['automation'] = {
        'temperature': _temperature_value(),
        'wind': worker._wind_samples[-1][1] if worker._wind_samples else None,
        'safe': wind_state['safe'],
        'safe_count': wind_state['safe_count'],
        'strong': wind_state['strong'],
        'exceedances': wind_state['exceedances'],
        'enabled_blinds': len(enabled_indices),
        'known_blinds': blind_state['known_count'],
        'all_open': all_open,
        'all_closed': all_closed,
    }
    if wind_state['strong']:
        _cancel_lowering_actions(worker)
        worker._temperature_action_sent = False
        if all_open:
            worker._wind_action_sent = False
        elif not worker._wind_action_sent:
            worker._wind_action_sent = _run_programs(worker, plugin_options['open_programs'], _('Strong wind protection'), priority=True)
        return
    worker._wind_action_sent = False
    now = datetime.datetime.now()
    allowed = in_time_window(now.hour * 60 + now.minute, _time_minutes(plugin_options.get('automation_start'), 480), _time_minutes(plugin_options.get('automation_end'), 1200))
    temperature = worker.status['automation']['temperature']
    shading = temperature is not None and temperature >= plugin_options['temperature_limit'] and wind_state['safe'] and allowed
    if shading:
        if all_closed:
            worker._temperature_action_sent = False
        elif not worker._temperature_action_sent:
            worker._temperature_action_sent = _run_programs(worker, plugin_options['close_programs'], _('Temperature shading'))
    else:
        worker._temperature_action_sent = False

def _save_blinds(blinds):
    plugin_options['blinds'] = blinds
    if sender is not None:
        sender.update()

def _blind_from_form(qdict, uid):
    blind = default_blind(uid)
    blind.update({
        'enabled': qdict.get('enabled') == 'on',
        'label': str(qdict.get('label', '')).strip(),
        'profile': str(qdict.get('profile', 'custom')),
        'host': str(qdict.get('host', '')).strip(),
        'open_url': str(qdict.get('open_url', '')).strip(),
        'stop_url': str(qdict.get('stop_url', '')).strip(),
        'close_url': str(qdict.get('close_url', '')).strip(),
        'status_url': str(qdict.get('status_url', '')).strip(),
        'closed_label': str(qdict.get('closed_label', '')).strip(),
        'open_label': str(qdict.get('open_label', '')).strip(),
        'tilt_positions': [safe_int(qdict.get('tilt{}_position'.format(i), i * 20), i * 20) for i in range(1, 5)],
        'tilt_labels': [str(qdict.get('tilt{}_label'.format(i), '')).strip() for i in range(1, 5)],
        'tilt_urls': [str(qdict.get('tilt{}_url'.format(i), '')).strip() for i in range(1, 5)],
    })
    from .blind_model import normalize_blind
    return normalize_blind(blind, lambda: uid)

################################################################################
# Web pages:                                                                   #
################################################################################

class home_page(ProtectedPage):
    """Load an html page for entering control."""

    def GET(self):
        normalize_options()
        return self.plugin_render.venetian_blind_overview(plugin_options, get_blinds())

    def POST(self):
        qdict = web.input()
        verify_csrf(qdict)
        uid = str(qdict.get('blind_uid', ''))
        target = str(qdict.get('target', 'stop'))
        blinds = get_blinds()
        index = next((i for i, blind in enumerate(blinds) if blind['uid'] == uid), -1)
        if index >= 0 and target in ('open', 'stop', 'closed', 'tilt1', 'tilt2', 'tilt3', 'tilt4'):
            send_cmd_to_blind(index, target)
        raise web.seeother(plugin_url(home_page), True)

class setup_page(ProtectedPage):
    """Load an html setup page."""

    def GET(self):
        normalize_options()
        qdict = web.input()
        delete = helpers.get_input(qdict, 'delete', False, lambda x: True)
        msg = str(qdict.get('msg', 'none'))
        if sender is not None and delete:
            verify_csrf(qdict)
            write_log([])
            log.info(NAME, _('Deleted all log files OK.'))
            raise web.seeother(plugin_url(setup_page), True)
        
        blinds = get_blinds()
        action = str(qdict.get('action', ''))
        editor = None
        is_new = False
        if action == 'add':
            editor = default_blind(uuid.uuid4().hex)
            editor['closed_label'] = _('Closed blind')
            editor['open_label'] = _('Open blind')
            editor['tilt_labels'] = [_('Tilt {}').format(index + 1) for index in range(4)]
            is_new = True
        elif action == 'edit':
            editor = next((dict(item) for item in blinds if item['uid'] == str(qdict.get('blind', ''))), None)
        return self.plugin_render.venetian_blind_settings(plugin_options, msg, blinds, editor, is_new, sensors.get(), programs.get())

    def POST(self):
        try:
            qdict = web.input(close_programs=[], open_programs=[])
            verify_csrf(qdict)
            action = str(qdict.get('action', 'save_global'))
            blinds = get_blinds()
            msg = 'saved'
            if action == 'save_global':
                for key in ('use_control', 'use_log', 'use_footer', 'automation_enabled'):
                    plugin_options[key] = qdict.get(key) == 'on'
                plugin_options['temperature_sensor'] = safe_int(qdict.get('temperature_sensor'), -1)
                for key in ('temperature_limit', 'wind_limit'):
                    plugin_options[key] = safe_float(qdict.get(key), plugin_options.get(key))
                plugin_options['safe_wind_samples'] = safe_int(qdict.get('safe_wind_samples'), 50)
                plugin_options['strong_wind_samples'] = safe_int(qdict.get('strong_wind_samples'), 2)
                plugin_options['strong_wind_interval'] = safe_int(qdict.get('strong_wind_interval'), 5)
                plugin_options['automation_start'] = str(qdict.get('automation_start', '08:00'))
                plugin_options['automation_end'] = str(qdict.get('automation_end', '20:00'))
                plugin_options['close_programs'] = [safe_int(value, -1) for value in qdict.get('close_programs', [])]
                plugin_options['open_programs'] = [safe_int(value, -1) for value in qdict.get('open_programs', [])]
                requested_view = str(qdict.get('view_mode', 'cards'))
                plugin_options['view_mode'] = requested_view if requested_view in ('cards', 'list') else 'cards'
            elif action == 'save_blind':
                requested = str(qdict.get('blind_uid', ''))
                existing = next((item for item in blinds if item['uid'] == requested), None)
                uid = existing['uid'] if existing else uuid.uuid4().hex
                record = _blind_from_form(qdict, uid)
                if existing:
                    blinds[blinds.index(existing)] = record
                    msg = 'updated'
                else:
                    blinds.append(record)
                    msg = 'added'
                _save_blinds(blinds)
            elif action == 'delete_blind':
                requested = str(qdict.get('blind_uid', ''))
                blinds = [item for item in blinds if item['uid'] != requested]
                _save_blinds(blinds)
                msg = 'deleted'
            elif action == 'test_command':
                requested = str(qdict.get('blind_uid', ''))
                index = next((i for i, item in enumerate(blinds) if item['uid'] == requested), -1)
                if index >= 0:
                    send_cmd_to_blind(index, str(qdict.get('target', 'stop')))
                msg = 'tested'
            normalize_options()
            redirect = plugin_url(setup_page) + '?msg=' + msg
            if action == 'test_command' and requested:
                redirect += '&action=edit&blind=' + quote_plus(requested)
            raise web.seeother(redirect, True)

        except web.SeeOther:
            raise
        except Exception:
            log.debug(NAME, _('Venetian blind plug-in') + ':\n' + traceback.format_exc())
            return self.core_render.notice('/', _('Venetian blind settings could not be saved.'))

class help_page(ProtectedPage):
    """Load an html page for help"""

    def GET(self):
        return self.plugin_render.venetian_blind_help()

class log_page(ProtectedPage):
    """Load an html page for help"""

    def GET(self):
        return self.plugin_render.venetian_blind_log(read_log())

class settings_json(ProtectedPage): 
    """Returns plugin settings in JSON format."""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        return json.dumps(plugin_options)

class log_json(ProtectedPage):
    """Returns data in JSON format."""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        return json.dumps(read_log())

class log_csv(ProtectedPage):
    """Simple Log API"""

    def GET(self):
        data = "Date/Time; Command; State \n"
        log_file = read_log()
        for interval in log_file:
            data += '; '.join([
                interval['datetime'],
                u'{}'.format(interval['cmd']),
                u'{}'.format(interval['status']),
            ]) + '\n'

        content = mimetypes.guess_type('log.csv')[0] or 'text/csv'
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-type', content) 
        web.header('Content-Disposition', 'attachment; filename="log.csv"')
        return data

class blind_status_json(ProtectedPage):
    """Returns status in JSON format."""

    def GET(self):
        global sender
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        data=[]
        normalize_options()
        for i in range(len(get_blinds())):
            try:
                if sender is None:
                    raise KeyError()
                data.append(sender.status['bstatus'][i])
            except Exception:
                data.append(_('unknown state'))
        return json.dumps(data)        
