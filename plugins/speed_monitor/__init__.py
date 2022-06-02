# -*- coding: utf-8 -*-
__author__ = u'Martin Pihrt' # www.pihrt.com

import json
import time
import datetime
import traceback
import mimetypes
import os

from threading import Thread, Event

import web

from ospy import helpers
from ospy.options import options
from ospy.log import log, logEM
from plugins import PluginOptions, plugin_url, plugin_data_dir
from ospy.webpages import ProtectedPage
from ospy.helpers import datetime_string

from ospy.webpages import showInFooter # Enable plugin to display readings in UI footer

from . import speedtest as st          # https://github.com/sivel/speedtest-cli

NAME = 'Speed Monitor'
MENU =  _(u'Package: Internet Speed Monitor')
LINK = 'settings_page'

speed_options = PluginOptions(
    NAME,
    {
        'use_monitor': True,    # use plugin
        'enable_log': False,    # use logging
        'test_interval': 1,     # testing time
        'log_interval': 10,     # logging time
        'log_records': 0,       # 0=unlimited logs
        'use_footer': True,     # show data from plugin in footer on home page
        'history': 0,           # selector for graph history
    }
)

################################################################################
# Main function loop:                                                          #
################################################################################

class Sender(Thread):
    def __init__(self):
        Thread.__init__(self)
        self.daemon = True
        self._stop_event = Event()

        self.status = {}
        self.status['down'] = 0
        self.status['up'] = 0
        self.status['ping'] = 0        

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
        last_millis = 0              # timer for save log
        last_test_millis = 0         # timer for testing speed
        
        speed_mon = None
        footText = ""
        tempText = _('Has not been loaded yet')

        if speed_options['use_monitor']:
            new_speeds = get_new_speeds()

        if speed_options['use_footer']:
            speed_mon = showInFooter() #  instantiate class to enable data in footer
            speed_mon.button = "speed_monitor/settings"       # button redirect on footer
            speed_mon.label =  _('Speed')                    # label on footer
            speed_mon.val = tempText.encode('utf8').decode('utf8')           # value on footer
        
        if speed_options['use_monitor']: 
            log.clear(NAME)
            log.info(NAME, tempText)
        else:
            tempText = _('Speed monitor is disabled.')

        while not self._stop_event.is_set():
            try:
                if speed_options['use_monitor']:
                    millis = int(round(time.time() * 1000))
                    test_interval = (speed_options['test_interval'] * 60000)
                    if (millis - last_test_millis) > test_interval:
                        last_test_millis = millis
                        try:
                            new_speeds = get_new_speeds()
                            tempText = _('Ping {} ms, Download {} Mb/s, Upload {} Mb/s').format(self.status['ping'], self.status['down'], self.status['up'])
                        except:
                            new_speeds = 0,0,0
                            tempText = _('Cannot be loaded')
                            pass    
                        self.status['ping'] = new_speeds[0] # Ping (ms)
                        self.status['down'] = new_speeds[1] # Download (Mb/s)
                        self.status['up'] = new_speeds[2]   # Upload (Mb/s)
                        footText = tempText + ' (' + datetime_string() + ' )'
                        log.clear(NAME)
                        log.info(NAME, datetime_string() + '\n' + tempText)
                    
                    if speed_options['enable_log']:
                        interval = (speed_options['log_interval'] * 60000)
                        if (millis - last_millis) > interval:
                            last_millis = millis
                            update_log()
                    
                if speed_options['use_footer']:
                    if speed_mon is not None:
                        speed_mon.val = footText.encode('utf8').decode('utf8')           # value on footer

                self._sleep(1)

            except Exception:
                log.clear(NAME)
                log.error(NAME, _('Speed Monitor plug-in') + ':\n' + traceback.format_exc())
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


def get_new_speeds():
    speed_test = st.Speedtest()
    speed_test.get_best_server()

    # Get ping (miliseconds)
    ping = speed_test.results.ping
    # Perform download and upload speed tests (bits per second)
    download = speed_test.download()
    upload = speed_test.upload()

    # Convert download and upload speeds to megabits per second
    download_mbs = round(download / (10**6), 2)
    upload_mbs = round(upload / (10**6), 2)

    return (ping, download_mbs, upload_mbs)


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
    global sender

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
    data['down'] = str(sender.status['down'])
    data['up'] = str(sender.status['up'])
    data['ping']  = str(sender.status['ping'])
      
    log_data.insert(0, data)
    if speed_options['log_records'] > 0:
        log_data = log_data[:speed_options['log_records']]

    try:
        write_log(log_data)
    except:
        write_log([])

    ### Data for graph log ###
    try:
        graph_data = read_graph_log()
    except:
        create_default_graph()
        graph_data = read_graph_log()

    timestamp = int(time.time())

    try:
        downdata = graph_data[0]['balances']
        downval = {'total': sender.status['down']}
        downdata.update({timestamp: downval})

        updata = graph_data[1]['balances']
        upval = {'total': sender.status['up']}
        updata.update({timestamp: upval})

        pingdata = graph_data[2]['balances']
        pingval = {'total': sender.status['ping']}
        pingdata.update({timestamp: pingval})        

        write_graph_log(graph_data)
        log.info(NAME, _('Saving to log files OK'))
    except:
        log.error(NAME, _('Speed Monitor plug-in') + ':\n' + traceback.format_exc())
        pass


