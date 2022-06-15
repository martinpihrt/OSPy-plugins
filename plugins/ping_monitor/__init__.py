# -*- coding: utf-8 -*-
# this plugin send ping to 1-3 address.

__author__ = u'Martin Pihrt' # www.pihrt.com

#todo restart
#todo log
#todo graf
#todo email

import json
import time
from random import randint
import datetime
import sys
import traceback
import os
import subprocess
import mimetypes

from threading import Thread, Event

import web

from ospy import helpers
from ospy.options import options
from ospy.log import log, logEM
from plugins import PluginOptions, plugin_url, plugin_data_dir
from ospy.helpers import reboot
from ospy.webpages import ProtectedPage
from ospy.helpers import datetime_string


NAME = 'Ping Monitor'
MENU =  _(u'Package: Ping Monitor')
LINK = 'settings_page'

plugin_options = PluginOptions(
    NAME,
    {  'use_ping': False,
       'address_1': '8.8.8.8',      # Google.com
       'address_2': '8.8.4.4',      # Google.com
       'address_3': '77.75.75.176', # Seznam.cz
       'ping_interval': 5,          # ping interval in second
       'ping_count': 3,             # for reboot (fault counter)
       'use_restart': False,
       'use_send_email': False,
       'send_interval': 24,
       'use_send_delete': False,
       'emlsubject':  _('Report from OSPy PING plugin'),
       'enable_log': False,
       'history': 0,                # selector for graph history
       'eplug': 0,                  # email plugin type (email notifications or email notifications SSL)
    }
)

status = { }
################################################################################
# Main function loop:                                                          #
################################################################################

