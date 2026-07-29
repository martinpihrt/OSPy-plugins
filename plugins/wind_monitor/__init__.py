# -*- coding: utf-8 -*-
__author__ = 'Martin Pihrt'
# This plugins check wind speed in meter per second. 
# This plugin read data from I2C counter PCF8583 on I2C address 0x50. Max count PCF8583 is 1 milion pulses per seconds

import json
import time as time_
import datetime
import time
import sys
import traceback
import os
import mimetypes

from collections import deque
from threading import Thread, Lock

import web
from ospy.stations import stations
from ospy.options import options
from ospy.log import log, logEM
from plugins import PluginOptions, plugin_url, plugin_data_dir, get_runtime
from ospy.webpages import ProtectedPage, clear_plugin_runtime_data
from ospy.helpers import datetime_string, verify_csrf
from ospy import helpers
from ospy.i2c_guard import i2c_transaction
from ospy.scheduler import predicted_schedule, combined_schedule
from ospy.programs import programs

from ospy.webpages import showInFooter # Enable plugin to display readings in UI footer
from .methods import (
    calculate_speed,
    calculate_trend,
    decode_bcd_counter,
    parse_decimal,
    update_confirmation,
    validate_measurement,
)


NAME = 'Wind Speed Monitor'
MENU =  _('Package: Wind Speed Monitor')
LINK = 'overview_page'
MEASUREMENT_SECONDS = 10.0
DIAGNOSTIC_LOG_NAME = 'diagnostic.log'
DIAGNOSTIC_LOG_BACKUP_NAME = 'diagnostic.log.1'
DIAGNOSTIC_LOG_MAX_BYTES = 1024 * 1024
DIAGNOSTIC_LOG_LINES = 500

wind_options = PluginOptions(
    NAME,
    {
        'use_wind_monitor': False,
        'address': False,            # True = 0x51, False = 0x50 for PCF8583
        'sendeml': True,             # True = send email with error
        'pulses': 2.0,               # 2 pulses per rotation
        'metperrot': 1.492,          # 1.492 meter per hour per rotation
        'maxspeed': 20.0,            # 20 max speed to deactivate stations
        'emlsubject': _('Report from OSPy WIND SPEED MONITOR plugin'),
        'enable_log': False,         # log to file and graph
        'log_interval': 1,           # log interval in minutes
        'log_records': 0,            # log records 0= unlimited 
        'use_kmh': False,            # measure in km/h or m/s
        'enable_log_change': False,  # enable save log max speed if max wind > last max wind
        'delete_max_24h': False,     # deleting max speed after xx hours or minutes
        'delete_max': '24h',         # 24 hours is default interval for deleting maximal speed
        'stoperr': False,            # True = stoping is enabled
        'used_stations': [],         # use this stations for stoping scheduler if stations is activated in scheduler
        'use_footer': True,          # show data from plugin in footer on home page
        'eplug': 0,                  # email plugin type (email notifications or email notifications SSL)
        'use_stop_pgm': False,       # run the program when exceeded
        'm_speed_trig': 10.0,        # maximum wind speed for starting the program in m/s
        'event_repetitions': 3,      # number of event repetitions for the action (3x repeating)
        'event_interval': 1,         # repeatedly exceeded in these interval (minutes)
        'ignore_interval': 24,       # ignore other events for a while (24 hours)
        'used_program': [],          # selector for running program (-1 is none)
        'en_sql_log': False,         # logging temperature to sql database
        'type_log': 0,               # 0 = show log and graph from local log file, 1 = from database
        'dt_from' : '2024-01-01T00:00',              # for graph history (from date time ex: 2024-02-01T6:00)
        'dt_to' : '2024-01-01T00:00',                # for graph history (to date time ex: 2024-03-17T12:00)        
        'diagnostic_logging': False,
        'filter_invalid': True,
        'max_accepted_speed': 40.0,
        'action_confirmations': 2,
    }
)

# Preserve numeric settings written by older releases with integer defaults.
try:
    _stored_wind_options = options.get(wind_options._plugin, {})
    for _numeric_key in ('pulses', 'metperrot', 'maxspeed', 'm_speed_trig'):
        if _numeric_key in _stored_wind_options:
            wind_options[_numeric_key] = float(
                str(_stored_wind_options[_numeric_key]).replace(',', '.'))
except (AttributeError, TypeError, ValueError):
    pass

runtime = get_runtime()
health_lock = Lock()
diagnostic_lock = Lock()
health_state = {
    'last_reading': 0,
    'last_email': 0,
    'last_action': 0,
    'last_error': 0,
    'last_error_message': '',
    'last_rejected': 0,
    'rejected_count': 0,
}


def wind_i2c_transaction(timeout=30.0, settle_time=0.02):
    try:
        return i2c_transaction(timeout=timeout, settle_time=settle_time, priority='high')
    except TypeError:
        return i2c_transaction(timeout=timeout, settle_time=settle_time)


def _diagnostic_path(backup=False):
    name = DIAGNOSTIC_LOG_BACKUP_NAME if backup else DIAGNOSTIC_LOG_NAME
    return os.path.join(plugin_data_dir('wind_monitor'), name)


def diagnostic_event(event, **values):
    if not wind_options.get('diagnostic_logging', False):
        return
    record = {
        'time': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3],
        'event': str(event),
    }
    record.update(values)
    line = json.dumps(record, ensure_ascii=False, sort_keys=True)
    try:
        with diagnostic_lock:
            path = _diagnostic_path()
            if os.path.exists(path) and os.path.getsize(path) >= DIAGNOSTIC_LOG_MAX_BYTES:
                backup = _diagnostic_path(True)
                try:
                    if os.path.exists(backup):
                        os.remove(backup)
                    os.replace(path, backup)
                except OSError:
                    pass
            with open(path, 'a', encoding='utf-8') as output:
                output.write(line + '\n')
    except OSError:
        pass


