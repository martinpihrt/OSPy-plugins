# !/usr/bin/env python
# -*- coding: utf-8 -*-

__author__ = 'Martin Pihrt'

import shutil
import web
import traceback
import time
from threading import Lock
import os
import mimetypes

from plugins import PluginOptions, plugin_url, plugin_data_dir, get_runtime
from ospy.log import log
from ospy.helpers import datetime_string, get_input, mkdir_p, del_rw, verify_csrf
from ospy.webpages import ProtectedPage


################################################################################
# Plugin name, translated name, link for web page in init, plugin options      #
################################################################################
NAME = 'OSPy package Backup'                                     # The unique name of the plugin listed in the plugin manager
MENU =  _('Package: OSPy package Backup')                        # The name of the plugin that will be visible in the running plugins tab and will be translated
LINK = 'settings_page'                                           # The default webpage when loading the plugin will be the settings page class

plugin_options = PluginOptions(
    NAME,
    {
        'bkp_name': [],                                          # a list of all bkp names in the plugin data directory
        'bkp_size': [],                                          # bkp size in bytes 
    }
)
runtime = get_runtime()
backup_lock = Lock()
health_lock = Lock()
health_state = {
    'running': False,
    'last_success': 0,
    'last_file': '',
    'last_size': 0,
    'last_error': 0,
    'last_error_message': '',
}

################################################################################
# Main function loop:                                                          #
################################################################################
class Sender:
    def __init__(self):
        log.clear(NAME)
        log.info(NAME, _('Plugin is started.'))

    def stop(self):
        runtime.request_stop()

    def update(self):
        pass

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
        sender = None


def record_backup_error(message):
    with health_lock:
        health_state['last_error'] = time.time()
        health_state['last_error_message'] = str(message).splitlines()[-1]


def health():
    """Return lifecycle and latest plug-in data backup state."""
    with health_lock:
        state = dict(health_state)
    details = {
        _('Lifecycle'): _('Started') if sender is not None else _('Stopped'),
        _('Backup in progress'): _('Yes') if state['running'] else _('No'),
        _('Last successful backup'): (
            datetime_string(time.localtime(state['last_success']))
            if state['last_success'] else _('Not available')
        ),
        _('Last backup file'): state['last_file'] or _('Not available'),
        _('Last backup size'): state['last_size'],
    }
    if state['last_error_message']:
        details[_('Last error')] = state['last_error_message']
    if sender is None:
        return {
            'status': 'error',
            'summary': _('OSPy Backup is stopped.'),
            'details': details,
        }
    if state['running']:
        return {
            'status': 'warning',
            'summary': _('A plug-in data backup is in progress.'),
            'details': details,
        }
    if state['last_error'] and state['last_error'] >= state['last_success']:
        return {
            'status': 'error',
            'summary': state['last_error_message'],
            'details': details,
        }
    if not state['last_success']:
        return {
            'status': 'unknown',
            'summary': _('No plug-in data backup has been created yet.'),
            'details': details,
        }
    return {
        'status': 'ok',
        'summary': _('The last plug-in data backup completed successfully.'),
        'details': details,
    }


def get_backup():
    if not backup_lock.acquire(False):
        record_backup_error(_('A plug-in data backup is already running.'))
        return False
    with health_lock:
        health_state['running'] = True
    try:
        if runtime.stop_event.is_set():
            raise RuntimeError(_('Backup was cancelled because the plug-in is stopping.'))
        filestamp = time.strftime('%Y.%m.%d_%H-%M-%S')
        bkp_name = '{}_{}'.format(filestamp, 'PluginsBackup')
        data_folder = plugin_data_dir()
        backup_folder = os.path.join('plugins', 'ospy_backup', 'backup')
        temp_folder = os.path.join('plugins', 'ospy_backup', 'temp')

        from plugins import plugin_names, plugin_dir

        log.debug(NAME, _('Deleting folder in ospy_backup/temp'))
        if os.path.isdir(temp_folder):
            shutil.rmtree(temp_folder, onerror=del_rw)                                                 # remove folder "temp" in ospy_backup
        log.debug(NAME, _('Deleting folder in ospy_backup/backup'))
        if os.path.isdir(backup_folder):
            shutil.rmtree(backup_folder, onerror=del_rw)                                               # remove folder "backup" in ospy_backup
        mkdir_p(temp_folder)
        mkdir_p(backup_folder)
        mkdir_p(data_folder)

        for module, name in plugin_names().items():
            if runtime.stop_event.is_set():
                raise RuntimeError(_('Backup was cancelled because the plug-in is stopping.'))
            if name != 'OSPy package Backup':                                                          # skip ospy_backup plugin data dir
                src_plugin_data_dir = os.path.join(os.path.abspath(plugin_dir(module)), 'data')        # ex: /home/pi/OSPy/plugins/wind_monitor/data
                dst_plugin_dir = os.path.join(temp_folder, name)
                if os.path.isdir(src_plugin_data_dir):                                                 # if data dir exist
                    log.debug(NAME, _('Copying folder') + ': {}.'.format(src_plugin_data_dir))
                    shutil.copytree(src_plugin_data_dir, dst_plugin_dir, copy_function = shutil.copy)  # copy from all plugins/plugins_name/data to ospy_backup/temp 

        log.debug(NAME, _('Creating zip file in ospy_backup/backup.'))
        shutil.make_archive(backup_folder + '/' + bkp_name, format='zip', root_dir=temp_folder)        # create zip file

        log.debug(NAME, _('Moving file: {}.zip to ospy_backup/data.').format(bkp_name))
        backup_path = shutil.move(backup_folder + '/' + bkp_name + '.zip', data_folder)                # move zip from to

        with health_lock:
            health_state['last_success'] = time.time()
            health_state['last_file'] = os.path.basename(backup_path)
            health_state['last_size'] = os.path.getsize(backup_path)
            health_state['last_error_message'] = ''

        return True
    except Exception:
        record_backup_error(traceback.format_exc())
        log.debug(NAME, _('OSPy package Backup') + ':\n' + traceback.format_exc())
        return False
    finally:
        with health_lock:
            health_state['running'] = False
        backup_lock.release()


