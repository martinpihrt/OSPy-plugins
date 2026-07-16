# -*- coding: utf-8 -*-
__author__ = 'Martin Pihrt' 

import time

from threading import Thread, Lock
import traceback
import json

import web
from ospy.log import log
from ospy.webpages import ProtectedPage
from ospy.helpers import determine_platform, get_rpi_revision, datetime_string, verify_csrf
from ospy.stations import stations
from plugins import PluginOptions, plugin_url, get_runtime


NAME = 'Direct 16 Relay Outputs'
MENU =  _('Package: Direct 16 Relay Outputs')
LINK = 'settings_page'
GPIO_PINS = [22, 24, 26, 32, 36, 38, 40, 21, 23, 29, 31, 33, 35, 37, 18, 19]
LOOP_INTERVAL = 0.5
ERROR_LOG_THROTTLE = 300

plugin_options = PluginOptions(
    NAME,
    {
        'enabled': False,  # default is OFF
        'relays': 1,       # default 1 relay
        'active': 'high'   # default is normal logic   
    })
runtime = get_runtime()
health_lock = Lock()
gpio_driver = None
health_state = {
    'last_cycle': 0,
    'configured_relays': 0,
    'active_relays': 0,
    'hardware_ready': False,
    'last_error': 0,
    'last_error_message': '',
}


