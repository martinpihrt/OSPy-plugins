# -*- coding: utf-8 -*-
__author__ = 'Martin Pihrt'
# this plugins check pressure in pipe if master station is switched on

import json
import time
import datetime
import sys
import os
import traceback
import mimetypes

from threading import Thread, Lock

import web
from ospy.stations import stations
from ospy.options import options
from ospy.log import log, logEM
from plugins import PluginOptions, plugin_url, plugin_data_dir, get_runtime
from ospy.webpages import ProtectedPage
from ospy.helpers import datetime_string, verify_csrf
from ospy import helpers
from ospy.scheduler import predicted_schedule, combined_schedule

from blinker import signal

from ospy.webpages import showInFooter # Enable plugin to display readings in UI footer


NAME = 'Pressure Monitor'
MENU =  _('Package: Pressure Monitor')
LINK = 'settings_page'
MAIN_LOOP_SLEEP = 2
PRESS_STATUS_POLL_MS = 5000
COUNTDOWN_LOG_INTERVAL = 10
ERROR_LOG_THROTTLE = 300

pressure_options = PluginOptions(
    NAME,
    {
        'time': 10,
        'use_press_monitor': False,
        'normally': False,
        'sendeml': True,
        'emlsubject': _('Report from OSPy PRESSURE MONITOR plugin'),
        'enable_log': False,
        'log_records': 0,       # 0 = unlimited
        'history': 0,           # selector for graph history
        'used_stations': [],    # use this stations for stoping scheduler if stations is activated in scheduler
        'use_footer': True,     # show data from plugin in footer on home page
        'eplug': 0,             # email plugin type (email notifications or email notifications SSL)
        'en_sql_log': False,    # logging temperature to sql database
        'type_log': 0,          # 0 = show log and graph from local log file, 1 = from database
        'dt_from' : '2024-01-01T00:00',  # for graph history (from date time ex: 2024-02-01T6:00)
        'dt_to' : '2024-01-01T00:00',    # for graph history (to date time ex: 2024-03-17T12:00) 
    }
)

global master
master = False
_last_error_log = {}
runtime = get_runtime()
health_lock = Lock()
health_state = {
    'last_cycle': 0,
    'sensor_active': None,
    'last_shutdown': 0,
    'last_error': 0,
    'last_error_message': '',
}


def log_pressure_problem(key, message):
    now = time.time()
    last = _last_error_log.get(key, 0)
    if now - last >= ERROR_LOG_THROTTLE:
        _last_error_log[key] = now
        log.error(NAME, message)

################################################################################
# GPIO input pullup:                                                           #
################################################################################

import RPi.GPIO as GPIO  # RPi hardware

pin_pressure = 12

try:
    GPIO.setup(pin_pressure, GPIO.IN, pull_up_down=GPIO.PUD_UP)
except NameError:
    pass


################################################################################
# Main function loop:                                                          #
################################################################################