def read_diagnostic_log(limit=DIAGNOSTIC_LOG_LINES):
    lines = []
    with diagnostic_lock:
        for path in (_diagnostic_path(True), _diagnostic_path()):
            try:
                with open(path, encoding='utf-8', errors='replace') as source:
                    lines.extend(source.readlines())
            except OSError:
                continue
    if limit is None:
        selected = lines
    else:
        selected = lines[-max(1, int(limit)):]
    return [line.rstrip() for line in selected]


def clear_diagnostic_log():
    with diagnostic_lock:
        for path in (_diagnostic_path(), _diagnostic_path(True)):
            try:
                os.remove(path)
            except OSError:
                pass


################################################################################
# Main function loop:                                                          #
################################################################################

class WindSender(Thread):
    def __init__(self):
        Thread.__init__(self)
        self.daemon = True
        self._stop_event = runtime.stop_event
        self.bus = None
   
        self.status = {}
        self.status['meter'] = 0.0
        self.status['kmeter'] = 0.0
        self.status['max_meter'] = 0
        self.status['log_date_maxspeed'] = datetime_string()
        self.status['trend'] = 'unknown'
        self.status['last_measurement'] = ''
        self.status['last_raw_pulses'] = 0
        self.status['last_pulse_rate'] = 0.0
        self.status['last_elapsed'] = 0.0
        self.status['last_rejected_reason'] = ''
        self.status['action_confirmation_count'] = 0
        self._trend_samples = deque(maxlen=12)

        self._sleep_time = 0
        self._last_error_log = 0
        self._last_rejected_log = 0
        self.start()
        runtime.register_thread(self)

    def stop(self):
        self._stop_event.set()

    def update(self):
        self._sleep_time = 0

    def _sleep(self, secs):
        self._sleep_time = secs
        while self._sleep_time > 0 and not self._stop_event.is_set():
            time_.sleep(1)
            self._sleep_time -= 1

    def _log_problem(self, message):
        now = time_.time()
        with health_lock:
            health_state['last_error'] = now
            health_state['last_error_message'] = str(message).splitlines()[-1]
        if now - self._last_error_log >= 300:
            log.error(NAME, message)
            self._last_error_log = now

    def _open_bus(self):
        if self.bus is not None:
            return
        try:
            import smbus
            self.bus = smbus.SMBus(0 if helpers.get_rpi_revision() == 1 else 1)
        except ImportError:
            log.warning(NAME, _('Could not import smbus.'))
            self.bus = None

    def close_bus(self):
        bus = self.bus
        self.bus = None
        if bus is not None:
            try:
                bus.close()
            except (AttributeError, OSError):
                pass

    def run(self):
        millis = int(round(time_.time() * 1000))

        last_millis = millis                            # timer for save log
        last_clear_millis = millis                      # last clear millis for timer
        last_24h_millis = millis                        # deleting maximal spead after 24 hour

        last_ignore_interval_millis = millis            # timer ignore other events for a while (in running program section)
        last_event_interval = millis                    # timer repeatedly exceeded in these interval (in running program section)

        send = False                                    # send email
        disable_text = True
        val = 0
        en_del_24h = True
        wind_mon = None

        ignore_intervals = False
        trig_once = False
        last_trig_once = False
        trig_count = 0
        hazard_active = False
        action_confirmation_count = 0

        if wind_options['use_footer']:
            wind_mon = showInFooter() #  instantiate class to enable data in footer
            wind_mon.label = _('Wind Speed')           # label on footer
            wind_mon.val = '---'                        # value on footer
            wind_mon.button = "wind_monitor/overview"   # button redirect on footer

        while not self._stop_event.is_set():
            try:
                normalize_options()
                if wind_options['use_wind_monitor']:    # if wind plugin is enabled
                    disable_text = True
                    self._open_bus()
                    measurement = None
                    if self.bus is not None and set_counter(self.bus):
                        measurement = counter(self.bus, self._stop_event)

                    if measurement is not None:
                        raw_pulses = measurement['raw_pulses']
                        elapsed = measurement['elapsed']
                        pulse_rate, val = calculate_speed(
                            raw_pulses,
                            elapsed,
                            wind_options['pulses'],
                            wind_options['metperrot'],
                        )
                        accepted, rejected_reason = validate_measurement(
                            val,
                            wind_options['filter_invalid'],
                            wind_options['max_accepted_speed'],
                        )
                        self.status['last_raw_pulses'] = raw_pulses
                        self.status['last_pulse_rate'] = round(pulse_rate, 3)
                        self.status['last_elapsed'] = round(elapsed, 3)
                        self.status['last_measurement'] = datetime_string()
                        self.status['last_rejected_reason'] = rejected_reason
                        diagnostic_event(
                            'measurement',
                            address=measurement['address'],
                            raw_bytes=measurement['raw_bytes'],
                            raw_pulses=raw_pulses,
                            elapsed=round(elapsed, 6),
                            pulse_rate=round(pulse_rate, 6),
                            speed_mps=round(val, 6),
                            accepted=accepted,
                            reason=rejected_reason,
                        )
                        if not accepted:
                            action_confirmation_count = 0
                            self.status['action_confirmation_count'] = 0
                            with health_lock:
                                health_state['last_rejected'] = time_.time()
                                health_state['rejected_count'] += 1
                            if time_.time() - self._last_rejected_log >= 300:
                                log.warning(
                                    NAME,
                                    _('Wind measurement was rejected as implausible.')
                                    + ' %.2f m/s' % val)
                                self._last_rejected_log = time_.time()
                            self._sleep(1)
                            continue

                        with health_lock:
                            health_state['last_reading'] = time_.time()

                        self.status['meter']  = round(val*1.0, 2)
                        self.status['kmeter'] = round(val*3.6, 2)
                        now_monotonic = time_.monotonic()
                        self._trend_samples.append((now_monotonic, self.status['meter']))
                        self.status['trend'] = calculate_trend(list(self._trend_samples))

                        if self.status['meter'] > self.status['max_meter']:
                            self.status['max_meter'] = self.status['meter']
                            self.status['log_date_maxspeed'] = datetime_string()
                            if wind_options['enable_log_change']:
                                if wind_options['enable_log'] or wind_options['en_sql_log']: 
                                    update_log()

                        log.info(NAME, datetime_string())
                        if wind_options['use_kmh']:
                            log.info(NAME, _('Speed') + ': ' + '%.1f' % round(self.status['meter']*3.6, 2) + ' ' + _('km/h') + ', ' + _('Pulses') + ': ' + '%.3f' % pulse_rate + ' ' + _('pulses/sec'))
                        else:
                            log.info(NAME, _('Speed') + ': ' + '%.1f' % round(self.status['meter'], 2) + ' ' + _('m/sec') + ', ' + _('Pulses') + ': ' +  '%.3f' % pulse_rate + ' ' + _('pulses/sec'))

                        if wind_options['use_kmh']:
                            log.info(NAME, '%s' % self.status['log_date_maxspeed'] + ' ' + _('Maximal speed') + ': ' + '%s' % round(self.status['max_meter']*3.6, 2) + ' ' + _('km/h'))  
                        else:    
                            log.info(NAME, '%s' % self.status['log_date_maxspeed'] + ' ' + _('Maximal speed') + ': ' + '%s' % round(self.status['max_meter'], 2)  + ' ' + _('m/sec'))  

                        if self.status['meter'] >= 42: 
                            log.error(NAME, datetime_string() + ' ' + _('Wind speed > 150 km/h (42 m/sec)'))

                        action_confirmation_count, action_confirmed = update_confirmation(
                            action_confirmation_count,
                            self.status['meter'] >= wind_options['maxspeed'],
                            wind_options['action_confirmations'],
                        )
                        if self.status['meter'] < wind_options['maxspeed']:
                            hazard_active = False
                        self.status['action_confirmation_count'] = action_confirmation_count

                        if action_confirmed and not hazard_active:
                            hazard_active = True
                            log.clear(NAME)
                            if wind_options['sendeml']:                   # if enabled send email
                                send = True  
                                log.info(NAME, datetime_string() + ' ' + _('Sending E-mail with notification.'))

                            if wind_options['stoperr']:                   # if enabled stoping for running stations in scheduler
                                set_stations_in_scheduler_off()           # set selected stations to stop in scheduler

                        millis = int(round(time_.time() * 1000))

                        if wind_options['enable_log'] or wind_options['en_sql_log']: # if logging
                            interval = (wind_options['log_interval'] * 60000)
                            if (millis - last_millis) >= interval:
                               last_millis = millis
                               update_log()

                        if (millis - last_clear_millis) >= 120000:            # after 120 second deleting in status screen
                               last_clear_millis = millis 
                               log.clear(NAME)

                        if wind_options['delete_max_24h']:                    # if enable deleting max after 24 hours (86400000 ms)
                            is_interval = True
                            if wind_options['delete_max'] == '1':             # after one minute
                                int_ms = 60000
                            elif wind_options['delete_max'] == '10':          # after 10 minutes
                                int_ms = 600000
                            elif wind_options['delete_max'] == '30':          # after 30 minutes
                                int_ms = 1800000
                            elif wind_options['delete_max'] == '1h':          # after one hours
                                int_ms = 3600000
                            elif wind_options['delete_max'] == '2h':          # after two hours
                                int_ms = 7200000
                            elif wind_options['delete_max'] == '10h':         # after 10 hours
                                int_ms = 36000000
                            elif wind_options['delete_max'] == '24h':         # after 24 hours
                                int_ms = 86400000                                                                                                                                                                
                            else:
                                is_interval = False

                            if (millis - last_24h_millis) >= int_ms and is_interval:          # after xx minutes or hours deleting maximal speed
                                last_24h_millis = millis
                                self.status['meter'] = 0
                                self.status['kmeter'] = 0
                                self.status['max_meter'] = 0
                                self.status['log_date_maxspeed'] = datetime_string()      
                                log.info(NAME, datetime_string() + ' ' + _('Deleting maximal speed after selected interval.'))
                                if wind_options['enable_log'] or wind_options['en_sql_log']: 
                                    update_log()

                        # running program after action ------------------------------------------------------------------------------------------------------
                        if wind_options['use_stop_pgm'] and not ignore_intervals:
                            if self.status['meter'] >= wind_options['m_speed_trig']:                                  # wind is > trig
                                trig_once = True
                                if not last_trig_once and trig_once:
                                    last_trig_once = True
                                    last_event_interval = millis                                                      # start minutes event counter
                                if (millis - last_event_interval) < (wind_options['event_interval']*60000):           # in minutes (ex: 1 min = 1x60000ms)
                                    trig_count += 1
                                    log.info(NAME, datetime_string() + ' ' + _('Speed was exceeded! Event # {}/{}.').format(trig_count, wind_options['event_repetitions']))
                                    if trig_count >= wind_options['event_repetitions']:
                                        trig_count = 0
                                        ignore_intervals = True
                                        last_trig_once = False
                                        last_ignore_interval_millis = millis
                                        log.info(NAME, datetime_string() + ' ' + _('The program will now start and setup block for {} hours.').format(wind_options['ignore_interval']))
                                        # run program
                                        for program in programs.get():
                                            if (program.index == wind_options['used_program'][0]):
                                                # options.manual_mode = False
                                                # log.finish_run(None)
                                                # stations.clear()    
                                                programs.run_now(program.index)
                                                log.debug(NAME, datetime_string() + ' ' + _('Run now program # {}.').format(program.index)) 
                                            program.index+1    
                                if (millis - last_event_interval) >= (wind_options['event_interval']*60000): 
                                    last_event_interval = millis
                                    trig_count = 0
                                    log.info(NAME, datetime_string() + ' ' + _('The number of exceedances in the set interval has not been exceeded, I reset the counter.'))
                        if wind_options['use_stop_pgm'] and ignore_intervals:                                         # reseting ignore interval (ex: after 24 hours)
                            if (millis - last_ignore_interval_millis) >= (wind_options['ignore_interval'] * 3600000): # ex: 1 hour (3600000)= 1000ms * 60sec * 60min
                                last_ignore_interval_millis = millis
                                ignore_intervals = False
                                log.info(NAME, datetime_string() + ' ' + _('The program has now been unblocked.'))
                        #------------------------------------------------------------------------------------------------------------------------------------

                        # footer msg
                        tempText = ""
                        if wind_options['use_kmh']:
                            tempText += '%s' % self.status['kmeter'] + ' ' + _('km/h')
                        else:
                            tempText += '%s' % self.status['meter'] + ' ' + _('m/s')
                        if wind_options['use_footer']:
                            if wind_mon is not None:
                                wind_mon.val = tempText.encode('utf8').decode('utf8')         # value on footer
                    else:
                        self._sleep(1)

                else:
                    if disable_text:
                        log.clear(NAME)
                        log.info(NAME, _('Wind speed monitor plug-in is disabled.'))
                        disable_text = False
                    self._sleep(1)

                if send:
                    msg = '<b>' + _('Wind speed monitor plug-in') + '</b> ' + '<br><p style="color:red;">' + _('System detected error: wind speed monitor. All stations set to OFF. Wind is') + ': ' + '%.1f' % (round(val*3.6,2)) + ' ' + _('km/h') + '. </p>'
                    msglog= _('System detected error: wind speed monitor. All stations set to OFF. Wind is') + ': ' + '%.1f' % (round(val,2)*3.6) + ' ' + _('km/h') + '.'
                    send = False
                    try:
                        try_mail = None
                        if wind_options['eplug']==0: # email_notifications
                            from plugins.email_notifications import try_mail
                        if wind_options['eplug']==1: # email_notifications SSL
                            from plugins.email_notifications_ssl import try_mail    
                        if try_mail is not None:                        
                            try_mail(msg, msglog, attachment=None, subject=wind_options['emlsubject']) # try_mail(text, logtext, attachment=None, subject=None)
                            with health_lock:
                                health_state['last_email'] = time_.time()

                    except Exception:
                        self._log_problem(_('Wind Speed monitor plug-in') + ':\n' + traceback.format_exc())

            except Exception:
                log.clear(NAME)
                self.close_bus()
                self._log_problem(_('Wind Speed monitor plug-in') + ':\n' + traceback.format_exc())
                self._sleep(60)
        self.close_bus()


