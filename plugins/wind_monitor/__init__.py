# -*- coding: utf-8 -*-
__author__ = u'Martin Pihrt'
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
from ospy.programs import programs

from ospy.webpages import showInFooter # Enable plugin to display readings in UI footer


NAME = 'Wind Speed Monitor'
MENU =  _('Package: Wind Speed Monitor')
LINK = 'settings_page'

wind_options = PluginOptions(
    NAME,
    {
        'use_wind_monitor': False,
        'address': False,            # True = 0x51, False = 0x50 for PCF8583
        'sendeml': True,             # True = send email with error
        'pulses': 2,                 # 2 pulses per rotation
        'metperrot': 1.492,          # 1.492 meter per hour per rotation
        'maxspeed': 20,              # 20 max speed to deactivate stations  
        'emlsubject': _('Report from OSPy WIND SPEED MONITOR plugin'),
        'enable_log': False,         # log to file and graph
        'log_interval': 1,           # log interval in minutes
        'log_records': 0,            # log records 0= unlimited 
        'use_kmh': False,            # measure in km/h or m/s
        'enable_log_change': False,  # enable save log max speed if max wind > last max wind
        'delete_max_24h': False,     # deleting max speed after xx hours or minutes
        'delete_max': '24h',         # 24 hours is default interval for deleting maximal speed 
        'history': 0,                # selector for graph history
        'stoperr': False,            # True = stoping is enabled
        'used_stations': [],         # use this stations for stoping scheduler if stations is activated in scheduler
        'use_footer': True,          # show data from plugin in footer on home page
        'eplug': 0,                  # email plugin type (email notifications or email notifications SSL)
        'use_stop_pgm': False,       # run the program when exceeded
        'm_speed_trig': 10,          # maximum wind speed for starting the program in m/s
        'event_repetitions': 3,      # number of event repetitions for the action (3x repeating)
        'event_interval': 1,         # repeatedly exceeded in these interval (minutes)
        'ignore_interval': 24,       # ignore other events for a while (24 hours)
        'used_program': [],          # selector for running program (-1 is none)
        'en_sql_log': False,         # logging temperature to sql database        
    }
)


################################################################################
# Main function loop:                                                          #
################################################################################

class WindSender(Thread):
    def __init__(self):
        Thread.__init__(self)
        self.daemon = True
        self._stop_event = Event()
   
        self.status = {}
        self.status['meter'] = 0.0
        self.status['kmeter'] = 0.0
        self.status['max_meter'] = 0
        self.status['log_date_maxspeed'] = datetime_string()

        self._sleep_time = 0
        self.start()

    def stop(self):
        self._stop_event.set()

    def update(self):
        self._sleep_time = 0

    def _sleep(self, secs):
        self._sleep_time = secs
        while self._sleep_time > 0 and not self._stop_event.is_set():
            time_.sleep(1)
            self._sleep_time -= 1

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

        if wind_options['use_footer']:
            wind_mon = showInFooter() #  instantiate class to enable data in footer
            wind_mon.label = _(u'Wind Speed')           # label on footer
            wind_mon.val = '---'                        # value on footer
            wind_mon.button = "wind_monitor/settings"   # button redirect on footer

        while not self._stop_event.is_set():
            try:
                if wind_options['use_wind_monitor']:    # if wind plugin is enabled
                    disable_text = True
                    try:
                        import smbus  # for PCF 8583
                        self.bus = smbus.SMBus(0 if helpers.get_rpi_revision() == 1 else 1)

                    except ImportError:
                        log.warning(NAME, _(u'Could not import smbus.'))

                    if self.bus is not None:
                        set_counter(self.bus)     # set pcf8583 as counter
                        puls = counter(self.bus)  # read pulses

                    if puls is not None and puls < 1000:        # limiter for maximal pulses from counter (error filter)
                        puls = counter(self.bus)/10.0           # counter value is value/10sec
                        val = puls/(wind_options['pulses']*1.0)
                        val = val*wind_options['metperrot']

                        self.status['meter']  = round(val*1.0, 2)
                        self.status['kmeter'] = round(val*3.6, 2)

                        if self.status['meter'] > self.status['max_meter']:
                            self.status['max_meter'] = self.status['meter']
                            self.status['log_date_maxspeed'] = datetime_string()
                            if wind_options['enable_log_change']:
                                if wind_options['enable_log'] or wind_options['en_sql_log']: 
                                    update_log()

                        log.info(NAME, datetime_string())
                        if wind_options['use_kmh']:
                            log.info(NAME, _('Speed') + ': ' + '%.1f' % round(self.status['meter']*3.6, 2) + ' ' + _('km/h') + ', ' + _('Pulses') + ': ' + '%s' % puls + ' ' + _('pulses/sec'))                  
                        else:
                            log.info(NAME, _('Speed') + ': ' + '%.1f' % round(self.status['meter'], 2) + ' ' + _('m/sec') + ', ' + _('Pulses') + ': ' +  '%s' % puls + ' ' + _('pulses/sec'))  

                        if wind_options['use_kmh']:
                            log.info(NAME, '%s' % self.status['log_date_maxspeed'] + ' ' + _('Maximal speed') + ': ' + '%s' % round(self.status['max_meter']*3.6, 2) + ' ' + _('km/h'))  
                        else:    
                            log.info(NAME, '%s' % self.status['log_date_maxspeed'] + ' ' + _('Maximal speed') + ': ' + '%s' % round(self.status['max_meter'], 2)  + ' ' + _('m/sec'))  

                        if self.status['meter'] >= 42: 
                            log.error(NAME, datetime_string() + ' ' + _('Wind speed > 150 km/h (42 m/sec)'))

                        if self.status['meter'] >= int(wind_options['maxspeed']):          # if wind speed is > options max speed
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
                        if wind_options['use_stop_pgm'] and not ignore_intervals:                                     # action is enabled and not active delay ignore
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

                    except Exception:
                        log.error(NAME, _('Wind Speed monitor plug-in') + ':\n' + traceback.format_exc()) 

            except Exception:
                log.clear(NAME)
                log.error(NAME, _('Wind Speed monitor plug-in') + ':\n' + traceback.format_exc())
                self._sleep(60)


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
        wind_sender.join()
        wind_sender = None


