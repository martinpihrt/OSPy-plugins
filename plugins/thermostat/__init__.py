# -*- coding: utf-8 -*-
__author__ = 'Martin Pihrt'

import json
import time
import traceback
import uuid
from threading import Thread, Lock

import web

from ospy.helpers import datetime_string, verify_csrf
from ospy.log import log
from ospy.options import options
from ospy.programs import programs
from ospy.stations import stations
from ospy.webpages import ProtectedPage, showInFooter, clear_plugin_runtime_data
from plugins import PluginOptions, plugin_url, get_runtime
from plugins.thermostat import model

try:
    from ospy.sensors import sensors
except Exception:
    sensors = None


NAME = 'Thermostat'
MENU = _('Package: Thermostat')
LINK = 'settings_page'

ERROR_LOG_THROTTLE = 300
MAX_THERMOSTATS = model.MAX_THERMOSTATS
INVALID_TEMPERATURE = model.INVALID_TEMPERATURE
MIN_CHECK_INTERVAL = model.MIN_CHECK_INTERVAL
MAX_CHECK_INTERVAL = model.MAX_CHECK_INTERVAL
SHELLY_VALUE_TYPES = model.SHELLY_VALUE_TYPES

plugin_options = PluginOptions(
    NAME,
    {
        'enabled': False,
        'check_interval': 30,
        'use_footer': False,
        'zones': [],
    }
)
runtime = get_runtime()
health_lock = Lock()
health_state = {
    'last_cycle': 0,
    'last_error': 0,
    'last_error_message': '',
}


def _normalize_zones():
    zones = plugin_options.get('zones', [])
    normalized = model.normalize_zones(
        zones,
        len(programs.get()),
        lambda: uuid.uuid4().hex,
        lambda index: _('Thermostat {}').format(index + 1),
    )

    if normalized != zones:
        plugin_options['zones'] = normalized
    return normalized


def _safe_int(value, default=0):
    return model.safe_int(value, default)


def _clamp(value, minimum, maximum):
    return model.clamp(value, minimum, maximum)


def source_title(source):
    titles = {
        'air_temp': _('Air Temperature DS'),
        'ospy_sensor': _('OSPy Sensor'),
        'shelly_cloud': _('Shelly Cloud'),
    }
    return titles.get(source, source)


def get_air_temp_channel_names():
    names = []
    try:
        from plugins import air_temp_humi
        for index in range(6):
            if hasattr(air_temp_humi, 'DS18B20_is_enabled') and not air_temp_humi.DS18B20_is_enabled(index):
                continue
            label = air_temp_humi.plugin_options.get('label_ds{}'.format(index), '')
            if label:
                names.append((index, '{} {}'.format(_('DS'), label)))
            else:
                names.append((index, '{} {}'.format(_('DS'), index + 1)))
    except Exception:
        for index in range(6):
            names.append((index, '{} {}'.format(_('DS'), index + 1)))
    return names


def get_sensor_channel_names():
    names = []
    try:
        if sensors is not None:
            for sensor in sensors.get():
                names.append((sensor.index, sensor.name))
    except Exception:
        pass
    return names


def get_shelly_devices():
    try:
        from plugins import shelly_cloud_integrator
        return shelly_cloud_integrator.shelly_devices.devices()
    except Exception:
        return []


def get_shelly_channel_names():
    names = []
    try:
        for index, device in enumerate(get_shelly_devices()):
            label = device.get('label', '')
            hardware = device.get('hw', '')
            if label and hardware:
                names.append((index, '{} ({})'.format(label, hardware)))
            elif label:
                names.append((index, label))
            elif hardware:
                names.append((index, hardware))
            else:
                names.append((index, device.get('id', _('Shelly device'))))
    except Exception:
        pass
    return names


def get_channel_names(source):
    if source == 'air_temp':
        return get_air_temp_channel_names()
    if source == 'ospy_sensor':
        return get_sensor_channel_names()
    if source == 'shelly_cloud':
        return get_shelly_channel_names()
    return []


