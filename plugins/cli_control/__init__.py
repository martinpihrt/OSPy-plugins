# -*- coding: utf-8 -*-
__author__ = 'Martin Pihrt'

import json
import time
import traceback
import web
import subprocess
import os


from blinker import signal

from ospy.stations import stations
from ospy.options import options
from ospy.helpers import datetime_string
from ospy import helpers 
from ospy.log import log
from threading import Thread, Event
from plugins import PluginOptions, plugin_url, plugin_data_dir
from ospy.webpages import ProtectedPage

NAME = 'CLI Control'         ### name for plugin in plugin manager ###
MENU =  _(u'Package: CLI Control')
LINK = 'settings_page'       ### link for page in plugin manager ###
 
plugin_options = PluginOptions(
    NAME,
    {u'use_control': False,
     u'on':  [u"echo 'example start command for station 1'",u"",u"",u"",u"",u"",u"",u""], 
     u'off': [u"echo 'example stop command for station 1'",u"",u"",u"",u"",u"",u"",u""],
     u'use_log': False  
    }
)


################################################################################
# Main function loop:                                                          #
################################################################################

class Sender(Thread):
    def __init__(self):
        Thread.__init__(self)
        self.daemon = True
        self._stop = Event()

        self.status = {}

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
        if plugin_options['use_control']:  # if plugin is enabled
            log.clear(NAME)
            log.info(NAME, _(u'CLI Control is enabled.'))
            try:
                station_on = signal('station_on')
                station_on.connect(on_station_on)
                station_off = signal('station_off')
                station_off.connect(on_station_off)
                station_clear = signal('station_clear')
                station_clear.connect(on_station_clear)
            except Exception:
                log.error(NAME, _(u'CLI Control plug-in') + ':\n' + traceback.format_exc())
                pass
        else:
            log.clear(NAME)
            log.info(NAME, _(u'CLI Control is disabled.'))

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

def run_command(cmd):
    """run command"""
    if plugin_options['use_control']:
        try:
            proc = subprocess.Popen(cmd, stderr=subprocess.STDOUT, # merge stdout and stderr
            stdout=subprocess.PIPE, shell=True)
            output = proc.communicate()[0]
            output = output.decode('utf-8')#.strip()
            log.info(NAME, output)
            if plugin_options['use_log']:
                update_log(cmd, output)
        except:
            log.error(NAME, _(u'CLI Control plug-in') + ':\n' + traceback.format_exc())
            pass

def on_station_on(name, **kw):
    """ Send CMD to ON when core program signals in station state."""
    index = int(kw[u"txt"])
    log.clear(NAME)
    log.info(NAME, _(u'Station {} change to ON').format(index+1))
    command = plugin_options['on'] 
    data = command[index]
    if data:
        log.info(NAME, _(u'Im trying to send an ON command: {}').format(index+1))
        run_command(data)
    else:
        log.info(NAME, _(u'No command is set for ON: {}').format(index+1))
    return 

def on_station_off(name, **kw):
    """ Send CMD to OFF when core program signals in station state."""
    index = int(kw[u"txt"])    
    log.clear(NAME)
    log.info(NAME, _(u'Station {} change to OFF').format(index+1))
    command = plugin_options['off'] 
    data = command[index]
    if data:
        log.info(NAME, _(u'Im trying to send an OFF command: {}').format(index+1))
        run_command(data)
    else:
        log.info(NAME, _(u'No command is set for OFF: {}').format(index+1))
    return

def on_station_clear(name, **kw):
    """ Send all CMD to OFF when core program signals in station state."""
    log.clear(NAME)
    log.info(NAME, _(u'All station change to OFF'))
    for station in stations.get():
        command = plugin_options['off']
        data = command[station.index]
        if data:
            log.info(NAME, _(u'Im trying to send an OFF command: {}').format(station.index+1))
            run_command(data)
        else:
            log.info(NAME, _(u'No command is set for OFF: {}').format(station.index+1))
    return

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
    log.info(NAME, _(u'Saving to log  files OK'))                    

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
        state = helpers.get_input(qdict, 'state', False, lambda x: True)
 
        if sender is not None and 'test' in qdict:
            test = qdict['test']
            if state:
                log.clear(NAME)
                log.info(NAME, _(u'Test CMD: {} ON.').format(int(test)+1))
                command = plugin_options['on'] 
                data = command[int(test)]
                if data:
                    run_command(data)
            else:
                log.clear(NAME)
                log.info(NAME, _(u'Test CMD: {} OFF.').format(int(test)+1))
                command = plugin_options['off'] 
                data = command[int(test)]
                if data:
                    run_command(data)

        if sender is not None and delete:
            write_log([])
            log.info(NAME, _(u'Deleted all log files OK'))
            raise web.seeother(plugin_url(settings_page), True)

        if sender is not None and show:
            raise web.seeother(plugin_url(log_page), True)

        return self.plugin_render.cli_control(plugin_options, log.events(NAME))

    def POST(self):
        qdict = web.input()
        
        try:
           ### add code to update commands ###
            if 'use_control' in qdict:
                if qdict['use_control']=='on':
                    plugin_options.__setitem__('use_control', True) #__setitem__(self, key, value)

            else:  
                plugin_options.__setitem__('use_control', False)

            if 'use_log' in qdict:
                if qdict['use_log']=='on':
                    plugin_options.__setitem__('use_log', True) #__setitem__(self, key, value)

            else:  
                plugin_options.__setitem__('use_log', False)                 

            commands = {u'on': [], u'off': []} 

            for i in range(options.output_count):
                commands['on'].append(qdict['con'+str(i)])
                commands['off'].append(qdict['coff'+str(i)])

            plugin_options.__setitem__('on', commands['on']) 
            plugin_options.__setitem__('off', commands['off'])

            if sender is not None:
                sender.update()

        except Exception:
            log.error(NAME, _(u'CLI Control plug-in') + ':\n' + traceback.format_exc())

        raise web.seeother(plugin_url(settings_page), True)

class help_page(ProtectedPage):
    """Load an html page for help"""

    def GET(self):
        return self.plugin_render.cli_control_help()

class log_page(ProtectedPage):
    """Load an html page for help"""

    def GET(self):
        return self.plugin_render.cli_control_log(read_log())

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
        data = "%s \n" % _(u'Command and State')

        try:
            log_records = read_log()

            for record in log_records:
            	data += record["datetime"] + u'\n'
            	data += _(u'Command') + u': ' + record["cmd"] + u'\n'
            	data += _(u'State') + u': ' + record["status"] + u'\n'
        except:
            pass

        web.header('Content-Type', 'text/csv')
        return data