class PressureSender(Thread):
    def __init__(self):
        Thread.__init__(self)
        self.daemon = True
        self._stop_event = runtime.stop_event
        
        self.status = {}
        self.status['Pstate%d'] = 0

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

    def run(self):
        receivers = [
            (signal('master_one_on'), notify_master_on),
            (signal('master_one_off'), notify_master_off),
            (signal('master_two_on'), notify_master_two_on),
            (signal('master_two_off'), notify_master_two_off),
            (signal('station_clear'), notify_station_clear),
        ]
        for source, receiver in receivers:
            source.connect(receiver)

        send = False

        last_time = int(time.time())
        actual_time = int(time.time())
        last_msg = ""
        now_msg = ""
        tempText = ""
        last_countdown_log = 0

        press_mon = None

        if pressure_options['use_footer']: 
            press_mon = showInFooter() #  instantiate class to enable data in footer
            press_mon.button = "pressure_monitor/settings"   # button redirect on footer
            press_mon.label =  _('Pressure')                 # label on footer

        while not self._stop_event.is_set():
            try:
                if pressure_options['use_press_monitor']:                              # if pressure plugin is enabled
                    if master and not options.manual_mode:                             # if master station 1 or 2 is on and not manual mode
                        if get_check_pressure():                                       # if pressure sensor is on
                            if pressure_options['enable_log'] or pressure_options['en_sql_log']: # if enabled logging and graphing
                                now_msg = 2
                                if now_msg != last_msg:
                                    update_log(1)
                                    last_msg = 1
                            actual_time = int(time.time())
                            count_val = int(pressure_options['time'])
                            if actual_time - last_countdown_log >= COUNTDOWN_LOG_INTERVAL:
                                last_countdown_log = actual_time
                                log.info(NAME, _('Time to test pressure sensor') + ': ' + str(
                                    max(0, count_val - (actual_time - last_time))) + ' ' + _('sec') + '.')
                            if actual_time - last_time > int(pressure_options['time']):# wait for activated pressure sensor (time delay)
                                last_time = actual_time
                                if get_check_pressure():                               # if pressure sensor is actual on
                                    set_stations_in_scheduler_off()
                                    with health_lock:
                                        health_state['last_shutdown'] = time.time()
                                    log.clear(NAME)
                                    log.info(NAME, _('Pressure sensor is not activated in time, stoping all stations in scheduler.'))
                                    if pressure_options['sendeml']:                    # if enabled send email
                                        send = True
                                        log.info(NAME, _('Sending E-Mail.'))
                                    if pressure_options['enable_log'] or pressure_options['en_sql_log']: # if enabled logging and graphing
                                        now_msg = 0
                                        if now_msg != last_msg:
                                            update_log(0)
                                            last_msg = 0

                        if not get_check_pressure():
                            last_time = int(time.time())
                    else:
                        if stations.master is not None or stations.master_two is not None:
                            last_time = int(time.time())

                    if send:
                        msg = '<b>' + _('Pressure monitor plug-in') + '</b> ' + '<br><p style="color:red;">' + _('System detected error: pressure sensor.') + '</p>'
                        msglog = _('Pressure monitor plug-in') + ': ' + _('System detected error: pressure sensor.')
                        try:
                            try_mail = None
                            if pressure_options['eplug']==0: # email_notifications
                                from plugins.email_notifications import try_mail
                            if pressure_options['eplug']==1: # email_notifications SSL
                                from plugins.email_notifications_ssl import try_mail
                            if try_mail is not None:
                                try_mail(msg, msglog, subject=pressure_options['emlsubject'])
                            send = False
                        except Exception:
                            log.info(NAME, _('E-mail not send! The Email Notifications plug-in is not found in OSPy or not correctly setuped.'))
                            log_pressure_problem('send_email', _('Pressure monitor plug-in') + ': ' + traceback.format_exc().splitlines()[-1])
                            send = False
                            self._sleep(5)
                            pass
                        
                    if get_check_pressure():
                        self.status['Pstate%d'] = _('Inactive')
                        tempText = _('Inactive')
                    else:
                        self.status['Pstate%d'] = _('Active')
                        tempText = _('Active')
                    if pressure_options['use_footer']:
                        if press_mon is not None:    
                            press_mon.val = tempText.encode('utf8').decode('utf8')          # value on footer

                else:
                    self.status['Pstate%d'] = _('Disabled')
                    tempText = _('Disabled')
                    if pressure_options['use_footer']:
                        if press_mon is not None:
                            press_mon.val = tempText.encode('utf8').decode('utf8')          # value on footer

                with health_lock:
                    health_state['last_cycle'] = time.time()
                    health_state['sensor_active'] = (
                        not get_check_pressure()
                        if pressure_options['use_press_monitor'] else None
                    )
                    health_state['last_error_message'] = ''

                self._sleep(MAIN_LOOP_SLEEP)

            except Exception:
                message = traceback.format_exc().splitlines()[-1]
                with health_lock:
                    health_state['last_error'] = time.time()
                    health_state['last_error_message'] = message
                log_pressure_problem('run_loop', _('Pressure monitor plug-in') + ': ' + message)
                self._sleep(60)
        for source, receiver in receivers:
            source.disconnect(receiver)


