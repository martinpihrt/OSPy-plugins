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

from threading import Thread, Event

import web
from ospy.stations import stations
from ospy.options import options
from ospy.log import log, logEM
from plugins import PluginOptions, plugin_url, plugin_data_dir
from ospy.webpages import ProtectedPage
from ospy.helpers import datetime_string
from ospy import helpers
from ospy.scheduler import predicted_schedule, combined_schedule

from blinker import signal

from ospy.webpages import showInFooter # Enable plugin to display readings in UI footer


NAME = 'Pressure Monitor'
MENU =  _('Package: Pressure Monitor')
LINK = 'settings_page'

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
    }
)

global master
master = False

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
        self._stop_event = Event()
        
        self.status = {}
        self.status['Pstate%d'] = 0

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
        master_one_on = signal('master_one_on')
        master_one_on.connect(notify_master_on)
        master_one_off = signal('master_one_off')
        master_one_off.connect(notify_master_off)
        master_two_on = signal('master_two_on')
        master_two_on.connect(notify_master_two_on)
        master_two_off = signal('master_two_off')
        master_two_off.connect(notify_master_two_off)
        station_clear = signal('station_clear')
        station_clear.connect(notify_station_clear)

        send = False

        last_time = int(time.time())
        actual_time = int(time.time())
        last_msg = ""
        now_msg = ""
        tempText = ""
 
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
                            log.info(NAME, _('Time to test pressure sensor') + ': ' + str(
                                count_val - (actual_time - last_time)) + ' ' + _('sec') + '.')
                            if actual_time - last_time > int(pressure_options['time']):# wait for activated pressure sensor (time delay)
                                last_time = actual_time
                                if get_check_pressure():                               # if pressure sensor is actual on
                                    set_stations_in_scheduler_off()
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
                            log.error(NAME, _('Pressure monitor plug-in') + ':\n' + traceback.format_exc())
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

                self._sleep(2)

            except Exception:
                log.error(NAME, _('Pressure monitor plug-in') + ':\n' + traceback.format_exc())
                self._sleep(60)


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
        pressure_sender.join()
        pressure_sender = None


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
        log.error(NAME, _('Pressure monitor plug-in') + ':\n' + traceback.format_exc())
        pass


### master 1 on ###
def notify_master_on(name, **kw):
    global master
    log.clear(NAME)
    log.info(NAME, datetime_string() + ' ' + _('Master station 1 is ON.'))
    if pressure_options['enable_log'] or pressure_options['en_sql_log']:
        update_log(2)
    master = True


### master 1 off ###
def notify_master_off(name, **kw):
    global master
    master = False
    log.info(NAME, datetime_string() + ' ' + _('Master station 1 is OFF.'))


### master 2 on ###
def notify_master_two_on(name, **kw):
    global master
    log.clear(NAME)
    log.info(NAME, datetime_string() + ' ' + _('Master station 2 is ON.'))
    if pressure_options['enable_log'] or pressure_options['en_sql_log']:
        update_log(2)
    master = True


### master 2 off ###
def notify_master_two_off(name, **kw):
    global master
    master = False
    log.info(NAME, datetime_string() + ' ' + _('Master station 2 is OFF.'))


### all stations off ###
def notify_station_clear(name, **kw):
    global master
    master = False
    log.info(NAME, datetime_string() + ' ' + _('All stations set to OFF.'))


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
        for used_stations in pressure_options['used_stations']: # selected stations for stoping
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


def write_log(json_data):
    """Write data to log json file."""
    with open(os.path.join(plugin_data_dir(), 'log.json'), 'w') as outfile:
        json.dump(json_data, outfile)


