# -*- coding: utf-8 -*-
__author__ = 'Martin Pihrt'

import json
import time
import traceback
from threading import Thread, Event

import web

from ospy.helpers import datetime_string, verify_csrf
from ospy.log import log
from ospy.options import options
from ospy.programs import programs
from ospy.stations import stations
from ospy.webpages import ProtectedPage, showInFooter, clear_plugin_runtime_data
from plugins import PluginOptions, plugin_url

try:
    from ospy.sensors import sensors
except Exception:
    sensors = None


NAME = 'Thermostat'
MENU = _('Package: Thermostat')
LINK = 'settings_page'

THERMOSTAT_COUNT = 3
INVALID_TEMPERATURE = -127
SHELLY_VALUE_TYPES = [
    'temperature',
    'temperature_2',
    'temperature_3',
    'temperature_4',
    'temperature_5',
]

DEFAULT_ZONES = [
    {
        'enabled': False,
        'name': 'Thermostat 1',
        'source': 'air_temp',
        'channel': 0,
        'value_type': 'temperature',
        'low_temp': 22.4,
        'high_temp': 22.6,
        'low_action': 'start',
        'high_action': 'stop',
        'program': 0,
    },
    {
        'enabled': False,
        'name': 'Thermostat 2',
        'source': 'air_temp',
        'channel': 1,
        'value_type': 'temperature',
        'low_temp': 22.4,
        'high_temp': 22.6,
        'low_action': 'start',
        'high_action': 'stop',
        'program': 0,
    },
    {
        'enabled': False,
        'name': 'Thermostat 3',
        'source': 'air_temp',
        'channel': 2,
        'value_type': 'temperature',
        'low_temp': 22.4,
        'high_temp': 22.6,
        'low_action': 'start',
        'high_action': 'stop',
        'program': 0,
    },
]

plugin_options = PluginOptions(
    NAME,
    {
        'enabled': False,
        'check_interval': 30,
        'use_footer': False,
        'zones': [dict(zone) for zone in DEFAULT_ZONES],
    }
)


def _safe_int(value, default=0):
    try:
        return int(value)
    except Exception:
        return default


def _safe_float(value, default=0.0):
    try:
        return float(str(value).replace(',', '.'))
    except Exception:
        return default


def _normalize_zones():
    zones = plugin_options.get('zones', [])
    if not isinstance(zones, list):
        zones = []

    normalized = []
    for index in range(THERMOSTAT_COUNT):
        base = dict(DEFAULT_ZONES[index])
        if index < len(zones) and isinstance(zones[index], dict):
            base.update(zones[index])
        base['enabled'] = bool(base.get('enabled', False))
        base['name'] = str(base.get('name') or _('Thermostat {}').format(index + 1))
        base['source'] = str(base.get('source') or 'air_temp')
        if base['source'] not in ('air_temp', 'ospy_sensor', 'shelly_cloud'):
            base['source'] = 'air_temp'
        base['channel'] = max(0, _safe_int(base.get('channel'), 0))
        base['value_type'] = str(base.get('value_type') or 'temperature')
        if base['value_type'] not in SHELLY_VALUE_TYPES:
            base['value_type'] = 'temperature'
        base['low_temp'] = _safe_float(base.get('low_temp'), 22.4)
        base['high_temp'] = _safe_float(base.get('high_temp'), 22.6)
        base['low_action'] = str(base.get('low_action') or 'start')
        base['high_action'] = str(base.get('high_action') or 'stop')
        if base['low_action'] not in ('none', 'start', 'stop'):
            base['low_action'] = 'start'
        if base['high_action'] not in ('none', 'start', 'stop'):
            base['high_action'] = 'stop'
        base['program'] = max(0, _safe_int(base.get('program'), 0))
        normalized.append(base)

    if normalized != zones:
        plugin_options['zones'] = normalized
    return normalized


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
        log.debug(NAME, traceback.format_exc())
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


def start_program(index):
    if not program_exists(index):
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
        and list(getattr(run_now, 'stations', [])) == list(getattr(target, 'stations', []))
        and list(getattr(run_now, 'schedule', [])) == list(getattr(target, 'schedule', []))
    )