def try_io(call, tries=10):
    assert tries > 0
    error = None
    result = None

    while tries:
        try:
            result = call()
        except IOError as e:
            error = e
            tries -= 1
            time.sleep(0.01)
        else:
            break

    if not tries:
        raise error

    return result


def set_counter(i2cbus):
    try:
        addr = 0
        if wind_options['address']:
            addr = 0x51
        else:
            addr = 0x50
        try_io(lambda: i2cbus.write_byte_data(addr, 0x00, 0x20)) # status registr setup to "EVENT COUNTER"
        try_io(lambda: i2cbus.write_byte_data(addr, 0x01, 0x00)) # reset LSB
        try_io(lambda: i2cbus.write_byte_data(addr, 0x02, 0x00)) # reset midle Byte
        try_io(lambda: i2cbus.write_byte_data(addr, 0x03, 0x00)) # reset MSB
        log.debug(NAME, _('Wind speed monitor plug-in') + ': ' + _('Setup PCF8583 as event counter - OK')) 
    except:
        log.error(NAME, _('Wind speed monitor plug-in') + ':\n' + _('Setup PCF8583 as event counter - FAULT'))
        log.error(NAME, _('Wind speed monitor plug-in') + '%s' % traceback.format_exc())


def counter(i2cbus): # reset PCF8583, measure pulses and return number pulses per second
    try:
        pulses = 0
        addr = 0
        if wind_options['address']:
            addr = 0x51
        else:
            addr = 0x50
        # reset PCF8583
        try_io(lambda: i2cbus.write_byte_data(addr, 0x01, 0x00)) # reset LSB
        try_io(lambda: i2cbus.write_byte_data(addr, 0x02, 0x00)) # reset midle Byte
        try_io(lambda: i2cbus.write_byte_data(addr, 0x03, 0x00)) # reset MSB
        time_.sleep(10)
        # read number (pulses in counter) and translate to DEC
        counter = try_io(lambda: i2cbus.read_i2c_block_data(addr, 0x00))
        num1 = (counter[1] & 0x0F)             # units
        num10 = (counter[1] & 0xF0) >> 4       # dozens
        num100 = (counter[2] & 0x0F)           # hundred
        num1000 = (counter[2] & 0xF0) >> 4     # thousand
        num10000 = (counter[3] & 0x0F)         # tens of thousands
        num100000 = (counter[3] & 0xF0) >> 4   # hundreds of thousands
        pulses = (num100000 * 100000) + (num10000 * 10000) + (num1000 * 1000) + (num100 * 100) + (num10 * 10) + num1
        return pulses
    except:
        log.error(NAME, _('Wind speed monitor plug-in') + u'%s' % traceback.format_exc())
        time_.sleep(10)
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
            from plugins.database_connector import execute_db
            # first create table windmonitor if not exists
            sql = "CREATE TABLE IF NOT EXISTS windmonitor (id INT NOT NULL AUTO_INCREMENT PRIMARY KEY, ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP, max VARCHAR(7), actual VARCHAR(7))"
            execute_db(sql, test=False, commit=False) # not commit
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