def get_shelly_value(device, value_type):
    mapping = {
        'temperature': ('temperature', 0),
        'temperature_2': ('temperature', 1),
        'temperature_3': ('temperature', 2),
        'temperature_4': ('temperature', 3),
        'temperature_5': ('temperature', 4),
    }
    key, index = mapping.get(value_type, ('temperature', 0))
    value = device.get(key, [])
    if index < len(value):
        return value[index]
    return INVALID_TEMPERATURE


def get_temperature(source, channel, value_type):
    try:
        if source == 'air_temp':
            from plugins import air_temp_humi
            return float(air_temp_humi.DS18B20_read_probe(channel))

        if source == 'ospy_sensor' and sensors is not None:
            sensor = sensors.get(channel)
            if sensor.sens_type == 5:
                return float(sensor.last_read_value[0])
            if sensor.sens_type == 1:
                return float(sensor.last_read_value[4])
            if sensor.sens_type == 2:
                return float(sensor.last_read_value[5])
            if sensor.sens_type == 3:
                return float(sensor.last_read_value[6])
            if sensor.sens_type == 4:
                return float(sensor.last_read_value[7])
            if sensor.sens_type == 6:
                idx = sensor.multi_type
                if 0 <= idx <= 8:
                    return float(sensor.last_read_value[idx])

        if source == 'shelly_cloud':
            devices = get_shelly_devices()
            if channel < len(devices):
                return float(get_shelly_value(devices[channel], value_type))
    except Exception:
        pass
    return INVALID_TEMPERATURE


def program_label(program):
    name = getattr(program, 'name', '')
    label = _('Program {}').format(program.index + 1)
    if name:
        label += ': ' + name
    return label


def action_label(action):
    labels = {
        'none': _('Do nothing'),
        'start': _('Start program'),
        'stop': _('Stop program'),
    }
    return labels.get(action, action)


def shelly_value_label(value_type):
    labels = {
        'temperature': _('Temperature 1'),
        'temperature_2': _('Temperature 2'),
        'temperature_3': _('Temperature 3'),
        'temperature_4': _('Temperature 4'),
        'temperature_5': _('Temperature 5'),
    }
    return labels.get(value_type, value_type)


def program_exists(index):
    return 0 <= index < len(programs.get())


def program_station_ids(index):
    if not program_exists(index):
        return set()
    return set(programs.get(index).stations)


def start_program(index):
    if not program_exists(index):
        return False
    if program_is_active(index):
        return False
    options.manual_mode = False
    programs.run_now_program = None
    programs.run_now(index)
    return True


def run_now_program_matches(index):
    if not program_exists(index) or programs.run_now_program is None:
        return False
    target = programs.get(index)
    run_now = programs.run_now_program
    return (
        getattr(run_now, 'name', None) == getattr(target, 'name', None)
        and set(getattr(run_now, 'stations', [])) == set(getattr(target, 'stations', []))
        and list(getattr(run_now, 'schedule', [])) == list(getattr(target, 'schedule', []))
    )


def interval_matches_program(interval, index):
    if not program_exists(index):
        return False

    if interval.get('program') == index:
        return True

    station_ids = program_station_ids(index)
    if interval.get('station') not in station_ids:
        return False

    target_run_now_name = '{} {}'.format(_('Run-Now'), programs.get(index).name)
    if interval.get('program_name') == target_run_now_name:
        return True

    return False


def program_is_active(index):
    if run_now_program_matches(index):
        return True
    return any(interval_matches_program(interval, index) for interval in log.active_runs())


def stop_program(index):
    if not program_exists(index):
        return False

    stop_run_now = run_now_program_matches(index)
    active = log.active_runs()
    matching_active = [interval for interval in active if interval_matches_program(interval, index)]

    if stop_run_now or any(interval.get('program') == -1 for interval in matching_active):
        programs.run_now_program = None

    stopped = stop_run_now
    for interval in matching_active:
        log.finish_run(interval)
        if not any(active_interval.get('station') == interval['station'] for active_interval in log.active_runs()):
            stations.deactivate(interval['station'])
        stopped = True
    return stopped


