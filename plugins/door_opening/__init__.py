# -*- coding: utf-8 -*-
__author__ = u'Martin Pihrt'

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
from ospy.helpers import datetime_string

from ospy.webpages import showInFooter # Enable plugin to display readings in UI footer


NAME = 'Door Opening'
MENU =  _(u'Package: Door Opening')
LINK = 'start_page'

plugin_options = PluginOptions(
    NAME,
    {
        'open_time': 2,
        'open_output': 0
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
        log.clear(NAME)
        log.info(NAME, datetime_string() + ' ' + _(u'Started for {} seconds.').format(plugin_options['open_time']))

        start = datetime.datetime.now()
        sid = int(plugin_options['open_output'])
        end = datetime.datetime.now() + datetime.timedelta(seconds=plugin_options['open_time'])
        new_schedule = {
            'active': True,
            'program': -1,
            'station': sid,
            'program_name': _(u'Door Opening'),
            'fixed': True,
            'cut_off': 0,
            'manual': True,
            'blocked': False,
            'start': start,
            'original_start': start,
            'end': end,
            'uid': '%s-%s-%d' % (str(start), "Manual", sid),
            'usage': stations.get(sid).usage
        }
        log.start_run(new_schedule)
        stations.activate(new_schedule['station'])

sender = None

################################################################################
# Helper functions:                                                            #
################################################################################
def start():
    door_footer = showInFooter()                        # instantiate class to enable data in footer
    door_footer.button = "door_opening/start"           # button redirect on footer
    door_footer.label = _(u'Opening Door')              # label on footer
    door_footer.val = _(u'Time {} seconds').format(plugin_options['open_time']) # value on footer
    pass

stop = start

################################################################################
# Web pages:                                                                   #
################################################################################
class start_page(ProtectedPage):
    """Load an html start page"""

    def GET(self):
        return self.plugin_render.door_opening(plugin_options, log.events(NAME))

    def POST(self):
        global sender

        plugin_options.web_update(web.input())
        if sender is not None:
            sender.join(5)

        sender = PluginSender()

        raise web.seeother(plugin_url(start_page), True)


class help_page(ProtectedPage):
    """Load an html page for help"""

    def GET(self):
        return self.plugin_render.door_opening_help()        


class settings_json(ProtectedPage):
    """Returns plugin settings in JSON format."""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        return json.dumps(plugin_options)