class Sender(Thread):
    def __init__(self):
        Thread.__init__(self)
        self.daemon = True
        self._stop_event = Event()

        global status

        millis = int(round(time.time() * 1000))

        status['ping1']  = 0
        status['ping2']  = 0
        status['ping3']  = 0
        status['last_ping1'] = 0
        status['last_ping2'] = 0
        status['last_ping3'] = 0
        status['state'] = "-"
        status['ERR_diff'] = int(round(time.time() * 1000))
        status['OK_diff'] = int(round(time.time() * 1000))
        status['now_run'] = True

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
        log.clear(NAME)
        time.sleep(
            randint(3, 10)
        )  # Sleep some time to prevent printing before startup information

        last_email_millis = 0    # timer for sending e-mails (ms)
        last_ping_millis  = 0    # timer for sending ping (ms)
        fault_counter     = 0    # counter for restart device
        en_log = False           # enable for update log
        en_fault = False         # enable count in ping counter

        while not self._stop_event.is_set():
            email_interval = plugin_options['send_interval']*3600000  # time for sending between e-mails (ms) -> 1 hour = 1000ms*60*60
            ping_interval  = plugin_options['ping_interval']*1000     # time for ping (ms) -> 1sec = 1000ms

            try:
                if plugin_options['use_ping']: 
                    millis = int(round(time.time() * 1000))           # actual time in ms

                    if(millis - last_ping_millis) >= ping_interval:   # is time for pinging?
                        last_ping_millis = millis
                        log.clear(NAME)
                        if plugin_options['address_1'] != '':
                            if ping_ip(plugin_options['address_1']):
                                log.info(NAME, datetime_string() + ' ' + str(plugin_options['address_1']) + ' ' +  _(u'is available.'))
                                status['ping1'] = 1
                            else:
                                log.info(NAME, datetime_string() + ' ' + str(plugin_options['address_1']) + ' ' +  _(u'is not available.'))
                                status['ping1'] = 0
                        else:
                            status['ping1'] = 0

                        if plugin_options['address_2'] != '':
                            if ping_ip(plugin_options['address_2']):
                                log.info(NAME, datetime_string() + ' ' + str(plugin_options['address_2']) + ' ' +  _(u'is available.'))
                                status['ping2'] = 1
                            else:
                                log.info(NAME, datetime_string() + ' ' + str(plugin_options['address_2']) + ' ' +  _(u'is not available.'))
                                status['ping2'] = 0
                        else:
                            status['ping2'] = 0

                        if plugin_options['address_3'] != '':
                            if ping_ip(plugin_options['address_3']) and plugin_options['address_3']!='':
                                log.info(NAME, datetime_string() + ' ' + str(plugin_options['address_3']) + ' ' +  _(u'is available.'))
                                status['ping3'] = 1
                            else:
                                log.info(NAME, datetime_string() + ' ' + str(plugin_options['address_3']) + ' ' +  _(u'is not available.'))
                                status['ping3'] = 0
                        else:
                            status['ping3'] = 0

                        if status['ping1'] == 0 and status['ping2'] == 0 and status['ping3'] == 0:
                            status['state'] = "ERROR"
                            en_fault = True
                        else:
                            status['state'] = "-"

                        if status['ping1'] != status['last_ping1']:
                            status['last_ping1'] = status['ping1']
                            en_log = True

                        if status['ping2'] != status['last_ping2']:
                            status['last_ping2'] = status['ping2']
                            en_log = True

                        if status['ping3'] != status['last_ping3']:
                            status['last_ping3'] = status['ping3'] 
                            en_log = True

                        if en_log:                              # is change?
                            en_log = False                      # only if changed
                            if plugin_options['enable_log']:    # is logging?
                                update_log()                    # saving to log

                            if en_fault:
                                en_fault = False
                                fault_counter += 1

                            if plugin_options['use_restart']:   # is enabled restarting?
                                if fault_counter >= plugin_options['ping_count']:  # is fault counter ready to restart?
                                    fault_counter = 0
                                    log.error(NAME, _(u'Ping has fault. Restarting system!'))
                                    reboot(True)                # Linux HW software reboot         


                    if plugin_options['use_send_email']: 
                        if(millis - last_email_millis) >= email_interval:   # is time for sending e-mail?
                            last_email_millis = millis
                            log_file = os.path.join(plugin_data_dir(), 'log.json')
                            log_csv_file = os.path.join(plugin_data_dir(), 'log.csv')
                            log_exists = os.path.exists(log_file)
                            log_csv_exists = os.path.exists(log_csv_file)
                            if log_exists:
                                create_csv_file()
                            if log_csv_exists:
                                try:
                                    from plugins.email_notifications import try_mail
                                    Subject = plugin_options['emlsubject']
                                    Message =  _(u'Ping Monitor send statistics at the day and time') + ': ' + datetime_string()
                                    try_mail = None
                                    if plugin_options['eplug']==0: # email_notifications
                                        from plugins.email_notifications import try_mail
                                    if plugin_options['eplug']==1: # email_notifications SSL
                                        from plugins.email_notifications_ssl import try_mail    
                                    if try_mail is not None:
                                        try_mail(Message, Message, log_csv_file, subject=plugin_options['emlsubject']) # try_mail(text, logtext, attachment=None, subject=None)

                                    if plugin_options['use_send_delete']:           # delete all logs after sending email
                                        write_log([])
                                        create_default_graph()
                                        os.remove(log_csv_file)

                                except Exception:     
                                    log.error(NAME, _(u'Ping Monitor plug-in') + ':\n' + traceback.format_exc())

                self._sleep(1)

            except Exception:
                log.clear(NAME)
                log.error(NAME, _(u'Ping Monitor plug-in') + ':\n' + traceback.format_exc())
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
        sender.join()
        sender = None


def ping_ip(current_ip_address):
    try:
        output = subprocess.check_output("ping -{} 1 {}".format('c', current_ip_address ), shell=True, universal_newlines=True)
        if 'unreachable' in output:
            return False
        else:
            return True
    except Exception:
        return False


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

def two_digits(n):
    return '%02d' % int(n)

def convertMillis(millis):
    seconds=(millis/1000)%60
    minutes=(millis/(1000*60))%60
    hours=(millis/(1000*60*60))%24
    return "{0}:{1}:{2}".format(two_digits(hours), two_digits(minutes), two_digits(seconds))