def create_default_graph():
    """Create default graph json file."""

    down = _(u'Downloading')
    up = _(u'Uploading')
    ping  = _(u'Ping')
 
    graph_data = [
       {"station": down, "balances": {}},
       {"station": up, "balances": {}}, 
       {"station": ping,  "balances": {}}
    ]
    write_graph_log(graph_data)
    log.info(NAME, _('Deleted all log files OK'))


################################################################################
# Web pages:                                                                   #
################################################################################

class settings_page(ProtectedPage):
    """Load an html page for entering adjustments."""

    def GET(self):
        global sender

        qdict  = web.input()
        delete = helpers.get_input(qdict, 'delete', False, lambda x: True)
        show = helpers.get_input(qdict, 'show', False, lambda x: True)
        test = helpers.get_input(qdict, 'test', False, lambda x: True)

        if sender is not None and delete:
           write_log([])
           create_default_graph()
           raise web.seeother(plugin_url(settings_page), True)

        if sender is not None and test:
            log.clear(NAME)
            try:
                new_speeds = get_new_speeds()
                sender._sleep(2)
                tempText = _('Ping {} ms, Download {} Mb/s, Upload {} Mb/s').format(sender.status['ping'], sender.status['down'], sender.status['up'])
            except:
                new_speeds = 0,0,0
                tempText = _('Cannot be loaded')
                log.error(NAME, _('Speed Monitor plug-in') + ':\n' + traceback.format_exc())
                pass    
            sender.status['ping'] = new_speeds[0] # Ping (ms)
            sender.status['down'] = new_speeds[1] # Download (Mb/s)
            sender.status['up'] = new_speeds[2]   # Upload (Mb/s)
            log.info(NAME, datetime_string() + ' ' + _('Test button') + '\n' + tempText) 
            raise web.seeother(plugin_url(settings_page), True)

        if sender is not None and 'history' in qdict:
           history = qdict['history']
           speed_options.__setitem__('history', int(history))

        if sender is not None and show:
            raise web.seeother(plugin_url(log_page), True)

        return self.plugin_render.speed_monitor(speed_options, log.events(NAME))


    def POST(self):
        speed_options.web_update(web.input(**speed_options)) #for save multiple select

        if sender is not None:
            sender.update()
        
        log.clear(NAME)
        log.info(NAME, _(u'Options has updated.'))
        
        raise web.seeother(plugin_url(settings_page), True)


class help_page(ProtectedPage):
    """Load an html page for help"""

    def GET(self):
        return self.plugin_render.speed_monitor_help()

class log_page(ProtectedPage):
    """Load an html page for help"""

    def GET(self):
        return self.plugin_render.speed_monitor_log(read_log())

class settings_json(ProtectedPage):
    """Returns plugin settings in JSON format."""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        return json.dumps(speed_options)


class data_json(ProtectedPage):
    """Returns plugin data in JSON format."""
    global sender

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        data =  {
          'down': sender.status['down'],
          'up': sender.status['up'],
          'ping': sender.status['ping']
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
        #import datetime
        data = []

        epoch = datetime.date(1970, 1, 1)                                      # first date
        current_time  = datetime.date.today()                                  # actual date

        if speed_options['history'] == 0:                                       # without filtering
            web.header('Access-Control-Allow-Origin', '*')
            web.header('Content-Type', 'application/json')
            return json.dumps(read_graph_log())

        if speed_options['history'] == 1:
            check_start  = current_time - datetime.timedelta(days=1)           # actual date - 1 day
        if speed_options['history'] == 2:
            check_start  = current_time - datetime.timedelta(days=7)           # actual date - 7 day (week)
        if speed_options['history'] == 3:
            check_start  = current_time - datetime.timedelta(days=30)          # actual date - 30 day (month)
        if speed_options['history'] == 4:
            check_start  = current_time - datetime.timedelta(days=365)         # actual date - 365 day (year)

        log_start = int((check_start - epoch).total_seconds())                 # start date for log in second (timestamp)

        json_data = read_graph_log()

        if len(json_data) > 0:
            for i in range(0, 4):                                              # 0 = minimum, 1 = maximum, 2 = actual, 3 = volume
                temp_balances = {}
                try:
                    for key in json_data[i]['balances']:
                        find_key =  int(key.encode('utf8'))                        # key is in unicode ex: u'1601347000' -> find_key is int number
                        if find_key >= log_start:                                  # timestamp interval 
                            temp_balances[key] = json_data[i]['balances'][key]
                    data.append({ 'station': json_data[i]['station'], 'balances': temp_balances })
                except:
                    pass    

        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        return json.dumps(data)

class log_csv(ProtectedPage):  # save log file from web as csv file type
    """Simple Log API"""
    def GET(self):
        log_file = read_log()
        down = _(u'Downloading')
        up = _(u'Uploading')
        ping  = _(u'Ping Time')
        data  = "Date/Time"
        data += "; Date"
        data += "; Time"
        data += "; %s (Mb/s)" % down
        data += "; %s (Mb/s)" % up
        data += "; %s (msec)" % ping
        data += '\n'

        for interval in log_file:
            data += '; '.join([
                interval['datetime'],
                interval['date'],
                interval['time'],
                u'{}'.format(interval['down']),
                u'{}'.format(interval['up']),
                u'{}'.format(interval['ping']),
            ]) + '\n'

        content = mimetypes.guess_type(os.path.join(plugin_data_dir(), 'log.json')[0])
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-type', content) 
        web.header('Content-Disposition', 'attachment; filename="log.csv"')
        return data