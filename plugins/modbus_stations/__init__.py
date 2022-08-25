# -*- coding: utf-8 -*-
__author__ = u'Martin Pihrt'

import json
import time
import traceback
import web
import subprocess
import os
import mimetypes

from blinker import signal

from ospy.stations import stations
from ospy.options import options
from ospy.helpers import datetime_string
from ospy import helpers 
from ospy.log import log
from threading import Thread, Event
from plugins import PluginOptions, plugin_url, plugin_data_dir
from ospy.webpages import ProtectedPage

NAME = 'Modbus Stations'     ### name for plugin in plugin manager ###
MENU =  _(u'Package: Modbus Stations')
LINK = 'settings_page'       ### link for page in plugin manager ###

plugin_options = PluginOptions(
    NAME,
    {'use_control': False,
     'use_log': False  
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
        if plugin_options['use_control']:  # if plugin is enabled
            log.clear(NAME)
            log.info(NAME, _(u'Modbus Stations enabled.'))
            try:
                station_on = signal('station_on')
                station_on.connect(on_station_on)
                station_off = signal('station_off')
                station_off.connect(on_station_off)
                station_clear = signal('station_clear')
                station_clear.connect(on_station_clear)
            except Exception:
                log.error(NAME, _(u'Modbus Stations plug-in') + ':\n' + traceback.format_exc())
                pass
        else:
            log.clear(NAME)
            log.info(NAME, _(u'Modbus Stations is disabled.'))

sender = None

################################################################################
# Helper functions:                                                            #
################################################################################

### start ###
def start():
    global sender
    if sender is None:
        sender = Sender()
 
### stop ###
def stop():
    global sender
    if sender is not None:
        sender.stop()
        sender.join()
        sender = None


def on_station_on(name, **kw):
    """ Send CMD to ON when core program signals in station state."""
    index = int(kw[u"txt"])
    log.clear(NAME)
    log.info(NAME, _(u'Station {} change to ON').format(index+1))
    

def on_station_off(name, **kw):
    """ Send CMD to OFF when core program signals in station state."""
    index = int(kw[u"txt"])    
    log.clear(NAME)
    log.info(NAME, _(u'Station {} change to OFF').format(index+1))
    

def on_station_clear(name, **kw):
    """ Send all CMD to OFF when core program signals in station state."""
    log.clear(NAME)
    log.info(NAME, _(u'All station change to OFF'))
    

def read_log():
    """Read log data from json file."""
    try:
        with open(os.path.join(plugin_data_dir(), 'log.json')) as logf:
            return json.load(logf)
    except IOError:
        return []

def write_log(json_data):
    """Write data to log json file."""
    with open(os.path.join(plugin_data_dir(), 'log.json'), 'w') as outfile:
        json.dump(json_data, outfile)

def update_log(cmd, status):
    """Update data in json files."""
    try:
        log_data = read_log()
    except:   
        write_log([])
        log_data = read_log()

    from datetime import datetime 

    data = {}
    data['cmd'] = cmd
    data['status'] = status
    data['datetime'] = datetime_string()

    log_data.insert(0, data)
    write_log(log_data)
    log.info(NAME, _(u'Saving to log files OK'))

################################################################################
# Web pages:                                                                   #
################################################################################

class settings_page(ProtectedPage):
    """Load an html page for entering adjustments."""

    def GET(self):
        global sender
        qdict = web.input()
        delete = helpers.get_input(qdict, 'delete', False, lambda x: True)
        show = helpers.get_input(qdict, 'show', False, lambda x: True)
 
        if sender is not None and delete:
            write_log([])
            log.info(NAME, _(u'Deleted all log files OK'))
            raise web.seeother(plugin_url(settings_page), True)

        if sender is not None and show:
            raise web.seeother(plugin_url(log_page), True)

        return self.plugin_render.modbus_stations(plugin_options, log.events(NAME))

    def POST(self):
        qdict = web.input()
        
        try:
            if 'use_control' in qdict:
                if qdict['use_control']=='on':
                    plugin_options.__setitem__('use_control', True)

            else:  
                plugin_options.__setitem__('use_control', False)

            if 'use_log' in qdict:
                if qdict['use_log']=='on':
                    plugin_options.__setitem__('use_log', True)

            else:
                plugin_options.__setitem__('use_log', False)


            if sender is not None:
                sender.update()

        except Exception:
            log.error(NAME, _(u'Modbus Stations plug-in') + ':\n' + traceback.format_exc())

        raise web.seeother(plugin_url(settings_page), True)

class help_page(ProtectedPage):
    """Load an html page for help"""

    def GET(self):
        return self.plugin_render.modbus_stations_help()

class log_page(ProtectedPage):
    """Load an html page for help"""

    def GET(self):
        return self.plugin_render.modbus_stations_log(read_log())

class settings_json(ProtectedPage): 
    """Returns plugin settings in JSON format."""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        return json.dumps(plugin_options)

class log_json(ProtectedPage):
    """Returns data in JSON format."""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        return json.dumps(read_log())

class log_csv(ProtectedPage):
    """Simple Log API"""

    def GET(self):
        data = "Date/Time; Command; State \n"
        log_file = read_log()
        for interval in log_file:
            data += '; '.join([
                interval['datetime'],
                u'{}'.format(interval['cmd']),
                u'{}'.format(interval['status']),
            ]) + '\n'

        content = mimetypes.guess_type(os.path.join(plugin_data_dir(), 'log.json')[0])
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-type', content) 
        web.header('Content-Disposition', 'attachment; filename="modbus_stations_log.csv"')
        return data
