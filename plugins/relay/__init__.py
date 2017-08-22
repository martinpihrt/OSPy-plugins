#!/usr/bin/env python
# -*- coding: utf-8 -*-
__author__ = 'Rimco'
 
import time
import web

from ospy.webpages import ProtectedPage
from ospy.outputs import outputs

#from ospy.stations import stations # for test station 8

NAME = 'Relay Test'
LINK = 'test_page'

class test_page(ProtectedPage):
    """Test relay by turning it on for a short time, then off."""

    def GET(self):
        try:
            outputs.relay_output = True
            #stations.activate(7)   # for test station 8
            time.sleep(3)
            outputs.relay_output = False
            #stations.deactivate(7) # for test station 8
        except Exception:
            pass
        raise web.seeother('/')  # return to home page


def start():
    pass

stop = start