pressure_sender = None

################################################################################
# Helper functions:                                                            #
################################################################################
def start():
    global pressure_sender
    if pressure_sender is None:
        pressure_sender = PressureSender()


def stop():
    global pressure_sender
    if pressure_sender is not None:
        pressure_sender.stop()
        pressure_sender.join(15)
        if pressure_sender.is_alive():
            log.error(NAME, _('The plug-in worker did not stop within the timeout.'))
        else:
            pressure_sender = None


def health():
    """Return pressure sensor, safety action and worker state."""
    with health_lock:
        state = dict(health_state)
    worker_running = pressure_sender is not None and pressure_sender.is_alive()
    details = {
        _('Worker thread'): _('Running') if worker_running else _('Stopped'),
        _('Monitoring enabled'): _('Yes') if pressure_options['use_press_monitor'] else _('No'),
        _('Master active'): _('Yes') if master else _('No'),
        _('Pressure sensor'): (
            _('Active') if state['sensor_active'] else _('Inactive')
            if state['sensor_active'] is not None else _('Not available')
        ),
        _('Last successful cycle'): (
            datetime_string(time.localtime(state['last_cycle']))
            if state['last_cycle'] else _('Not available')
        ),
        _('Last safety shutdown'): (
            datetime_string(time.localtime(state['last_shutdown']))
            if state['last_shutdown'] else _('Not available')
        ),
    }
    if state['last_error_message']:
        details[_('Last error')] = state['last_error_message']
    if not worker_running:
        return {
            'status': 'error',
            'summary': _('Pressure Monitor worker is not running.'),
            'details': details,
        }
    if state['last_error'] and state['last_error'] >= state['last_cycle']:
        return {
            'status': 'error',
            'summary': state['last_error_message'],
            'details': details,
        }
    if not pressure_options['use_press_monitor']:
        return {
            'status': 'unknown',
            'summary': _('Pressure monitoring is disabled.'),
            'details': details,
        }
    if not state['last_cycle']:
        return {
            'status': 'unknown',
            'summary': _('Pressure Monitor is waiting for its first check.'),
            'details': details,
        }
    if master and state['sensor_active'] is False:
        return {
            'status': 'warning',
            'summary': _('The pressure sensor is inactive while a master station is active.'),
            'details': details,
        }
    return {
        'status': 'ok',
        'summary': _('Pressure Monitor is responding.'),
        'details': details,
    }


def get_check_pressure():
    try:
        if pressure_options['normally']:
            if GPIO.input(pin_pressure):  # pressure detected
                press = 1
            else:
                press = 0
        elif pressure_options['normally'] != 'on':
            if not GPIO.input(pin_pressure):
                press = 1
            else:
                press = 0
        return press
    except:
        message = traceback.format_exc().splitlines()[-1]
        with health_lock:
            health_state['last_error'] = time.time()
            health_state['last_error_message'] = message
        log_pressure_problem('gpio_read', _('Pressure monitor plug-in') + ': ' + message)
        return 1


### master 1 on ###
def notify_master_on(name, **kw):
    try:
        global master
        log.clear(NAME)
        log.info(NAME, datetime_string() + ' ' + _('Master station 1 is ON.'))
        if pressure_options['enable_log'] or pressure_options['en_sql_log']:
            update_log(2)
        master = True
    except:
        log_pressure_problem('master_on', _('Pressure monitor plug-in') + ': ' + traceback.format_exc().splitlines()[-1])

### master 1 off ###
def notify_master_off(name, **kw):
    try:
        global master
        master = False
        log.info(NAME, datetime_string() + ' ' + _('Master station 1 is OFF.'))
    except:
        log_pressure_problem('master_off', _('Pressure monitor plug-in') + ': ' + traceback.format_exc().splitlines()[-1])

