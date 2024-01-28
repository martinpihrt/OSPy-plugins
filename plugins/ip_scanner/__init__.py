# !/usr/bin/env python3
# -*- coding: utf-8 -*-

__author__ = 'Martin Pihrt'

import web                                                       # Framework web.py
import traceback                                                 # For Errors listing via callback where the event occurred
import json
import time
import subprocess

from threading import Thread, Event

from ospy.webpages import ProtectedPage                          # For check user login permissions
from ospy import helpers
from ospy.log import log

find_now = False
msg = []

################################################################################
# Plugin name, translated name, link for web page in init, plugin options      #
################################################################################
NAME = 'IP Scanner'                                              # The unique name of the plugin listed in the plugin manager
MENU =  _('Package: IP Scanner')                                 # The name of the plugin that will be visible in the running plugins tab and will be translated
LINK = 'status_page'                                             # The default webpage when loading the plugin will be the settings page class


################################################################################
# Main function loop:                                                          #
################################################################################

class MSGSender(Thread):
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
        global find_now, msg
        while not self._stop_event.is_set():
            try:
                if find_now:
                    msg = []
                    result = subprocess.check_output(["arp", "-n"]).decode("utf-8")
                    msg.append(_('My OSPy IP address') + (' {}\n').format(helpers.get_ip()))
                    msg.append(_('IP Address') + '\t\t' + _('MAC Address'))
                    for line in result.split('\n')[1:]:
                        parts = line.split()
                        if len(parts) >= 2:
                            ip = parts[0]
                            mac = parts[2]
                            msg.append(ip + '\t\t' + mac)
                    find_now = False

                self._sleep(2)

            except Exception:
                log.error(NAME, _('IP Scanner plug-in') + ': \n' + traceback.format_exc())
                self._sleep(60)

msg_sender = None

################################################################################
# Helper functions:                                                            #
################################################################################
def start():
    global msg_sender
    if msg_sender is None:
        msg_sender = MSGSender()


def stop():
    global msg_sender
    if msg_sender is not None:
        msg_sender.stop()
        msg_sender.join()
        msg_sender = None


################################################################################
# Web pages:                                                                   #
################################################################################

class status_page(ProtectedPage):
    """Load an html page for entering adjustments."""

    def GET(self):
        global find_now

        qdict = web.input()
        find = helpers.get_input(qdict, 'find', False, lambda x: True)
        if find:        
            find_now = True

        return self.plugin_render.ip_scanner()


class msg_json(ProtectedPage):
    """Returns plugin data in JSON format."""

    def GET(self):
        global msg

        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        
        data = {}
        data['msg'] = msg

        return json.dumps(data)