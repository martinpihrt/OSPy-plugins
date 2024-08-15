# !/usr/bin/env python
# -*- coding: utf-8 -*-

__author__ = 'Martin Pihrt'

import shutil
import web
import traceback
import time
from threading import Thread, Event
import os
import mimetypes

from plugins import PluginOptions, plugin_url, plugin_data_dir
from ospy.log import log
from ospy.helpers import datetime_string, get_input, mkdir_p, del_rw
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

################################################################################
# Main function loop:                                                          #
################################################################################
class Sender(Thread):
    def __init__(self):
        Thread.__init__(self)
        self.daemon = True
        self._stop_event = Event()
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
        log.info(NAME, _('Plugin is started.'))
        if not self._stop_event.is_set():
            try:
                self._sleep(1)

            except Exception:
                log.clear(NAME)
                log.error(NAME, _('OSPy package Backup') + ':\n' + traceback.format_exc())

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


def get_backup():
    try:
        filestamp = time.strftime('%Y.%m.%d_%H-%M-%S')
        bkp_name = '{}_{}'.format(filestamp, 'PluginsBackup')
        data_folder = os.path.join('plugins', 'ospy_backup', 'data')
        backup_folder = os.path.join('plugins', 'ospy_backup', 'backup')
        temp_folder = os.path.join('plugins', 'ospy_backup', 'temp')

        from plugins import plugin_names, plugin_dir

        log.debug(NAME, _('Deleting folder in ospy_backup/temp'))
        shutil.rmtree(temp_folder, onerror=del_rw)                                                     # remove folder "temp" in ospy_backup
        log.debug(NAME, _('Deleting folder in ospy_backup/backup'))
        shutil.rmtree(backup_folder, onerror=del_rw)                                                   # remove folder "temp" in ospy_backup        

        for module, name in plugin_names().items():
            if name != 'OSPy package Backup':                                                          # skip ospy_backup plugin data dir
                src_plugin_data_dir = os.path.join(os.path.abspath(plugin_dir(module)), 'data')        # ex: /home/pi/OSPy/plugins/wind_monitor/data
                dst_plugin_dir = os.path.join(temp_folder, name)
                if os.path.isdir(src_plugin_data_dir):                                                 # if data dir exist
                    log.debug(NAME, _('Copying folder') + ': {}.'.format(src_plugin_data_dir))
                    shutil.copytree(src_plugin_data_dir, dst_plugin_dir, copy_function = shutil.copy)  # copy from all plugins/plugins_name/data to ospy_backup/temp 

        log.debug(NAME, _('Creating zip file in ospy_backup/backup.'))
        shutil.make_archive(backup_folder + '/' + bkp_name, format='zip', root_dir=temp_folder)        # create zip file

        log.debug(NAME, _('Moving file: {}.zip to ospy_backup/data.').format(bkp_name))
        shutil.move(backup_folder + '/' + bkp_name + '.zip', data_folder)                              # move zip from to

        return True
    except:
        log.debug(NAME, _('OSPy package Backup') + ':\n' + traceback.format_exc())
        pass
        return False


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
                log.clear(NAME)
                if get_backup():
                    log.info(NAME, datetime_string() + '\n' + _('Created all backup files OK.'))
                else:
                    log.info(NAME, datetime_string() + '\n' + _('Failed to create backup, see debug list (if debug is enabled in ospy system).'))

            if 'delete' in qdict and sender is not None:
                delete = qdict['delete']
                if len(plugin_options['bkp_name']) > 0:
                    del_file = os.path.join(plugin_data_dir(), plugin_options['bkp_name'][int(delete)] )
                    if os.path.isfile(del_file):
                        os.remove(del_file)
                        log.debug(NAME, datetime_string() + '\n' + _('Deleting file has sucesfully.'))
                    else:
                        log.error(NAME, datetime_string() + '\n' + _('File for deleting not found!'))

            if 'download' in qdict and sender is not None:
                download = qdict['download']
                if len(plugin_options['bkp_name']) > 0:
                    down_name = plugin_options['bkp_name'][int(download)]
                    down_path = os.path.join(plugin_data_dir(), down_name)
                    if os.path.isfile(down_path):
                        _file = os.path.join(plugin_data_dir(), down_name)
                        _content = mimetypes.guess_type(down_path)[0]                                     
                        log.debug(NAME, _('Download file: {} type: {}.').format(_file, _content))
                        web.header('Access-Control-Allow-Origin', '*')                                    
                        web.header('Content-type', _content)
                        web.header('Content-Disposition', 'attachment; filename="{}"'.format(down_name))
                        #return web.output(open(down_path, 'rb').read())
                        with open(down_path, 'rb') as f:
                            return f.read()

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