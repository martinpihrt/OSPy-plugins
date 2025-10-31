# -*- coding: utf-8 -*-
__author__ = 'Martin Pihrt'

import json
import time
import traceback
import os
import mimetypes
import csv
import web

from threading import Thread, Event

from datetime import datetime
from ospy import helpers
from ospy.options import options
from ospy.log import log
from plugins import PluginOptions, plugin_url, plugin_data_dir
from ospy.helpers import datetime_string
from ospy.webpages import ProtectedPage

from plugins.network_ping_monitor.pythonping import ping

NAME = 'Network Ping Monitor'
MENU = _('Package: Network Ping Monitor')
LINK = 'settings_page'

plugin_options = PluginOptions(
    NAME,
    {  'use_ping': False,
       'address_1': '8.8.8.8',         # Google.com
       'address_2': '78.128.246.93',   # Cesnet.cz
       'address_3': '85.162.11.19',    # Cetin.cz
       'label_1': 'google.com',
       'label_2': 'cesnet.cz',
       'label_3': 'cetin.cz',
       'SUMMARY_INTERVAL': 30,
       'enable_log': False,
       'en_sql_log': False,
       'type_log': 0,
       'log_records': 0,
       'log_interval': 1,
    }
)

state = {}
state['ping1'] = False
state['ping2'] = False
state['ping3'] = False
state['rtt1'] = None
state['rtt2'] = None
state['rtt3'] = None

servers = {
    plugin_options["label_1"]: {"ip": plugin_options["address_1"], "status": None, "last_change": None},
    plugin_options["label_2"]: {"ip": plugin_options["address_2"], "status": None, "last_change": None},
    plugin_options["label_3"]: {"ip": plugin_options["address_3"], "status": None, "last_change": None}
}


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
        last_all_status = None
        last_all_change = None
        last_summary = time.time()
        last_periodic_log = time.time() - (plugin_options['log_interval'] * 60)
        while not self._stop_event.is_set():
            if not plugin_options['use_ping']:
                log.clear(NAME)
                msg = _('Plug-in is not enabled.')
                log.info(NAME, datetime_string() + ' ' + msg)
                self._sleep(5)
            else:
                try:
                    all_statuses = []
                    all_times = []

                    for name, data in servers.items():
                        status, avg = ping_test(data["ip"])
                        all_statuses.append(status)
                        if status:
                            all_times.append(avg)

                        now = datetime.now()

                        if data["status"] is None or status != data["status"]:
                            if status and data["status"] is False and data["last_change"] is not None:
                                outage_duration = now - data["last_change"]
                                duration_str = str(outage_duration).split('.')[0]
                                msg = f"[{name}] " + _('AVAILABLE AGAIN after outage') + f" {avg} ms"
                                log.info(NAME, datetime_string() + ' ' + msg)
                                update_log_if_enabled(msg)
                            elif not status:
                                msg = f"[{name}] " + _('Unavailable')
                                log.info(NAME, datetime_string() + ' ' + msg)
                                update_log_if_enabled(msg)
                            elif status and data["status"] is None:
                                msg = f"[{name}] " + _('Available') + f" {avg} ms"
                                log.info(NAME, datetime_string() + ' ' + msg)
                                update_log_if_enabled(msg)

                            data["status"] = status
                            data["last_change"] = now

                        if name == plugin_options["label_1"]:
                            state['ping1'] = status
                            state['rtt1'] = avg
                        if name == plugin_options["label_2"]:
                            state['ping2'] = status
                            state['rtt2'] = avg
                        if name == plugin_options["label_3"]:
                            state['ping3'] = status
                            state['rtt3'] = avg

                    if all(all_statuses):
                        if last_all_status != True:
                            if last_all_status is False and last_all_change is not None:
                                outage_duration = datetime.now() - last_all_change
                                duration_str = str(outage_duration).split('.')[0]
                                avg_rtt = round(sum(all_times)/len(all_times), 2) if all_times else 0
                                msg = _('All servers are available AGAIN after an outage.') + " {}".format(duration_str) +  ", " + _('Average RTT:') + " {} ms".format(avg_rtt)
                                log.info(NAME, datetime_string() + ' ' + msg)
                                update_log_if_enabled(msg)
                            else:
                                avg_rtt = round(sum(all_times)/len(all_times), 2) if all_times else 0
                                msg = _('All servers are available, average RTT:') + f" {avg_rtt} ms"
                                log.info(NAME, datetime_string() + ' ' + msg)
                                update_log_if_enabled(msg)
                            last_all_status = True
                            last_all_change = datetime.now()

                    elif not any(all_statuses):
                        if last_all_status != False:
                            msg = _('All servers are unavailable')
                            log.info(NAME, datetime_string() + ' ' + msg)
                            update_log_if_enabled(msg)
                        last_all_status = False
                        last_all_change = datetime.now()

                    try:
                        interval_secs = int(plugin_options.get('log_interval', 1)) * 60
                    except Exception:
                        interval_secs = 60

                    if time.time() - last_periodic_log >= interval_secs:
                        status_list = []
                        for name, data in servers.items():
                            status_str = _('Available') if data['status'] else _('Unavailable')
                            status_list.append(f"{name}: {status_str}")
                        avg_rtt = round(sum(all_times)/len(all_times), 2) if all_times else 0
                        msg = _('Periodic status log') + ': ' + ', '.join(status_list) + + _('Average RTT:') + f' {avg_rtt} ms'
                        log.info(NAME, datetime_string() + ' ' + msg)
                        update_log_if_enabled(msg)
                        last_periodic_log = time.time()

                    if time.time() - last_summary >= plugin_options['SUMMARY_INTERVAL']:
                        log.clear(NAME)
                        summary = []
                        available_times = []
                        for name, data in servers.items():
                            status_str = _('Available') if data["status"] else _('Unavailable')
                            summary.append(f"{name}: {status_str}")
                            if data["status"] and data["status"] is not None:
                                available_times.append(data.get("avg_time", 0))
                        avg_rtt = round(sum(all_times)/len(all_times), 2) if all_times else 0
                        log.info(NAME, datetime_string() + ' ' + _('Summary of statuses:') + ' {}\n'.format(',\n'.join(summary)) + '.\n' + _('Average RTT of available servers:') + f' {avg_rtt} ms')
                        last_summary = time.time()
                    self._sleep(5)

                except Exception:
                    log.clear(NAME)
                    log.error(NAME, _('Network Ping Monitor plug-in') + ':\n' + traceback.format_exc())
                    self._sleep(60)

