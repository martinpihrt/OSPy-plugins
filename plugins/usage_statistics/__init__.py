# -*- coding: utf-8 -*-
__author__ = u'Martin Pihrt'
# this plugins print statistics from web 

from threading import Thread, Event

import json
import hashlib
import time
import traceback
import urllib.request

import web
from ospy.webpages import ProtectedPage
from ospy.log import log
from plugins import PluginOptions, plugin_url
from ospy.helpers import datetime_string, verify_csrf


NAME = 'Usage Statistics'
MENU =  _(u'Package: Usage Statistics')
LINK = 'status_page'
STATISTICS_URL = 'https://pihrt.com/ospystats/statistics.json'
REQUEST_TIMEOUT = 10
MAX_DOWNLOAD_BYTES = 1024 * 1024
REFRESH_INTERVAL = 3600
MANUAL_REFRESH_INTERVAL = 60
ERROR_LOG_THROTTLE = 300


def _normalize_id(value):
    return str(value or '').strip().lower()


def _id_matches(record_id, local_id):
    """Accept legacy plain UUIDs and new SHA-256 anonymized identifiers."""
    record_id = _normalize_id(record_id)
    local_id = _normalize_id(local_id)
    if not record_id or not local_id:
        return False
    if record_id == local_id:
        return True
    return record_id == hashlib.sha256(local_id.encode('utf-8')).hexdigest()


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
            'records': [],
            'updated': ''
            }

        self._sleep_time = 0
        self._last_update = 0
        self._last_error_log = 0
        self.start()

    def stop(self):
        self._stop_event.set()

    def _sleep(self, secs):
        self._sleep_time = secs
        while self._sleep_time > 0 and not self._stop_event.is_set():
            time.sleep(1)
            self._sleep_time -= 1

    def update(self):
        self._sleep_time = 0

    def _log_problem(self, message):
        now = time.time()
        if now - self._last_error_log >= ERROR_LOG_THROTTLE:
            log.error(NAME, message)
            self._last_error_log = now

    def _download_statistics(self):
        request = urllib.request.Request(STATISTICS_URL, headers={'User-Agent': 'OSPy Usage Statistics'})
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
            return response.read(MAX_DOWNLOAD_BYTES + 1)

    def update_statistics(self, force=False):
        """Refresh cached statistics data."""
        if not force and self._last_update and time.time() - self._last_update < MANUAL_REFRESH_INTERVAL:
            return

        try:
            body = self._download_statistics()
            if len(body) > MAX_DOWNLOAD_BYTES:
                raise ValueError(_('Downloaded statistics file is too large.'))

            json_data = json.loads(body.decode('utf-8'))
            users = json_data.get('user', [])
            if not isinstance(users, list):
                users = []

            records = []
            userID = ''
            userID_compare = ''
            self.status['pageID'] = ' '

            try:
                with open("./ospy/statistics/user_id", "r") as f:
                    userID = f.read().strip()
                userID_compare = _normalize_id(userID)
                self.status['pageID'] = _(u'Your ID is: ') + str(userID)
                self.status['current_id'] = userID
            except Exception:
                self.status['current_id'] = ''

            for user in users:
                if not isinstance(user, dict):
                    continue
                record_id = str(user.get('id', '')).strip()
                record_current = _id_matches(record_id, userID_compare)
                records.append({
                    'id': record_id,
                    'log': str(user.get('log', '')),
                    'ospy': str(user.get('ospy', '')),
                    'cpu': str(user.get('cpu', '')),
                    'distribution': str(user.get('distribution', '')),
                    'system': str(user.get('system', '')),
                    'python': str(user.get('python', '')),
                    'current': record_current,
                    'card_class': 'usage-card usage-card-current' if record_current else 'usage-card'
                })

            records.sort(key=lambda record: not record.get('current', False))
            self.status['pageOK'] =  _(u'The data from') +  ' www.pihrt.com ' +  _(u'was downloaded correctly.') + ' ' + datetime_string()
            self.status['pageOKstate'] = True
            self.status['records'] = records
            self.status['updated'] = datetime_string()
            self._last_update = time.time()
            log.clear(NAME)
            log.info(NAME, _('Usage statistics downloaded. Records: {}.').format(len(records)))

        except Exception:
            self.status['pageOK'] = _(u'Error: data cannot be downloaded from') +  ' www.pihrt.com!'
            self.status['pageOKstate'] = False
            self.status['current_id'] = ''
            self.status['records'] = []
            self._last_update = time.time()
            self._log_problem(_('Usage statistics plug-in') + ':\n' + traceback.format_exc())


    def run(self):
        self.started.set()
        while not self._stop_event.is_set():
            self.update_statistics(force=True)
            self._sleep(REFRESH_INTERVAL)

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


def get_checker():
    global checker
    if checker is None:
        checker = StatusChecker()
    checker.started.wait(2)
    return checker

################################################################################
# Web pages:                                                                   #
################################################################################
class status_page(ProtectedPage):
    """Load an html statistics data."""

    def GET(self):
        status_checker = get_checker()
        status_checker.update_statistics()
        return self.plugin_render.usage_statistics(status_checker.status, log.events(NAME))

    def POST(self):
        qdict = web.input()
        verify_csrf(qdict)
        get_checker().update_statistics(force=True)

        raise web.seeother(plugin_url(status_page), True)
