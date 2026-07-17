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
import shlex

from threading import Lock

from plugins import PluginOptions, plugin_url, plugin_data_dir
from ospy.log import log
from ospy.helpers import datetime_string, get_input, verify_csrf
from ospy.webpages import ProtectedPage


################################################################################
# Plugin name, translated name, link for web page in init, plugin options      #
################################################################################
NAME = 'Database Connector'
MENU =  _('Package: Database Connector')
LINK = 'settings_page'
DB_CONNECT_TIMEOUT = 5
DB_ERROR_LOG_THROTTLE = 60
DB_COMMAND_LOG_THROTTLE = 60

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

is_installed_ok = False
_last_error_log = {'message': None, 'time': 0}
_last_command_log = 0
health_lock = Lock()
health_state = {
    'last_success': 0,
    'last_error': 0,
    'last_error_message': '',
    'connector_version': '',
}

################################################################################
# Main function loop:                                                          #
################################################################################
started = False

################################################################################
# Helper functions:                                                            #
################################################################################
def start():
    global is_installed_ok, started
    started = True
    log.clear(NAME)
    if not plugin_options['use']:
        return
    try:
        import mysql.connector
        version = mysql.connector.__version_info__
        version_text = '.'.join(str(part) for part in version[:3])
        with health_lock:
            health_state['connector_version'] = version_text
            health_state['last_error_message'] = ''
        is_installed_ok = True
        log.info(NAME, _('Installed version mysql-connector-python:') + ' ' + version_text)
    except Exception as error:
        is_installed_ok = False
        record_db_error(error)
        log.info(NAME, _('Mysql-connector-python is not installed or any error.'))
        log.info(NAME, _('Error') + ':\n' + traceback.format_exc())


def stop():
    global started
    started = False


def record_db_success():
    with health_lock:
        health_state['last_success'] = time.time()
        health_state['last_error_message'] = ''


def record_db_error(message):
    with health_lock:
        health_state['last_error'] = time.time()
        health_state['last_error_message'] = str(message).splitlines()[-1]


def health():
    """Return connector dependency, configuration and last query state."""
    with health_lock:
        state = dict(health_state)
    details = {
        _('Lifecycle'): _('Started') if started else _('Stopped'),
        _('Host'): '{}:{}'.format(plugin_options['host'], plugin_options['port']),
        _('Database'): plugin_options['database'],
        _('Connector version'): state['connector_version'] or _('Not available'),
        _('Last successful database operation'): (
            datetime_string(time.localtime(state['last_success']))
            if state['last_success'] else _('Not available')
        ),
    }
    if state['last_error_message']:
        details[_('Last error')] = state['last_error_message']
    if not plugin_options['use']:
        return {
            'status': 'unknown',
            'summary': _('Database Connector is disabled.'),
            'details': details,
        }
    if not started:
        return {
            'status': 'error',
            'summary': _('Database Connector is stopped.'),
            'details': details,
        }
    if not is_installed_ok:
        return {
            'status': 'error',
            'summary': _('Mysql-connector-python is not installed or any error.'),
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
            'status': 'warning',
            'summary': _('Database connection has not been tested yet.'),
            'details': details,
        }
    return {
        'status': 'ok',
        'summary': _('Database connection is responding.'),
        'details': details,
    }


def install_db():
    cmd = "sudo pip install mysql-connector-python"
    log.info(NAME, _('Installing mysql connector python'))
    log.info(NAME, _('In error: externally-managed-environment use sudo rm /usr/lib/python3.11/EXTERNALLY-MANAGED and next install connector.') + '\n')
    log.info(NAME, _('If the installation is not successful, run the installation script to install the sql package "sudo bash ospy_setup.sh" in OSPy dir.') + '\n')
    run_command(cmd)


def run_command(cmd, return_text = None):
    try:
        args = shlex.split(cmd) if isinstance(cmd, str) else cmd
        proc = subprocess.run(args, stderr=subprocess.STDOUT, stdout=subprocess.PIPE, timeout=120)
        output = proc.stdout.decode('utf-8')
        if return_text is not None:
            return output
        else:
            log.info(NAME, output)

    except Exception:
        log.error(NAME, _('Database Connector plug-in') + ':\n' + traceback.format_exc())


def db_config():
    return {
      'user': plugin_options['user'],
      'password': plugin_options['pass'],
      'host': plugin_options['host'],
      'port': int(plugin_options['port']),
      'connection_timeout': DB_CONNECT_TIMEOUT,
      'raise_on_warnings': True
    }


def log_db_error(message):
    now = time.time()
    record_db_error(message)
    if message != _last_error_log['message'] or now - _last_error_log['time'] >= DB_ERROR_LOG_THROTTLE:
        _last_error_log['message'] = message
        _last_error_log['time'] = now
        log.error(NAME, message)