################################################################################
# Main function loop:                                                          #
################################################################################
class Relay16Checker(Thread):
    def __init__(self):
        Thread.__init__(self)
        self.daemon = True
        self._stop_event = runtime.stop_event

        self._sleep_time = 0
        self.start()
        runtime.register_thread(self)

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
        global gpio_driver
        log.clear(NAME)
        error_check = False # error signature
        relay_pins = GPIO_PINS
        relay_count = -1
        msg_debug_err = True
        msg_debug_on = [True,True,True,True,True,True,True,True,True,True,True,True,True,True,True,True]
        msg_debug_off = [True,True,True,True,True,True,True,True,True,True,True,True,True,True,True,True]
        time_cleaner = 0
 
        last_error_log = 0
        normalize_options(plugin_options)

        if not plugin_options['enabled']:
           log.info(NAME, _('Relay 16 plug-in') + ': ' +  _('is disabled.'))

        while not self._stop_event.is_set():
            try: 
                normalize_options(plugin_options)
                if relay_count != plugin_options['relays'] and plugin_options['enabled']:
                    relay_count = plugin_options['relays']
                    log.clear(NAME)
                    log.info(NAME, _('Relay 16 plug-in') + ': ' + datetime_string() + ' ' + str(plugin_options['relays']) + ' ' + _('Outputs set.'))

                    #### define the GPIO pins that will be used ####
                    try:
                        if determine_platform() == 'pi': # If this will run on Raspberry Pi:
                            import RPi.GPIO as GPIO  # RPi hardware
                            gpio_driver = GPIO
                            GPIO.setmode(GPIO.BOARD) #IO channels are identified by header connector pin numbers. Pin numbers are

                            if get_rpi_revision() >= 2:
                                log.info(NAME, _('Relay 16 plug-in') + ': ' + _('Possible GPIO pins') + str(relay_pins) + '.')
                                for i in range(plugin_options['relays']):   # count 1 or 2, 4, 8, 16 outputs
                                    try:
                                        GPIO.setup(relay_pins[i], GPIO.OUT) # set pin as outputs
                                    except Exception:
                                        error_check = True                  # not set pins -> this is error
                                        log.error(NAME, _('Relay 16 plug-in') + ':\n' + traceback.format_exc())
                            else:
                                log.info(NAME, _('Relay 16 plug-in') + ': ' + _('Sorry Raspberry Pi 1 is old version.'))
                                error_check = True
                        else:
                            log.info(NAME, _('Relay 16 plug-in') + ': ' + _('Relay board plugin only supported on Raspberry Pi.'))
                            error_check = True

                    except Exception:
                        if msg_debug_err:
                            log.error(NAME, _('Relay 16 plug-in') + ':\n' + traceback.format_exc())
                            msg_debug_err = False
                        error_check = True

                #### plugin 
                if plugin_options['enabled']:                   # if plugin is enabled
                  if error_check == False:                      # if not check error
                     for station in stations.get():
                       if station.index < len(relay_pins) and station.index+1 <= plugin_options['relays']:  # only if station count is < count relay outputs

                         ### ON
                         if station.active:                            # stations is on 
                            if plugin_options['active'] == 'high':     # normal high logic
                               # relay output on to 3.3V 
                               GPIO.output(relay_pins[station.index], GPIO.HIGH)
                               if msg_debug_on[station.index]:
                                  log.info(NAME, _('Relay 16 plug-in') + ': ' + datetime_string() + ' ' + _('Setings Relay Output') + ' ' + str(relay_pins[station.index]) + ' ' + _('to HIGH') + ' (' + _('Station') + ' ' + str(station.index+1) + ' ' + _('ON') + ').')
                                  msg_debug_on[station.index] = False
                                  msg_debug_off[station.index] = True 
                            else:                                      # inversion low logic
                               # relay output on to 0V 
                               GPIO.output(relay_pins[station.index], GPIO.LOW)
                               if msg_debug_on[station.index]:
                                  log.info(NAME, _('Relay 16 plug-in') + ': ' + datetime_string() + ' ' + _('Setings Relay Output') + ' ' + str(relay_pins[station.index]) + ' ' + _('to LOW') + ' (' + _('Station') + ' ' + str(station.index+1) + ' ' + _('ON') + ').') 
                                  msg_debug_on[station.index] = False
                                  msg_debug_off[station.index] = True

                         ### OFF
                         else:                                         # stations is off
                            if plugin_options['active'] == 'high':     # normal high logic
                               # relay output off to 0V
                               GPIO.output(relay_pins[station.index], GPIO.LOW)
                               if msg_debug_off[station.index]:
                                  log.info(NAME, _('Relay 16 plug-in') + ': ' + datetime_string() + ' ' + _('Setings Relay Output') + ' ' + str(relay_pins[station.index]) + ' ' + _('to LOW') + ' (' + _('Station') + ' ' + str(station.index+1) +  ' ' + _('OFF') + ').')
                                  msg_debug_off[station.index] = False
                                  msg_debug_on[station.index] = True
                            else:                                      # inversion low logic
                               # relay output off to 3.3V   
                               GPIO.output(relay_pins[station.index], GPIO.HIGH)
                               if msg_debug_off[station.index]:
                                  log.info(NAME, _('Relay 16 plug-in') + ': ' + datetime_string() + ' ' + _('Setings Relay Output') + ' ' + str(relay_pins[station.index]) + ' ' + _('to HIGH') + ' (' + _('Station') + ' ' + str(station.index+1)  + ' ' + _('OFF') + ').')
                                  msg_debug_off[station.index] = False
                                  msg_debug_on[station.index] = True

                active_relays = sum(
                    1 for station in stations.get()
                    if station.index < plugin_options['relays'] and station.active
                )
                with health_lock:
                    health_state['last_cycle'] = time.time()
                    health_state['configured_relays'] = plugin_options['relays']
                    health_state['active_relays'] = active_relays
                    health_state['hardware_ready'] = (
                        bool(plugin_options['enabled']) and not error_check
                    )
                    health_state['last_error_message'] = ''

                if self._stop_event.wait(LOOP_INTERVAL):
                    break

                time_cleaner += 1

                if time_cleaner >= 120: # 60 sec timer (ex: 120 * time.sleep(0.5) is 60 sec)
                   time_cleaner = 0
                   relay_count = -1
                   msg_debug_err = True
                   msg_debug_on = [True,True,True,True,True,True,True,True,True,True,True,True,True,True,True,True]
                   msg_debug_off = [True,True,True,True,True,True,True,True,True,True,True,True,True,True,True,True]

            except Exception:
                now = time.time()
                message = traceback.format_exc().splitlines()[-1]
                with health_lock:
                    health_state['last_error'] = now
                    health_state['last_error_message'] = message
                    health_state['hardware_ready'] = False
                if now - last_error_log >= ERROR_LOG_THROTTLE:
                    log.error(NAME, _('Relay 16 plug-in') + ':\n' + traceback.format_exc())
                    last_error_log = now
                self._sleep(60)


checker = None


################################################################################
# Helper functions:                                                            #
################################################################################
  
def start():
    global checker
    if checker is None:
        checker = Relay16Checker()


