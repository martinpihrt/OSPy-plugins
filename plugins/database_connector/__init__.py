# !/usr/bin/env python
# -*- coding: utf-8 -*-

__author__ = 'Martin Pihrt'

import web
import json
import traceback
import time
import subprocess
import os
import mimetypes

from threading import Thread, Event

from plugins import PluginOptions, plugin_url, plugin_data_dir
from ospy.log import log
from ospy.helpers import datetime_string, get_input
from ospy.webpages import ProtectedPage


################################################################################
# Plugin name, translated name, link for web page in init, plugin options      #
################################################################################
NAME = 'Database Connector'
MENU =  _('Package: Database Connector')
LINK = 'settings_page'

plugin_options = PluginOptions(
    NAME,
    {
        'use': False,
        'host': '192.168.88.248',
        'user': 'username',
        'pass': 'password',
        'port':  3306,
        'database': 'ospy',
        'sql_name': [],                # a list of all sql names in the plugin data directory
        'sql_size': [],                # sql size in bytes        
    }
)

config = {
  'user': plugin_options['user'],
  'password': plugin_options['pass'],
  'host': plugin_options['host'],
  #'database': plugin_options['database'],
  'port': plugin_options['port'],
  'raise_on_warnings': True
}

is_installed_ok = False

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
        global is_installed_ok
        log.clear(NAME)
        if not self._stop_event.is_set():
            try:
                if plugin_options['use']:
                    try:
                        import mysql.connector
                        version = mysql.connector.__version_info__
                        log.info(NAME, _('Installed version mysql-connector-python:') + ' {}.{}.{}'.format(version[0], version[1], version[2]))
                        is_installed_ok = True
                    except ImportError:
                        log.info(NAME, _('Mysql-connector-python is not installed or any error.'))
                        log.info(NAME, _('Error') + ':\n' + traceback.format_exc())

            except Exception:
                log.clear(NAME)
                log.error(NAME, _('Database Connector') + ':\n' + traceback.format_exc())
                self._sleep(1)

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


def install_db():
    cmd = "sudo pip install mysql-connector-python"
    log.info(NAME, _('Installing mysql connector python'))
    log.info(NAME, _('In error: externally-managed-environment use sudo rm /usr/lib/python3.11/EXTERNALLY-MANAGED and next install connector.') + '\n')
    log.info(NAME, _('If the installation is not successful, run the installation script to install the sql package "sudo bash ospy_setup.sh" in OSPy dir.') + '\n')
    run_command(cmd)


def run_command(cmd, return_text = None):
    try:
        proc = subprocess.Popen(
        cmd,
        stderr=subprocess.STDOUT, # merge stdout and stderr
        stdout=subprocess.PIPE,
        shell=True)
        output = proc.communicate()[0].decode('utf-8')
        if return_text is not None:
            return output
        else:
            log.info(NAME, output)

    except Exception:
        log.error(NAME, _('Database Connector plug-in') + ':\n' + traceback.format_exc())


def execute_db(sql = "", commit = False, test = False, fetch = False):
    global is_installed_ok
    if is_installed_ok:
        import mysql.connector
        from mysql.connector import errorcode

        msg = None
        result = None
        try:
            cnx = mysql.connector.connect(**config)
            if cnx and cnx.is_connected():
                cur = cnx.cursor()
                if not test:
                    cur.execute("USE {}".format(plugin_options['database']))
            
                rows = cur.execute(sql)
                if rows is not None:
                    msg = cur.fetchall()
                log.clear(NAME)
                log.info(NAME, datetime_string() + '\n' + _('Command being executed') + ': {}'.format(sql))
            
                if commit:
                    cnx.commit()
                    log.info(NAME, _('Committed data in db') + '.') 
            
                if test:
                    msg = cur.fetchall()
                    msg_len = len(msg)
                    if msg_len > 1:
                        import re
                        dbtype = re.sub("[()',]","", str(msg[1]))  # remove char ()', in string. Database server type (etc: mysql...)
                        dbname = ''
                        for c in range(2, msg_len):
                            dbname += re.sub("[()',]","", str(msg[c])) + '\n'
                        log.info(NAME, _('Database type') + ': {}'.format(dbtype) + '\n' + _('Found databases') + ': \n{}'.format(dbname))
                    else:
                        log.info(NAME, _('Not found') + '.')

                if fetch and not test:
                    msg = cur.fetchall()
            
                cur.close()
            return -1 if msg is None else msg

        except mysql.connector.Error as err:
            if err.errno == errorcode.ER_ACCESS_DENIED_ERROR:
                log.error(NAME, _('Something is wrong with your user name or password'))
            elif err.errno == errorcode.ER_BAD_DB_ERROR:
                log.error(NAME, _('Database does not exist'))
            elif err.errno == errorcode.ER_TABLE_EXISTS_ERROR:
                log.error(NAME, _('Table already exists'))
            else:
                log.error(NAME, err)
            return None

        else:
            cnx.close()

        return None