wind_sender = None

################################################################################
# Helper functions:                                                            #
################################################################################
def start():
    global wind_sender
    if wind_sender is None:
        wind_sender = WindSender()


def stop():
    global wind_sender
    if wind_sender is not None:
        wind_sender.stop()
        runtime.request_stop()
        wind_sender.close_bus()
        wind_sender.join(15)
        if not wind_sender.is_alive():
            wind_sender = None
    clear_plugin_runtime_data('wind_monitor')


def try_io(call, tries=10):
    assert tries > 0
    total_tries = tries
    error = None
    result = None

    while tries:
        try:
            result = call()
        except IOError as e:
            error = e
            tries -= 1
            diagnostic_event(
                'i2c_retry',
                attempt=total_tries - tries,
                remaining=tries,
                error=str(e),
            )
            time.sleep(0.01)
        else:
            break

    if not tries:
        raise error

    return result


def safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def decimal_input(qdict, key, default):
    try:
        return parse_decimal(qdict.get(key, default), key)
    except ValueError:
        raise web.badrequest(_('Invalid value for') + ' ' + '{}:{}'.format(
            key, qdict.get(key)))


def normalize_options():
    normalized = {
        'pulses': max(0.001, min(1000000.0, safe_float(wind_options.get('pulses', 2), 2))),
        'metperrot': max(0.001, min(1000000.0, safe_float(wind_options.get('metperrot', 1.492), 1.492))),
        'maxspeed': max(0, min(1000, safe_float(wind_options.get('maxspeed', 20), 20))),
        'm_speed_trig': max(0, min(1000, safe_float(wind_options.get('m_speed_trig', 10), 10))),
        'log_interval': max(1, min(1440, safe_int(wind_options.get('log_interval', 1), 1))),
        'log_records': max(0, min(10000, safe_int(wind_options.get('log_records', 0), 0))),
        'event_repetitions': max(1, min(100, safe_int(wind_options.get('event_repetitions', 3), 3))),
        'event_interval': max(1, min(1440, safe_int(wind_options.get('event_interval', 1), 1))),
        'ignore_interval': max(1, min(8760, safe_int(wind_options.get('ignore_interval', 24), 24))),
        'max_accepted_speed': max(0.1, min(1000.0, safe_float(
            wind_options.get('max_accepted_speed', 40.0), 40.0))),
        'action_confirmations': max(1, min(10, safe_int(
            wind_options.get('action_confirmations', 2), 2))),
        'eplug': 1 if safe_int(wind_options.get('eplug', 0), 0) == 1 else 0,
        'used_stations': [
            safe_int(station, -1)
            for station in wind_options.get('used_stations', [])
            if safe_int(station, -1) >= 0
        ],
        'used_program': [
            safe_int(program, -1)
            for program in wind_options.get('used_program', [])
            if safe_int(program, -1) >= 0
        ],
    }
    if not normalized['used_program']:
        normalized['used_program'] = [-1]

    # Normalization runs in the measurement loop. Persist only an actual
    # correction instead of rewriting every setting on every sample.
    for key, value in normalized.items():
        current = wind_options.get(key)
        if current != value or type(current) is not type(value):
            wind_options[key] = value


