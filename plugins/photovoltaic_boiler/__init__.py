# -*- coding: utf-8 -*-
__author__ = 'Martin Pihrt'

import json
import time
import datetime
import traceback
import os
from threading import Thread, Lock

import web
import plugins as plugin_manager

from ospy.options import options
from ospy.log import log
from plugins import PluginOptions, plugin_url, plugin_data_dir, get_runtime
from ospy.webpages import ProtectedPage
from ospy.helpers import get_rpi_revision, verify_csrf
from ospy.helpers import datetime_string
from ospy import helpers
from ospy.stations import stations
from ospy.sensors import sensors

from ospy.webpages import showInFooter # Enable plugin to display readings in UI footer
#from ospy.webpages import showOnTimeline # Enable plugin to display station data on timeline


NAME = 'Photovoltaic Boiler'
MENU =  _('Package: Photovoltaic Boiler')
LINK = 'settings_page'
MAIN_LOOP_SLEEP = 1
SENSOR_REFRESH_INTERVAL = 30
STATUS_LOG_INTERVAL = 30
ERROR_LOG_THROTTLE = 300


plugin_options = PluginOptions(
    NAME,
    {
    'enabled_a': False,   # enable or disable regulation
    'probe_A_on': 0,      # for selector temperature probe ON (0-5)
    'temp_a_on': 45,      # temperature for output ON
    'control_output_A': 0,# selector for output (0 to station count)
    'start_hh': 19,       # hour for start
    'start_mm': 30,       # minute for start
    'stop_hh': 23,        # hour for stop
    'stop_mm': 0,         # minute for stop
    'two_time': True,     # next time for start and stop
    'start_hh_2': 13,     # hour for start2
    'start_mm_2': 0,      # minute for start2
    'stop_hh_2': 18,      # hour for stop2
    'stop_mm_2': 30,      # minute for stop2       
    'probe_A_on_sens': 0, # for selector from sensors xx - temperature ON
    'sensor_probe': 0,    # selector for type probes: 0=none, 1=sensors, 2=air temp plugin
    'use_footer': True,   # show data from plugin in footer on home page
    }
)


global status
_last_error_log = {}
runtime = get_runtime()
health_lock = Lock()
health_state = {
    'last_cycle': 0,
    'last_temperature': None,
    'regulation_enabled': False,
    'output': '',
    'state': '',
    'last_error': 0,
    'last_error_message': '',
}

def plugin_is_running(module):
    try:
        return module in plugin_manager.running()
    except Exception:
        return False


def log_boiler_problem(key, message):
    now = time.time()
    last = _last_error_log.get(key, 0)
    if now - last >= ERROR_LOG_THROTTLE:
        _last_error_log[key] = now
        log.error(NAME, message)


def selected_station():
    try:
        index = int(plugin_options['control_output_A'])
        if index < 0 or index >= stations.count():
            return None
        return stations.get(index)
    except Exception:
        return None

################################################################################
# Main function loop:                                                          #
################################################################################