sender = None


def read_log():
    try:
        with open(os.path.join(plugin_data_dir(), 'log.json')) as logf:
            return json.load(logf)
    except IOError:
        return []

def write_log(json_data):
    try:
        with open(os.path.join(plugin_data_dir(), 'log.json'), 'w') as outfile:
            json.dump(json_data, outfile)
    except Exception:
        log.error(NAME, _('Error writing to local log file') + ':\n' + traceback.format_exc())

def update_log(event):
    if not plugin_options['enable_log']:
        return
    try:
        try:
            log_data = read_log()
        except Exception:
            write_log([])
            log_data = read_log()
        data = {
            'datetime': datetime_string(),
            'date': datetime.now().strftime('%d.%m.%Y'),
            'time': datetime.now().strftime('%H:%M:%S'),
            'event': str(event),
            'ping1': bool(state.get('ping1', False)),
            'ping2': bool(state.get('ping2', False)),
            'ping3': bool(state.get('ping3', False)),
            'rtt1': state.get('rtt1'),
            'rtt2': state.get('rtt2'),
            'rtt3': state.get('rtt3')
        }
        log_data.insert(0, data)
        if plugin_options['log_records'] > 0:
            log_data = log_data[:plugin_options['log_records']]
        write_log(log_data)
        log.info(NAME, _('Saving to local log files OK'))
    except Exception:
        log.error(NAME, _('Network Ping Monitor plug-in') + ':\n' + traceback.format_exc())

def create_sql_table():
    try:
        from plugins.database_connector import execute_db
        sql = ("CREATE TABLE IF NOT EXISTS netping ("
               "id INT NOT NULL AUTO_INCREMENT PRIMARY KEY, "
               "ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP, "
               "event VARCHAR(255), "
               "ping1 TINYINT(1), "
               "ping2 TINYINT(1), "
               "ping3 TINYINT(1), "
               "rtt1 FLOAT, "
               "rtt2 FLOAT, "
               "rtt3 FLOAT)")
        execute_db(sql, test=False, commit=False)
        log.debug(NAME, _('Creating SQL table netping OK'))
    except Exception:
        log.error(NAME, _('Network Ping Monitor plug-in') + ':\n' + traceback.format_exc())

def update_sql_log(event):
    if not plugin_options['en_sql_log']:
        return
    try:
        from plugins.database_connector import execute_db
        create_sql_table()
        p1 = 1 if state.get('ping1') else 0
        p2 = 1 if state.get('ping2') else 0
        p3 = 1 if state.get('ping3') else 0
        r1 = state.get('rtt1') if state.get('rtt1') else 0
        r2 = state.get('rtt2') if state.get('rtt2') else 0
        r3 = state.get('rtt3') if state.get('rtt3') else 0
        sql = ("INSERT INTO netping (event, ping1, ping2, ping3, rtt1, rtt2, rtt3) VALUES ('%s', %d, %d, %d, %f, %f, %f)" %
               (str(event).replace("'", "''"), p1, p2, p3, r1, r2, r3))
        execute_db(sql, test=False, commit=True)
        log.info(NAME, _('Saving to SQL database.'))
    except Exception:
        log.error(NAME, _('Network Ping Monitor plug-in') + ':\n' + traceback.format_exc())

def update_log_if_enabled(event):
    try:
        update_log(event)
    except Exception:
        log.error(NAME, _('Error updating local log') + ':\n' + traceback.format_exc())
    try:
        update_sql_log(event)
    except Exception:
        log.error(NAME, _('Error updating SQL log') + ':\n' + traceback.format_exc())