def backup_file_from_index(index_value):
    try:
        index = int(index_value)
        read_bkp_folder()
        if index < 0 or index >= len(plugin_options['bkp_name']):
            return None, None
        filename = os.path.basename(plugin_options['bkp_name'][index])
        path = os.path.abspath(os.path.join(plugin_data_dir(), filename))
        data_dir = os.path.abspath(plugin_data_dir())
        if not path.startswith(data_dir + os.sep):
            return None, None
        if not os.path.isfile(path):
            return None, None
        return filename, path
    except Exception:
        return None, None


def stream_file(path, chunk_size=64 * 1024):
    with open(path, 'rb') as source:
        while True:
            chunk = source.read(chunk_size)
            if not chunk:
                break
            yield chunk


### Read all sql files in data folder ###
def read_bkp_folder():
    try:
        dir_name =  plugin_data_dir() + '/'
        # Get list of all files only in the given directory
        list_of_files = filter( lambda x: os.path.isfile(os.path.join(dir_name, x)), os.listdir(dir_name) )
        # Sort list of files based on last modification time in ascending order
        list_of_files = sorted( list_of_files, key = lambda x: os.path.getmtime(os.path.join(dir_name, x)))
        # Along with last modification time of file
        f = []
        g = []

        for file_name in list_of_files:
            file_path = os.path.join(dir_name, file_name)
            size = os.path.getsize(file_path)
            f.append(file_name)
            g.append(round(size, 2))

        plugin_options.__setitem__('bkp_name', f)
        plugin_options.__setitem__('bkp_size', g)

    except Exception:
        log.error(NAME, _('OSPy package Backup') + ':\n' + traceback.format_exc())

################################################################################
# Web pages:                                                                   #
################################################################################

class settings_page(ProtectedPage):
    """Load an html page for entering adjustments."""

    def GET(self):
        try:
            global sender
            qdict = web.input()
            bkp = get_input(qdict, 'bkp', False, lambda x: True)

            if sender is not None and bkp:
                verify_csrf(qdict)
                log.clear(NAME)
                if get_backup():
                    log.info(NAME, datetime_string() + '\n' + _('Created all backup files OK.'))
                else:
                    log.info(NAME, datetime_string() + '\n' + _('Failed to create backup, see debug list (if debug is enabled in ospy system).'))

            if 'delete' in qdict and sender is not None:
                verify_csrf(qdict)
                del_name, del_file = backup_file_from_index(qdict['delete'])
                if del_file:
                    os.remove(del_file)
                    log.debug(NAME, datetime_string() + '\n' + _('Deleting file has sucesfully.'))
                else:
                    log.error(NAME, datetime_string() + '\n' + _('File for deleting not found!'))

            if 'download' in qdict and sender is not None:
                down_name, down_path = backup_file_from_index(qdict['download'])
                if down_path:
                    _content = mimetypes.guess_type(down_path)[0] or 'application/zip'
                    log.debug(NAME, _('Download file: {} type: {}.').format(down_path, _content))
                    web.header('Access-Control-Allow-Origin', '*')
                    web.header('Content-type', _content)
                    web.header('Content-Length', os.path.getsize(down_path))
                    web.header('Content-Disposition', 'attachment; filename="{}"'.format(down_name))
                    return stream_file(down_path)
                log.error(NAME, datetime_string() + '\n' + _('Backup file not found!'))

            read_bkp_folder()
            return self.plugin_render.ospy_backup(plugin_options, log.events(NAME))

        except:
            log.error(NAME, _('OSPy package Backup') + ':\n' + traceback.format_exc())
            msg = _('An internal error was found in the system, see the error log for more information. The error is in part:') + ' '
            msg += _('ospy_backup -> settings_page GET')
            return self.core_render.notice('/', msg)           



class help_page(ProtectedPage):
    """Load an html page for help"""

    def GET(self):
        try:
            return self.plugin_render.ospy_backup_help()
        except:
            log.error(NAME, _('OSPy package Backup') + ':\n' + traceback.format_exc())
            msg = _('An internal error was found in the system, see the error log for more information. The error is in part:') + ' '
            msg += _('ospy_backup -> help_page GET')
            return self.core_render.notice('/', msg)