def execute_action(action, program_index):
    if action == 'start':
        return start_program(program_index)
    if action == 'stop':
        return stop_program(program_index)
    return True


class ThermostatChecker(Thread):
    def __init__(self):
        Thread.__init__(self)
        self.daemon = True
        self._stop_event = runtime.stop_event
        self._sleep_time = 0
        self.zone_state = {}
        self.zone_temperatures = {}
        self.footer = None
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

    def update_footer(self, text):
        if plugin_options['use_footer']:
            if self.footer is None:
                self.footer = showInFooter()
                self.footer.label = _('Thermostat')
                self.footer.button = 'thermostat/settings'
            self.footer.val = text.encode('utf8').decode('utf8')
        else:
            clear_plugin_runtime_data('thermostat')
            self.footer = None

    def _log_problem(self, message):
        now = time.time()
        with health_lock:
            health_state['last_error'] = now
            health_state['last_error_message'] = str(message).splitlines()[-1]
        if now - self._last_error_log >= ERROR_LOG_THROTTLE:
            log.error(NAME, message)
            self._last_error_log = now

    def _reconcile_zones(self, zones):
        zone_ids = {zone['id'] for zone in zones}
        self.zone_state = {
            zone_id: self.zone_state.get(zone_id, 'unknown')
            for zone_id in zone_ids
        }
        self.zone_temperatures = {
            zone_id: self.zone_temperatures.get(zone_id)
            for zone_id in zone_ids
        }

    def run(self):
        last_enabled = None
        while not self._stop_event.is_set():
            try:
                zones = _normalize_zones()
                self._reconcile_zones(zones)
                plugin_options['check_interval'] = _clamp(_safe_int(plugin_options.get('check_interval'), 30), MIN_CHECK_INTERVAL, MAX_CHECK_INTERVAL)
                if not plugin_options['enabled']:
                    if last_enabled is not False:
                        if last_enabled is True:
                            for zone in zones:
                                if zone['enabled']:
                                    stop_program(zone['program'])
                        log.clear(NAME)
                        log.info(NAME, _('Thermostat plug-in is disabled.'))
                        self.update_footer(_('Disabled'))
                        last_enabled = False
                    self._sleep(60)
                    continue

                if last_enabled is not True:
                    log.clear(NAME)
                    log.info(NAME, datetime_string() + ' ' + _('Thermostat plug-in is enabled.'))
                    last_enabled = True

                footer_parts = []
                now = time.localtime()
                now_minutes = now.tm_hour * 60 + now.tm_min
                duplicate_programs = model.duplicate_enabled_program_ids(zones)
                handled_programs = set()
                for zone in zones:
                    zone_id = zone['id']
                    state = self.zone_state[zone_id]
                    if not zone['enabled']:
                        self.zone_state[zone_id] = 'disabled'
                        self.zone_temperatures[zone_id] = None
                        continue

                    if zone['program'] in duplicate_programs and zone['program'] in handled_programs:
                        if state != 'setup_error':
                            log.info(NAME, datetime_string() + ' ' + _('{} uses a program already assigned to another enabled thermostat.').format(zone['name']))
                        self.zone_state[zone_id] = 'setup_error'
                        self.zone_temperatures[zone_id] = None
                        footer_parts.append('{} {}'.format(zone['name'], _('setup error')))
                        continue
                    handled_programs.add(zone['program'])

                    if not model.zone_in_time_window(zone, now_minutes):
                        if state != 'scheduled_off':
                            stopped = stop_program(zone['program'])
                            log.info(NAME, datetime_string() + ' ' + _('{} is outside its operating time. Program stop result: {}.').format(zone['name'], _('OK') if stopped else _('not changed')))
                        self.zone_state[zone_id] = 'scheduled_off'
                        self.zone_temperatures[zone_id] = None
                        footer_parts.append('{} {}'.format(zone['name'], _('outside operating time')))
                        continue

                    if zone['low_temp'] >= zone['high_temp']:
                        if state != 'setup_error':
                            log.info(NAME, datetime_string() + ' ' + _('{} has invalid temperature limits. Low temperature must be lower than high temperature.').format(zone['name']))
                        self.zone_state[zone_id] = 'setup_error'
                        self.zone_temperatures[zone_id] = None
                        footer_parts.append('{} {}'.format(zone['name'], _('setup error')))
                        continue

                    temperature = get_temperature(zone['source'], zone['channel'], zone['value_type'])
                    if temperature == INVALID_TEMPERATURE:
                        if state != 'missing':
                            log.info(NAME, datetime_string() + ' ' + _('{} temperature is not available.').format(zone['name']))
                        self.zone_state[zone_id] = 'missing'
                        self.zone_temperatures[zone_id] = None
                        footer_parts.append('{} ---'.format(zone['name']))
                        continue
                    self.zone_temperatures[zone_id] = temperature

                    new_state = state
                    action = None
                    if temperature >= zone['high_temp']:
                        new_state = 'high'
                        action = zone['high_action']
                    elif temperature <= zone['low_temp']:
                        new_state = 'low'
                        action = zone['low_action']
                    elif state in ('unknown', 'disabled', 'scheduled_off'):
                        new_state = 'hold'

                    footer_parts.append('{} {:.1f}C'.format(zone['name'], temperature))

                    should_repeat_start = (
                        action == 'start'
                        and new_state == state
                        and not program_is_active(zone['program'])
                    )

                    if new_state != state or should_repeat_start:
                        self.zone_state[zone_id] = new_state
                        if action and action != 'none':
                            ok = execute_action(action, zone['program'])
                            program_name = program_label(programs.get(zone['program'])) if program_exists(zone['program']) else _('Unknown program')
                            log.info(NAME, datetime_string() + ' ' + _('{}: {:.1f} C, action {}, program {}, result {}.').format(zone['name'], temperature, action_label(action), program_name, _('OK') if ok else _('not changed')))
                        else:
                            log.info(NAME, datetime_string() + ' ' + _('{}: {:.1f} C, no action.').format(zone['name'], temperature))

                if footer_parts:
                    self.update_footer(' | '.join(footer_parts))
                else:
                    self.update_footer(_('No active thermostat'))

                with health_lock:
                    health_state['last_cycle'] = time.time()
                    health_state['last_error_message'] = ''
                sleep_time = _clamp(_safe_int(plugin_options.get('check_interval'), 30), MIN_CHECK_INTERVAL, MAX_CHECK_INTERVAL)
                current = time.localtime()
                boundary = model.seconds_until_boundary(current.tm_hour * 3600 + current.tm_min * 60 + current.tm_sec, zones)
                if boundary is not None:
                    sleep_time = min(sleep_time, max(1, boundary))
                self._sleep(sleep_time)
            except Exception:
                self._log_problem(_('Thermostat plug-in') + ':\n' + traceback.format_exc())
                self._sleep(60)