def set_counter(i2cbus):
    try:
        addr = 0
        if wind_options['address']:
            addr = 0x51
        else:
            addr = 0x50
        with wind_i2c_transaction():
            try_io(lambda: i2cbus.write_byte_data(addr, 0x00, 0x20)) # status registr setup to "EVENT COUNTER"
            try_io(lambda: i2cbus.write_byte_data(addr, 0x01, 0x00)) # reset LSB
            try_io(lambda: i2cbus.write_byte_data(addr, 0x02, 0x00)) # reset midle Byte
            try_io(lambda: i2cbus.write_byte_data(addr, 0x03, 0x00)) # reset MSB
            status = try_io(lambda: i2cbus.read_byte_data(addr, 0x00))
        if (status & 0x30) != 0x20:
            diagnostic_event('setup_rejected', address='0x%02X' % addr, status=status)
            raise IOError(_('PCF8583 event-counter mode was not confirmed.'))
        diagnostic_event('setup', address='0x%02X' % addr, status=status, result='ok')
        log.debug(NAME, _('Wind speed monitor plug-in') + ': ' + _('Setup PCF8583 as event counter - OK')) 
        return True
    except Exception:
        diagnostic_event(
            'setup_error',
            address='0x%02X' % addr,
            error=traceback.format_exc().splitlines()[-1],
        )
        log.error(NAME, _('Wind speed monitor plug-in') + ':\n' + _('Setup PCF8583 as event counter - FAULT'))
        log.error(NAME, _('Wind speed monitor plug-in') + '%s' % traceback.format_exc())
        return False