def should_log_command(test=False):
    global _last_command_log
    now = time.time()
    if test or now - _last_command_log >= DB_COMMAND_LOG_THROTTLE:
        _last_command_log = now
        return True
    return False


def is_idempotent_table_create(sql):
    normalized = ' '.join(str(sql).strip().upper().split())
    return normalized.startswith('CREATE TABLE IF NOT EXISTS ')


def table_exists(table_name):
    table_name = str(table_name).strip()
    if not table_name or not table_name.replace('_', '').isalnum():
        return False
    rows = execute_db(
        "SHOW TABLES LIKE '{}'".format(table_name),
        test=False,
        commit=False,
        fetch=True,
    )
    return bool(rows)


def execute_db(sql = "", commit = False, test = False, fetch = False):
    global is_installed_ok
    if is_installed_ok:
        import mysql.connector
        from mysql.connector import errorcode

        msg = None
        result = None
        cnx = None
        cur = None
        try:
            cnx = mysql.connector.connect(**db_config())
            if cnx and cnx.is_connected():
                cur = cnx.cursor()
                if not test:
                    cur.execute("USE {}".format(plugin_options['database']))
            
                rows = cur.execute(sql)
                if rows is not None:
                    msg = cur.fetchall()
                if should_log_command(test):
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

                record_db_success()
            else:
                log_db_error(_('Database connection/query failed') + ': ' + _('Not connected'))
                return None

            return -1 if msg is None else msg

        except mysql.connector.Error as err:
            if err.errno == errorcode.ER_ACCESS_DENIED_ERROR:
                log_db_error(_('Something is wrong with your user name or password'))
            elif err.errno == errorcode.ER_BAD_DB_ERROR:
                log_db_error(_('Database does not exist'))
            elif (err.errno == errorcode.ER_TABLE_EXISTS_ERROR and
                    is_idempotent_table_create(sql)):
                # With raise_on_warnings enabled, MySQL Connector can promote
                # the harmless IF NOT EXISTS note to an exception. The server
                # has already kept the existing table unchanged.
                record_db_success()
                return -1
            elif err.errno == errorcode.ER_TABLE_EXISTS_ERROR:
                log_db_error(_('Table already exists'))
            else:
                log_db_error(_('Database connection/query failed') + ': {}'.format(err))
            return None

        except Exception as err:
            log_db_error(_('Database connection/query failed') + ': {}'.format(err))
            return None

        finally:
            if cur is not None:
                try:
                    cur.close()
                except Exception:
                    pass
            if cnx is not None:
                try:
                    cnx.close()
                except Exception:
                    pass

        return None

    return None


def get_dump():
    try:
        filestamp = time.strftime('%Y%m%d-%H%M%S')
        bkp_name = '{}_{}.sql'.format(plugin_options['database'], filestamp)
        path = os.path.join(plugin_data_dir(), bkp_name)
        cmd = [
            'mysqldump',
            '-h', str(plugin_options['host']),
            '-P', str(plugin_options['port']),
            '-u', str(plugin_options['user']),
            '-p{}'.format(str(plugin_options['pass'])),
            str(plugin_options['database'])
        ]
        with open(path, 'w') as dump_file:
            process = subprocess.run(cmd, stdout=dump_file, stderr=subprocess.PIPE, text=True, timeout=120)
        if process.returncode != 0:
            log.error(NAME, process.stderr)
            return False
        log.info(NAME, 'Database dumped to' + ' ' + bkp_name)
        return True
    except subprocess.TimeoutExpired:
        log.error(NAME, _('Database backup timed out.'))
        return False
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
                verify_csrf(qdict)
                sql = "SHOW DATABASES"
                execute_db(sql, test=True, commit=False)

            if sender is not None and install:
                verify_csrf(qdict)
                install_db()

            return self.plugin_render.database_connector(plugin_options, log.events(NAME))

        except:
            log.error(NAME, _('Database Connector') + ':\n' + traceback.format_exc())
            msg = _('An internal error was found in the system, see the error log for more information. The error is in part:') + ' '
            msg += _('database_connector -> settings_page GET')
            return self.core_render.notice('/', msg)

    def POST(self):
        try:
            qdict = web.input()
            verify_csrf(qdict)
            plugin_options.web_update(qdict)
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
                verify_csrf(qdict)
                if get_dump():
                    log.info(NAME, datetime_string() + ': ' + _('Created database backup.'))
                else:
                    log.error(NAME, datetime_string() + ': ' + _('Error in database backup.'))

            if 'delete' in qdict and sender is not None:
                verify_csrf(qdict)
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
