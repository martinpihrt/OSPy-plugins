# -*- coding: utf-8 -*-
__author__ = 'Martin Pihrt'
# this plugins check power line and shutdown ospi system (count down to reconect power line) and shutdown UPS after time.

import json
import time
import datetime
import sys
import os
import traceback
import mimetypes

from threading import Thread, Event

import web
from ospy.helpers import poweroff
from ospy.log import log, logEM
from plugins import PluginOptions, plugin_url, plugin_data_dir
from ospy.webpages import ProtectedPage
from ospy.helpers import datetime_string
from ospy.options import options
from ospy import helpers

from ospy.webpages import showInFooter # Enable plugin to display readings in UI footer


NAME = 'UPS Monitor'
MENU =  _('Package: UPS Monitor')
LINK = 'settings_page'

ups_options = PluginOptions(
    NAME,
    {
        'time': 60, # in minutes
        'ups': False,
        'sendeml': False,
        'emlsubject': _('Report from OSPy UPS plugin'),
        'enable_log': False,
        'log_records': 0,                             # 0 = unlimited
        'use_footer': True,                           # show data from plugin in footer on home page
        'eplug': 0,                                   # email plugin type (email notifications or email notifications SSL)
        'en_sql_log': False,                          # logging temperature to sql database
        'type_log': 0,                                # 0 = show log and graph from local log file, 1 = from database
        'dt_from' : '2024-01-01T00:00',               # for graph history (from date time ex: 2024-02-01T6:00)
        'dt_to' : '2024-01-01T00:00',                 # for graph history (to date time ex: 2024-03-17T12:00)
    }
)

################################################################################
# GPIO input pullup and output:                                                #
################################################################################

import RPi.GPIO as GPIO  # RPi hardware

pin_power_ok = 16 # GPIO23
pin_ups_down = 18 # GPIO24

try:
    GPIO.setup(pin_power_ok, GPIO.IN, pull_up_down=GPIO.PUD_UP)
except NameError:
    pass

try:
    GPIO.setmode(GPIO.BOARD) ## Use board pin numbering
    GPIO.setup(pin_ups_down, GPIO.OUT)
    GPIO.output(pin_ups_down, GPIO.LOW)
except NameError:
    pass


################################################################################
# Main function loop:                                                          #
################################################################################