def counter(i2cbus, stop_event=None):
    """Reset PCF8583, measure pulses and return raw count with actual duration."""
    try:
        addr = 0
        if wind_options['address']:
            addr = 0x51
        else:
            addr = 0x50
        # reset PCF8583
        with wind_i2c_transaction():
            try_io(lambda: i2cbus.write_byte_data(addr, 0x01, 0x00)) # reset LSB
            try_io(lambda: i2cbus.write_byte_data(addr, 0x02, 0x00)) # reset midle Byte
            try_io(lambda: i2cbus.write_byte_data(addr, 0x03, 0x00)) # reset MSB
        started = time_.monotonic()
        if stop_event is not None:
            if stop_event.wait(MEASUREMENT_SECONDS):
                return None
        else:
            time_.sleep(MEASUREMENT_SECONDS)
        lock_requested = time_.monotonic()
        with wind_i2c_transaction():
            lock_acquired = time_.monotonic()
            raw_bytes = try_io(lambda: i2cbus.read_i2c_block_data(addr, 0x01, 3))
        finished = time_.monotonic()
        raw_pulses = decode_bcd_counter(raw_bytes)
        diagnostic_event(
            'counter_read',
            address='0x%02X' % addr,
            raw_bytes=[int(value) for value in raw_bytes],
            raw_pulses=raw_pulses,
            elapsed=round(finished - started, 6),
            i2c_wait=round(lock_acquired - lock_requested, 6),
        )
        return {
            'address': '0x%02X' % addr,
            'raw_bytes': [int(value) for value in raw_bytes],
            'raw_pulses': raw_pulses,
            'elapsed': finished - started,
            'i2c_wait': lock_acquired - lock_requested,
        }
    except IOError as e:
        if str(e) == 'I2C bus is busy.':
            log.debug(NAME, datetime_string() + ': ' + _('I2C bus is busy, wind counter read skipped.'))
        else:
            log.error(NAME, _('Wind speed monitor plug-in') + u'%s' % traceback.format_exc())
        diagnostic_event('counter_error', error=str(e))
        return None
    except Exception:
        diagnostic_event(
            'counter_error',
            error=traceback.format_exc().splitlines()[-1],
        )
        log.error(NAME, _('Wind speed monitor plug-in') + u'%s' % traceback.format_exc())
        return None


def set_stations_in_scheduler_off():
    """Stoping selected station in scheduler."""
    
    current_time  = datetime.datetime.now()
    check_start = current_time - datetime.timedelta(days=1)
    check_end = current_time + datetime.timedelta(days=1)

    # In manual mode we cannot predict, we only know what is currently running and the history
    if options.manual_mode:
        active = log.finished_runs() + log.active_runs()
    else:
        active = combined_schedule(check_start, check_end)

    ending = False

    # active stations
    for entry in active:
        for used_stations in wind_options['used_stations']: # selected stations for stoping
            if entry['station'] == used_stations:           # is this station in selected stations? 
                log.finish_run(entry)                       # save end in log 
                stations.deactivate(entry['station'])       # stations to OFF
                ending = True   

    if ending:
        with health_lock:
            health_state['last_action'] = time_.time()
        log.info(NAME, _('Stoping stations in scheduler'))


def get_all_values():
    """Return all posible values for others use."""
    status = wind_sender.status
    try:
        if wind_options['use_kmh']:
            return round(status['meter']*3.6, 2), round(status['max_meter']*3.6, 2), status['log_date_maxspeed']  # km/hod
        else:
            return round(status['meter'], 2), round(status['max_meter'], 2), status['log_date_maxspeed']          # m/sec
    except:
        return -1, -1, datetime_string()


def read_log():
    """Read log data from json file."""
    try:
        with open(os.path.join(plugin_data_dir('wind_monitor'), 'log.json')) as logf:
            return json.load(logf)
    except (IOError, ValueError):
        return []


def read_graph_log():
    """Read graph data from json file."""

    try:
        with open(os.path.join(plugin_data_dir('wind_monitor'), 'graph.json')) as logf:
            return json.load(logf)
    except (IOError, ValueError):
        return []


def write_log(json_data):
    """Write data to log json file."""

    with open(os.path.join(plugin_data_dir('wind_monitor'), 'log.json'), 'w') as outfile:
        json.dump(json_data, outfile)


def write_graph_log(json_data):
    """Write data to graph json file."""

    with open(os.path.join(plugin_data_dir('wind_monitor'), 'graph.json'), 'w') as outfile:
        json.dump(json_data, outfile)


