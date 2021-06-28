# -*- coding: utf-8 -*-
__author__ = 'Martin Pihrt'
# this plugins check power line and shutdown ospi system (count down to reconect power line) and shutdown UPS after time.

import json
import time
import datetime
import sys
import os
import traceback

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
MENU =  _(u'Package: UPS Monitor')
LINK = 'settings_page'

ups_options = PluginOptions(
    NAME,
    {
        'time': 60, # in minutes
        'ups': False,
        'sendeml': False,
        'emlsubject': _(u'Report from OSPy UPS plugin'),
        'enable_log': False,
        'log_records': 0,                             # 0 = unlimited
        'history': 0                                  # selector for graph history
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
        self._stop = Event()

        self.status = {}
        self.status['power%d'] = 0

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
        reboot_time = False
        once = True
        once_two = True
        once_three = True

        last_time = int(time.time())

        ups_mon = showInFooter() #  instantiate class to enable data in footer
        ups_mon.button = "ups_adj/settings"            # button redirect on footer
        ups_mon.label =  _(u'UPS')                      # label on footer

        while not self._stop.is_set():
            try:
                if ups_options['ups']:                                     # if ups plugin is enabled
                    test = get_check_power()
                
                    if not test:
                        text = _(u'OK')
                    else:
                        text = _(u'FAULT')
                    self.status['power%d'] = text

                    ups_mon.val = text.encode('utf8')              # value on footer

                    if not test:
                        last_time = int(time.time())

                    if test:                                               # if power line is not active
                        reboot_time = True                                 # start countdown timer
                        if once:
                            # send email with info power line fault
                            msg = '<b>' + _(u'UPS plug-in') + '</b> ' + '<br><p style="color:red;">' + _(u'Detected fault on power line.') + '</p>'
                            msglog = _(u'UPS plug-in') + ': ' + _(u'Detected fault on power line.')
                            log.info(NAME, msglog)
                            if ups_options['sendeml']:                       # if enabled send email
                                try:
                                    from plugins.email_notifications import try_mail                                    
                                    try_mail(msg, msglog, attachment=None, subject=ups_options['emlsubject']) # try_mail(text, logtext, attachment=None, subject=None)

                                except Exception:     
                                    log.error(NAME, _(u'UPS plug-in') + ':\n' + traceback.format_exc())
                                once_three = True
                            if ups_options['enable_log']:    
                                update_log(0)
                            once = False

                    if reboot_time and test:
                        count_val = int(ups_options['time']) * 60             # value for countdown
                        actual_time = int(time.time())
                        log.clear(NAME)
                        log.info(NAME, _(u'Time to shutdown') + ': ' + str(count_val - (actual_time - last_time)) + ' ' + _(u'sec'))
                        if ((actual_time - last_time) >= count_val):        # if countdown is 0
                            last_time = actual_time
                            test = get_check_power()
                            if test:                                         # if power line is current not active
                                log.clear(NAME)
                                log.info(NAME, _(u'Power line is not restore in time -> sends email and shutdown system.'))
                                reboot_time = False
                                if ups_options['sendeml']:                    # if enabled send email
                                    if once_two:
                                        # send email with info shutdown system
                                        msg = '<b>' + _(u'UPS plug-in') + '</b> ' + '<br><p style="color:red;">' + _(u'Power line is not restore in time -> shutdown system!') + '</p>'
                                        msglog =  _(u'UPS plug-in') + ': ' + _(u'Power line is not restore in time -> shutdown system!')
                                        try:
                                            from plugins.email_notifications import try_mail                                    
                                            try_mail(msg, msglog, attachment=None, subject=ups_options['emlsubject']) # try_mail(text, logtext, attachment=None, subject=None)

                                        except Exception:     
                                            log.error(NAME, _(u'UPS plug-in') + ':\n' + traceback.format_exc()) 
                                        once_two = False

                                GPIO.output(pin_ups_down, GPIO.HIGH)          # switch on GPIO fo countdown UPS battery power off
                                self._sleep(4)
                                GPIO.output(pin_ups_down, GPIO.LOW)
                                poweroff(1, True)                             # shutdown system

                    if not test:
                        if once_three:
                            if ups_options['sendeml']:                     # if enabled send email
                                msg = '<b>' + _(u'UPS plug-in') + '</b> ' + '<br><p style="color:green;">' + _(u'Power line has restored - OK.') + '</p>'
                                msglog = _(u'UPS plug-in') + ': ' +  _(u'Power line has restored - OK.')
                                log.clear(NAME)
                                log.info(NAME, msglog)
                                try:
                                    from plugins.email_notifications import try_mail                                    
                                    try_mail(msg, msglog, attachment=None, subject=ups_options['emlsubject']) # try_mail(text, logtext, attachment=None, subject=None)

                                except Exception:     
                                    log.error(NAME, _(u'UPS plug-in') + ':\n' + traceback.format_exc()) 

                                once = True
                                once_two = True
                                once_three = False
                            if ups_options['enable_log']:
                                update_log(1)

                self._sleep(2)

            except Exception:
                log.error(NAME, _(u'UPS plug-in') + ': \n' + traceback.format_exc())
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
        log.info(NAME, _(u'UPS plugin is started.'))


def stop():
    global ups_sender
    if ups_sender is not None:
        ups_sender.stop()
        ups_sender.join()
        ups_sender = None


def get_check_power_str():
    if GPIO.input(pin_power_ok) == 0:
        pwr = _(u'GPIO Pin = 0 Power line is OK.')
    else:
        pwr = _(u'GPIO Pin = 1 Power line ERROR.')
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
    except:
        create_default_graph()
        pass    
 
    write_graph_log(graph_data)

    log.info(NAME, _(u'Saving to log  files OK'))


def create_default_graph():
    """Create default graph json file."""

    state = _(u'State')
 
    graph_data = [
       {"station": state, "balances": {}}
    ]
    write_graph_log(graph_data)  
    log.debug(NAME, _(u'Creating default graph log files OK'))

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

        if ups_sender is not None and delete:
           write_log([])
           create_default_graph()

           raise web.seeother(plugin_url(settings_page), True) 

        if ups_sender is not None and 'history' in qdict:
           history = qdict['history']
           ups_options.__setitem__('history', int(history)) #__setitem__(self, key, value)            

        if ups_sender is not None and show:
            raise web.seeother(plugin_url(log_page), True)                

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
        return self.plugin_render.ups_adj_log(read_log(), ups_options)             


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
           text = _(u'OK')
        else:
           text = _(u'FAULT')

        data =  {
          'label': ups_options['emlsubject'],
          'ups_state':  text
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

        if ups_options['history'] == 0:                                        # without filtering
            web.header('Access-Control-Allow-Origin', '*')
            web.header('Content-Type', 'application/json')
            return json.dumps(read_graph_log())

        if ups_options['history'] == 1:
            check_start  = current_time - datetime.timedelta(days=1)           # actual date - 1 day
        if ups_options['history'] == 2:
            check_start  = current_time - datetime.timedelta(days=7)           # actual date - 7 day (week)
        if ups_options['history'] == 3:
            check_start  = current_time - datetime.timedelta(days=30)          # actual date - 30 day (month)
        if ups_options['history'] == 4:
            check_start  = current_time - datetime.timedelta(days=365)         # actual date - 365 day (year)                       

        log_start = int((check_start - epoch).total_seconds())                 # start date for log in second (timestamp)
                
        try:  
            json_data = read_graph_log()   
        except: 
            create_default_graph()
            json_data = read_graph_log()
                                          
        temp_balances = {}
        try:
            for key in json_data[0]['balances']:
                find_key =  int(key.encode('utf8'))                                # key is in unicode ex: u'1601347000' -> find_key is int number
                if find_key >= log_start:                                          # timestamp interval 
                    temp_balances[key] = json_data[0]['balances'][key]
            data.append({ 'station': json_data[0]['station'], 'balances': temp_balances })
        except:
            write_log([])
            create_default_graph()
            pass    

        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        return json.dumps(data)

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