checker = None


def start():
    global checker
    if checker is None:
        checker = ThermostatChecker()


def stop():
    global checker
    if checker is not None:
        checker.stop()
        checker.join(15)
        if checker.is_alive():
            log.error(NAME, _('The plug-in worker did not stop within the timeout.'))
        else:
            checker = None
    clear_plugin_runtime_data('thermostat')


def health():
    """Return thermostat zones, temperature sources and worker state."""
    with health_lock:
        state = dict(health_state)
    worker_running = checker is not None and checker.is_alive()
    zones = _normalize_zones()
    enabled_zones = [zone for zone in zones if zone['enabled']]
    zone_states = checker.zone_state if checker is not None else {}
    temperatures = checker.zone_temperatures if checker is not None else {}
    missing = sum(
        1 for zone in enabled_zones
        if zone_states.get(zone['id'], 'unknown') in ('missing', 'setup_error')
    )
    details = {
        _('Worker thread'): _('Running') if worker_running else _('Stopped'),
        _('Thermostat enabled'): _('Yes') if plugin_options['enabled'] else _('No'),
        _('Enabled zones'): len(enabled_zones),
        _('Zones with unavailable temperature or setup error'): missing,
        _('Active program actions'): sum(
            1 for zone in enabled_zones
            if program_is_active(zone['program'])
        ),
        _('Last successful cycle'): (
            datetime_string(time.localtime(state['last_cycle']))
            if state['last_cycle'] else _('Not available')
        ),
    }
    for zone in enabled_zones:
        zone_state = zone_states.get(zone['id'], 'unknown')
        temperature = temperatures.get(zone['id'])
        details[zone['name']] = (
            '{:.1f} C ({})'.format(temperature, zone_state)
            if temperature is not None else zone_state
        )
    if state['last_error_message']:
        details[_('Last error')] = state['last_error_message']
    if not worker_running:
        return {
            'status': 'error',
            'summary': _('Thermostat worker is not running.'),
            'details': details,
        }
    if not plugin_options['enabled']:
        return {
            'status': 'unknown',
            'summary': _('Thermostat is disabled.'),
            'details': details,
        }
    if state['last_error'] and state['last_error'] >= state['last_cycle']:
        return {
            'status': 'error',
            'summary': state['last_error_message'],
            'details': details,
        }
    if not enabled_zones:
        return {
            'status': 'warning',
            'summary': _('No thermostat zone is enabled.'),
            'details': details,
        }
    if missing:
        return {
            'status': 'warning',
            'summary': _('One or more thermostat zones cannot read a valid temperature.'),
            'details': details,
        }
    if not state['last_cycle']:
        return {
            'status': 'unknown',
            'summary': _('Thermostat is waiting for its first control cycle.'),
            'details': details,
        }
    return {
        'status': 'ok',
        'summary': _('Thermostat is responding.'),
        'details': details,
    }


