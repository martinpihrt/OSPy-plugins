# -*- coding: utf-8 -*-
__author__ = 'Martin Pihrt'

import json
import time
import traceback
import os
import mimetypes
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
        last_all_status = None         # Last state all servers (True/False)
        last_all_change = None         # Time for last global state
        last_summary = time.time()     # Time for last summary print
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

                        # Change in the status of an individual server
                        if data["status"] is None or status != data["status"]:
                            if status and data["status"] is False and data["last_change"] is not None:
                                outage_duration = now - data["last_change"]
                                duration_str = str(outage_duration).split('.')[0]
                                msg = "[{}] ".format(name) + _('AVAILABLE AGAIN after outage') + " {} ms".format(avg)
                                log.info(NAME, datetime_string() + ' ' + msg)
                            elif not status:
                                msg = "[{}] ".format(name) + _('Unavailable')
                                log.info(NAME, datetime_string() + ' ' + msg)
                            elif status and data["status"] is None:
                                msg = "[{}] ".format(name) + _('Available') + " {} ms".format(avg)
                                log.info(NAME, datetime_string() + ' ' + msg)

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

                    # Global status of all servers
                    if all(all_statuses):
                        if last_all_status != True:
                            if last_all_status is False and last_all_change is not None:
                                outage_duration = datetime.now() - last_all_change
                                duration_str = str(outage_duration).split('.')[0]
                                avg_rtt = round(sum(all_times)/len(all_times), 2)
                                msg = _('All servers are available AGAIN after an outage.') + " {}".format(duration_str) +  ", " + _('Average RTT:') + " {} ms".format(avg_rtt)
                                log.info(NAME, datetime_string() + ' ' + msg)
                            else:
                                avg_rtt = round(sum(all_times)/len(all_times), 2)
                                msg = _('All servers are available, average RTT:') + " {} ms".format(avg_rtt)
                                log.info(NAME, datetime_string() + ' ' + msg)
                            last_all_status = True
                            last_all_change = datetime.now()

                    elif not any(all_statuses):
                        if last_all_status != False:
                            msg = _('All servers are unavailable')
                            log.info(NAME, datetime_string() + ' ' + msg)
                        last_all_status = False
                        last_all_change = datetime.now()

                    # Summary printout of all statuses every SUMMARY_INTERVAL seconds
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
                        log.info(NAME, datetime_string() + ' ' + _('Summary of statuses:') + ' {}\n'.format(',\n'.join(summary)) + '.\n' + _('Average RTT of available servers:') + ' {}'.format(avg_rtt) + ' ' + _('ms'))
                        last_summary = time.time()
                    self._sleep(5)

                except Exception:
                    log.clear(NAME)
                    log.error(NAME, _('Network Ping Monitor plug-in') + ':\n' + traceback.format_exc())
                    self._sleep(60)

sender = None


################################################################################
# Helper functions                                                             #
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

def ping_test(ip):
    try:
        result = ping(ip, verbose=False, interval=1, timeout=1, count=2)
        times = [r.time_elapsed_ms for r in result if r.success]

        if len(times) == len(result):  # all request OK
            avg_time = round(sum(times) / len(times), 2)
            return True, avg_time
        else:
            return False, False
    except Exception:
        return False, False


################################################################################
# Web pages                                                                    #
################################################################################

class settings_page(ProtectedPage):
    def GET(self):
        global sender
        qdict  = web.input()
 
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
        return self.plugin_render.network_ping_monitor_log(read_log(), plugin_options)

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
                "ping1": state["ping1"],
                "rtt1": state["rtt1"],
                "ping2": state["ping2"],
                "rtt2": state["rtt2"],
                "ping3": state["ping3"],
                "rtt3": state["rtt3"],
                "events": log.events(NAME)[-10:],  # posledních 10 záznamů
                "use_ping": plugin_options["use_ping"]
            }
            return json.dumps(data)
        except Exception as e:
            return json.dumps({"error": str(e)})