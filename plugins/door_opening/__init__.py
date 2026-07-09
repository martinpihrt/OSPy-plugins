# -*- coding: utf-8 -*-
__author__ = 'Martin Pihrt'

import json
import time
import web
import datetime
import traceback

from threading import Thread, Event

from ospy import helpers
from ospy.stations import stations
from ospy.scheduler import predicted_schedule, combined_schedule
from ospy.webpages import ProtectedPage
from plugins import PluginOptions, plugin_url, plugin_data_dir
from ospy.log import log, logEM
from ospy.helpers import datetime_string, verify_csrf

from ospy.webpages import showInFooter # Enable plugin to display readings in UI footer


NAME = 'Door Opening'
MENU =  _('Package: Door Opening')
LINK = 'start_page'
MIN_OPEN_TIME = 1
MAX_OPEN_TIME = 3600

plugin_options = PluginOptions(
    NAME,
    {
        'open_time': 2,
        'open_output': 0,
        'use_footer': False
    }
)


class PluginSender(Thread):
    def __init__(self):
        Thread.__init__(self)
        self.daemon = True
        self._sleep_time = 0
        self.start()

    def update(self):
        self._sleep_time = 0

    def run(self):
        global sender
        try:
            open_time = normalize_open_time(plugin_options['open_time'])
            sid = normalize_station_index(plugin_options['open_output'])
            if sid is None:
                log.clear(NAME)
                log.error(NAME, _('Selected output is not available.'))
                return

            if door_opening_is_active(sid):
                log.clear(NAME)
                log.info(NAME, _('Door Opening is already running for this output.'))
                return

            log.clear(NAME)
            log.info(NAME, datetime_string() + ' ' + _('Started for {} seconds.').format(open_time))

            start = datetime.datetime.now()
            end = datetime.datetime.now() + datetime.timedelta(seconds=open_time)
            station = stations.get(sid)
            new_schedule = {
                'active': True,
                'program': -1,
                'station': sid,
                'program_name': _('Door Opening'),
                'fixed': True,
                'cut_off': 0,
                'manual': True,
                'blocked': False,
                'start': start,
                'original_start': start,
                'end': end,
                'uid': '%s-%s-%d' % (str(start), "Manual", sid),
                'usage': station.usage
            }
            log.start_run(new_schedule)
            stations.activate(new_schedule['station'])
        except Exception:
            log.error(NAME, _('Door Opening plug-in') + ':\n' + traceback.format_exc())
        finally:
            if sender is self:
                sender = None

sender = None

################################################################################
# Helper functions:                                                            #
################################################################################
def normalize_open_time(value):
    try:
        value = int(value)
    except:
        value = plugin_options['open_time']
    return max(MIN_OPEN_TIME, min(MAX_OPEN_TIME, value))


def normalize_station_index(value):
    try:
        sid = int(value)
        stations.get(sid)
        return sid
    except:
        return None


def door_opening_is_active(sid):
    try:
        for interval in log.active_runs():
            if interval.get('station') == sid and interval.get('program_name') == _('Door Opening'):
                return True
    except Exception:
        pass
    return False


def update_footer():
    if plugin_options['use_footer']:
        door_footer = showInFooter()                        # instantiate class to enable data in footer
        door_footer.button = "door_opening/start"           # button redirect on footer
        door_footer.label = _('Opening Door')               # label on footer
        msg = _('Time {} seconds').format(normalize_open_time(plugin_options['open_time']))
        door_footer.val = msg.encode('utf8').decode('utf8') # value on footer


def start():
    update_footer()

stop = start

################################################################################
# Web pages:                                                                   #
################################################################################
class start_page(ProtectedPage):
    """Load an html start page"""

    def GET(self):
        try:
            return self.plugin_render.door_opening(plugin_options, log.events(NAME))
        except:
            log.error(NAME, _('Door Opening plug-in') + ':\n' + traceback.format_exc())
            msg = _('An internal error was found in the system, see the error log for more information. The error is in part:') + ' '
            msg += _('door_opening -> start_page GET')
            return self.core_render.notice('/', msg)

    def POST(self):
        try:
            global sender

            qdict = web.input()

            verify_csrf(qdict)

            plugin_options.web_update(qdict)
            plugin_options.__setitem__('open_time', normalize_open_time(plugin_options['open_time']))
            sid = normalize_station_index(plugin_options['open_output'])
            if sid is None:
                log.clear(NAME)
                log.error(NAME, _('Selected output is not available.'))
                raise web.seeother(plugin_url(start_page), True)
            plugin_options.__setitem__('open_output', sid)
            update_footer()

            if sender is not None:
                if sender.is_alive():
                    sender.join(1)
                else:
                    sender = None

            sender = PluginSender()
            raise web.seeother(plugin_url(start_page), True)

        except:
            log.error(NAME, _('Door Opening plug-in') + ':\n' + traceback.format_exc())
            msg = _('An internal error was found in the system, see the error log for more information. The error is in part:') + ' '
            msg += _('door_opening -> start_page POST')
            return self.core_render.notice('/', msg)

class help_page(ProtectedPage):
    """Load an html page for help"""

    def GET(self):
        try:
            return self.plugin_render.door_opening_help()        
        except:
            log.error(NAME, _('Door Opening plug-in') + ':\n' + traceback.format_exc())
            msg = _('An internal error was found in the system, see the error log for more information. The error is in part:') + ' '
            msg += _('door_opening -> help_page GET')
            return self.core_render.notice('/', msg)

class settings_json(ProtectedPage):
    """Returns plugin settings in JSON format."""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        try:
            return json.dumps(plugin_options)
        except:
            return {}