### master 2 on ###
def notify_master_two_on(name, **kw):
    try:
        global master
        log.clear(NAME)
        log.info(NAME, datetime_string() + ' ' + _('Master station 2 is ON.'))
        if pressure_options['enable_log'] or pressure_options['en_sql_log']:
            update_log(2)
        master = True
    except:
        log_pressure_problem('master_two_on', _('Pressure monitor plug-in') + ': ' + traceback.format_exc().splitlines()[-1])

### master 2 off ###
def notify_master_two_off(name, **kw):
    try:
        global master
        master = False
        log.info(NAME, datetime_string() + ' ' + _('Master station 2 is OFF.'))
    except:
        log_pressure_problem('master_two_off', _('Pressure monitor plug-in') + ': ' + traceback.format_exc().splitlines()[-1])

### all stations off ###
def notify_station_clear(name, **kw):
    try:
        global master
        master = False
        log.info(NAME, datetime_string() + ' ' + _('All stations set to OFF.'))
    except:
        log_pressure_problem('station_clear', _('Pressure monitor plug-in') + ': ' + traceback.format_exc().splitlines()[-1])

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
    used_station_ids = []
    for used_station in pressure_options['used_stations']:
        try:
            used_station_ids.append(int(used_station))
        except Exception:
            pass

    for entry in active:
        for used_stations in used_station_ids:                  # selected stations for stoping
            if entry['station'] == used_stations:               # is this station in selected stations?
                log.finish_run(entry)                           # save end in log 
                stations.deactivate(entry['station'])           # stations to OFF
                ending = True   

    if ending:
        log.info(NAME, _('Stoping stations in scheduler'))


def read_log():
    """Read log data from json file."""
    try:
        with open(os.path.join(plugin_data_dir(), 'log.json')) as logf:
            return json.load(logf)
    except IOError:
        return []


def read_graph_log():
    """Read graph data from json file."""
    try:
        with open(os.path.join(plugin_data_dir(), 'graph.json')) as logf:
            return json.load(logf)
    except IOError:
        return []


def read_sql_log():
    """Read log data from database file."""
    data = None

    try:
        from plugins.database_connector import execute_db
        sql = "SELECT * FROM pressmonitor ORDER BY id DESC"
        data = execute_db(sql, test=False, commit=False, fetch=True) # fetch=true return data from table in format: id,datetime,ds1,ds2,ds3,ds4,ds5,ds6,dhttemp,dhthumi,dhtstate
    except:
        log_pressure_problem('read_sql_log', _('Pressure monitor plug-in') + ': ' + traceback.format_exc().splitlines()[-1])
        pass

    return data


def read_graph_sql_log():
    """Read graph data from database file and convert it to json balance file."""
    data = []

    try:
        sql_data = read_sql_log()
        statelabel  = _('State')
 
        graph_data = [
            {"station": statelabel, "balances": {}}
        ]

        if sql_data is not None:
            for row in sql_data:
                # row[0] is ID, row[1] is datetime, row[2] is state
                epoch = int(datetime.datetime.timestamp(row[1]))
                temp1 = graph_data[0]['balances']
                state = {'total': float(row[2])}
                temp1.update({epoch: state})

        data = graph_data

    except:
        log_pressure_problem('read_graph_sql_log', _('Pressure monitor plug-in') + ': ' + traceback.format_exc().splitlines()[-1])
        pass

    return data


def write_log(json_data):
    """Write data to log json file."""
    try:
        with open(os.path.join(plugin_data_dir(), 'log.json'), 'w') as outfile:
            json.dump(json_data, outfile)
    except:
        log_pressure_problem('write_log', _('Pressure monitor plug-in') + ': ' + traceback.format_exc().splitlines()[-1])

def write_graph_log(json_data):
    """Write data to graph json file."""
    try:
        with open(os.path.join(plugin_data_dir(), 'graph.json'), 'w') as outfile:
            json.dump(json_data, outfile)
    except:
        log_pressure_problem('write_graph_log', _('Pressure monitor plug-in') + ': ' + traceback.format_exc().splitlines()[-1])

