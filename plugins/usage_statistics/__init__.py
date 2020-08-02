# -*- coding: utf-8 -*-
__author__ = 'Martin Pihrt'
# this plugins print statistics from web 

from threading import Thread, Event

import time
import subprocess
import traceback

import web
from ospy.webpages import ProtectedPage
from ospy.log import log, logEM
from plugins import PluginOptions, plugin_url
from ospy.options import options
from ospy.helpers import datetime_string


NAME = 'Usage Statistics'
LINK = 'status_page'

class StatusChecker(Thread):
    def __init__(self):
        Thread.__init__(self)
        self.daemon = True
        self.started = Event()
        self._stop = Event()

        self.status = {
            'pageOK': _('Error: data cannot be downloaded from') +  ' www.pihrt.com!',
            'pageID': ' ',
            'pageOKstate': False
            }

        self._sleep_time = 0
        self.start()

    def stop(self):
        self._stop.set()

    def _sleep(self, secs):
        self._sleep_time = secs
        while self._sleep_time > 0 and not self._stop.is_set():
            time.sleep(1)
            self._sleep_time -= 1

    def update_statistics(self):
        """Returns the statistics data."""

        try:
           import requests

           link = "https://pihrt.com/ospystats/statistics.json"
           req = requests.get(link)
           bodytext = req.text
           #log.debug(NAME, bodytext) # downloaded text

           import json

           jsonStr = json.loads(bodytext)
           IDlenght = len(jsonStr['user'])

           log.clear(NAME)
           for i in range(0, IDlenght-1):
              log.info(NAME, _('ID') + ': ' + str(jsonStr['user'][i]['id']))
              log.info(NAME, _('Log') + ': ' + str(jsonStr['user'][i]['log']))
              log.info(NAME, _('OSPy') + ': ' + str(jsonStr['user'][i]['ospy']))
              log.info(NAME, _('CPU') + ': ' + str(jsonStr['user'][i]['cpu']))
              log.info(NAME, _('Distribution') + ': ' + str(jsonStr['user'][i]['distribution']))
              log.info(NAME, _('System') + ': ' + str(jsonStr['user'][i]['system']))
              log.info(NAME, _('Python') + ': ' + str(jsonStr['user'][i]['python']) + '\n')

           self.status['pageOK'] =  _('The data from') +  ' www.pihrt.com ' +  _('was downloaded correctly.') + ' ' + datetime_string()
           self.status['pageOKstate'] = True

           try:
              f = open("./ospy/statistics/user_id", "r")
              userID = (f.read()) 
              self.status['pageID'] = _('Your ID is: ') + str(userID)
           except:
              #log.error(NAME, _('Usage statistics plug-in') + ':\n' + traceback.format_exc())
              pass


        except Exception:
           self.status['pageOK'] = _('Error: data cannot be downloaded from') +  ' www.pihrt.com!'
           self.status['pageOKstate'] = False
           log.clear(NAME)
           #log.error(NAME, _('Usage statistics plug-in') + ':\n' + traceback.format_exc())


    def run(self):
        try:
             self.update_statistics()

        except Exception:
             self.started.set()
             log.error(NAME, _('Usage statistics plug-in') + ':\n' + traceback.format_exc())

checker = None

################################################################################
# Helper functions:                                                            #
################################################################################
def start():
    global checker
    if checker is None:
        checker = StatusChecker()


def stop():
    global checker
    if checker is not None:
        checker.stop()
        checker.join()
        checker = None

################################################################################
# Web pages:                                                                   #
################################################################################
class status_page(ProtectedPage):
    """Load an html statistics data."""

    def GET(self):
        checker.update_statistics()
        checker.started.wait(2)    # Make sure we are initialized
        return self.plugin_render.usage_statistics(checker.status, log.events(NAME))

    def POST(self):
        if checker is not None:
            checker.update()

        raise web.seeother(plugin_url(status_page), True)