class UPSSender(Thread):
    def __init__(self):
        Thread.__init__(self)
        self.daemon = True
        self._stop_event = Event()

        self.status = {}
        self.status['power%d'] = 0

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
        reboot_time = False
        once = True
        once_two = True
        once_three = True

        last_time = int(time.time())

        ups_mon = None

        if ups_options['use_footer']:
            ups_mon = showInFooter() #  instantiate class to enable data in footer
            ups_mon.button = "ups_adj/settings"            # button redirect on footer
            ups_mon.label =  _('UPS')                      # label on footer

        while not self._stop_event.is_set():
            try:
                if ups_options['ups']:                                     # if ups plugin is enabled
                    test = get_check_power()
                
                    if not test:
                        text = _(u'OK')
                    else:
                        text = _(u'FAULT')
                    self.status['power%d'] = text

                    if ups_options['use_footer']:
                        if ups_mon is not None:
                            ups_mon.val = text.encode('utf8').decode('utf8')              # value on footer

                    if not test:
                        last_time = int(time.time())

                    if test:                                               # if power line is not active
                        reboot_time = True                                 # start countdown timer
                        if once:
                            # send email with info power line fault
                            msg = '<b>' + _('UPS plug-in') + '</b> ' + '<br><p style="color:red;">' + _('Detected fault on power line.') + '</p>'
                            msglog = _('UPS plug-in') + ': ' + _('Detected fault on power line.')
                            log.info(NAME, msglog)
                            if ups_options['sendeml']:                       # if enabled send email
                                try:
                                    try_mail = None
                                    if ups_options['eplug']==0: # email_notifications
                                        from plugins.email_notifications import try_mail
                                    if ups_options['eplug']==1: # email_notifications SSL
                                        from plugins.email_notifications_ssl import try_mail    
                                    if try_mail is not None:
                                        try_mail(msg, msglog, attachment=None, subject=ups_options['emlsubject']) # try_mail(text, logtext, attachment=None, subject=None)

                                except Exception:
                                    log.error(NAME, _('UPS plug-in') + ':\n' + traceback.format_exc())
                                once_three = True
                            if ups_options['enable_log'] or ups_options['en_sql_log']:
                                update_log(0)
                            once = False

                    if reboot_time and test:
                        count_val = int(ups_options['time']) * 60             # value for countdown
                        actual_time = int(time.time())
                        log.clear(NAME)
                        log.info(NAME, _('Time to shutdown') + ': ' + str(count_val - (actual_time - last_time)) + ' ' + _('sec'))
                        if ((actual_time - last_time) >= count_val):        # if countdown is 0
                            last_time = actual_time
                            test = get_check_power()
                            if test:                                         # if power line is current not active
                                log.clear(NAME)
                                log.info(NAME, _('Power line is not restore in time -> sends email and shutdown system.'))
                                reboot_time = False
                                if ups_options['sendeml']:                    # if enabled send email
                                    if once_two:
                                        # send email with info shutdown system
                                        msg = '<b>' + _('UPS plug-in') + '</b> ' + '<br><p style="color:red;">' + _('Power line is not restore in time -> shutdown system!') + '</p>'
                                        msglog =  _('UPS plug-in') + ': ' + _('Power line is not restore in time -> shutdown system!')
                                        try:
                                            try_mail = None
                                            if ups_options['eplug']==0: # email_notifications
                                                from plugins.email_notifications import try_mail
                                            if ups_options['eplug']==1: # email_notifications SSL
                                                from plugins.email_notifications_ssl import try_mail    
                                            if try_mail is not None:                                            
                                                try_mail(msg, msglog, attachment=None, subject=ups_options['emlsubject']) # try_mail(text, logtext, attachment=None, subject=None)

                                        except Exception:
                                            log.error(NAME, _('UPS plug-in') + ':\n' + traceback.format_exc()) 
                                        once_two = False

                                GPIO.output(pin_ups_down, GPIO.HIGH)          # switch on GPIO fo countdown UPS battery power off
                                self._sleep(4)
                                GPIO.output(pin_ups_down, GPIO.LOW)
                                poweroff(1, True)                             # shutdown system

                    if not test:
                        if once_three:
                            if ups_options['sendeml']:                     # if enabled send email
                                msg = '<b>' + _('UPS plug-in') + '</b> ' + '<br><p style="color:green;">' + _('Power line has restored - OK.') + '</p>'
                                msglog = _('UPS plug-in') + ': ' +  _('Power line has restored - OK.')
                                log.clear(NAME)
                                log.info(NAME, msglog)
                                try:
                                    try_mail = None
                                    if ups_options['eplug']==0: # email_notifications
                                        from plugins.email_notifications import try_mail
                                    if ups_options['eplug']==1: # email_notifications SSL
                                        from plugins.email_notifications_ssl import try_mail    
                                    if try_mail is not None:
                                        try_mail(msg, msglog, attachment=None, subject=ups_options['emlsubject']) # try_mail(text, logtext, attachment=None, subject=None)

                                except Exception:     
                                    log.error(NAME, _('UPS plug-in') + ':\n' + traceback.format_exc()) 

                            once = True
                            once_two = True
                            once_three = False
                            if ups_options['enable_log'] or ups_options['en_sql_log']:
                                update_log(1)

                self._sleep(2)

            except Exception:
                log.error(NAME, _('UPS plug-in') + ': \n' + traceback.format_exc())
                self._sleep(60)


ups_sender = None