def update_log(status):
    """Update data in json files."""

    if pressure_options['enable_log']:
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
        data['state'] = str(status)

        log_data.insert(0, data)
        if pressure_options['log_records'] > 0:
            log_data = log_data[:pressure_options['log_records']]
        write_log(log_data)

        ### Data for graph log ###
        try:
            graph_data = read_graph_log()
        except:
            create_default_graph()
            graph_data = read_graph_log()

        timestamp = int(time.time())

        try:
            state = graph_data[0]['balances']
            stateval = {'total': status}
            state.update({timestamp: stateval})
        
            write_graph_log(graph_data)
            log.info(NAME, _('Saving to log files OK.'))
        except:
            create_default_graph()

    if pressure_options['en_sql_log']:
        try:
            from plugins.database_connector import execute_db, table_exists
            if not table_exists('pressmonitor'):
                sql = "CREATE TABLE IF NOT EXISTS pressmonitor (id INT NOT NULL AUTO_INCREMENT PRIMARY KEY, ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP, actual VARCHAR(3))"
                execute_db(sql, test=False, commit=False)
            # next insert data to table pressmonitor
            sql = "INSERT INTO `pressmonitor` (`actual`) VALUES ('%s')" % (status)
            execute_db(sql, test=False, commit=True)  # yes commit inserted data
            log.info(NAME, _('Saving to SQL database.'))
        except:
            log_pressure_problem('update_sql_log', _('Pressure monitor plug-in') + ': ' + traceback.format_exc().splitlines()[-1])
            pass

def create_default_graph():
    """Create default graph json file."""
    state = _('State')
    graph_data = [
       {"station": state, "balances": {}}
    ]
    write_graph_log(graph_data)
    log.debug(NAME, _('Creating default graph log files OK'))

################################################################################
# Web pages:                                                                   #
################################################################################

class settings_page(ProtectedPage):
    """Load an html page for entering wind speed monitor settings."""

    def GET(self):
        try:
            global pressure_sender

            qdict = web.input()
            show = helpers.get_input(qdict, 'show', False, lambda x: True)
            delSQL = helpers.get_input(qdict, 'delSQL', False, lambda x: True)
            delfilter = helpers.get_input(qdict, 'delfilter', False, lambda x: True)

            if pressure_sender is not None and 'dt_from' in qdict and 'dt_to' in qdict:
                verify_csrf(qdict)
                dt_from = qdict['dt_from']
                dt_to = qdict['dt_to']
                pressure_options.__setitem__('dt_from', dt_from) #__setitem__(self, key, value)
                pressure_options.__setitem__('dt_to', dt_to)     #__setitem__(self, key, value)

            if pressure_sender is not None and delfilter:
                verify_csrf(qdict)
                from datetime import datetime, timedelta
                dt_now = (datetime.today() + timedelta(days=1)).date()
                pressure_options.__setitem__('dt_from', "2020-01-01T00:00")
                pressure_options.__setitem__('dt_to', "{}T00:00".format(dt_now))

            if pressure_sender is not None and show:
                raise web.seeother(plugin_url(log_page), True)

            if pressure_sender is not None and delSQL:
                verify_csrf(qdict)
                try:
                    from plugins.database_connector import execute_db
                    sql = "DROP TABLE IF EXISTS `pressmonitor`"
                    execute_db(sql, test=False, commit=False)  
                    log.info(NAME, _('Deleting the pressmonitor table from the database.'))
                except:
                    log.error(NAME, _('Pressure monitor plug-in') + ':\n' + traceback.format_exc())

            status = pressure_sender.status if pressure_sender is not None else {}
            return self.plugin_render.pressure_monitor(pressure_options, status, log.events(NAME))

        except:
            log.error(NAME, _('Pressure monitor plug-in') + ':\n' + traceback.format_exc())
            msg = _('An internal error was found in the system, see the error log for more information. The error is in part:') + ' '
            msg += _('pressure_monitor -> settings_page GET')
            return self.core_render.notice('/', msg)

    def POST(self):
        try:
            qdict = web.input(**pressure_options)
            verify_csrf(qdict)
            pressure_options.web_update(qdict) #for save multiple select
            if pressure_sender is not None:
                pressure_sender.update()
            raise web.seeother(plugin_url(settings_page), True)
        except:
            log.error(NAME, _('Pressure monitor plug-in') + ':\n' + traceback.format_exc())
            msg = _('An internal error was found in the system, see the error log for more information. The error is in part:') + ' '
            msg += _('pressure_monitor -> settings_page POST')
            return self.core_render.notice('/', msg)