def update_log():
    """Update data in json files."""

    if wind_options['enable_log']:
        ### Data for log ###
        try:
            log_data = read_log()
        except:   
            write_log([])
            log_data = read_log()

        from datetime import datetime

        data = {'datetime': datetime_string()}
        data['date'] = str(datetime.now().strftime('%d.%m.%Y'))
        data['time'] = str(datetime.now().strftime('%H:%M:%S'))
        data['maximum'] = str(get_all_values()[1])
        data['actual']  = str(get_all_values()[0])

        log_data.insert(0, data)
        if wind_options['log_records'] > 0:
            log_data = log_data[:wind_options['log_records']]

        write_log(log_data)

        ### Data for graph log ###
        try:
            graph_data = read_graph_log()
        except:
            create_default_graph()
            graph_data = read_graph_log()

        timestamp = int(time_.time())

        try:
            maximum = graph_data[0]['balances']
            maxval = {'total': get_all_values()[1]}
            maximum.update({timestamp: maxval})

            actual = graph_data[1]['balances']
            actval = {'total': get_all_values()[0]}
            actual.update({timestamp: actval})
        
            write_graph_log(graph_data)
            log.info(NAME, datetime_string() + ' ' + _('Saving to log  files OK'))
        except:
            create_default_graph()

    if wind_options['en_sql_log']:
        try:
            from plugins.database_connector import execute_db, table_exists
            if not table_exists('windmonitor'):
                sql = "CREATE TABLE IF NOT EXISTS windmonitor (id INT NOT NULL AUTO_INCREMENT PRIMARY KEY, ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP, max VARCHAR(7), actual VARCHAR(7))"
                execute_db(sql, test=False, commit=False)
            # next insert data to table windmonitor
            sql = "INSERT INTO `windmonitor` (`max`, `actual`) VALUES ('%s','%s')" % (get_all_values()[1],get_all_values()[0])
            execute_db(sql, test=False, commit=True)  # yes commit inserted data
            log.info(NAME, _('Saving to SQL database.'))
        except:
            log.error(NAME, _('Wind speed monitor plug-in') + ':\n' + traceback.format_exc())
            pass             


def create_default_graph():
    """Create default graph json file."""

    maximum = _('Maximum')
    actual  = _('Actual')
 
    graph_data = [
       {"station": maximum, "balances": {}}, 
       {"station": actual, "balances": {}}
    ]
    write_graph_log(graph_data)  
    log.debug(NAME,datetime_string() + ' ' + _('Creating default graph log files OK'))


################################################################################
# Web pages:                                                                   #
################################################################################


def _empty_status():
    return {
        'meter': 0.0,
        'kmeter': 0.0,
        'max_meter': 0,
        'log_date_maxspeed': datetime_string(),
        'trend': 'unknown',
        'last_measurement': '',
        'last_raw_pulses': 0,
        'last_pulse_rate': 0.0,
        'last_elapsed': 0.0,
        'last_rejected_reason': '',
        'action_confirmation_count': 0,
    }


class overview_page(ProtectedPage):
    """Display live wind status and history graph."""

    def GET(self):
        qdict = web.input()
        normalize_options()
        reset = helpers.get_input(qdict, 'reset', False, lambda x: True)
        show = helpers.get_input(qdict, 'show', False, lambda x: True)

        if wind_sender is not None and reset:
            verify_csrf(qdict)
            wind_sender.status['max_meter'] = 0
            wind_sender.status['log_date_maxspeed'] = datetime_string()
            log.clear(NAME)
            log.info(NAME, datetime_string() + ' ' + _('Maximal speed has reseted.'))
            raise web.seeother(plugin_url(overview_page), True)

        if wind_sender is not None and show:
            raise web.seeother(plugin_url(log_page), True)

        status = wind_sender.status if wind_sender is not None else _empty_status()
        return self.plugin_render.wind_monitor(wind_options, status, log.events(NAME))


class settings_page(ProtectedPage):
    """Load an html page for entering wind speed monitor settings."""

    def GET(self):
        qdict = web.input()
        normalize_options()
        delSQL = helpers.get_input(qdict, 'delSQL', False, lambda x: True)
        if wind_sender is not None and delSQL:
            verify_csrf(qdict)
            try:
                from plugins.database_connector import execute_db
                sql = "DROP TABLE IF EXISTS `windmonitor`"
                execute_db(sql, test=False, commit=False)  
                log.info(NAME, _('Deleting the windmonitor table from the database.'))
            except:
                log.error(NAME, _('Wind speed monitor plug-in') + ':\n' + traceback.format_exc())
                pass            

        return self.plugin_render.wind_monitor_settings(wind_options)

    def POST(self):
        decimal_fields = (
            'pulses',
            'metperrot',
            'maxspeed',
            'm_speed_trig',
            'max_accepted_speed',
        )
        qdict = web.input(used_stations=[], used_program=[])
        verify_csrf(qdict)
        decimal_values = {
            key: decimal_input(qdict, key, wind_options.get(key))
            for key in decimal_fields
        }
        wind_options.web_update(qdict, skipped=decimal_fields)
        for key, value in decimal_values.items():
            wind_options[key] = value
        normalize_options()

        if wind_sender is not None:
            wind_sender.update()

        if wind_options['use_wind_monitor']:
            log.clear(NAME) 
            log.info(NAME, _('Wind monitor is enabled.'))
        else:
            log.clear(NAME)
            log.info(NAME, _('Wind monitor is disabled.'))

        log.info(NAME, datetime_string() + ' ' + _('Options has updated.'))

        raise web.seeother(plugin_url(overview_page), True)


class help_page(ProtectedPage):
    """Load an html page for help"""

    def GET(self):
        return self.plugin_render.wind_monitor_help()


class log_page(ProtectedPage):
    """Load an html page for help"""

    def GET(self):
        global wind_sender
        qdict = web.input()
        delete = helpers.get_input(qdict, 'delete', False, lambda x: True)
        delSQL = helpers.get_input(qdict, 'delSQL', False, lambda x: True)
        
        if wind_sender is not None and delete and wind_options['enable_log']:
           verify_csrf(qdict)
           write_log([])
           create_default_graph()
           log.info(NAME, _('Deleted all log files OK'))

        if wind_sender is not None and delSQL and wind_options['en_sql_log']:
            verify_csrf(qdict)
            try:
                from plugins.database_connector import execute_db
                sql = "DROP TABLE IF EXISTS `windmonitor`"
                execute_db(sql, test=False, commit=False)  
                log.info(NAME, _('Deleting the windmonitor table from the database.'))
            except:
                log.error(NAME, _('Wind speed monitor plug-in') + ':\n' + traceback.format_exc())
                pass          

        return self.plugin_render.wind_monitor_log(read_log(), read_sql_log(), wind_options)