def mobile_status():
    result = health()
    return {'status': result.get('status', 'unknown'),
            'title': _('Thermostat'), 'summary': result.get('summary', ''),
            'updated': datetime_string()}


def mobile_cards(**_kwargs):
    result = health()
    metrics = [
        {'id': 'thermostat_{}'.format(index), 'label': label,
         'value': value, 'unit': ''}
        for index, (label, value) in enumerate(result.get('details', {}).items())
    ]
    return [{'id': 'thermostat_status', 'kind': 'metrics',
             'title': _('Thermostat zones'), 'metrics': metrics}]


def template_data():
    zones = _normalize_zones()
    return {
        'sources': [
            ('air_temp', source_title('air_temp')),
            ('ospy_sensor', source_title('ospy_sensor')),
            ('shelly_cloud', source_title('shelly_cloud')),
        ],
        'shelly_value_types': [(value_type, shelly_value_label(value_type)) for value_type in SHELLY_VALUE_TYPES],
        'programs': programs.get(),
        'channels': {
            'air_temp': get_air_temp_channel_names(),
            'ospy_sensor': get_sensor_channel_names(),
            'shelly_cloud': get_shelly_channel_names(),
        },
        'max_thermostats': MAX_THERMOSTATS,
        'new_zone': model.default_zone(_('New thermostat')),
        'can_add': len(zones) < MAX_THERMOSTATS,
    }