################################################################################
# Helper functions:                                                            #
################################################################################
def start():
    global ups_sender
    if ups_sender is None:
        ups_sender = UPSSender()
        log.clear(NAME)
        log.info(NAME, _('UPS plugin is started.'))


def stop():
    global ups_sender
    if ups_sender is not None:
        ups_sender.stop()
        ups_sender.join()
        ups_sender = None


def get_check_power_str():
    if GPIO.input(pin_power_ok) == 0:
        pwr = _('GPIO Pin = 0 Power line is OK.')
    else:
        pwr = _('GPIO Pin = 1 Power line ERROR.')
    return pwr


def get_check_power():
    try:
        if GPIO.input(pin_power_ok):  # power line detected
            pwr = 1
        else:
            pwr = 0
        return pwr
    except NameError:
        pass


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

    if ups_options['enable_log']:
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
        if ups_options['log_records'] > 0:
            log_data = log_data[:ups_options['log_records']]
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
            log.info(NAME, _('Saving to log  files OK'))
        except:
            create_default_graph()

    if ups_options['en_sql_log']:
        try:
            from plugins.database_connector import execute_db
            # first create table upsmonitor if not exists
            sql = "CREATE TABLE IF NOT EXISTS upsmonitor (id INT NOT NULL AUTO_INCREMENT PRIMARY KEY, ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP, actual VARCHAR(3))"
            execute_db(sql, test=False, commit=False) # not commit
            # next insert data to table upsmonitor
            sql = "INSERT INTO `upsmonitor` (`actual`) VALUES ('%s')" % (status)
            execute_db(sql, test=False, commit=True)  # yes commit inserted data
            log.info(NAME, _('Saving to SQL database.'))
        except:
            log.error(NAME, _('UPS plugin') + ':\n' + traceback.format_exc())
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
    """Load an html page for entering USP adjustments."""

    def GET(self):
        global ups_sender

        qdict = web.input()
        delete = helpers.get_input(qdict, 'delete', False, lambda x: True)
        show = helpers.get_input(qdict, 'show', False, lambda x: True)
        delSQL = helpers.get_input(qdict, 'delSQL', False, lambda x: True)

        delfilter = helpers.get_input(qdict, 'delfilter', False, lambda x: True)

        if ups_sender is not None and 'dt_from' in qdict and 'dt_to' in qdict:
            dt_from = qdict['dt_from']
            dt_to = qdict['dt_to']
            ups_options.__setitem__('dt_from', dt_from) #__setitem__(self, key, value)
            ups_options.__setitem__('dt_to', dt_to)     #__setitem__(self, key, value)

        if ups_sender is not None and show:
            raise web.seeother(plugin_url(log_page), True)

        if ups_sender is not None and delSQL:
            try:
                from plugins.database_connector import execute_db
                sql = "DROP TABLE IF EXISTS `upsmonitor`"
                execute_db(sql, test=False, commit=False)  
                log.info(NAME, _('Deleting the upsmonitor table from the database.'))
            except:
                log.error(NAME, _('UPS plug-in') + ':\n' + traceback.format_exc())
                pass            

        return self.plugin_render.ups_adj(ups_options, ups_sender.status, log.events(NAME))

    def POST(self):
        ups_options.web_update(web.input())

        if ups_sender is not None:
            ups_sender.update()
        raise web.seeother(plugin_url(settings_page), True)


class help_page(ProtectedPage):
    """Load an html page for help"""

    def GET(self):
        return self.plugin_render.ups_adj_help()