class diagnostic_page(ProtectedPage):
    """Display the bounded PCF8583 and I2C diagnostic log."""

    def GET(self):
        qdict = web.input()
        delete = helpers.get_input(qdict, 'delete', False, lambda x: True)
        if delete:
            verify_csrf(qdict)
            clear_diagnostic_log()
            log.info(NAME, _('Wind diagnostic log was deleted.'))
            raise web.seeother(plugin_url(diagnostic_page), True)
        return self.plugin_render.wind_monitor_diagnostic(
            read_diagnostic_log(), wind_options)


class diagnostic_download(ProtectedPage):
    """Download the current bounded diagnostic log."""

    def GET(self):
        data = '\n'.join(read_diagnostic_log(None))
        if data:
            data += '\n'
        web.header('Content-Type', 'text/plain; charset=utf-8')
        web.header(
            'Content-Disposition',
            'attachment; filename="wind_monitor_diagnostic_{}.log"'.format(
                time.strftime('%Y%m%d-%H%M%S')))
        return data


class settings_json(ProtectedPage):
    """Returns plugin settings in JSON format."""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        normalize_options()
        return json.dumps(wind_options)


class data_json(ProtectedPage):
    """Returns plugin data in JSON format."""
    global wind_sender

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        data =  {
          'log_maxspeed': round(wind_sender.status['max_meter'], 2) if wind_sender is not None else 0,    # in m/sec
          'log_speed': round(wind_sender.status['meter'],2) if wind_sender is not None else 0,          # in m/sec
          'log_date_maxspeed': wind_sender.status['log_date_maxspeed'] if wind_sender is not None else datetime_string(),
          'label': wind_options['emlsubject']
        }

        return json.dumps(data)


class log_json(ProtectedPage):
    """Returns data in JSON format."""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        return json.dumps(read_log())


def read_sql_log():
    """Read log data from database file."""
    data = None

    try:
        from plugins.database_connector import execute_db
        sql = "SELECT * FROM windmonitor ORDER BY id DESC"
        data = execute_db(sql, test=False, commit=False, fetch=True) # fetch=true return data from table in format: id,datetime,ds1,ds2,ds3,ds4,ds5,ds6,dhttemp,dhthumi,dhtstate
    except:
        log.error(NAME, _('Wind speed monitor plug-in') + ':\n' + traceback.format_exc())
        pass

    return data


def read_graph_sql_log():
    """Read graph data from database file and convert it to json balance file."""
    data = []

    try:
        sql_data = read_sql_log()
        maximum = _('Maximum')
        actual  = _('Actual')
 
        graph_data = [
            {"station": maximum, "balances": {}}, 
            {"station": actual, "balances": {}}
        ]

        if sql_data is not None:
            for row in sql_data:
                # row[0] is ID, row[1] is datetime, row[2] is maximal
                epoch = int(datetime.datetime.timestamp(row[1]))
            
                temp0 = graph_data[0]['balances']
                max = {'total': float(row[2])}
                temp0.update({epoch: max})
            
                temp1 = graph_data[1]['balances']
                actual = {'total': float(row[3])}
                temp1.update({epoch: actual})

        data = graph_data

    except:
        log.error(NAME, _('Wind speed monitor plug-in') + ':\n' + traceback.format_exc())
        pass

    return data


class graph_json(ProtectedPage):
    """Returns graph data in JSON format."""

    def GET(self):
        data = []
        try:
            from datetime import datetime
            qdict = web.input()

            dt_from_text = qdict.get('dt_from', wind_options['dt_from'])
            dt_to_text = qdict.get('dt_to', wind_options['dt_to'])

            dt_from = datetime.strptime(dt_from_text, '%Y-%m-%dT%H:%M') # from
            dt_to   = datetime.strptime(dt_to_text, '%Y-%m-%dT%H:%M')   # to

            epoch_time = datetime(1970, 1, 1)

            log_start = int((dt_from - epoch_time).total_seconds())
            log_end = int((dt_to - epoch_time).total_seconds())
 
            try:
                if wind_options['type_log'] == 0:
                    json_data = read_graph_log()
                if wind_options['type_log'] == 1:
                    json_data = read_graph_sql_log()
            except:
                json_data = []
                pass

            if len(json_data) > 0:
                for i in range(0, 2):
                    temp_balances = {}
                    for key in json_data[i]['balances']:
                        try:
                            find_key = int(key)
                        except:
                            find_key = key   
                        if find_key >= log_start and find_key <= log_end:          # timestamp interval from <-> to
                            find_data = json_data[i]['balances'][key] 
                            temp_balances[key] = json_data[i]['balances'][key]

                    data.append({ 'station': json_data[i]['station'], 'balances': temp_balances })

        except:
            log.error(NAME, _('Wind speed monitor plug-in') + ':\n' + traceback.format_exc())
            pass

        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        return json.dumps(data)


class log_csv(ProtectedPage):  # save log file from web as csv file type
    """Simple Log API"""
    def GET(self):
        log_file = read_log()
        maximum = _('Maximum')
        actual  = _('Actual')
        data = "Date/Time; Date; Time"
        if wind_options['use_kmh']: 
            data += "; %s km/h" % maximum
            data += "; %s km/h" % actual
        else:
            data += "; %s m/sec" % maximum
            data += "; %s m/sec" % actual
        data += '\n'

        for interval in log_file:
            data += '; '.join([
                interval['datetime'],
                interval['date'],
                interval['time'],
                '{}'.format(interval['maximum']),
                '{}'.format(interval['actual']),
            ]) + '\n'

        filestamp = time.strftime('%Y%m%d-%H%M%S')
        filename = 'log_{}_.csv'.format(filestamp)
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-type', 'text/csv') # https://developer.mozilla.org/en-US/docs/Web/HTTP/Basics_of_HTTP/MIME_types/Common_types
        web.header('Content-Disposition', 'attachment; filename="{}"'.format(filename))
        return data