def get_dump():
    try:
        filestamp = time.strftime('%Y%m%d-%H%M%S')
        bkp_name = '{}_{}.sql'.format(plugin_options['database'], filestamp)
        path = os.path.join(plugin_data_dir(), bkp_name)
        import re
        sanity_password = re.sub('["]','\\"', str(plugin_options['pass'])) # sanity in password if char is "  example:  123"456  -> 123\\"456
        process = os.popen("mysqldump -h %s -P %s -u %s -p%s %s > %s" % (
            plugin_options['host'],
            plugin_options['port'],
            plugin_options['user'],
            sanity_password,
            plugin_options['database'],
            path)
        )
        preprocessed = process.read()
        print(preprocessed)
        process.close()
        log.info(NAME, 'Database dumped to' + ' ' + bkp_name)
        return True
    except:
        log.error(NAME, _('Database Connector') + ':\n' + traceback.format_exc())
        pass
        return False


### Read all sql files in data folder ###
def read_sql_folder():
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

        plugin_options.__setitem__('sql_name', f)
        plugin_options.__setitem__('sql_size', g)

    except Exception:
        log.error(NAME, _('Database Connector') + ':\n' + traceback.format_exc())
              

################################################################################
# Web pages:                                                                   #
################################################################################

class settings_page(ProtectedPage):
    """Load an html page for entering adjustments."""

    def GET(self):
        try:
            global sender
            qdict  = web.input()
            test = get_input(qdict, 'test', False, lambda x: True)
            install = get_input(qdict, 'install', False, lambda x: True)

            if sender is not None and test:
                sql = "SHOW DATABASES"
                execute_db(sql, test=True, commit=False)

            if sender is not None and install:
                install_db()

            return self.plugin_render.database_connector(plugin_options, log.events(NAME))

        except:
            log.error(NAME, _('Database Connector') + ':\n' + traceback.format_exc())
            msg = _('An internal error was found in the system, see the error log for more information. The error is in part:') + ' '
            msg += _('database_connector -> settings_page GET')
            return self.core_render.notice('/', msg)

    def POST(self):
        try:
            plugin_options.web_update(web.input())
            raise web.seeother(plugin_url(settings_page), True)
        except:
            log.error(NAME, _('Database Connector') + ':\n' + traceback.format_exc())
            msg = _('An internal error was found in the system, see the error log for more information. The error is in part:') + ' '
            msg += _('database_connector -> settings_page POST')
            return self.core_render.notice('/', msg)

class backup_page(ProtectedPage):
    """Load an html page for backup"""

    def GET(self):
        try:
            global sender
            qdict  = web.input()
            backup = get_input(qdict, 'backup', False, lambda x: True)

            log.clear(NAME)
            if sender is not None and backup:
                if get_dump():
                    log.info(NAME, datetime_string() + ': ' + _('Created database backup.'))
                else:
                    log.error(NAME, datetime_string() + ': ' + _('Error in database backup.'))

            if 'delete' in qdict and sender is not None:
                delete = qdict['delete']
                if len(plugin_options['sql_name']) > 0:
                    del_file = os.path.join(plugin_data_dir(), plugin_options['sql_name'][int(delete)] )
                    if os.path.isfile(del_file):
                        os.remove(del_file)
                        log.debug(NAME, datetime_string() + ': ' + _('Deleting file has sucesfully.'))
                    else:
                        log.error(NAME, datetime_string() + ': ' + _('File for deleting not found!'))

            if 'download' in qdict and sender is not None:
                download = qdict['download']
                if len(plugin_options['sql_name']) > 0:
                    down_name = plugin_options['sql_name'][int(download)]
                    down_path = os.path.join(plugin_data_dir(), down_name)
                    if os.path.isfile(down_path):
                        _file = os.path.join(plugin_data_dir(), down_name)
                        _content = mimetypes.guess_type(down_path)[0]
                        log.debug(NAME, _('Download file: {} type: {}.').format(_file, _content))
                        web.header('Access-Control-Allow-Origin', '*')
                        web.header('Content-type', _content)
                        web.header('Content-Disposition', 'attachment; filename="{}"'.format(down_name))
                        with open(down_path, 'rb') as f:
                            return f.read()

            read_sql_folder()
            return self.plugin_render.database_connector_backup(plugin_options, log.events(NAME))

        except:
            log.error(NAME, _('Database Connector') + ':\n' + traceback.format_exc())
            msg = _('An internal error was found in the system, see the error log for more information. The error is in part:') + ' '
            msg += _('database_connector -> backup_page GET')
            return self.core_render.notice('/', msg)

class help_page(ProtectedPage):
    """Load an html page for help"""

    def GET(self):
        try:
            return self.plugin_render.database_connector_help()
        except:
            log.error(NAME, _('Database Connector') + ':\n' + traceback.format_exc())
            msg = _('An internal error was found in the system, see the error log for more information. The error is in part:') + ' '
            msg += _('database_connector -> help_page GET')
            return self.core_render.notice('/', msg)

class settings_json(ProtectedPage):
    """Returns plugin settings in JSON format."""
    """Try in web browser: OSPy/plugin_name/settings_json"""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        try:
            return json.dumps(plugin_options)
        except:
            return {}