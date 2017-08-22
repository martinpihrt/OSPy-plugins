#!/usr/bin/env python
# -*- coding: utf-8 -*-
__author__ = 'Martin Pihrt'
# this plugins check power line and shutdown ospi system (count down to reconect power line) and shutdown UPS after time.

import json
import time
import sys
import traceback

from threading import Thread, Event

import web
from ospy.helpers import poweroff
from ospy.log import log
from plugins import PluginOptions, plugin_url
from ospy.webpages import ProtectedPage
from ospy.helpers import datetime_string

import i18n

NAME = 'UPS Monitor'
LINK = 'settings_page'

ups_options = PluginOptions(
    NAME,
    {
        "time": 60, # in minutes
        "ups": False,
        "sendeml": False,
    }
)

################################################################################
# GPIO input pullup and output:                                                #
################################################################################

import RPi.GPIO as GPIO  # RPi hardware

pin_power_ok = 16 # GPIO23
pin_ups_down = 18 # GPIO24

try:
    GPIO.setup(pin_power_ok, GPIO.IN, pull_up_down=GPIO.PUD_UP)
except NameError:
    pass

try:
    GPIO.setmode(GPIO.BOARD) ## Use board pin numbering
    GPIO.setup(pin_ups_down, GPIO.OUT)
    GPIO.output(pin_ups_down, GPIO.LOW)
except NameError:
    pass


################################################################################
# Main function loop:                                                          #
################################################################################

class UPSSender(Thread):
    def __init__(self):
        Thread.__init__(self)
        self.daemon = True
        self._stop = Event()

        self.status = {}
        self.status['power%d'] = 0

        self._sleep_time = 0
        self.start()

    def stop(self):
        self._stop.set()

    def update(self):
        self._sleep_time = 0

    def _sleep(self, secs):
        self._sleep_time = secs
        while self._sleep_time > 0 and not self._stop.is_set():
            time.sleep(1)
            self._sleep_time -= 1

    def run(self):
        reboot_time = False
        once = True
        once_two = True
        once_three = True

        last_time = int(time.time())

        while not self._stop.is_set():
            try:
                if ups_options['ups']:                                     # if ups plugin is enabled
                    test = get_check_power()

                    if not test:
                        text = _('OK')
                    else:
                        text = _('FAULT')
                    self.status['power%d'] = text

                    if not test:
                        last_time = int(time.time())

                    if test:                                               # if power line is not active
                        reboot_time = True                                  # start countdown timer
                        if once:
                            msg = _('UPS plugin detected fault on power line.') # send email with info power line fault
                            log.info(NAME, msg)
                            if ups_options['sendeml']:                       # if enabled send email
                                send_email(msg)
                                once_three = True
                            once = False

                    if reboot_time and test:
                        count_val = int(ups_options['time']) * 60             # value for countdown
                        actual_time = int(time.time())
                        log.clear(NAME)
                        log.info(NAME, _('Time to shutdown') + ': ' + str(count_val - (actual_time - last_time)) + ' ' + _('sec'))
                        if ((actual_time - last_time) >= count_val):        # if countdown is 0
                            last_time = actual_time
                            test = get_check_power()
                            if test:                                         # if power line is current not active
                                log.clear(NAME)
                                log.info(NAME, _('Power line is not restore in time -> sends email and shutdown system.'))
                                reboot_time = False
                                if ups_options['sendeml']:                    # if enabled send email
                                    if once_two:
                                        msg = _('UPS plugin - power line is not restore in time -> shutdown system!') # send email with info shutdown system
                                        send_email(msg)
                                        once_two = False

                                GPIO.output(pin_ups_down,
                                            GPIO.HIGH)          # switch on GPIO fo countdown UPS battery power off
                                self._sleep(4)
                                GPIO.output(pin_ups_down, GPIO.LOW)
                                poweroff(1, True)                             # shutdown system

                    if not test:
                        if once_three:
                            if ups_options['sendeml']:                     # if enabled send email
                                msg = _('UPS plugin - power line has restored - OK.')
                                log.clear(NAME)
                                log.info(NAME, msg)
                                send_email(msg)
                                once = True
                                once_two = True
                                once_three = False

                self._sleep(1)

            except Exception:
                log.error(NAME, _('UPS plug-in') + ': \n' + traceback.format_exc())
                self._sleep(60)


ups_sender = None

################################################################################
# Helper functions:                                                            #
################################################################################
def start():
    global ups_sender
    if ups_sender is None:
        ups_sender = UPSSender()
        log.clear(NAME)
        log.info(NAME, _('UPS plugin is started.'))


def stop():
    global ups_sender
    if ups_sender is not None:
        ups_sender.stop()
        ups_sender.join()
        ups_sender = None


def send_email(msg):
    """Send email"""
    message = datetime_string() + ': ' + msg
    try:
        from plugins.email_notifications import email
        email(message)
        log.info(NAME, _('Email was sent') + ': ' + message)
    except Exception:
        log.info(NAME, _('Email was not sent') + '! ' + traceback.format_exc())


def get_check_power_str():
    if GPIO.input(pin_power_ok) == 0:
        pwr = 'GPIO Pin = 0 Power line is OK.'
    else:
        pwr = 'GPIO Pin = 1 Power line ERROR.'
    return str(pwr)


def get_check_power():
    try:
        if GPIO.input(pin_power_ok):  # power line detected
            pwr = 1
        else:
            pwr = 0
        return pwr
    except NameError:
        pass


################################################################################
# Web pages:                                                                   #
################################################################################


class settings_page(ProtectedPage):
    """Load an html page for entering USP adjustments."""

    def GET(self):
        return self.plugin_render.ups_adj(ups_options, ups_sender.status, log.events(NAME))

    def POST(self):
        ups_options.web_update(web.input())

        if ups_sender is not None:
            ups_sender.update()
        raise web.seeother(plugin_url(settings_page), True)


class settings_json(ProtectedPage):
    """Returns plugin settings in JSON format."""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        return json.dumps(ups_options)