def update_log():
    """Update data in json files.""" 
    global status

    ### Data for log ###
    try:
        log_data = read_log()
    except:
        write_log([])
        log_data = read_log()

    from datetime import datetime 

    data = {'date': datetime.now().strftime('%d.%m.%Y')}
    data['time'] = datetime.now().strftime('%H:%M:%S')
    data['ping1'] = str(status['last_ping1'])
    data['ping2'] = str(status['last_ping2'])
    data['ping3'] = str(status['last_ping3'])
    data['state'] = str(status['state'])

    if status['state'] == "ERROR":
        status['ERR_diff'] = int(round(time.time() * 1000))           # actual time in ms
        data['time_dif'] = -1
    else:
        status['OK_diff'] = int(round(time.time() * 1000))            # actual time in ms
        time_dif = status['OK_diff'] - status['ERR_diff']

        if not status['now_run']:                                     # blocking save diff time after plugin started
            if status['last_ping1']=="1" or status['last_ping2']=="1" or status['last_ping3']=="1":
                status['ERR_diff'] = int(round(time.time() * 1000))   # if any check is ok > remove time outage 
            data['time_dif'] = time_dif
        else:
            data['time_dif'] = -1

        status['now_run'] = False

    log_data.insert(0, data)

    try:
        write_log(log_data)
    except:
        write_log([])

    ### Data for graph ###
    try:
        graph_data = read_graph_log()
    except:
        create_default_graph()
        graph_data = read_graph_log()

    timestamp = int(time.time())

    try:
        if plugin_options['address_1'] != '': 
            ping1 = graph_data[0]['balances']
            ping1val = {'total': status['last_ping1']}
            ping1.update({timestamp: ping1val})

        if plugin_options['address_2'] != '': 
            ping2 = graph_data[1]['balances']
            ping2val = {'total': status['last_ping2']}
            ping2.update({timestamp: ping2val})

        if plugin_options['address_3'] != '': 
            ping3 = graph_data[2]['balances']
            ping3val = {'total': status['last_ping3']}
            ping3.update({timestamp: ping3val})

        write_graph_log(graph_data)
        log.info(NAME, _(u'Saving to log files OK.'))
    except:
        create_default_graph()


def create_default_graph():
    """Create default graph json file."""
    if plugin_options['address_1'] != '':
        ping1 = "IP1: " + plugin_options['address_1']
    else:
        ping1 = ""
    if plugin_options['address_2'] != '':
        ping2 = "IP2: " + plugin_options['address_2']
    else:
        ping2 = ""
    if plugin_options['address_3'] != '':
        ping3 = "IP3: " + plugin_options['address_3']
    else:
        ping3 = ""

    graph_data = [
       {"station": ping1, "balances": {}},
       {"station": ping2, "balances": {}},
       {"station": ping3, "balances": {}}
    ]
    write_graph_log(graph_data)
    log.info(NAME, _(u'Deleted all log files OK'))


def create_csv_file():
    try:
        import csv

        log_csv_file = os.path.join(plugin_data_dir(), 'log.csv')

        with open(log_csv_file, 'w') as csv_write:
            fieldnames = ['Date', 'Time', 'IP1', 'IP2', 'IP3', 'STATE', 'OUTAGE']
            writer = csv.DictWriter(csv_write, fieldnames=fieldnames)
            writer.writeheader()

            log_records = read_log()
            for record in log_records:
                data = {'Date':  record['date']}
                data['Time']   = record['time']
                data['IP1']    = record['ping1']
                data['IP2']    = record['ping2']
                data['IP3']    = record['ping3']
                data['STATE']  = record['state']
                if record['time_dif'] > 1:
                    if record['time_dif'] < 86400000:
                        data['OUTAGE']  = convertMillis(record['time_dif'])
                    else:
                        data['OUTAGE'] = '> 24 hours'
                else:
                    data['OUTAGE'] = ''

                writer.writerow(data)

    except Exception:
        log.clear(NAME)
        log.error(NAME, _(u'Ping Monitor plug-in') + ':\n' + traceback.format_exc())


################################################################################
# Web pages:                                                                   #
################################################################################