class Sender(Thread):
    
    def __init__(self):
        Thread.__init__(self)
        self.daemon = True
        self._stop_event = runtime.stop_event

        self.status = {}

        self._sleep_time = 0
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

    def _try_read(self, val):
        try:
            return val
        except:
            pass
            return -127.0

    def run(self):
        temperature_ds = [-127,-127,-127,-127,-127,-127]
        msg_a_on = True
        send = False
        temp_sw = None

        if plugin_options['use_footer']:
            temp_sw = showInFooter() #  instantiate class to enable data in footer
            temp_sw.button = "photovoltaic_boiler/settings"   # button redirect on footer
            temp_sw.label =  _('Photovoltaic Boiler')         # label on footer

        ds_a_on  = -127.0

        millis = 0                                 # timer for clearing status on the web pages after 5 sec
        last_millis = int(round(time.time() * 1000))
        last_sensor_refresh = 0

        a_state = -3                               # for state in footer "Waiting."
        regulation_text = _('Waiting to turned on or off.')

        if not plugin_options['enabled_a']:
            a_state = -1                           # for state in footer "Waiting (not enabled regulation in options)."

        log.info(NAME, datetime_string() + ' ' + _('Waiting.'))
        end = datetime.datetime.now()

        while not self._stop_event.is_set():
            try:
                if plugin_options["sensor_probe"] == 2 and time.time() - last_sensor_refresh >= SENSOR_REFRESH_INTERVAL: # loading probe name from plugin air_temp_humi
                    try:
                        last_sensor_refresh = time.time()
                        if not plugin_is_running('air_temp_humi'):
                            raise Exception(_('The plug-in is not running.'))
                        from plugins.air_temp_humi import plugin_options as air_temp_data
                        self.status['ds_name_0'] = air_temp_data['label_ds0']
                        self.status['ds_name_1'] = air_temp_data['label_ds1']
                        self.status['ds_name_2'] = air_temp_data['label_ds2']
                        self.status['ds_name_3'] = air_temp_data['label_ds3']
                        self.status['ds_name_4'] = air_temp_data['label_ds4']
                        self.status['ds_name_5'] = air_temp_data['label_ds5']
                        self.status['ds_count']  = air_temp_data['ds_used']

                        from plugins.air_temp_humi import DS18B20_read_probe           # value with temperature from probe DS1-DS6
                        temperature_ds = [DS18B20_read_probe(0), DS18B20_read_probe(1), DS18B20_read_probe(2), DS18B20_read_probe(3), DS18B20_read_probe(4), DS18B20_read_probe(5)]

                    except:
                        log_boiler_problem('air_temp_humi', _('Unable to load settings from Air Temperature and Humidity Monitor plugin! Is the plugin Air Temperature and Humidity Monitor installed and set up?'))
                        self.status['ds_count'] = 0
                        pass

                # regulation
                if plugin_options['enabled_a'] and plugin_options["sensor_probe"] != 0:# enabled regulation and selected input for probes sensor/airtemp plugin
                    if plugin_options["sensor_probe"] == 1 and sensors.count()>0:
                        sensor_on = sensors.get(int(plugin_options['probe_A_on_sens']))
                        if sensor_on.sens_type == 5:                                   # temperature sensor
                            ds_a_on = self._try_read(sensor_on.last_read_value)
                        elif sensor_on.sens_type == 6 and sensor_on.multi_type == 0:   # multitemperature sensor DS1
                            ds_a_on = self._try_read(sensor_on.last_read_value[0])
                        elif sensor_on.sens_type == 6 and sensor_on.multi_type == 1:   # multitemperature sensor DS2
                            ds_a_on = self._try_read(sensor_on.last_read_value[1])
                        elif sensor_on.sens_type == 6 and sensor_on.multi_type == 2:   # multitemperature sensor DS3
                            ds_a_on = self._try_read(sensor_on.last_read_value[2])
                        elif sensor_on.sens_type == 6 and sensor_on.multi_type == 3:   # multitemperature sensor DS4
                            ds_a_on = self._try_read(sensor_on.last_read_value[3])
                        else:
                            ds_a_on = -127.0

                        if isinstance(ds_a_on, (str)):
                            ds_a_on = -127.0

                    elif plugin_options["sensor_probe"] == 2:
                        ds_a_on = temperature_ds[plugin_options['probe_A_on']]         # air temp sensor
                        
                    station_a = selected_station()
                    if station_a is None:
                        raise Exception(_('Selected output is not available.'))

                    # only for testing!
                    #ds_a_on = 22.0

                    probes_ok = True
                    if ds_a_on == -127.0:
                        probes_ok = False
                        #a_state = -2
                        # The station switches off if the sensors has a fault
                        #sid = station_a.index
                        #active = log.active_runs()
                        #for interval in active:
                        #    if interval['station'] == sid:
                        #        stations.deactivate(sid)
                        #        log.finish_run(interval)
                        #        regulation_text = datetime_string() + ' ' + _('Regulation set OFF.') + ' ' + ' (' + _('Output') + ' ' +  str(station_a.index+1) + ').'
                        #        log.clear(NAME)
                        #        log.info(NAME, regulation_text)
                        #msg_a_on = True

                    current_time  = datetime.datetime.now()

                    ### first time
                    start_ok = False
                    stop_ok = False
                    if int(current_time.hour) == int(plugin_options['start_hh']):
                        if int(current_time.minute) == int(plugin_options['start_mm']):
                            start_ok = True

                    if int(current_time.hour) == int(plugin_options['stop_hh']):
                        if int(current_time.minute) == int(plugin_options['stop_mm']):
                            stop_ok = True

                    ### second time
                    start_2_ok = False
                    stop_2_ok = False
                    if int(current_time.hour) == int(plugin_options['start_hh_2']):
                        if int(current_time.minute) == int(plugin_options['start_mm_2']):
                            if plugin_options['two_time']:
                                start_2_ok = True

                    if int(current_time.hour) == int(plugin_options['stop_hh_2']):
                        if int(current_time.minute) == int(plugin_options['stop_mm_2']):
                            if plugin_options['two_time']:
                                stop_2_ok = True

                    if int(ds_a_on) < int(plugin_options['temp_a_on']) and probes_ok:
                        if start_ok or start_2_ok: # ON
                            a_state = 1
                            if msg_a_on:
                                msg_a_on = False
                                regulation_text = datetime_string() + ' ' + _('Regulation set ON.') + ' ' + ' (' + _('Output') + ' ' +  str(station_a.index+1) + ').'
                                log.clear(NAME) 
                                log.info(NAME, regulation_text)
                                start = datetime.datetime.now()
                                sid = station_a.index
                                dif_h = plugin_options['stop_hh'] - current_time.hour
                                dif_m = plugin_options['stop_mm'] - current_time.minute
                                dif_h_2 = plugin_options['stop_hh_2'] - current_time.hour
                                dif_m_2 = plugin_options['stop_mm_2'] - current_time.minute
                                if plugin_options['two_time']:
                                    if start_ok:
                                        end = datetime.datetime.now() + datetime.timedelta(hours=dif_h, minutes=dif_m)
                                    if start_2_ok:
                                        end = datetime.datetime.now() + datetime.timedelta(hours=dif_h_2, minutes=dif_m_2)
                                else:
                                    end = datetime.datetime.now() + datetime.timedelta(hours=dif_h, minutes=dif_m)
                                new_schedule = {
                                    'active': True,
                                    'program': -1,
                                    'station': sid,
                                    'program_name': _('Photovoltaic Boiler'),
                                    'fixed': True,
                                    'cut_off': 0,
                                    'manual': True,
                                    'blocked': False,
                                    'start': start,
                                    'original_start': start,
                                    'end': end,
                                    'uid': '%s-%s-%d' % (str(start), "Manual", sid),
                                    'usage': stations.get(sid).usage
                                }
                                log.start_run(new_schedule)
                                stations.activate(new_schedule['station'])
                    else:
                        msg_a_on = True

                    ### if "boiler" end in schedule release msg_a_on to true in regulation for next scheduling ###
                    if current_time > end:
                        if probes_ok:
                            a_state = -3
                        if not msg_a_on:
                            sid = station_a.index
                            stations.deactivate(sid)
                            active = log.active_runs()
                            for interval in active:
                                if interval['station'] == sid:
                                    log.finish_run(interval)
                        msg_a_on = True

                else:
                    a_state = -1

                # footer text
                tempText = ' '

                if a_state == 0:
                    tempText += regulation_text
                if a_state == 1:
                    tempText += regulation_text
                if a_state == -1:
                    tempText = _('Waiting (not enabled regulation in options, or not selected input).')
                if a_state == -2:
                    tempText = _('Some probe shows a fault, regulation is blocked!')
                if a_state == -3:
                    tempText = _('Waiting.')

                if plugin_options['use_footer']:
                    if temp_sw is not None:
                        temp_sw.val = tempText.encode('utf8').decode('utf8')    # value on footer

                station_a = selected_station()
                with health_lock:
                    health_state['last_cycle'] = time.time()
                    health_state['last_temperature'] = None if ds_a_on == -127.0 else ds_a_on
                    health_state['regulation_enabled'] = bool(plugin_options['enabled_a'])
                    health_state['output'] = (
                        str(station_a.index + 1) if station_a is not None else ''
                    )
                    health_state['state'] = tempText.strip()
                    health_state['last_error_message'] = ''

                millis = int(round(time.time() * 1000))
                if (millis - last_millis) > STATUS_LOG_INTERVAL * 1000:
                    last_millis = millis
                    log.clear(NAME)
                    if plugin_options["sensor_probe"] == 1:
                        try:
                            if options.temp_unit == 'C':
                                log.info(NAME, datetime_string() + '\n' + sensor_on.name + ' (' + _('Boiler') + ') %.1f \u2103 \n' % ds_a_on)
                            else:
                                log.info(NAME, datetime_string() + '\n' + sensor_on.name + ' (' + _('Boiler') + ') %.1f \u2109 \n' % ds_a_on)
                        except:
                            pass
                    elif plugin_options["sensor_probe"] == 2:
                        log.info(NAME, datetime_string() + '\n' + _('Boiler') + ' %.1f \u2103 \n' % ds_a_on)
                    log.info(NAME, tempText)

                self._sleep(MAIN_LOOP_SLEEP)

            except Exception:
                message = traceback.format_exc().splitlines()[-1]
                with health_lock:
                    health_state['last_error'] = time.time()
                    health_state['last_error_message'] = message
                log_boiler_problem('run_loop', _('Photovoltaic Boiler plug-in') + ': ' + message)
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
        if sender.is_alive():
            log.error(NAME, _('The plug-in worker did not stop within the timeout.'))
        else:
            sender = None
        ### we stop the running output if the plugin exits
        station_a = selected_station()
        if station_a is None:
            return
        sid = station_a.index
        active = log.active_runs()
        for interval in active:
            if interval['station'] == sid and interval.get('program_name') == _('Photovoltaic Boiler'):
                stations.deactivate(sid)
                log.finish_run(interval)


