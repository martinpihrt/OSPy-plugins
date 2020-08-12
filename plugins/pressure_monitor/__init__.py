# -*- coding: utf-8 -*-
__author__ = 'Martin Pihrt'
# this plugins check pressure in pipe if master station is switched on

import json
import time
from datetime import datetime
import sys
import os
import traceback

from threading import Thread, Event

import web
from ospy.stations import stations
from ospy.options import options
from ospy.log import log, logEM
from plugins import PluginOptions, plugin_url, plugin_data_dir
from ospy.webpages import ProtectedPage
from ospy.helpers import datetime_string
from ospy import helpers

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
        'log_records': 0                                             # 0 = unlimited
    }
)

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
        self._stop = Event()
        
        self.status = {}
        self.status['Pstate%d'] = 0

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
        send = False

        once_text = True
        two_text = True
        three_text = True
        four_text = True
        five_text = True

        last_time = int(time.time())
        actual_time = int(time.time())

        InFooter = showInFooter() #  instantiate class to enable data in footer

        while not self._stop.is_set():
            try:
                if pressure_options['use_press_monitor']:                              # if pressure plugin is enabled
                    four_text = True
                    if get_master_is_on():                                             # if master station is on
                        three_text = True
                        if once_text:                                                  # text on the web if master is on
                            log.clear(NAME)
                            log.info(NAME, _('Master station is ON.'))
                            once_text = False
                            if pressure_options['enable_log']:                         # if enabled logging and graphing
                                update_log(2)
                        if get_check_pressure():                                       # if pressure sensor is on
                            if pressure_options['enable_log']:                         # if enabled logging and graphing
                                update_log(1)
                            actual_time = int(time.time())
                            count_val = int(pressure_options['time'])
                            log.clear(NAME)
                            log.info(NAME, _('Time to test pressure sensor') + ': ' + str(
                                count_val - (actual_time - last_time)) + ' ' + _('sec'))
                            if actual_time - last_time > int(pressure_options['time']):# wait for activated pressure sensor (time delay)
                                last_time = actual_time
                                if get_check_pressure():                               # if pressure sensor is actual on
                                #  options.scheduler_enabled = False                   # set scheduler to off
                                    log.finish_run(None)                               # save log
                                    stations.clear()                                   # set all station to off
                                    log.clear(NAME)
                                    log.info(NAME, _('Pressure sensor is not activated in time -> stops all stations and send email.'))
                                    if pressure_options['sendeml']:                    # if enabled send email
                                        send = True
                                    if pressure_options['enable_log']:                 # if enabled logging and graphing
                                        update_log(0)                                        
                        
                        if not get_check_pressure():
                            last_time = int(time.time())
                            if five_text:
                                once_text = True
                                five_text = False
                    else:
                        if stations.master is not None:
                            if two_text:
                                log.clear(NAME)
                                log.info(NAME, _('Master station is OFF.'))
                                two_text = False
                                five_text = True
                            last_time = int(time.time())

                else:
                    once_text = True
                    two_text = True
                    if four_text:                                                # text on the web if plugin is disabled
                        log.clear(NAME)
                        log.info(NAME, _('Pressure monitor plug-in is disabled.'))
                        four_text = False

                if stations.master is None:                                      # text on the web if master station is none
                    if three_text:
                        log.clear(NAME)
                        log.info(NAME, _('Not used master station.'))
                        three_text = False

                if send:
                    msg = '<b>' + _('Pressure monitor plug-in') + '</b> ' + '<br><p style="color:red;">' + _('System detected error: pressure sensor.') + '</p>'
                    msglog = _('Pressure monitor plug-in') + ': ' + _('System detected error: pressure sensor.')
                    try:
                        from plugins.email_notifications import try_mail                             
                        try_mail(msg, msglog, subject=pressure_options['emlsubject']) # try_mail(text, logtext, attachment=None, subject=None)

                    except Exception:     
                        log.error(NAME, _('Pressure monitor plug-in') + ':\n' + traceback.format_exc())  
                    send = False    
                
                InFooter.button = "pressure_monitor/settings"   # button redirect on footer
                InFooter.label =  _('Pressure')                 # label on footer
                InFooter.unit  = " "                            # unit on footer
                tempText = ""
                if get_check_pressure():
                    self.status['Pstate%d'] = _('INACTIVE')
                    tempText = _('INACTIVE')
                else:                
                    self.status['Pstate%d'] = _('ACTIVE')
                    tempText = _('ACTIVE')
                InFooter.val = tempText.encode('utf8')          # value on footer    
                
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
    except NameError:
        pass


def get_master_is_on():
    if stations.master is not None or stations.master_two is not None and not options.manual_mode:  # if is use master station and not manual control
        for station in stations.get():
            if station.is_master or station.is_master_two:                                          # if station is master
                if station.active:                                                                  # if master is active
                    return True
                else:
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


def update_log(status):
    """Update data in json files.""" 

    ### Data for log ###
    try:
        log_data = read_log()
    except:
        write_log([])
        log_data = read_log()

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

    state = graph_data[0]['balances']
    stateval = {'total': status}
    state.update({timestamp: stateval})
 
    write_graph_log(graph_data)

    log.info(NAME, _('Saving to log  files OK'))


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

        if pressure_sender is not None and delete:
           write_log([])
           create_default_graph()

           raise web.seeother(plugin_url(settings_page), True) 

        return self.plugin_render.pressure_monitor(pressure_options, pressure_sender.status, log.events(NAME))

    def POST(self):
        pressure_options.web_update(web.input())

        if pressure_sender is not None:
            pressure_sender.update()
        raise web.seeother(plugin_url(settings_page), True)


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
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        return json.dumps(read_graph_log())


class log_csv(ProtectedPage):  # save log file from web as csv file type
    """Simple Log API"""

    def GET(self):
        state = _('State')

        data  = "Date/Time"
        data += ";\t Date"
        data += ";\t Time"
        data += ";\t %s" % state
        data += '\n'

        try:
            log_records = read_log()

            for record in log_records:
                data +=         record['datetime']
                data += ";\t" + record['date']
                data += ";\t" + record['time']
                data += ";\t" + record["state"]
                data += '\n'
        except:
            pass                  

        web.header('Content-Type', 'text/csv')
        return data        


