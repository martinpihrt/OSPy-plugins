# -*- coding: utf-8 -*-
__author__ = 'Martin Pihrt'
# This plugin controls OpenSprinkler OSPy via 8 defined buttons. I2C controller MCP23017 on range 0x20 to 0x27 address.

import json
import time
import datetime
import traceback
import os
from threading import Thread, Lock

import web

from ospy.log import log
from plugins import PluginOptions, plugin_url, get_runtime
from ospy.webpages import ProtectedPage
from ospy.stations import stations
from ospy.scheduler import scheduler
from ospy.programs import programs
from ospy.options import options
from ospy.runonce import run_once
from ospy import helpers
from ospy.helpers import get_rpi_revision, datetime_string, reboot, restart, poweroff, verify_csrf
from ospy.scheduler import predicted_schedule, combined_schedule
from ospy.i2c_guard import i2c_transaction

from blinker import signal


NAME = 'Button Control'
MENU =  _('Package: Button Control')
LINK = 'settings_page'
last_led_output = None
runtime = get_runtime()
health_lock = Lock()
health_state = {
    'last_success': 0,
    'last_error': 0,
    'last_error_message': '',
}

plugin_options = PluginOptions(
    NAME,
    {'use_button': False,
     'button0': 'reboot',
     'button1': 'pwrOff',
     'button2': 'stopAll',
     'button3': 'schedEn',
     'button4': 'runP1',
     'button5': 'runP2',
     'button6': 'runP3',
     'button7': 'runP4',
     'used_stations': [],    # use this stations for stoping scheduler if stations is activated in scheduler
     'i2c_addr': 39,         # 32 decimal to 37 decimal (is 0x20 to 0x27)
     'first_stop': False,    # First stop everything running and then start the program. If we want to start a new program and add it to the running ones, we will leave this option off.
    }
)

rebooted = signal('rebooted')
def report_rebooted():
    rebooted.send()

reppoweroff = signal('poweroff')
def report_poweroff():
    reppoweroff.send()


def _program_index_from_action(action):
    action = str(action or '')
    if action.lower().startswith('runp') and action[4:].isdigit():
        program_number = int(action[4:])
        if program_number > 0:
            return program_number - 1
    return None


def _program_label(program):
    name = getattr(program, 'name', '')
    label = _('Run now program {}').format(program.index + 1)
    if name:
        label += ': ' + name
    return label


def _run_program_now(program_index):
    for program in programs.get():
        if program.index == program_index:
            log.info(NAME, datetime_string() + ': ' + _program_label(program))
            options.manual_mode = False
            if plugin_options['first_stop']:
                log.finish_run(None)
                stations.clear()
            programs.run_now(program.index)
            return True
    log.info(NAME, datetime_string() + ': ' + _('Program {} was not found.').format(program_index + 1))
    return False

################################################################################
# Main function loop:                                                          #
################################################################################

class PluginSender(Thread):
    def __init__(self):
        Thread.__init__(self)
        self.daemon = True
        self._stop_event = runtime.stop_event
        
        self.bus = None
        
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
        log.clear(NAME)  
        disable_text = True

        while not self._stop_event.is_set():
            try:
                if plugin_options['use_button']:  # if button plugin is enabled
                    disable_text = True
                    actual_buttons = read_buttons()
                    
                    # led_outputs(actual_buttons) # for test

                    for i in range(8):
                       tb = "button" + str(i)    
                       if actual_buttons == i and plugin_options[tb]== "reboot":
                          log.info(NAME, datetime_string() + ': ' + _('System reboot')) 
                          stations.clear()
                          report_rebooted()
                          reboot(block=True) # Linux HW software
                          self._sleep(1)
                       
                       if actual_buttons == i and plugin_options[tb]== "pwrOff":
                          log.info(NAME, datetime_string() + ': ' + _('System shutdown')) 
                          stations.clear()
                          report_poweroff()
                          poweroff(wait=10, block=True)   # shutdown HW system
                          self._sleep(1)
                         
                       if actual_buttons == i and plugin_options[tb]== "stopAll":
                          log.info(NAME, datetime_string() + ': ' + _('Selected stations now stopped'))
                          set_stations_in_scheduler_off()
                          self._sleep(1) 

                       if actual_buttons == i and plugin_options[tb]== "schedEn":
                          log.info(NAME, datetime_string() + ': ' + _('Scheduler is now enabled')) 
                          options.scheduler_enabled = True
                          self._sleep(1)

                       if actual_buttons == i and plugin_options[tb]== "schedDis":
                          log.info(NAME, datetime_string() + ': ' + _('Scheduler is now disabled')) 
                          options.scheduler_enabled = False
                          self._sleep(1)

                       program_index = _program_index_from_action(plugin_options[tb])
                       if actual_buttons == i and program_index is not None:
                          _run_program_now(program_index)
                          self._sleep(1)

                    self._sleep(1)

                else:
                    # text on the web if plugin is disabled
                    if disable_text:  
                       log.clear(NAME)
                       log.info(NAME, _('Button plug-in is disabled.'))
                       disable_text = False  
                    self._sleep(1)

            except Exception:
                log.clear(NAME)
                log.error(NAME, _('Button plug-in') + ':\n' + traceback.format_exc())
                self._sleep(60)
                pass
                