def read_sql_log():
    """Read log data from database table `netping` and return rows ordered desc."""
    try:
        from plugins.database_connector import execute_db
        sql = "SELECT id, ts, event, ping1, ping2, ping3, rtt1, rtt2, rtt3 FROM netping ORDER BY id DESC"
        data = execute_db(sql, test=False, commit=False, fetch=True)
        return data or []
    except Exception:
        log.error(NAME, _('Network Ping Monitor plug-in') + ':\n' + traceback.format_exc())
        return []

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

def ping_test(ip):
    try:
        result = ping(ip, verbose=False, interval=1, timeout=1, count=2)
        times = [r.time_elapsed_ms for r in result if r.success]
        if len(times) == len(result):
            avg_time = round(sum(times) / len(times), 2)
            return True, avg_time
        else:
            return False, False
    except Exception:
        return False, False

class settings_page(ProtectedPage):
    def GET(self):
        return self.plugin_render.network_ping_monitor(plugin_options, log.events(NAME), state)

    def POST(self):
        plugin_options.web_update(web.input())
        if sender is not None:
            sender.update()
        raise web.seeother(plugin_url(settings_page), True)

class help_page(ProtectedPage):
    def GET(self):
        return self.plugin_render.network_ping_monitor_help()

class log_page(ProtectedPage):
    def GET(self):
        """
        Render log page. Supports query params:
         - ?delete  : delete local JSON logs (if enable_log True)
         - ?delSQL  : delete SQL table netping (if en_sql_log True)
         - ?showsql  : optional, force show SQL logs (not required if type_log set)
        """
        qdict = web.input()
        delete = helpers.get_input(qdict, 'delete', False, lambda x: True)
        delSQL = helpers.get_input(qdict, 'delSQL', False, lambda x: True)

        # handle deletes
        if delete and plugin_options['enable_log']:
            write_log([])
            log.info(NAME, _('Deleted all local log files OK'))

        if delSQL and plugin_options['en_sql_log']:
            try:
                from plugins.database_connector import execute_db
                sql = "DROP TABLE IF EXISTS `netping`"
                execute_db(sql, test=False, commit=False)
                log.info(NAME, _('Deleted SQL table netping OK'))
            except Exception:
                log.error(NAME, _('Network Ping Monitor plug-in') + ':\n' + traceback.format_exc())

        # prepare records based on type_log
        records = []
        records_sql = None
        if plugin_options['type_log'] == 0:
            records = read_log()
        else:
            records_sql = read_sql_log()

        return self.plugin_render.network_ping_monitor_log(records, records_sql, plugin_options)

class csv_download(ProtectedPage):
    def GET(self):
        """
        Download CSV: if type_log == 0 -> local JSON log, else -> SQL table
        """
        try:
            if plugin_options['type_log'] == 0:
                data = read_log()
                header = ['datetime', 'date', 'time', 'event', 'ping1', 'ping2', 'ping3', 'rtt1', 'rtt2', 'rtt3']
                rows = []
                for entry in data:
                    rows.append([
                        entry.get('datetime',''),
                        entry.get('date',''),
                        entry.get('time',''),
                        entry.get('event',''),
                        entry.get('ping1',''),
                        entry.get('ping2',''),
                        entry.get('ping3',''),
                        entry.get('rtt1',''),
                        entry.get('rtt2',''),
                        entry.get('rtt3',''),
                    ])
                filename = 'netping_log_local.csv'
            else:
                sql_rows = read_sql_log()
                header = ['id', 'ts', 'event', 'ping1', 'ping2', 'ping3', 'rtt1', 'rtt2', 'rtt3']
                rows = []
                for r in sql_rows:
                    # r is tuple (id, ts, event, ping1, ping2, ping3, rtt1, rtt2, rtt3)
                    rows.append([r[0], str(r[1]), r[2], r[3], r[4], r[5], r[6], r[7], r[8]])
                filename = 'netping_log_db.csv'

            web.header('Content-Type', 'text/csv')
            web.header('Content-Disposition', 'attachment; filename="%s"' % filename)
            out = []
            out.append(','.join(header))
            for row in rows:
                # ensure commas inside fields are escaped / quoted
                row_quoted = []
                for v in row:
                    s = '' if v is None else str(v)
                    if ',' in s or '"' in s:
                        s = '"' + s.replace('"', '""') + '"'
                    row_quoted.append(s)
                out.append(','.join(row_quoted))
            return '\n'.join(out)

        except Exception:
            log.error(NAME, _('Error creating CSV') + ':\n' + traceback.format_exc())
            web.internalerror()

class settings_json(ProtectedPage):
    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        try:
            return json.dumps(plugin_options)
        except:
            return {}

class data_json(ProtectedPage):
    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        try:
            data = {
                'ping1': state['ping1'],
                'rtt1': state['rtt1'],
                'ping2': state['ping2'],
                'rtt2': state['rtt2'],
                'ping3': state['ping3'],
                'rtt3': state['rtt3'],
                'events': log.events(NAME)[-10:],
                'use_ping': plugin_options['use_ping']
            }
            return json.dumps(data)
        except Exception as e:
            return json.dumps({'error': str(e)})