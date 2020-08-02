# -*- coding: utf-8 -*-
# this plugin send ping to 1-3 address.

__author__ = 'Martin Pihrt' # www.pihrt.com

#todo restart
#todo log
#todo graf
#todo email

import json
import time
from random import randint
from datetime import datetime
import sys
import traceback
import os
import subprocess

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
LINK = 'settings_page'

plugin_options = PluginOptions(
    NAME,
    {  'use_ping': False,
       'address_1': '8.8.8.8',      # Google.com
       'address_2': '8.8.4.4',      # Google.com
       'address_3': '77.75.75.176', # Seznam.cz
       'ping_interval': 2,          # ping interval in second
       'ping_count': 3,             # for reboot (fault counter)
       'use_restart': False,
       'use_send_email': False,
       'send_interval': 24,
       'use_send_delete': False,
       'emlsubject':  _('Report from OSPy PING plugin'),
       'enable_log': False
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
        self._stop = Event()

        global status

        status['ping1']  = 0
        status['ping2']  = 0
        status['ping3']  = 0
        status['last_ping1'] = 0
        status['last_ping2'] = 0
        status['last_ping3'] = 0
        status['state'] = "-"

        self._sleep_time = 0
        self.start()

    def stop(self):
        self._stop.set()

    def update(self):
        self._sleep_time = 0

    def _sleep(self, secs):
        self._sleep_time = secs
        while self._sleep_time > 0 and not self._stop.is_set():
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

        while not self._stop.is_set():
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
                                log.info(NAME, datetime_string() + ' ' + str(plugin_options['address_1']) + ' ' +  _('is available.')) 
                                status['ping1'] = 1                          
                            else:
                                log.info(NAME, datetime_string() + ' ' + str(plugin_options['address_1']) + ' ' +  _('is not available.'))
                                status['ping1'] = 0
                                en_fault = True

                        if plugin_options['address_2'] != '':        
                            if ping_ip(plugin_options['address_2']):
                                log.info(NAME, datetime_string() + ' ' + str(plugin_options['address_2']) + ' ' +  _('is available.'))   
                                status['ping2'] = 1                        
                            else:
                                log.info(NAME, datetime_string() + ' ' + str(plugin_options['address_2']) + ' ' +  _('is not available.'))
                                status['ping2'] = 0
                                en_fault = True

                        if plugin_options['address_3'] != '':        
                            if ping_ip(plugin_options['address_3']) and plugin_options['address_3']!='':
                                log.info(NAME, datetime_string() + ' ' + str(plugin_options['address_3']) + ' ' +  _('is available.'))   
                                status['ping3'] = 1                        
                            else:
                                log.info(NAME, datetime_string() + ' ' + str(plugin_options['address_3']) + ' ' +  _('is not available.'))  
                                status['ping3'] = 0
                                en_fault = True

                        if status['ping1'] == 0 and status['ping2'] == 0 and status['ping3'] == 0:  
                            status['state'] = "ERROR" 
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
                                    log.error(NAME, _('Ping has fault. Restarting system!'))
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
                                    Message =  _('Ping Monitor send statistics at the day and time') + ': ' + datetime_string()
                                    
                                    try_mail(Message, Message, log_csv_file, subject=plugin_options['emlsubject']) # try_mail(text, logtext, attachment=None, subject=None)

                                    if plugin_options['use_send_delete']:           # delete all logs after sending email
                                        write_log([])
                                        create_default_graph()
                                        os.remove(log_csv_file)

                                except Exception:     
                                    log.error(NAME, _('Ping Monitor plug-in') + ':\n' + traceback.format_exc())   
                                                                   

                self._sleep(1)  

            except Exception:
                log.clear(NAME)
                log.error(NAME, _('Ping Monitor plug-in') + ':\n' + traceback.format_exc())
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


def update_log():
    """Update data in json files.""" 
    global status

    try:
        log_data = read_log()
    except:   
        write_log([])
        log_data = read_log()

    data = {'date': datetime.now().strftime('%d.%m.%Y')}
    data['time'] = datetime.now().strftime('%H:%M:%S')
    data['ping1'] = str(status['last_ping1'])
    data['ping2'] = str(status['last_ping2'])
    data['ping3'] = str(status['last_ping3'])
    data['state'] = str(status['state'])
      
    log_data.insert(0, data)

    try:    
        write_log(log_data)
    except:    
        write_log([])

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

        log.info(NAME, _('Saving to log files OK.'))
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
    log.info(NAME, _('Deleted all log files OK'))


def create_csv_file():
    try:
        import csv

        log_csv_file = os.path.join(plugin_data_dir(), 'log.csv')

        with open(log_csv_file, 'w') as csv_write:
            fieldnames = ['Date', 'Time', 'IP1', 'IP2', 'IP3', 'STATE']
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
                writer.writerow(data)

    except Exception:
        log.clear(NAME)
        log.error(NAME, _('Ping Monitor plug-in') + ':\n' + traceback.format_exc())            


################################################################################
# Web pages:                                                                   #
################################################################################

class settings_page(ProtectedPage):
    """Load an html page for entering adjustments."""

    def GET(self):
        global sender, status

        qdict  = web.input()
        delete = helpers.get_input(qdict, 'delete', False, lambda x: True)

        if sender is not None and delete:
            write_log([])
            create_default_graph()
            log_csv_file = os.path.join(plugin_data_dir(), 'log.csv')
            log_csv_exists = os.path.exists(log_csv_file)
            if log_csv_exists:
                os.remove(log_csv_file)

            raise web.seeother(plugin_url(settings_page), True)

        return self.plugin_render.ping_monitor(plugin_options, log.events(NAME))


    def POST(self):
        plugin_options.web_update(web.input())

        if sender is not None:
            sender.update()

        if not plugin_options['use_ping']:
            log.clear(NAME)
            log.info(NAME, _('Ping monitor is disabled.'))

        log.info(NAME, _('Options has updated.'))
        raise web.seeother(plugin_url(settings_page), True)


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
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        return json.dumps(read_graph_log())


class log_csv(ProtectedPage):  # save log file from web as csv file type
    """Simple Log API"""

    def GET(self):
        data  = "\tDate"
        data += ";\t Time"
        data += ";\t %s" % "IP1: " + plugin_options['address_1']
        data += ";\t %s" % "IP2: " + plugin_options['address_2']
        data += ";\t %s" % "IP3: " + plugin_options['address_3']
        data += ";\t State"
        data += '\n'        

        try:
            log_records = read_log()
            for record in log_records:
                data +=         record['date']
                data += ";\t" + record['time']
                data += ";\t" + record["ping1"]
                data += ";\t" + record["ping2"]
                data += ";\t" + record["ping3"]
                data += ";\t" + record["state"]
                data += '\n'
        except:
            pass        

        web.header('Content-Type', 'text/csv')
        return data
   