def stop_program(index):
    if not program_exists(index):
        return False

    stop_run_now = run_now_program_matches(index)
    target_run_now_name = '{} {}'.format(_('Run-Now'), programs.get(index).name)
    if stop_run_now:
        programs.run_now_program = None

    stopped = stop_run_now
    for interval in log.active_runs():
        if interval.get('program') == index or (stop_run_now and interval.get('program_name') == target_run_now_name):
            stations.deactivate(interval['station'])
            log.finish_run(interval)
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
        self._stop_event = Event()
        self._sleep_time = 0
        self.zone_state = ['unknown'] * THERMOSTAT_COUNT
        self.footer = None
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

    def run(self):
        disabled_text = True
        while not self._stop_event.is_set():
            try:
                _normalize_zones()
                if not plugin_options['enabled']:
                    if disabled_text:
                        log.clear(NAME)
                        log.info(NAME, _('Thermostat plug-in is disabled.'))
                        self.update_footer(_('Disabled'))
                        disabled_text = False
                    self._sleep(60)
                    continue

                disabled_text = True
                footer_parts = []
                for index, zone in enumerate(plugin_options['zones']):
                    if not zone['enabled']:
                        self.zone_state[index] = 'disabled'
                        continue

                    if zone['low_temp'] >= zone['high_temp']:
                        log.info(NAME, datetime_string() + ' ' + _('{} has invalid temperature limits. Low temperature must be lower than high temperature.').format(zone['name']))
                        footer_parts.append('{} {}'.format(zone['name'], _('setup error')))
                        continue

                    temperature = get_temperature(zone['source'], zone['channel'], zone['value_type'])
                    if temperature == INVALID_TEMPERATURE:
                        log.info(NAME, datetime_string() + ' ' + _('{} temperature is not available.').format(zone['name']))
                        footer_parts.append('{} ---'.format(zone['name']))
                        continue

                    new_state = self.zone_state[index]
                    action = None
                    if temperature >= zone['high_temp']:
                        new_state = 'high'
                        action = zone['high_action']
                    elif temperature <= zone['low_temp']:
                        new_state = 'low'
                        action = zone['low_action']
                    elif self.zone_state[index] in ('unknown', 'disabled'):
                        new_state = 'hold'

                    footer_parts.append('{} {:.1f}C'.format(zone['name'], temperature))

                    if new_state != self.zone_state[index]:
                        self.zone_state[index] = new_state
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

                self._sleep(max(5, int(plugin_options['check_interval'])))
            except Exception:
                log.error(NAME, _('Thermostat plug-in') + ':\n' + traceback.format_exc())
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
        checker = None
    clear_plugin_runtime_data('thermostat')


def template_data():
    _normalize_zones()
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
    }


class settings_page(ProtectedPage):
    """Load an html page for entering thermostat settings."""

    def GET(self):
        return self.plugin_render.thermostat(plugin_options, log.events(NAME), template_data())

    def POST(self):
        qdict = web.input()
        verify_csrf(qdict)
        zones = []
        for index, default_zone in enumerate(plugin_options['zones']):
            zone = dict(default_zone)
            zone['enabled'] = 'enabled{}'.format(index) in qdict
            zone['name'] = qdict.get('name{}'.format(index), zone['name'])
            zone['source'] = qdict.get('source{}'.format(index), zone['source'])
            zone['channel'] = _safe_int(qdict.get('channel{}'.format(index), zone['channel']), zone['channel'])
            zone['value_type'] = qdict.get('value_type{}'.format(index), zone['value_type'])
            zone['low_temp'] = _safe_float(qdict.get('low_temp{}'.format(index), zone['low_temp']), zone['low_temp'])
            zone['high_temp'] = _safe_float(qdict.get('high_temp{}'.format(index), zone['high_temp']), zone['high_temp'])
            zone['low_action'] = qdict.get('low_action{}'.format(index), zone['low_action'])
            zone['high_action'] = qdict.get('high_action{}'.format(index), zone['high_action'])
            zone['program'] = _safe_int(qdict.get('program{}'.format(index), zone['program']), zone['program'])
            zones.append(zone)

        plugin_options['enabled'] = 'enabled' in qdict
        plugin_options['use_footer'] = 'use_footer' in qdict
        plugin_options['check_interval'] = max(5, _safe_int(qdict.get('check_interval', plugin_options['check_interval']), 30))
        plugin_options['zones'] = zones
        _normalize_zones()
        if checker is not None:
            checker.update()
        raise web.seeother(plugin_url(settings_page), True)


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