class log_sql_csv(ProtectedPage):  # save log file from database as csv file type from web
    """Simple Log API"""
    def GET(self):
        data = []
        try:
            from plugins.database_connector import execute_db
            sql = "SELECT * FROM windmonitor"
            log_file = execute_db(sql, test=False, commit=False, fetch=True)
            maximum = _('Maximum')
            actual  = _('Actual')
            data = "ID; Date/Time"
            if wind_options['use_kmh']: 
                data += "; %s km/h" % maximum
                data += "; %s km/h" % actual
            else:
                data += "; %s m/sec" % maximum
                data += "; %s m/sec" % actual
            data += '\n'
            for interval in log_file:
                data += '; '.join([
                    '{}'.format(str(interval[0])),
                    '{}'.format(str(interval[1])),
                    '{}'.format(str(interval[2])),
                    '{}'.format(str(interval[3])),                    
                ]) + '\n'

        except:
            log.error(NAME, _('Air Temperature and Humidity Monitor plug-in') + ':\n' + traceback.format_exc())
            pass
        
        filestamp = time.strftime('%Y%m%d-%H%M%S')
        filename = 'log_{}_.csv'.format(filestamp)
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-type', 'text/csv') # https://developer.mozilla.org/en-US/docs/Web/HTTP/Basics_of_HTTP/MIME_types/Common_types
        web.header('Content-Disposition', 'attachment; filename="{}"'.format(filename))
        return data


class log_sql_json(ProtectedPage):
    """Returns data in JSON format from database file log."""

    def GET(self):
        data = []
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        try:
            data = json.dumps(read_sql_log())
        except:
            log.error(NAME, _('Wind speed monitor plug-in') + ':\n' + traceback.format_exc())
            pass
        return data


class wind_json(ProtectedPage):
    """Return live wind status for the overview page."""

    def GET(self):
        global wind_sender
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        status = wind_sender.status if wind_sender is not None else _empty_status()
        trend = status.get('trend', 'unknown')
        trend_labels = {
            'up': _('Rising'),
            'down': _('Falling'),
            'steady': _('Steady'),
            'unknown': _('Waiting for trend data'),
        }
        trend_symbols = {
            'up': '↑',
            'down': '↓',
            'steady': '→',
            'unknown': '·',
        }
        data = {
            'enabled': bool(wind_options.get('use_wind_monitor', False)),
            'running': wind_sender is not None and wind_sender.is_alive(),
            'trend': trend,
            'trend_symbol': trend_symbols.get(trend, '·'),
            'trend_label': trend_labels.get(trend, trend_labels['unknown']),
            'last_measurement': status.get('last_measurement', ''),
            'raw_pulses': status.get('last_raw_pulses', 0),
            'pulse_rate': status.get('last_pulse_rate', 0.0),
            'elapsed': status.get('last_elapsed', 0.0),
            'rejected_reason': status.get('last_rejected_reason', ''),
            'confirmation_count': status.get('action_confirmation_count', 0),
            'confirmation_required': wind_options.get('action_confirmations', 2),
            'maximum_at': status.get('log_date_maxspeed', ''),
            'activity': '\n'.join(log.events(NAME)),
        }
        try:
            if wind_options['use_kmh']:
                data['wind'] = '{} {}'.format(round(status['meter']*3.6, 2), _('km/h'))
                data['maximum'] = '{} {}'.format(round(status['max_meter']*3.6, 2), _('km/h'))
            else:
                data['wind'] = '{} {}'.format(round(status['meter'], 2), _('m/s'))
                data['maximum'] = '{} {}'.format(round(status['max_meter'], 2), _('m/s'))
            data['status'] = _('Measurement is active.') if data['enabled'] and data['running'] else _('Measurement is inactive.')
        except Exception:
            data['wind'] = '{}'.format(_('Any error'))
            data['maximum'] = '-'
            data['status'] = _('Wind monitor data is unavailable.')
        return json.dumps(data)


def health():
    """Return a compact status for the OSPy diagnostics page."""
    worker_alive = wind_sender is not None and wind_sender.is_alive()
    bus_open = wind_sender is not None and wind_sender.bus is not None
    with health_lock:
        state = dict(health_state)
    status_data = wind_sender.status if wind_sender is not None else {
        'meter': 0.0, 'kmeter': 0.0, 'max_meter': 0.0, 'log_date_maxspeed': '',
        'trend': 'unknown', 'last_elapsed': 0.0, 'last_raw_pulses': 0,
        'last_rejected_reason': '',
    }
    details = {
        'worker': _('Running') if worker_alive else _('Stopped'),
        'enabled': bool(wind_options.get('use_wind_monitor', False)),
        'i2c_address': '0x51' if wind_options.get('address', False) else '0x50',
        'i2c_bus': _('Open') if bus_open else _('Unavailable'),
        'speed_mps': status_data['meter'],
        'maximum_mps': status_data['max_meter'],
        'maximum_at': status_data['log_date_maxspeed'],
        'trend': status_data.get('trend', 'unknown'),
        'measurement_seconds': status_data.get('last_elapsed', 0.0),
        'raw_pulses': status_data.get('last_raw_pulses', 0),
        'filter_enabled': bool(wind_options.get('filter_invalid', True)),
        'maximum_accepted_mps': wind_options.get('max_accepted_speed', 40.0),
        'last_rejected_reason': status_data.get('last_rejected_reason', ''),
        'rejected_measurements': state.get('rejected_count', 0),
        'diagnostic_logging': bool(wind_options.get('diagnostic_logging', False)),
        'station_stop_enabled': bool(wind_options.get('stoperr', False)),
        'program_action_enabled': bool(wind_options.get('use_stop_pgm', False)),
        'last_reading': state['last_reading'],
        'last_email': state['last_email'],
        'last_action': state['last_action'],
        'last_error': state['last_error'],
    }
    if state['last_error_message']:
        details['error'] = state['last_error_message']
    if not worker_alive:
        status = 'error'
        summary = _('Wind monitor worker is not running.')
    elif not wind_options.get('use_wind_monitor', False):
        status = 'unknown'
        summary = _('Wind monitor is disabled.')
    elif not bus_open:
        status = 'error'
        summary = _('Wind counter is not available.')
    elif state['last_error'] and state['last_error'] > state['last_reading']:
        status = 'warning'
        summary = _('Wind monitor reported an error.')
    else:
        status = 'ok'
        summary = _('Wind monitor is reading the counter.')
    return {'status': status, 'summary': summary, 'details': details}
