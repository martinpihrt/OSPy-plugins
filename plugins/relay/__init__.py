# -*- coding: utf-8 -*-
__author__ = 'Rimco'
 
import web
import traceback
from threading import Thread, Event

from ospy.log import log
from ospy.helpers import verify_csrf
from ospy.webpages import ProtectedPage
from ospy.outputs import outputs
from plugins import plugin_url, get_runtime


NAME = 'Relay Test'
MENU =  _('Package: Relay Test')
LINK = 'test_page'
TEST_SECONDS = 3
runtime = get_runtime()


class RelaySender(Thread):
    def __init__(self):
        Thread.__init__(self)
        self.daemon = True
        self._stop_event = Event()
        self.start()

    def stop(self):
        self._stop_event.set()

    def run(self):
        global sender
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
            if sender is self:
                sender = None


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
                runtime.register_thread(sender)
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
    worker = sender
    if worker is not None:
        worker.stop()
        worker.join(5)
        if sender is worker and not worker.is_alive():
            sender = None
    outputs.relay_output = False


def health():
    """Return relay-test worker and output state."""
    worker_alive = sender is not None and sender.is_alive()
    relay_active = bool(outputs.relay_output)
    return {
        'status': 'ok',
        'summary': (
            _('Relay test is running.')
            if worker_alive else _('Relay test is ready.')
        ),
        'details': {
            _('Worker thread'): _('Running') if worker_alive else _('Stopped'),
            _('Relay output'): _('ON') if relay_active else _('OFF'),
            _('Test duration'): '{} s'.format(TEST_SECONDS),
        },
    }
