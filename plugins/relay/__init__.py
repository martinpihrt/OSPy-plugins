# -*- coding: utf-8 -*-
__author__ = 'Rimco'
 
import time
import web
import traceback

from ospy.log import log
from ospy.webpages import ProtectedPage
from ospy.outputs import outputs


NAME = 'Relay Test'
MENU =  _('Package: Relay Test')
LINK = 'test_page'

class test_page(ProtectedPage):
    """Test relay by turning it on for a short time, then off."""

    def GET(self):
        try:
            outputs.relay_output = True
            log.debug(NAME, _('Relay Test: ON')) 
            time.sleep(3)
            outputs.relay_output = False
            log.debug(NAME, _('Relay Test: OFF'))
            raise web.seeother('/')  # return to home page
        except:
            log.error(NAME, _('Relay Test plug-in') + ':\n' + traceback.format_exc())
            msg = _('An internal error was found in the system, see the error log for more information. The error is in part:') + ' '
            msg += _('relay -> test_page GET')
            return self.core_render.notice('/', msg)

def start():
    pass

stop = start