plugin_sender = None

################################################################################
# Helper functions:                                                            #
################################################################################
def start():
    global plugin_sender
    if plugin_sender is None:
        plugin_sender = PluginSender()
        runtime.register_thread(plugin_sender)


def stop():
    global plugin_sender
    worker = plugin_sender
    if worker is not None:
        worker.stop()
        worker.join(5)
        if plugin_sender is worker and not worker.is_alive():
            plugin_sender = None


def record_button_success():
    with health_lock:
        health_state['last_success'] = time.time()
        health_state['last_error_message'] = ''


def record_button_error(message):
    with health_lock:
        health_state['last_error'] = time.time()
        health_state['last_error_message'] = str(message).splitlines()[-1]


def health():
    """Return worker, configuration and MCP23017 communication state."""
    with health_lock:
        state = dict(health_state)
    worker_alive = plugin_sender is not None and plugin_sender.is_alive()
    details = {
        _('Worker thread'): _('Running') if worker_alive else _('Stopped'),
        _('I2C address'): '0x{:02x}'.format(int(plugin_options['i2c_addr'])),
        _('Last successful read'): (
            datetime_string(time.localtime(state['last_success']))
            if state['last_success'] else _('Not available')
        ),
    }
    if state['last_error_message']:
        details[_('Last error')] = state['last_error_message']
    if not plugin_options['use_button']:
        return {
            'status': 'unknown',
            'summary': _('Button Control is disabled.'),
            'details': details,
        }
    if not worker_alive:
        return {
            'status': 'error',
            'summary': _('Button Control worker is stopped.'),
            'details': details,
        }
    if state['last_error'] > state['last_success']:
        return {
            'status': 'error',
            'summary': state['last_error_message'],
            'details': details,
        }
    if not state['last_success']:
        return {
            'status': 'warning',
            'summary': _('Waiting for the first button-controller response.'),
            'details': details,
        }
    return {
        'status': 'ok',
        'summary': _('Button controller is responding.'),
        'details': details,
    }


def set_stations_in_scheduler_off():
    """Stoping selected station in scheduler."""
    
    current_time  = datetime.datetime.now()
    check_start = current_time - datetime.timedelta(days=1)
    check_end = current_time + datetime.timedelta(days=1)

    # In manual mode we cannot predict, we only know what is currently running and the history
    if options.manual_mode:
        active = log.finished_runs() + log.active_runs()
    else:
        active = combined_schedule(check_start, check_end)    

    ending = False

    # active stations
    for entry in active:
        for used_stations in plugin_options['used_stations']: # selected stations for stoping
            if entry['station'] == used_stations:             # is this station in selected stations? 
                log.finish_run(entry)                         # save end in log 
                stations.deactivate(entry['station'])         # stations to OFF
                ending = True   

    if ending:
        log.info(NAME, _('Stoping stations in scheduler'))        

        
def try_io(call, tries=10):
    assert tries > 0
    error = None
    result = None

    while tries:
        try:
            result = call()
        except IOError as e:
            error = e
            tries -= 1
        else:
            break

    if not tries:
        raise error

    return result


def button_i2c_transaction():
    try:
        return i2c_transaction(priority='normal')
    except TypeError:
        return i2c_transaction()