def health():
    """Return regulation, temperature and worker state for diagnostics."""
    with health_lock:
        state = dict(health_state)
    worker_running = sender is not None and sender.is_alive()
    details = {
        _('Worker thread'): _('Running') if worker_running else _('Stopped'),
        _('Regulation enabled'): _('Yes') if state['regulation_enabled'] else _('No'),
        _('Selected output'): state['output'] or _('Not available'),
        _('Temperature'): (
            '{:.1f}'.format(state['last_temperature'])
            if state['last_temperature'] is not None else _('Not available')
        ),
        _('Regulation state'): state['state'] or _('Not available'),
        _('Last successful cycle'): (
            datetime_string(time.localtime(state['last_cycle']))
            if state['last_cycle'] else _('Not available')
        ),
    }
    if state['last_error_message']:
        details[_('Last error')] = state['last_error_message']
    if not worker_running:
        return {
            'status': 'error',
            'summary': _('Photovoltaic Boiler worker is not running.'),
            'details': details,
        }
    if state['last_error'] and state['last_error'] >= state['last_cycle']:
        return {
            'status': 'error',
            'summary': state['last_error_message'],
            'details': details,
        }
    if not state['last_cycle']:
        return {
            'status': 'unknown',
            'summary': _('Photovoltaic Boiler is waiting for its first control cycle.'),
            'details': details,
        }
    if state['regulation_enabled'] and state['last_temperature'] is None:
        return {
            'status': 'warning',
            'summary': _('The configured boiler temperature is not available.'),
            'details': details,
        }
    return {
        'status': 'ok',
        'summary': _('Photovoltaic Boiler is responding.'),
        'details': details,
    }