class settings_page(ProtectedPage):
    """Load an html page for entering adjustments."""

    def GET(self):
        global sender, status

        qdict  = web.input()
        delete = helpers.get_input(qdict, 'delete', False, lambda x: True)
        show = helpers.get_input(qdict, 'show', False, lambda x: True)

        if sender is not None and delete:
            write_log([])
            create_default_graph()
            log_csv_file = os.path.join(plugin_data_dir(), 'log.csv')
            log_csv_exists = os.path.exists(log_csv_file)
            if log_csv_exists:
                os.remove(log_csv_file)   

            raise web.seeother(plugin_url(settings_page), True)

        if sender is not None and 'history' in qdict:
           history = qdict['history']
           plugin_options.__setitem__('history', int(history))

        if sender is not None and show:
            raise web.seeother(plugin_url(log_page), True)

        return self.plugin_render.ping_monitor(plugin_options, log.events(NAME))


    def POST(self):
        plugin_options.web_update(web.input())

        if sender is not None:
            sender.update()

        if not plugin_options['use_ping']:
            log.clear(NAME)
            log.info(NAME, _(u'Ping monitor is disabled.'))

        log.info(NAME, _(u'Options has updated.'))
        raise web.seeother(plugin_url(settings_page), True)


class help_page(ProtectedPage):
    """Load an html page for help"""

    def GET(self):
        return self.plugin_render.ping_monitor_help()


class log_page(ProtectedPage):
    """Load an html page for help"""

    def GET(self):
        return self.plugin_render.ping_monitor_log(read_log(), plugin_options)


class settings_json(ProtectedPage):
    """Returns plugin settings in JSON format."""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        return json.dumps(plugin_options)


class data_json(ProtectedPage):
    """Returns plugin data in JSON format."""

    def GET(self):
        global status

        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        ping1 = "IP1: " + plugin_options['address_1']
        ping2 = "IP2: " + plugin_options['address_2']
        ping3 = "IP3: " + plugin_options['address_3']
        ping1_state = status['last_ping1']
        ping2_state = status['last_ping2']
        ping3_state = status['last_ping3']

        data =  {
          'ping1': ping1,
          'ping2': ping2,
          'ping3': ping3,
          'ping1_state': ping1_state,
          'ping2_state': ping2_state,
          'ping3_state': ping3_state,
          'label': plugin_options['emlsubject'],
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

        if plugin_options['history'] == 0:                                     # without filtering
            web.header('Access-Control-Allow-Origin', '*')
            web.header('Content-Type', 'application/json')
            return json.dumps(read_graph_log())

        if plugin_options['history'] == 1:
            check_start  = current_time - datetime.timedelta(days=1)           # actual date - 1 day
        if plugin_options['history'] == 2:
            check_start  = current_time - datetime.timedelta(days=7)           # actual date - 7 day (week)
        if plugin_options['history'] == 3:
            check_start  = current_time - datetime.timedelta(days=30)          # actual date - 30 day (month)
        if plugin_options['history'] == 4:
            check_start  = current_time - datetime.timedelta(days=365)         # actual date - 365 day (year)

        log_start = int((check_start - epoch).total_seconds())                 # start date for log in second (timestamp)

        json_data = read_graph_log()

        if len(json_data) > 0:
            for i in range(0, 3):                                              # 0 = ping 1, 1 = ping 2, 2 = ping 3
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
        data = "Date; Time; IP1 ({}); IP2 ({}); IP3 ({}); State; Outage \n".format(plugin_options['address_1'], plugin_options['address_2'], plugin_options['address_3'])
        log_file = read_log()
        for interval in log_file:
            data += '; '.join([
                interval['date'],
                interval['time'],
                u'{}'.format(interval['ping1']),
                u'{}'.format(interval['ping2']),
                u'{}'.format(interval['ping3']),
                u'{}'.format(interval['state']),
                u'{}'.format(convertMillis(interval['time_dif']) if interval['time_dif'] > 1 else ''),
            ]) + '\n'

        content = mimetypes.guess_type(os.path.join(plugin_data_dir(), 'log.json')[0])
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-type', content) 
        web.header('Content-Disposition', 'attachment; filename="log.csv"')
        return data