def read_buttons():
    bus = None
    try:
        import smbus  

        bus = smbus.SMBus(0 if helpers.get_rpi_revision() == 1 else 1) 
        
        # Set 8 GPA pins as input pull-UP
        with button_i2c_transaction():
            try_io(lambda: bus.write_byte_data(plugin_options['i2c_addr'],0x0C,0xFF)) #bus.write_byte_data(0x27,0x0C,0xFF)  
     
        # Wait for device
        time.sleep(0.2) 

        # Read state of GPIOA register
        with button_i2c_transaction():
            MySwitch = try_io(lambda: bus.read_byte_data(plugin_options['i2c_addr'],0x12))  # MySwitch = bus.read_byte_data(0x27,0x12)
        record_button_success()
               
        inBut = 255-MySwitch; # inversion number for led off if button is not pressed

        led_outputs(inBut)    # switch on actual led if button is pressed

        button_number = -1
        if inBut == 128:
            button_number = 7
            log.debug(NAME, _('Switch 8 pressed'))
        if inBut == 64:
            button_number = 6
            log.debug(NAME, _('Switch 7 pressed'))
        if inBut == 32:
            button_number = 5
            log.debug(NAME, _('Switch 6 pressed'))
        if inBut == 16:
            button_number = 4
            log.debug(NAME, _('Switch 5 pressed'))
        if inBut == 8:
            button_number = 3
            log.debug(NAME, _('Switch 4 pressed'))
        if inBut == 4:
            button_number = 2
            log.debug(NAME, _('Switch 3 pressed'))
        if inBut == 2:
            button_number = 1
            log.debug(NAME, _('Switch 2 pressed'))
        if inBut == 1:
            button_number = 0
            log.debug(NAME, _('Switch 1 pressed'))
        return button_number #if button is not pressed return -1

    except IOError as e:
        if str(e) == 'I2C bus is busy.':
            log.debug(NAME, datetime_string() + ': ' + _('I2C bus is busy, button read skipped.'))
        else:
            record_button_error(str(e))
            log.clear(NAME)
            log.debug(NAME, datetime_string() + ': ' + _('Read button - FAULT'))
            log.debug(NAME, _('Is hardware connected? Is bus address corectly setuped?'))
            log.error(NAME, '\n' + traceback.format_exc())
        return -1

    except Exception:
        record_button_error(traceback.format_exc().splitlines()[-1])
        log.clear(NAME)
        log.debug(NAME, datetime_string() + ': ' + _('Read button - FAULT'))
        log.debug(NAME, _('Is hardware connected? Is bus address corectly setuped?'))
        log.error(NAME, '\n' + traceback.format_exc())
        return -1
    finally:
        if bus is not None:
            try:
                bus.close()
            except Exception:
                pass

def led_outputs(led):
    global last_led_output

    if led == last_led_output:
        return

    bus = None
    try:
        import smbus  

        bus = smbus.SMBus(0 if helpers.get_rpi_revision() == 1 else 1) 
 
        with i2c_transaction():
            try_io(lambda: bus.write_byte_data(plugin_options['i2c_addr'],0x01,0x00)) # bus.write_byte_data(0x27,0x01,0x00)
        
        # Wait for device
        time.sleep(0.2) 
        
        with i2c_transaction():
            try_io(lambda: bus.write_byte_data(plugin_options['i2c_addr'],0x13,led))  # bus.write_byte_data(0x27,0x13,led)

        last_led_output = led
              
    except IOError as e:
        if str(e) == 'I2C bus is busy.':
            log.debug(NAME, datetime_string() + ': ' + _('I2C bus is busy, LED update skipped.'))
        else:
            record_button_error(str(e))
            log.error(NAME, datetime_string() + ': ' + _('Set LED - FAULT'))
            log.error(NAME, _('Is hardware connected? Is bus address corectly setuped?'))
        pass

    except Exception:
        record_button_error(traceback.format_exc().splitlines()[-1])
        log.error(NAME, datetime_string() + ': ' + _('Set LED - FAULT'))
        log.error(NAME, _('Is hardware connected? Is bus address corectly setuped?'))
        #log.error(NAME, '\n' + traceback.format_exc())
    finally:
        if bus is not None:
            try:
                bus.close()
            except Exception:
                pass

################################################################################
# Web pages:                                                                   #
################################################################################

class settings_page(ProtectedPage):
    """Load an html page for entering plugin settings."""

    def GET(self):
        try:
            return self.plugin_render.button_control(plugin_options, log.events(NAME), programs.get())
        except:
            log.error(NAME, _('Button plug-in') + ':\n' + traceback.format_exc())
            msg = _('An internal error was found in the system, see the error log for more information. The error is in part:') + ' '
            msg += _('button_control -> settings_page GET')
            return self.core_render.notice('/', msg)

    def POST(self):
        try:
            qdict = web.input(**plugin_options) #for save multiple select
            helpers.verify_csrf(qdict)
            plugin_options.web_update(qdict)
            if plugin_sender is not None:
                plugin_sender.update()
            raise web.seeother(plugin_url(settings_page), True)
        except:
            log.error(NAME, _('Button plug-in') + ':\n' + traceback.format_exc())
            msg = _('An internal error was found in the system, see the error log for more information. The error is in part:') + ' '
            msg += _('button_control -> settings_page POST')
            return self.core_render.notice('/', msg)

class help_page(ProtectedPage):
    """Load an html page for help"""

    def GET(self):
        try:
            return self.plugin_render.button_control_help()        
        except:
            log.error(NAME, _('Button plug-in') + ':\n' + traceback.format_exc())
            msg = _('An internal error was found in the system, see the error log for more information. The error is in part:') + ' '
            msg += _('button_control -> help_page GET')
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
