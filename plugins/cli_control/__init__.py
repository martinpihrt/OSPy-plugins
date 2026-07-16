# -*- coding: utf-8 -*-
__author__ = 'Martin Pihrt'

import json
import traceback
import web
import subprocess
import os
import mimetypes

from blinker import signal

from ospy.stations import stations
from ospy.options import options
from ospy.helpers import datetime_string, verify_csrf
from ospy import helpers 
from ospy.log import log
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

connected_signals = set()
command_state = {
    'last_command': '',
    'last_result': '',
    'last_run': '',
}

################################################################################
# Helper functions:                                                            #
################################################################################

### start ###
def start():
    handlers = {
        'station_on': on_station_on,
        'station_off': on_station_off,
        'station_clear': on_station_clear,
    }
    for signal_name, handler in handlers.items():
        signal(signal_name).connect(handler, weak=False)
        connected_signals.add(signal_name)
    log.clear(NAME)
    log.info(
        NAME,
        _('CLI Control is enabled.')
        if plugin_options['use_control'] else _('CLI Control is disabled.')
    )
 
### stop ###
def stop():
    handlers = {
        'station_on': on_station_on,
        'station_off': on_station_off,
        'station_clear': on_station_clear,
    }
    for signal_name, handler in handlers.items():
        signal(signal_name).disconnect(handler)
        connected_signals.discard(signal_name)


def health():
    """Return signal registration, command configuration and last result."""
    configured = sum(
        1 for command in list(plugin_options['on']) + list(plugin_options['off'])
        if str(command).strip()
    )
    details = {
        _('Registered signals'): '{}/3'.format(len(connected_signals)),
        _('Configured commands'): configured,
        _('Last command'): command_state['last_command'] or _('None'),
        _('Last result'): command_state['last_result'] or _('Not available'),
        _('Last run'): command_state['last_run'] or _('Not available'),
    }
    if len(connected_signals) != 3:
        return {
            'status': 'error',
            'summary': _('CLI signal receivers are not fully registered.'),
            'details': details,
        }
    if not plugin_options['use_control']:
        return {
            'status': 'unknown',
            'summary': _('CLI Control is disabled.'),
            'details': details,
        }
    if command_state['last_result'] == 'error':
        return {
            'status': 'error',
            'summary': _('The last CLI command failed.'),
            'details': details,
        }
    return {
        'status': 'ok',
        'summary': _('CLI Control is ready.'),
        'details': details,
    }

def run_command(cmd):
    """run command"""
    if plugin_options['use_control']:
        command_state['last_command'] = str(cmd)
        command_state['last_run'] = datetime_string()
        try:
            msg_ok =  _('Command OK')
            msg_err = _('Command failed')
            log.debug(NAME, datetime_string() + ': {}'.format(cmd))
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True)
            output, _stderr = proc.communicate(timeout=60)
            output = output.decode('utf-8', errors='replace')
            ret = proc.returncode
            if ret != 0:
                command_state['last_result'] = 'error'
                log.error(NAME, msg_err + f" ({ret})\n{output}")
                if plugin_options['use_log']:
                    update_log(cmd, msg_err + f" ({ret})\n{output}")
            else:
                command_state['last_result'] = 'ok'
                log.info(NAME, msg_ok + f" ({ret})\n{output}")
                if plugin_options['use_log']:
                    update_log(cmd, msg_ok + f" ({ret})\n{output}")
        except subprocess.TimeoutExpired:
            command_state['last_result'] = 'error'
            proc.kill()
            output, _stderr = proc.communicate()
            output = output.decode('utf-8', errors='replace')
            msg_err = _('Command failed')
            log.error(NAME, msg_err + ' (timeout)\n' + output)
            if plugin_options['use_log']:
                update_log(cmd, msg_err + ' (timeout)\n' + output)
        except:
            command_state['last_result'] = 'error'
            log.error(NAME, datetime_string() + ':\n' + traceback.format_exc())
            pass
    else:
        log.info(NAME, _('CLI Control is disabled.'))

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

        if connected_signals and 'test' in qdict:
            verify_csrf(qdict)
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

        if connected_signals and delete:
            verify_csrf(qdict)
            write_log([])
            log.info(NAME, _('Deleted all log files successfully.'))
            raise web.seeother(plugin_url(settings_page), True)

        if connected_signals and show:
            raise web.seeother(plugin_url(log_page), True)

        return self.plugin_render.cli_control(plugin_options, log.events(NAME))

    def POST(self):
        qdict = web.input()
        verify_csrf(qdict)
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
        
        commands = {'on': [], 'off': []}
        for i in range(options.output_count):
            commands['on'].append(qdict['con'+str(i)])
            commands['off'].append(qdict['coff'+str(i)])

        plugin_options.__setitem__('on', commands['on']) 
        plugin_options.__setitem__('off', commands['off'])

        log.clear(NAME)
        log.info(NAME, _('CLI Control settings updated successfully.'))
        raise web.seeother(plugin_url(settings_page), True)


class help_page(ProtectedPage):
    """Load an HTML help page."""

    def GET(self):
        return self.plugin_render.cli_control_help()


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