class help_page(ProtectedPage):
    """Load an html page for help"""

    def GET(self):
        try:
            return self.plugin_render.pressure_monitor_help()
        except:
            log.error(NAME, _('Pressure monitor plug-in') + ':\n' + traceback.format_exc())
            msg = _('An internal error was found in the system, see the error log for more information. The error is in part:') + ' '
            msg += _('pressure_monitor -> help_page GET')
            return self.core_render.notice('/', msg)


class log_page(ProtectedPage):
    """Load an html page for help"""

    def GET(self):
        try:
            global pressure_sender
            qdict = web.input()
            delete = helpers.get_input(qdict, 'delete', False, lambda x: True)
            delSQL = helpers.get_input(qdict, 'delSQL', False, lambda x: True)

            if pressure_sender is not None and delete and pressure_options['enable_log']:
                verify_csrf(qdict)
                write_log([])
                create_default_graph()
                log.info(NAME, _('Deleted all log files OK'))

            if pressure_sender is not None and delSQL and pressure_options['en_sql_log']:
                verify_csrf(qdict)
                try:
                    from plugins.database_connector import execute_db
                    sql = "DROP TABLE IF EXISTS `pressmonitor`"
                    execute_db(sql, test=False, commit=False)  
                    log.info(NAME, _('Deleting the pressmonitor table from the database.'))
                except:
                    log.error(NAME, _('Pressure monitor plug-in') + ':\n' + traceback.format_exc())
                    pass

            return self.plugin_render.pressure_monitor_log(read_log(), read_sql_log(), pressure_options)

        except:
            log.error(NAME, _('Pressure monitor plug-in') + ':\n' + traceback.format_exc())
            msg = _('An internal error was found in the system, see the error log for more information. The error is in part:') + ' '
            msg += _('pressure_monitor -> log_page GET')
            return self.core_render.notice('/', msg)


class settings_json(ProtectedPage):
    """Returns plugin settings in JSON format."""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        try:
            return json.dumps(pressure_options)
        except:
            return {}


class data_json(ProtectedPage):
    """Returns plugin data in JSON format."""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        data = {}
        try:
            if get_check_pressure():
                text = _('INACTIVE')
            else:
                text = _('ACTIVE')

            data =  {
                'label': pressure_options['emlsubject'],
                'pres_state':  text
            }

            return json.dumps(data)

        except:
            return data


class log_json(ProtectedPage):
    """Returns data in JSON format."""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        try:
            return json.dumps(read_log())
        except:
            return {}

class log_sql_json(ProtectedPage):
    """Returns data in JSON format from database file log."""

    def GET(self):
        data = []
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        try:
            data = json.dumps(read_sql_log())
        except:
            log.error(NAME, _('Pressure monitor plug-in') + ':\n' + traceback.format_exc())
            pass
        return data


