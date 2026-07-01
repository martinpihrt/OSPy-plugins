# -*- coding: utf-8 -*-
__author__ = u'Martin Pihrt'
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
from ospy.helpers import datetime_string, verify_csrf


NAME = 'Usage Statistics'
MENU =  _(u'Package: Usage Statistics')
LINK = 'status_page'

class StatusChecker(Thread):
    def __init__(self):
        Thread.__init__(self)
        self.daemon = True
        self.started = Event()
        self._stop_event = Event()

        self.status = {
            'pageOK': _(u'Error: data cannot be downloaded from') +  ' www.pihrt.com!',
            'pageID': ' ',
            'pageOKstate': False,
            'current_id': '',
            'records': []
            }

        self._sleep_time = 0
        self.start()

    def stop(self):
        self._stop_event.set()

    def _sleep(self, secs):
        self._sleep_time = secs
        while self._sleep_time > 0 and not self._stop_event.is_set():
            time.sleep(1)
            self._sleep_time -= 1

    def update_statistics(self):
        """Returns the statistics data."""

        try:
           import requests

           link = "https://pihrt.com/ospystats/statistics.json"
           req = requests.get(link, timeout=10)
           bodytext = req.text
           #log.debug(NAME, bodytext) # downloaded text

           import json

           jsonStr = json.loads(bodytext)
           users = jsonStr.get('user', [])
           records = []
           userID = ''
           self.status['pageID'] = ' '

           try:
              with open("./ospy/statistics/user_id", "r") as f:
                 userID = f.read().strip()
              self.status['pageID'] = _(u'Your ID is: ') + str(userID)
              self.status['current_id'] = userID
           except:
              self.status['current_id'] = ''
              #log.error(NAME, _('Usage statistics plug-in') + ':\n' + traceback.format_exc())
              pass

           log.clear(NAME)
           for user in users:
              record_id = str(user.get('id', ''))
              record = {
                 'id': record_id,
                 'log': str(user.get('log', '')),
                 'ospy': str(user.get('ospy', '')),
                 'cpu': str(user.get('cpu', '')),
                 'distribution': str(user.get('distribution', '')),
                 'system': str(user.get('system', '')),
                 'python': str(user.get('python', '')),
                 'current': userID != '' and record_id == userID,
                 'card_class': 'usage-card usage-card-current' if userID != '' and record_id == userID else 'usage-card'
              }
              records.append(record)

              log.info(NAME, _('ID') + ': ' + record['id'])
              log.info(NAME, _('Log') + ': ' + record['log'])
              log.info(NAME, _('OSPy') + ': ' + record['ospy'])
              log.info(NAME, _('CPU') + ': ' + record['cpu'])
              log.info(NAME, _('Distribution') + ': ' + record['distribution'])
              log.info(NAME, _('System') + ': ' + record['system'])
              log.info(NAME, _('Python') + ': ' + record['python'] + '\n')

           records.sort(key=lambda record: not record.get('current', False))
           self.status['pageOK'] =  _(u'The data from') +  ' www.pihrt.com ' +  _(u'was downloaded correctly.') + ' ' + datetime_string()
           self.status['pageOKstate'] = True
           self.status['records'] = records


        except Exception:
           self.status['pageOK'] = _(u'Error: data cannot be downloaded from') +  ' www.pihrt.com!'
           self.status['pageOKstate'] = False
           self.status['current_id'] = ''
           self.status['records'] = []
           log.clear(NAME)
           #log.error(NAME, _('Usage statistics plug-in') + ':\n' + traceback.format_exc())


    def run(self):
        try:
             self.update_statistics()

        except Exception:
             self.started.set()
             log.error(NAME, _(u'Usage statistics plug-in') + ':\n' + traceback.format_exc())

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
        checker.join(15)
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
        verify_csrf()
        if checker is not None:
            checker.update()

        raise web.seeother(plugin_url(status_page), True)
