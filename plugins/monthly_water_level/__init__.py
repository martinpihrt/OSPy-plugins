# -*- coding: utf-8 -*-

import time
from threading import Thread, Event
import datetime

import web
from ospy.log import log
from ospy.options import level_adjustments
from ospy.webpages import ProtectedPage
from plugins import PluginOptions, plugin_url


NAME = 'Monthly Water Level'
MENU =  _(u'Package: Monthly Water Level')
LINK = 'settings_page'

plugin_options = PluginOptions(
    NAME,
    {
        key: 100 for key in range(12)
    })


def _sleep_time():
    """Calculates how long to sleep until just after midnight."""
    now = datetime.datetime.now()
    return 5 + 3600 * 24 - (now.second + now.minute * 60 + now.hour * 3600)


class MonthChecker(Thread):
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
        while not self._stop_event.is_set():
            month = time.localtime().tm_mon - 1  # Current month.
            level_adjustments[NAME] = plugin_options[month] / 100.0  # Set the water level% (levels list is zero based).
            log.debug(NAME, _(u'Monthly Adjust: Setting water level to') + '%d%%' % plugin_options[month])

            self._sleep(_sleep_time())


checker = None


def start():
    global checker
    if checker is None:
        checker = MonthChecker()


def stop():
    global checker
    if checker is not None:
        checker.stop()
        checker.join()
        checker = None
    if NAME in level_adjustments:
        del level_adjustments[NAME]


class settings_page(ProtectedPage):
    """Load an html page for entering monthly irrigation time adjustments"""

    def GET(self):
        return self.plugin_render.monthly_water_level(plugin_options)

    def POST(self):
        qdict = web.input()
        months = ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec']
        vals = {}
        for index, month in enumerate(months):
            vals[index] = max(0, min(10000, int(qdict[month])))
        plugin_options.web_update(vals)
        if checker is not None:
            checker.update()
        raise web.seeother(plugin_url(settings_page), True)


class help_page(ProtectedPage):
    """Load an html page for help"""

    def GET(self):
        return self.plugin_render.monthly_water_level_help()        