def write_graph_log(json_data):
    """Write data to graph json file."""
    with open(os.path.join(plugin_data_dir(), 'graph.json'), 'w') as outfile:
        json.dump(json_data, outfile)


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
            from plugins.database_connector import execute_db
            # first create table upsmonitor if not exists
            sql = "CREATE TABLE IF NOT EXISTS pressmonitor (id INT NOT NULL AUTO_INCREMENT PRIMARY KEY, ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP, actual VARCHAR(3))"
            execute_db(sql, test=False, commit=False) # not commit
            # next insert data to table pressmonitor
            sql = "INSERT INTO `pressmonitor` (`actual`) VALUES ('%s')" % (status)
            execute_db(sql, test=False, commit=True)  # yes commit inserted data
            log.info(NAME, _('Saving to SQL database.'))
        except:
            log.error(NAME, _('Pressure monitor plug-in') + ':\n' + traceback.format_exc())
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
    """Load an html page for entering pressure adjustments."""

    def GET(self):
        global pressure_sender

        qdict = web.input()
        delete = helpers.get_input(qdict, 'delete', False, lambda x: True)
        show = helpers.get_input(qdict, 'show', False, lambda x: True)

        if pressure_sender is not None and delete:
           write_log([])
           create_default_graph()

           raise web.seeother(plugin_url(settings_page), True)

        if pressure_sender is not None and 'history' in qdict:
           history = qdict['history']
           pressure_options.__setitem__('history', int(history))

        if pressure_sender is not None and show:
            raise web.seeother(plugin_url(log_page), True)

        return self.plugin_render.pressure_monitor(pressure_options, pressure_sender.status, log.events(NAME))

    def POST(self):
        pressure_options.web_update(web.input(**pressure_options)) #for save multiple select

        if pressure_sender is not None:
            pressure_sender.update()
        raise web.seeother(plugin_url(settings_page), True)


class help_page(ProtectedPage):
    """Load an html page for help"""

    def GET(self):
        return self.plugin_render.pressure_monitor_help()


class log_page(ProtectedPage):
    """Load an html page for help"""

    def GET(self):
        return self.plugin_render.pressure_monitor_log(read_log(), pressure_options)


class settings_json(ProtectedPage):
    """Returns plugin settings in JSON format."""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        return json.dumps(pressure_options)


class data_json(ProtectedPage):
    """Returns plugin data in JSON format."""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
  
        if get_check_pressure():
           text = _('INACTIVE')
        else:
           text = _('ACTIVE')
  
        data =  {
          'label': pressure_options['emlsubject'],
          'pres_state':  text
        }

        return json.dumps(data)

class log_json(ProtectedPage):
    """Returns data in JSON format."""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        return json.dumps(read_log())


class graph_json(ProtectedPage):
    """Returns graph data in JSON format."""

    def GET(self):
        data = []

        epoch = datetime.date(1970, 1, 1)                                      # first date
        current_time  = datetime.date.today()                                  # actual date

        if pressure_options['history'] == 0:                                   # without filtering
            web.header('Access-Control-Allow-Origin', '*')
            web.header('Content-Type', 'application/json')
            return json.dumps(read_graph_log())

        if pressure_options['history'] == 1:
            check_start  = current_time - datetime.timedelta(days=1)           # actual date - 1 day
        if pressure_options['history'] == 2:
            check_start  = current_time - datetime.timedelta(days=7)           # actual date - 7 day (week)
        if pressure_options['history'] == 3:
            check_start  = current_time - datetime.timedelta(days=30)          # actual date - 30 day (month)
        if pressure_options['history'] == 4:
            check_start  = current_time - datetime.timedelta(days=365)         # actual date - 365 day (year)

        log_start = int((check_start - epoch).total_seconds())                 # start date for log in second (timestamp)

        try:
            json_data = read_graph_log()
        except:
            json_data = []
            pass

        temp_balances = {}

        if len(json_data) > 0:
            for key in json_data[0]['balances']:
                find_key =  int(key.encode('utf8'))                            # key is in unicode ex: u'1601347000' -> find_key is int number
                if find_key >= log_start:                                      # timestamp interval 
                    temp_balances[key] = json_data[0]['balances'][key]
            data.append({ 'station': json_data[0]['station'], 'balances': temp_balances })

        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        return json.dumps(data)


class log_csv(ProtectedPage):  # save log file from web as csv file type
    """Simple Log API"""
    def GET(self):
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


class press_json(ProtectedPage):
    """Returns seconds press state in JSON format."""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        data = {}
        test = get_check_pressure()
        if not test:
           data['press'] = _('ACTIVE')
        else:
           data['press'] = _('INACTIVE')
        return json.dumps(data)