class graph_json(ProtectedPage):
    """Returns graph data in JSON format."""

    def GET(self):
        data = []
        try:
            from datetime import datetime
            qdict = web.input()

            dt_from_text = qdict.get('dt_from', pressure_options['dt_from'])
            dt_to_text = qdict.get('dt_to', pressure_options['dt_to'])

            dt_from = datetime.strptime(dt_from_text, '%Y-%m-%dT%H:%M') # from
            dt_to   = datetime.strptime(dt_to_text, '%Y-%m-%dT%H:%M')   # to

            epoch_time = datetime(1970, 1, 1)

            log_start = int((dt_from - epoch_time).total_seconds())
            log_end = int((dt_to - epoch_time).total_seconds())
 
            try:
                if pressure_options['type_log'] == 0:
                    json_data = read_graph_log()
                if pressure_options['type_log'] == 1:
                    json_data = read_graph_sql_log()
            except:
                json_data = []
                pass

            if len(json_data) > 0:
                for i in range(0, 1):
                    temp_balances = {}
                    for key in json_data[i]['balances']:
                        try:
                            find_key = int(key.encode('utf8'))                     # key is in unicode ex: u'1601347000' -> find_key is int number
                        except:
                            find_key = key   
                        if find_key >= log_start and find_key <= log_end:          # timestamp interval from <-> to
                            find_data = json_data[i]['balances'][key] 
                            temp_balances[key] = json_data[i]['balances'][key]

                    data.append({ 'station': json_data[i]['station'], 'balances': temp_balances })

        except:
            log.error(NAME, _('Pressure monitor plug-in') + ':\n' + traceback.format_exc())
            pass

        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        return json.dumps(data)


class log_csv(ProtectedPage):  # save log file from web as csv file type
    """Simple Log API"""
    def GET(self):
        data = ""
        try:
            log_file = read_log()
            state = _('State')
            data = "Date/Time; Date; Time; " + state + "\n"

            for interval in log_file:
                data += '; '.join([
                    interval['datetime'],
                    interval['date'],
                    interval['time'],
                    '{}'.format(interval['state']),
                ]) + '\n'

            content = mimetypes.guess_type(os.path.join(plugin_data_dir(), 'log.json')[0])
            web.header('Access-Control-Allow-Origin', '*')
            web.header('Content-type', content) 
            web.header('Content-Disposition', 'attachment; filename="log.csv"')
            return data

        except:
            log.error(NAME, _('Pressure monitor plug-in') + ':\n' + traceback.format_exc())
            msg = _('An internal error was found in the system, see the error log for more information. The error is in part:') + ' '
            msg += _('pressure_monitor -> log_csv GET')
            return self.core_render.notice('/', msg)


class log_sql_csv(ProtectedPage):  # save log file from database as csv file type from web
    """Simple Log API"""
    def GET(self):
        data = []
        try:
            from plugins.database_connector import execute_db
            sql = "SELECT * FROM pressmonitor"
            log_file = execute_db(sql, test=False, commit=False, fetch=True)
            state = _('State')
            data = "ID; Date/Time" + state + "\n"
            for interval in log_file:
                data += '; '.join([
                    '{}'.format(str(interval[0])),
                    '{}'.format(str(interval[1])),
                    '{}'.format(str(interval[2])),
                ]) + '\n'
            filestamp = time.strftime('%Y%m%d-%H%M%S')
            filename = 'log_{}_.csv'.format(filestamp)
            web.header('Access-Control-Allow-Origin', '*')
            web.header('Content-type', 'text/csv') # https://developer.mozilla.org/en-US/docs/Web/HTTP/Basics_of_HTTP/MIME_types/Common_types
            web.header('Content-Disposition', 'attachment; filename="{}"'.format(filename))
            return data

        except:
            log.error(NAME, _('Pressure monitor plug-in') + ':\n' + traceback.format_exc())
            msg = _('An internal error was found in the system, see the error log for more information. The error is in part:') + ' '
            msg += _('pressure_monitor -> log_sql_csv GET')
            return self.core_render.notice('/', msg)


class press_json(ProtectedPage):
    """Returns seconds press state in JSON format."""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        data = {}
        try:
            test = get_check_pressure()
            if not test:
                data['press'] = _('ACTIVE')
            else:
                data['press'] = _('INACTIVE')
            return json.dumps(data)
        except:
            return data
