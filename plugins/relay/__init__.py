# -*- coding: utf-8 -*-
__author__ = 'Rimco'
 
import web
import traceback
from threading import Thread, Event

from ospy.log import log
from ospy.helpers import verify_csrf
from ospy.webpages import ProtectedPage
from ospy.outputs import outputs
from plugins import plugin_url


NAME = 'Relay Test'
MENU =  _('Package: Relay Test')
LINK = 'test_page'
TEST_SECONDS = 3


class RelaySender(Thread):
    def __init__(self):
        Thread.__init__(self)
        self.daemon = True
        self._stop_event = Event()
        self.start()

    def stop(self):
        self._stop_event.set()

    def run(self):
        try:
            log.clear(NAME)
            outputs.relay_output = True
            log.info(NAME, _('Relay Test: ON'))
            self._stop_event.wait(TEST_SECONDS)
        except Exception:
            log.error(NAME, _('Relay Test plug-in') + ':\n' + traceback.format_exc())
        finally:
            outputs.relay_output = False
            log.info(NAME, _('Relay Test: OFF'))


sender = None


class test_page(ProtectedPage):
    """Test relay by turning it on for a short time, then off."""

    def GET(self):
        return self.plugin_render.relay(log.events(NAME))

    def POST(self):
        global sender
        try:
            verify_csrf()
            if sender is None or not sender.is_alive():
                sender = RelaySender()
            else:
                log.info(NAME, _('Relay test is already running.'))
        except Exception:
            log.error(NAME, _('Relay Test plug-in') + ':\n' + traceback.format_exc())
            msg = _('An internal error was found in the system, see the error log for more information. The error is in part:') + ' '
            msg += _('relay -> test_page POST')
            return self.core_render.notice('/', msg)
        raise web.seeother(plugin_url(test_page), True)

def start():
    pass

def stop():
    global sender
    if sender is not None:
        sender.stop()
        sender.join(5)
        sender = None
    outputs.relay_output = False