def stop():
    global checker
    if checker is not None:
        checker.stop()
        checker.join(15)
        if checker.is_alive():
            log.error(NAME, _('The plug-in worker did not stop within the timeout.'))
        else:
            checker = None
    release_relays()


def release_relays():
    """Drive configured relay outputs to their inactive level."""
    if gpio_driver is None:
        return
    inactive = gpio_driver.LOW if plugin_options['active'] == 'high' else gpio_driver.HIGH
    for pin in GPIO_PINS[:plugin_options['relays']]:
        try:
            gpio_driver.output(pin, inactive)
        except Exception:
            log.error(NAME, _('Unable to release relay output') + ': ' + str(pin))
    with health_lock:
        health_state['active_relays'] = 0


def health():
    """Return GPIO relay and worker state for diagnostics."""
    with health_lock:
        state = dict(health_state)
    worker_running = checker is not None and checker.is_alive()
    details = {
        _('Worker thread'): _('Running') if worker_running else _('Stopped'),
        _('Relay outputs enabled'): _('Yes') if plugin_options['enabled'] else _('No'),
        _('Configured relays'): state['configured_relays'],
        _('Active relays'): state['active_relays'],
        _('Hardware ready'): _('Yes') if state['hardware_ready'] else _('No'),
        _('Trigger level'): str(plugin_options['active']).upper(),
        _('Last successful cycle'): (
            datetime_string(time.localtime(state['last_cycle']))
            if state['last_cycle'] else _('Not available')
        ),
    }
    if state['last_error_message']:
        details[_('Last error')] = state['last_error_message']
    if not worker_running:
        return {
            'status': 'error',
            'summary': _('Direct 16 Relay Outputs worker is not running.'),
            'details': details,
        }
    if state['last_error'] and state['last_error'] >= state['last_cycle']:
        return {
            'status': 'error',
            'summary': state['last_error_message'],
            'details': details,
        }
    if not plugin_options['enabled']:
        return {
            'status': 'unknown',
            'summary': _('Direct relay outputs are disabled.'),
            'details': details,
        }
    if not state['hardware_ready']:
        return {
            'status': 'error',
            'summary': _('Relay GPIO hardware is not ready.'),
            'details': details,
        }
    return {
        'status': 'ok',
        'summary': _('Direct relay outputs are responding.'),
        'details': details,
    }


def to_int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def normalize_options(values):
    relays = to_int(values.get('relays'), plugin_options['relays'])
    values['relays'] = max(1, min(len(GPIO_PINS), relays))
    if values.get('active') not in ('low', 'high'):
        values['active'] = 'high'
    return values

################################################################################
# Web pages:                                                                   #
################################################################################
class settings_page(ProtectedPage):
    """Load an html page for entering relay 16 adjustments"""

    def GET(self):
        try:
            return self.plugin_render.relay_16(plugin_options, log.events(NAME))
        except:
            log.error(NAME, _('Relay 16 plug-in') + ':\n' + traceback.format_exc())
            msg = _('An internal error was found in the system, see the error log for more information. The error is in part:') + ' '
            msg += _('relay_16 -> settings_page GET')
            return self.core_render.notice('/', msg)


    def POST(self):
        try:
            qdict = web.input()
            verify_csrf(qdict)
            normalize_options(qdict)
            plugin_options.web_update(qdict)
            if checker is not None:
                checker.update()
            raise web.seeother(plugin_url(settings_page), True)
        except:
            log.error(NAME, _('Relay 16 plug-in') + ':\n' + traceback.format_exc())
            msg = _('An internal error was found in the system, see the error log for more information. The error is in part:') + ' '
            msg += _('relay_16 -> settings_page POST')
            return self.core_render.notice('/', msg)


class help_page(ProtectedPage):
    """Load an html page for help"""

    def GET(self):
        try:
            return self.plugin_render.relay_16_help()
        except:
            log.error(NAME, _('Relay 16 plug-in') + ':\n' + traceback.format_exc())
            msg = _('An internal error was found in the system, see the error log for more information. The error is in part:') + ' '
            msg += _('relay_16 -> help_page GET')
            return self.core_render.notice('/', msg)


class settings_json(ProtectedPage):
    """Returns plugin settings in JSON format"""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        try:
            return json.dumps(plugin_options)
        except:
            return {}