class log_page(ProtectedPage):
    """Load an html page for help"""

    def GET(self):
        global ups_sender
        qdict = web.input()
        delete = helpers.get_input(qdict, 'delete', False, lambda x: True)
        delSQL = helpers.get_input(qdict, 'delSQL', False, lambda x: True)
        
        if ups_sender is not None and delete and ups_options['enable_log']:
           write_log([])
           create_default_graph()
           log.info(NAME, _('Deleted all log files OK'))

        if ups_sender is not None and delSQL and ups_options['en_sql_log']:
            try:
                from plugins.database_connector import execute_db
                sql = "DROP TABLE IF EXISTS `upsmonitor`"
                execute_db(sql, test=False, commit=False)  
                log.info(NAME, _('Deleting the upsmonitor table from the database.'))
            except:
                log.error(NAME, _('UPS plugin') + ':\n' + traceback.format_exc())
                pass          

        return self.plugin_render.ups_adj_log(read_log(), read_sql_log(), ups_options)


class settings_json(ProtectedPage):
    """Returns plugin settings in JSON format."""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        return json.dumps(ups_options)


class data_json(ProtectedPage):
    """Returns plugin data in JSON format."""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        test = get_check_power()
        if not test:
           text = _('OK')
        else:
           text = _('FAULT')

        data =  {
          'label': ups_options['emlsubject'],
          'ups_state':  text
        }

        return json.dumps(data)


def read_sql_log():
    """Read log data from database file."""
    data = None

    try:
        from plugins.database_connector import execute_db
        sql = "SELECT * FROM upsmonitor ORDER BY id DESC"
        data = execute_db(sql, test=False, commit=False, fetch=True)
    except:
        log.error(NAME, _('UPS plugin') + ':\n' + traceback.format_exc())
        pass

    return data


class log_json(ProtectedPage):
    """Returns data in JSON format."""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        return json.dumps(read_log())


def read_graph_sql_log():
    """Read graph data from database file and convert it to json balance file."""
    data = []

    try:
        sql_data = read_sql_log()
        state = _('State')
 
        graph_data = [
            {"station": state, "balances": {}}
        ]

        if sql_data is not None:
            for row in sql_data:
                # row[0] is ID, row[1] is datetime, row[2] is state
                epoch = int(datetime.datetime.timestamp(row[1]))
            
                temp0 = graph_data[0]['balances']
                state = {'total': float(row[2])}
                temp0.update({epoch: state})

        data = graph_data

    except:
        log.error(NAME, _('UPS plugin') + ':\n' + traceback.format_exc())
        pass

    return data


class graph_json(ProtectedPage):
    """Returns graph data in JSON format."""

    def GET(self):
        data = []
        try:
            from datetime import datetime

            dt_from = datetime.strptime(ups_options['dt_from'], '%Y-%m-%dT%H:%M') # from
            dt_to   = datetime.strptime(ups_options['dt_to'], '%Y-%m-%dT%H:%M')   # to

            epoch_time = datetime(1970, 1, 1)

            log_start = int((dt_from - epoch_time).total_seconds())
            log_end = int((dt_to - epoch_time).total_seconds())
 
            try:
                if ups_options['type_log'] == 0:
                    json_data = read_graph_log()
                if ups_options['type_log'] == 1:
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
            log.error(NAME, _('UPS plugin') + ':\n' + traceback.format_exc())
            pass

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
            sql = "SELECT * FROM upsmonitor"
            log_file = execute_db(sql, test=False, commit=False, fetch=True)
            state = _('State')
            data = "ID; Date/Time; " + state + "\n"
            for interval in log_file:
                data += '; '.join([
                    '{}'.format(str(interval[0])),
                    '{}'.format(str(interval[1])),
                    '{}'.format(str(interval[2])),                   
                ]) + '\n'

        except:
            log.error(NAME, _('UPS plugin') + ':\n' + traceback.format_exc())
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
            log.error(NAME, _('UPS plugin') + ':\n' + traceback.format_exc())
            pass
        return data


class ups_json(ProtectedPage):
    """Returns seconds ups state in JSON format."""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        data = {}
        test = get_check_power()
        if not test:
           data['ups'] = _('OK')
        else:
           data['ups'] = _('FAULT')
        return json.dumps(data)