class settings_page(ProtectedPage):
    """Load an html page for entering wind speed monitor settings."""

    def GET(self):
        global wind_sender

        qdict = web.input()
        reset = helpers.get_input(qdict, 'reset', False, lambda x: True)
        delete = helpers.get_input(qdict, 'delete', False, lambda x: True)
        show = helpers.get_input(qdict, 'show', False, lambda x: True)
        delSQL = helpers.get_input(qdict, 'delSQL', False, lambda x: True)        

        if wind_sender is not None and reset:
            wind_sender.status['max_meter'] = 0
            wind_sender.status['log_date_maxspeed'] = datetime_string()
            log.clear(NAME)
            log.info(NAME, datetime_string() + ' ' + _('Maximal speed has reseted.'))
            raise web.seeother(plugin_url(settings_page), True)

        if wind_sender is not None and delete:
            write_log([])
            create_default_graph()
            log.info(NAME, datetime_string() + ' ' + _('Deleted all log files OK'))
            raise web.seeother(plugin_url(settings_page), True)

        if wind_sender is not None and 'history' in qdict:
            history = qdict['history']
            wind_options.__setitem__('history', int(history))

        if wind_sender is not None and show:
            raise web.seeother(plugin_url(log_page), True)

        if wind_sender is not None and delSQL:
            try:
                from plugins.database_connector import execute_db
                sql = "DROP TABLE IF EXISTS `windmonitor`"
                execute_db(sql, test=False, commit=False)  
                log.info(NAME, _('Deleting the windmonitor table from the database.'))
            except:
                log.error(NAME, _('Wind speed monitor plug-in') + ':\n' + traceback.format_exc())
                pass            

        return self.plugin_render.wind_monitor(wind_options, wind_sender.status, log.events(NAME))

    def POST(self):
        wind_options.web_update(web.input(used_stations=[])) #for save multiple select

        if wind_sender is not None:
            wind_sender.update()

        if wind_options['use_wind_monitor']:
            log.clear(NAME) 
            log.info(NAME, _('Wind monitor is enabled.'))
        else:
            log.clear(NAME)
            log.info(NAME, _('Wind monitor is disabled.'))

        log.info(NAME, datetime_string() + ' ' + _('Options has updated.'))

        raise web.seeother(plugin_url(settings_page), True)

class help_page(ProtectedPage):
    """Load an html page for help"""

    def GET(self):
        return self.plugin_render.wind_monitor_help()

class log_page(ProtectedPage):
    """Load an html page for help"""

    def GET(self):
        return self.plugin_render.wind_monitor_log(read_log(), wind_options)

class settings_json(ProtectedPage):
    """Returns plugin settings in JSON format."""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        return json.dumps(wind_options)

class data_json(ProtectedPage):
    """Returns plugin data in JSON format."""
    global wind_sender

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        data =  {
          'log_maxspeed': round(wind_sender.status['max_meter'], 2),    # in m/sec
          'log_speed': round(wind_sender.status['meter'],2),          # in m/sec
          'log_date_maxspeed': wind_sender.status['log_date_maxspeed'],
          'label': wind_options['emlsubject']
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

        if wind_options['history'] == 0:                                       # without filtering
            web.header('Access-Control-Allow-Origin', '*')
            web.header('Content-Type', 'application/json')
            return json.dumps(read_graph_log())

        if wind_options['history'] == 1:
            check_start  = current_time - datetime.timedelta(days=1)           # actual date - 1 day
        if wind_options['history'] == 2:
            check_start  = current_time - datetime.timedelta(days=7)           # actual date - 7 day (week)
        if wind_options['history'] == 3:
            check_start  = current_time - datetime.timedelta(days=30)          # actual date - 30 day (month)
        if wind_options['history'] == 4:
            check_start  = current_time - datetime.timedelta(days=365)         # actual date - 365 day (year)

        log_start = int((check_start - epoch).total_seconds())                 # start date for log in second (timestamp)

        try:
            json_data = read_graph_log()
        except:
            json_data = []
            pass

        if len(json_data) > 0:
            for i in range(0, 2):                                              # 0 = maximum, 2 = actual
                temp_balances = {}
                for key in json_data[i]['balances']:
                    find_key =  int(key.encode('utf8'))                        # key is in unicode ex: u'1601347000' -> find_key is int number
                    if find_key >= log_start:                                  # timestamp interval 
                        temp_balances[key] = json_data[i]['balances'][key]
                data.append({ 'station': json_data[i]['station'], 'balances': temp_balances })

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
                u'{}'.format(interval['maximum']),
                u'{}'.format(interval['actual']),
            ]) + '\n'

        content = mimetypes.guess_type(os.path.join(plugin_data_dir(), 'log.json')[0])
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-type', content) 
        web.header('Content-Disposition', 'attachment; filename="log.csv"')
        return data

class wind_json(ProtectedPage):
    """Returns seconds water in JSON format."""

    def GET(self):
        global wind_sender
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        data = {}
        try:
            if wind_options['use_kmh']:
                data['wind'] = '{} {}'.format(round(wind_sender.status['meter']*3.6, 2), _('km/h'))
            else:
                data['wind'] = '{} {}'.format(round(wind_sender.status['meter'], 2), _('m/s'))
        except:
            data['wind'] = '{}'.format(_('Any error'))
        return json.dumps(data)