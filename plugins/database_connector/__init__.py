# !/usr/bin/env python
# -*- coding: utf-8 -*-

__author__ = 'Martin Pihrt'

import web
import json
import traceback
import time
import subprocess

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
        'database': 'ospy'
    }
)


maria_installed_ok = False

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
        global maria_installed_ok
        log.clear(NAME)
        if not self._stop_event.is_set():
            try:
                if plugin_options['use']:
                    try:
                        import mariadb
                        log.info(NAME, _('Mariadb installed - OK.'))
                        maria_installed_ok = True             
                    except ImportError:
                        log.info(NAME, _('Mariadb is not installed.'))
                        log.info(NAME, _('Please wait installing mariadb...'))
                        cmd = "sudo apt-get install -y libmariadb-dev"
                        run_command(cmd)
                        cmd = "sudo apt-get install libmariadb3"
                        run_command(cmd)                        
                        log.info(NAME, _('Mariadb is now installed.'))

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


def run_command(cmd):
    try:
        proc = subprocess.Popen(
        cmd,
        stderr=subprocess.STDOUT, # merge stdout and stderr
        stdout=subprocess.PIPE,
        shell=True)
        output = proc.communicate()[0].decode('utf-8')
        log.info(NAME, output)

    except Exception:
        log.error(NAME, _('Database Connector plug-in') + ':\n' + traceback.format_exc())


def execute_db(sql = "", commit = False, test = False):
    global maria_installed_ok
    if maria_installed_ok:
        import mariadb
        msg = None
        try:
            conn = mariadb.connect(
                user=plugin_options['user'],
                password=plugin_options['pass'],
                host=plugin_options['host'],
                port=plugin_options['port'],
                #database=plugin_options['database']
            )
            cur = conn.cursor()
            if not test:
                cur.execute("USE {}".format(plugin_options['database']))
            
            rows = cur.execute(sql)
            if rows is not None:
                msg = cur.fetchall()
            
            log.clear(NAME)
            log.info(NAME, datetime_string() + '\n' + _('Command being executed') + ': {}'.format(sql))
            
            if commit:
                conn.commit()
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
            
            cur.close()
            return -1 if msg is None else msg

        except mariadb.Error as e:
            log.error(NAME, datetime_string() + '\n' + _('Error connecting to MariaDB Platform') + ':\n{}'.format(e))
            return e


################################################################################
# Web pages:                                                                   #
################################################################################

class settings_page(ProtectedPage):
    """Load an html page for entering adjustments."""

    def GET(self):
        global sender
        qdict  = web.input()

        test = get_input(qdict, 'test', False, lambda x: True)

        if sender is not None and test:
            sql = "SHOW DATABASES"
            execute_db(sql, test=True, commit=False)

        return self.plugin_render.database_connector(plugin_options, log.events(NAME))
    
    def POST(self):
        plugin_options.web_update(web.input())
        raise web.seeother(plugin_url(settings_page), True)


class help_page(ProtectedPage):
    """Load an html page for help"""

    def GET(self):
        return self.plugin_render.database_connector_help()


class settings_json(ProtectedPage):
    """Returns plugin settings in JSON format."""
    """Try in web browser: OSPy/plugin_name/settings_json"""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        return json.dumps(plugin_options)