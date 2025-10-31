# -*- coding: utf-8 -*-
__author__ = 'Martin Pihrt'

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

NAME = 'CLI Control'         ### name for plugin in plugin manager ###
MENU =  _('Package: CLI Control')
LINK = 'settings_page'       ### link for page in plugin manager ###

plugin_options = PluginOptions(
    NAME,
    {'use_control': False,
     'on':  ["echo 'example start command for station 1'","","","","","","",""],
     'off': ["echo 'example stop command for station 1'","","","","","","",""],
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
            log.info(NAME, _('CLI Control is enabled.'))
            try:
                station_on = signal('station_on')
                station_on.connect(on_station_on)
                station_off = signal('station_off')
                station_off.connect(on_station_off)
                station_clear = signal('station_clear')
                station_clear.connect(on_station_clear)
            except Exception:
                log.error(NAME, _('CLI Control plug-in') + ':\n' + traceback.format_exc())
                pass
        else:
            log.clear(NAME)
            log.info(NAME, _('CLI Control is disabled.'))

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
            output = output.decode('utf8')#.strip()
            log.info(NAME, output)
            if plugin_options['use_log']:
                update_log(cmd, output)
        except:
            log.error(NAME, _('CLI Control plug-in') + ':\n' + traceback.format_exc())
            pass

def on_station_on(name, **kw):
    """ Send CMD to ON when core program signals in station state."""
    try:
        index = int(kw["txt"])
        log.clear(NAME)
        log.info(NAME, _('Station {} change to ON').format(index+1))
        command = plugin_options['on'] 
        data = command[index]
        if data:
            log.info(NAME, _('Im trying to send an ON command: {}').format(index+1))
            run_command(data)
        else:
            log.info(NAME, _('No command is set for ON: {}').format(index+1))
    except:
        log.error(NAME, _('CLI Control plug-in') + ':\n' + traceback.format_exc())
        pass

def on_station_off(name, **kw):
    """ Send CMD to OFF when core program signals in station state."""
    try:
        index = int(kw["txt"])
        log.clear(NAME)
        log.info(NAME, _('Station {} change to OFF').format(index+1))
        command = plugin_options['off']
        data = command[index]
        if data:
            log.info(NAME, _('Im trying to send an OFF command: {}').format(index+1))
            run_command(data)
        else:
            log.info(NAME, _('No command is set for OFF: {}').format(index+1))
    except:
        log.error(NAME, _('CLI Control plug-in') + ':\n' + traceback.format_exc())
        pass   

def on_station_clear(name, **kw):
    """ Send all CMD to OFF when core program signals in station state."""
    try:
        log.clear(NAME)
        log.info(NAME, _('All station change to OFF'))
        for station in stations.get():
            command = plugin_options['off']
            data = command[station.index]
            if data:
                log.info(NAME, _('Im trying to send an OFF command: {}').format(station.index+1))
                run_command(data)
            else:
                log.info(NAME, _('No command is set for OFF: {}').format(station.index+1))
    except:
        log.error(NAME, _('CLI Control plug-in') + ':\n' + traceback.format_exc())
        pass

def read_log():
    """Read log data from json file."""
    try:
        with open(os.path.join(plugin_data_dir(), 'log.json')) as logf:
            return json.load(logf)
    except IOError:
        return []

def write_log(json_data):
    """Write data to log json file."""
    try:
        with open(os.path.join(plugin_data_dir(), 'log.json'), 'w') as outfile:
            json.dump(json_data, outfile)
    except:
        log.error(NAME, _('CLI Control plug-in') + ':\n' + traceback.format_exc())
        pass

def update_log(cmd, status):
    """Update data in json files."""
    try:
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
        log.info(NAME, _('Saving to log files OK'))
    except:
        log.error(NAME, _('CLI Control plug-in') + ':\n' + traceback.format_exc())
        pass


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
            index = int(test)
            if state:
                log.clear(NAME)
                log.info(NAME, _('Test CMD: {} ON.').format(index + 1))
                command = plugin_options['on']
                cmd = command[index]
                if cmd:
                    run_command(cmd)
                else:
                    log.info(NAME, _('No ON command set for station {}').format(index + 1))
            else:
                log.clear(NAME)
                log.info(NAME, _('Test CMD: {} OFF.').format(index + 1))
                command = plugin_options['off']
                cmd = command[index]
                if cmd:
                    run_command(cmd)
                else:
                    log.info(NAME, _('No OFF command set for station {}').format(index + 1))

        if sender is not None and delete:
            write_log([])
            log.info(NAME, _('Deleted all log files successfully.'))
            raise web.seeother(plugin_url(settings_page), True)

        if sender is not None and show:
            raise web.seeother(plugin_url(log_page), True)

        return self.plugin_render.cli_control(plugin_options, log.events(NAME))

    def POST(self):    
        qdict = web.input()
        plugin_options['use_control'] = qdict.get('use_control') == 'on'
        plugin_options['use_log'] = qdict.get('use_log') == 'on'

        
        commands = {'on': [], 'off': []}
        for i in range(options.output_count):
            commands['on'].append(qdict.get(f'con{i}', ''))
            commands['off'].append(qdict.get(f'coff{i}', ''))

        plugin_options['on'] = commands['on']
        plugin_options['off'] = commands['off']

        if sender is not None:
            sender.update()

        log.info(NAME, _('CLI Control settings updated successfully.'))
        raise web.seeother(plugin_url(settings_page), True)


class help_page(ProtectedPage):
    """Load an HTML help page."""

    def GET(self):
        try:
            return self.plugin_render.cli_control_help()
        except Exception:
            log.error(NAME, _('CLI Control plug-in error in help_page GET:\n') + traceback.format_exc())
            msg = (
                _('An internal error was found in the system, see the error log for more information. ')
                + _('The error is in part: cli_control -> help_page GET')
            )
            return self.core_render.notice('/', msg)

class log_page(ProtectedPage):
    """Load an HTML page with log data."""

    def GET(self):
        data = read_log()
        return self.plugin_render.cli_control_log(data)

class settings_json(ProtectedPage):
    """Returns plugin settings in JSON format."""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        return json.dumps(plugin_options)

class log_json(ProtectedPage):
    """Returns plugin log data in JSON format."""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        try:
            return json.dumps(read_log())
        except Exception:
            log.error(NAME, _('CLI Control plug-in error in log_json GET:\n') + traceback.format_exc())
            return json.dumps({'error': 'Unable to read log data'})


class log_csv(ProtectedPage):
    """Provides log data as downloadable CSV file."""

    def GET(self):
        try:
            log_file = read_log()

            # Prepare CSV content
            csv_data = "Date/Time; Command; State\n"
            for entry in log_file:
                csv_data += '; '.join([
                    entry.get('datetime', ''),
                    entry.get('cmd', '').replace(';', ','),
                    entry.get('status', '').replace(';', ','),
                ]) + '\n'

            # Set headers for download
            web.header('Access-Control-Allow-Origin', '*')
            web.header('Content-Type', 'text/csv; charset=utf-8')
            web.header('Content-Disposition', 'attachment; filename="cli_control_log.csv"')

            log.info(NAME, _('Log file exported as CSV successfully.'))
            return csv_data

        except Exception:
            log.error(NAME, _('CLI Control plug-in error in log_csv GET:\n') + traceback.format_exc())
            return _('Error while generating CSV log file. Please check system log for details.')