################################################################################
# Web pages:                                                                   #
################################################################################

class settings_page(ProtectedPage):
    """Load an html page for entering adjustments and deleting logs"""

    def GET(self):
        try:
            global sender
            if sender is not None:
                sender.update()
            status = sender.status if sender is not None else {}
            return self.plugin_render.photovoltaic_boiler(plugin_options, log.events(NAME), status)
        except:
            log.error(NAME, _('Photovoltaic Boiler plug-in') + ':\n' + traceback.format_exc())
            msg = _('An internal error was found in the system, see the error log for more information. The error is in part:') + ' '
            msg += _('photovoltaic_boiler -> settings_page GET')
            return self.core_render.notice('/', msg)

    def POST(self):
        try:
            global sender
            qdict = web.input()
            verify_csrf(qdict)
            plugin_options.web_update(qdict)
            if sender is not None:
                sender.update()
            raise web.seeother(plugin_url(settings_page), True)
        except:
            log.error(NAME, _('Photovoltaic Boiler plug-in') + ':\n' + traceback.format_exc())
            msg = _('An internal error was found in the system, see the error log for more information. The error is in part:') + ' '
            msg += _('photovoltaic_boiler -> settings_page POST')
            return self.core_render.notice('/', msg)


class help_page(ProtectedPage):
    """Load an html page for help"""

    def GET(self):
        try:
            return self.plugin_render.photovoltaic_boiler_help()
        except:
            log.error(NAME, _('Photovoltaic Boiler plug-in') + ':\n' + traceback.format_exc())
            msg = _('An internal error was found in the system, see the error log for more information. The error is in part:') + ' '
            msg += _('photovoltaic_boiler -> help_page GET')
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