def _zone_from_input(qdict, existing=None):
    zones = _normalize_zones()
    raw = dict(existing or model.default_zone(_('New thermostat')))
    raw.update({
        'id': str(qdict.get('zone_id') or raw.get('id') or uuid.uuid4().hex),
        'enabled': 'enabled' in qdict,
        'name': str(qdict.get('name', raw['name'])).strip()[:120],
        'source': qdict.get('source', raw['source']),
        'channel': qdict.get('channel', raw['channel']),
        'value_type': qdict.get('value_type', raw['value_type']),
        'low_temp': qdict.get('low_temp', raw['low_temp']),
        'high_temp': qdict.get('high_temp', raw['high_temp']),
        'low_action': qdict.get('low_action', raw['low_action']),
        'high_action': qdict.get('high_action', raw['high_action']),
        'program': qdict.get('program', raw['program']),
        'time_limited': 'time_limited' in qdict,
        'start_time': qdict.get('start_time', raw['start_time']),
        'end_time': qdict.get('end_time', raw['end_time']),
    })
    if not raw['name']:
        raise ValueError(_('Enter a thermostat name.'))
    if raw['time_limited'] and (
            not model.valid_time(str(raw['start_time']))
            or not model.valid_time(str(raw['end_time']))):
        raise ValueError(_('Enter valid operating times.'))
    zone = model.normalize_zone(
        raw, raw['name'], len(programs.get()), lambda: uuid.uuid4().hex)
    if not programs.get() and zone['enabled']:
        raise ValueError(_('Create an OSPy program before enabling this thermostat.'))
    try:
        model.validate_zone(zone)
    except ValueError as error:
        if str(error) == 'invalid temperature limits':
            raise ValueError(_('Low temperature must be lower than high temperature.'))
        if str(error) == 'empty time window':
            raise ValueError(_('Start and end time must be different when operating time is enabled.'))
        raise ValueError(_('Enter valid operating times.'))
    if model.duplicate_enabled_program(zones, zone):
        raise ValueError(_('Each enabled thermostat must use a different program.'))
    return zone


class settings_page(ProtectedPage):
    """Load an html page for entering thermostat settings."""

    def GET(self):
        request = web.input(open='')
        return self.plugin_render.thermostat(
            plugin_options, log.events(NAME), template_data(), '',
            str(request.get('open', '')))

    def POST(self):
        qdict = web.input()
        verify_csrf(qdict)
        default_action = 'save_zone' if qdict.get('form_kind') == 'zone' else 'save_settings'
        action = str(qdict.get('action', default_action))
        open_zone = str(qdict.get('zone_id', ''))
        try:
            zones = _normalize_zones()
            if action == 'save_settings':
                was_enabled = plugin_options['enabled']
                plugin_options['enabled'] = 'enabled' in qdict
                plugin_options['use_footer'] = 'use_footer' in qdict
                plugin_options['check_interval'] = _clamp(_safe_int(qdict.get('check_interval', plugin_options['check_interval']), 30), MIN_CHECK_INTERVAL, MAX_CHECK_INTERVAL)
                if was_enabled and not plugin_options['enabled']:
                    for zone in zones:
                        if zone['enabled']:
                            stop_program(zone['program'])
                open_zone = ''
            elif action == 'save_zone':
                existing = next((zone for zone in zones if zone['id'] == open_zone), None)
                if existing is None and len(zones) >= MAX_THERMOSTATS:
                    raise ValueError(_('A maximum of {} thermostats can be configured.').format(MAX_THERMOSTATS))
                saved = _zone_from_input(qdict, existing)
                if existing is not None:
                    local_time = time.localtime()
                    now_minutes = local_time.tm_hour * 60 + local_time.tm_min
                    if existing['enabled'] and (
                            not saved['enabled']
                            or existing['program'] != saved['program']
                            or not model.zone_in_time_window(saved, now_minutes)):
                        stop_program(existing['program'])
                    zones[zones.index(existing)] = saved
                else:
                    zones.append(saved)
                plugin_options['zones'] = zones
                open_zone = saved['id']
            elif action == 'delete_zone':
                existing = next((zone for zone in zones if zone['id'] == open_zone), None)
                if existing is not None:
                    if existing['enabled']:
                        stop_program(existing['program'])
                    plugin_options['zones'] = [zone for zone in zones if zone['id'] != open_zone]
                open_zone = ''
            else:
                raise ValueError(_('Unknown thermostat settings action.'))
        except ValueError as error:
            web.ctx.status = '400 Bad Request'
            return self.plugin_render.thermostat(
                plugin_options, log.events(NAME), template_data(), str(error),
                open_zone)
        if checker is not None:
            checker.update()
        target = plugin_url(settings_page)
        if open_zone:
            target += '?open=' + open_zone
        raise web.seeother(target, True)


class help_page(ProtectedPage):
    """Load an html page for help."""

    def GET(self):
        return self.plugin_render.thermostat_help()


class settings_json(ProtectedPage):
    """Returns plugin settings in JSON format."""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        return json.dumps(plugin_options)
