# -*- coding: utf-8 -*-
__author__ = u'Martin Pihrt'
# this plugins send and check SMS data for modem to control your OSPy

from threading import Thread, Lock
import json
import time
import traceback
import os

import web
from ospy import helpers
from ospy import version
from ospy.inputs import inputs
from ospy.options import options
from ospy.log import log
from plugins import PluginOptions, plugin_url, get_runtime
from ospy.webpages import ProtectedPage
from ospy.helpers import reboot, poweroff, verify_csrf
from ospy.programs import programs
from ospy.stations import stations
from ospy.helpers import datetime_string


NAME = 'SMS Modem'
MENU =  _(u'Package: SMS Modem')
LINK = 'settings_page'
ERROR_LOG_THROTTLE = 300
MISSING_DEPENDENCY_SLEEP = 300

sms_options = PluginOptions(
    NAME,
    {
        u'tel1': u'+xxxyyyyyyyyy',
        u'tel2': u'+xxxyyyyyyyyy',
        u'use_sms': False,
        u'use_strength': False,
        u'txt1': u'info',
        u'txt2': u'stop',
        u'txt3': u'start',
        u'txt4': u'restart',
        u'txt5': u'power',
        u'txt6': u'update',
        u'txt7': u'foto',
        u'txt8': u'help',
        u'txt9': u'run'
    }
)
runtime = get_runtime()
health_lock = Lock()
health_state = {
    'last_check': 0,
    'modem_connected': False,
    'signal_percent': None,
    'last_command': '',
    'last_error': 0,
    'last_error_message': '',
}

# Plugin system will catch the following error and disable the plugin automatically:
# import gammu  # for SMS modem import gammu
# if no install modem and gammu visit: https://pihrt.com/clanky/moje-rapsberry-pi-sms-ovladani-rpi
# USB modem HUAWEI E303 + SIM card with telephone provider

################################################################################
# Main function loop:                                                          #
################################################################################


class SMSSender(Thread):
    def __init__(self):
        Thread.__init__(self)
        self.daemon = True
        self._stop_event = runtime.stop_event
        self._last_error_log = 0

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

    def log_problem(self, message):
        now = time.time()
        error_message = traceback.format_exc().splitlines()[-1]
        with health_lock:
            health_state['last_error'] = now
            health_state['last_error_message'] = error_message
        if now - self._last_error_log >= ERROR_LOG_THROTTLE:
            log.error(NAME, message + '\n' + traceback.format_exc())
            self._last_error_log = now

    def run(self):
        once_text = True
        two_text = True

        while not self._stop_event.is_set():
            try:
                if sms_options["use_sms"]:  # if use_sms is enable (on)
                    if two_text:
                        log.clear(NAME)
                        log.info(NAME, _(u'SMS Modem plug-in is enabled'))
                        once_text = True
                        two_text = False
                        if not os.path.exists("/usr/bin/gammu"):
                            log.clear(NAME)
                            log.info(NAME, _(u'Gammu is not installed.'))
                            log.info(NAME, _(u'Install required packages from the system package manager and restart this plug-in.'))
                            log.info(NAME, 'sudo apt install gammu python3-gammu')
                            self._sleep(MISSING_DEPENDENCY_SLEEP)
                            continue
                        if not os.path.exists("/root/.gammurc"):
                            log.info(NAME, _(u'Saving Gammu config to /root/.gammurc...'))
                            try:
                                with open("/root/.gammurc", "w") as f:
                                    f.write("[gammu]\n")
                                    f.write("port = /dev/ttyUSB0\n")
                                    f.write("model = \n")
                                    f.write("connection = at19200\n")
                                    f.write("synchronizetime = yes\n")
                                    f.write("logfile =\n")
                            except Exception:
                                self.log_problem(_(u'Could not save Gammu config.'))
                    sms_check(self)  # Check SMS command from modem

                else:
                    if once_text:
                        log.clear(NAME)
                        log.info(NAME, _(u'SMS Modem plug-in is disabled'))
                        once_text = False
                        two_text = True

                self._sleep(10)

            except Exception:
                self.log_problem(_(u'SMS Modem plug-in') + ':')
                self._sleep(60)


sms_sender = None

################################################################################
# Helper functions:                                                            #
################################################################################
def start():
    global sms_sender
    if sms_sender is None:
        sms_sender = SMSSender()


def stop():
    global sms_sender
    if sms_sender is not None:
        sms_sender.stop()
        sms_sender.join(15)
        if sms_sender.is_alive():
            log.error(NAME, _('The plug-in worker did not stop within the timeout.'))
        else:
            sms_sender = None


def health():
    """Return modem and worker state without exposing telephone numbers."""
    with health_lock:
        state = dict(health_state)
    worker_running = sms_sender is not None and sms_sender.is_alive()
    admin_count = sum(
        1 for value in (sms_options['tel1'], sms_options['tel2'])
        if value and value != '+xxxyyyyyyyyy'
    )
    details = {
        _('Worker thread'): _('Running') if worker_running else _('Stopped'),
        _('SMS modem enabled'): _('Yes') if sms_options['use_sms'] else _('No'),
        _('Configured administrators'): admin_count,
        _('Gammu executable available'): _('Yes') if os.path.exists('/usr/bin/gammu') else _('No'),
        _('Modem connected'): _('Yes') if state['modem_connected'] else _('No'),
        _('Signal strength'): (
            '{} %'.format(state['signal_percent'])
            if state['signal_percent'] is not None else _('Not available')
        ),
        _('Last modem check'): (
            datetime_string(time.localtime(state['last_check']))
            if state['last_check'] else _('Not available')
        ),
        _('Last command'): state['last_command'] or _('Not available'),
    }
    if state['last_error_message']:
        details[_('Last error')] = state['last_error_message']
    if not worker_running:
        return {
            'status': 'error',
            'summary': _('SMS Modem worker is not running.'),
            'details': details,
        }
    if not sms_options['use_sms']:
        return {
            'status': 'unknown',
            'summary': _('SMS modem control is disabled.'),
            'details': details,
        }
    if state['last_error'] and state['last_error'] >= state['last_check']:
        return {
            'status': 'error',
            'summary': state['last_error_message'],
            'details': details,
        }
    if not state['modem_connected']:
        return {
            'status': 'error',
            'summary': _('SMS modem is not connected.'),
            'details': details,
        }
    return {
        'status': 'ok',
        'summary': _('SMS Modem is responding.'),
        'details': details,
    }

def sms_check(self):
    """Control and processing SMS"""
    try:
        import gammu
    except Exception:
        log.debug(NAME, _(u'Error: No module named gammu'))
        with health_lock:
            health_state['last_error'] = time.time()
            health_state['last_error_message'] = _('Python Gammu module is not available.')
        self._sleep(MISSING_DEPENDENCY_SLEEP)
        return
        
    tel1 = sms_options['tel1']
    tel2 = sms_options['tel2']
    comm1 = sms_options['txt1']
    comm2 = sms_options['txt2']
    comm3 = sms_options['txt3']
    comm4 = sms_options['txt4']
    comm5 = sms_options['txt5']
    comm6 = sms_options['txt6']
    comm7 = sms_options['txt7']
    comm8 = sms_options['txt8']
    comm9 = sms_options['txt9']

    sm = gammu.StateMachine()
    sm.ReadConfig()
    try:
        sm.Init()
        log.debug(NAME, datetime_string() + ': ' + _(u'Checking SMS...'))
    except Exception:
        log.debug(NAME, _(u'Error: Phone (modem) not connected.'))
        with health_lock:
            health_state['last_error'] = time.time()
            health_state['last_error_message'] = _('Phone modem is not connected.')
            health_state['modem_connected'] = False
        self._sleep(60)
        return
    with health_lock:
        health_state['last_check'] = time.time()
        health_state['modem_connected'] = True
        health_state['last_error_message'] = ''

    if sms_options["use_strength"]:    # print strength signal in status Window every check SMS
        signal = sm.GetSignalQuality() # list: SignalPercent, SignalStrength, BitErrorRate
        with health_lock:
            health_state['signal_percent'] = signal['SignalPercent']
        log.info(NAME, datetime_string() + ': ' + _(u'Signal') + ': ' + str(signal['SignalPercent']) + u'% ' + str(signal['SignalStrength']) + u'dB')
    
    status = sm.GetSMSStatus()
    remain = status['SIMUsed'] + status['PhoneUsed'] + status['TemplatesUsed']
    sms = []
    start = True
    while remain > 0:
        if start:
            cursms = sm.GetNextSMS(Start=True, Folder=0)
            start = False
        else:
            cursms = sm.GetNextSMS(Location=cursms[0]['Location'], Folder=0)
        remain = remain - len(cursms)
        sms.append(cursms)
    data = gammu.LinkSMS(sms)
    for x in data:
        v = gammu.DecodeSMS(x)
        m = x[0]
        log.debug(NAME, '%-15s: %s' % ('Sender', m['Number']))
        log.debug(NAME, '%-15s: %s' % ('Date', str(m['DateTime'])))
        log.debug(NAME, '%-15s: %s' % ('State', m['State']))
        log.debug(NAME, '%-15s: %s' % ('SMS command', m['Text']))
        if (m['Number'] == tel1) or (m['Number'] == tel2):  # If telephone is admin 1 or admin 2
            log.info(NAME, datetime_string() + ': ' + _(u'SMS from admin'))
            if m['State'] == "UnRead":          # If SMS is unread
                with health_lock:
                    health_state['last_command'] = str(m['Text'])
                log.clear(NAME)
                if m['Text'] == comm1:           # If command = comm1 (info - send SMS to admin phone1 and phone2)
                    log.info(NAME, _('Command') + ' ' + comm1 + ' ' + _(u'is processed'))
                    # send 1/2 SMS with text 1
                    up = helpers.uptime()
                    temp = helpers.get_cpu_temp(options.temp_unit) + ' ' + options.temp_unit
                    ip = str(helpers.get_ip())
                    ver = version.ver_date
                    datastr = (
                    'SMS 1/2. ' + datetime_string() + ', TEMP: ' + temp + ', IP: ' + ip + ', SW: ' + ver + ', UP: ' + up  )
                    message = {
                        'Text': datastr,
                        'SMSC': {'Location': 1},
                        'Number': m['Number'],
                    }
                    sm.SendSMS(message) # send sms 1/2
                    log.info(NAME, datastr)
                    # send 2/2 SMS with text 2
                    if inputs.rain_sensed():
                        rain = "Active"
                    else:
                        rain = "Inactive"
                    try:
                        from plugins import pressure_monitor
                        state_press = pressure_monitor.get_check_pressure()

                        if state_press:
                            press = "High"
                        else:
                            press = "Low"
                    except Exception:
                        press = "N/A"
                    finished = [run for run in log.finished_runs() if not run['blocked']]
                    if finished:
                        last_prog = finished[-1]['start'].strftime('%H:%M: ') + finished[-1]['program_name']
                    else:
                        last_prog = 'None'
                    datastr = ('SMS 2/2. ' + 'RAIN: ' + rain + ', PRESS: ' + press + ', LAST: ' + last_prog)
                    message = {
                        'Text': datastr,
                        'SMSC': {'Location': 1},
                        'Number': m['Number'],
                    }
                    sm.SendSMS(message) # send sms 2/2
                    log.info(NAME, datastr)

                    log.info(NAME,
                             _(u'Command') + ': ' + comm1 + ' ' + _(u'was processed and confirmation was sent as SMS to') + ': ' + m['Number'])
                    sm.DeleteSMS(m['Folder'], m['Location'])  # SMS deleted
                    log.info(NAME, _(u'Received SMS was deleted'))

                elif m['Text'] == comm2:        # If command = comm2 (stop - scheduler)
                    log.info(NAME, _(u'Command') + ' ' + comm2 + ' ' + _(u'is processed'))
                    options.scheduler_enabled = False
                    log.finish_run(None)
                    stations.clear()

                    message = {
                        'Text': 'Command: ' + comm2 + ' was processed',
                        'SMSC': {'Location': 1},
                        'Number': m['Number'],
                    }
                    sm.SendSMS(message)
                    log.info(NAME,
                             _(u'Command') + ': ' + comm2 + ' ' + _(u'was processed and confirmation was sent as SMS to') + ': ' + m['Number'])
                    sm.DeleteSMS(m['Folder'], m['Location'])
                    log.info(NAME, _(u'Received SMS was deleted'))

                elif m['Text'] == comm3:         # If command = comm3 (start - scheduler)
                    log.info(NAME, _(u'Command') + ' ' + comm3 + ' ' + _(u'is processed'))
                    options.scheduler_enabled = True
                    message = {
                        'Text': 'Command: ' + comm3 + ' was processed',
                        'SMSC': {'Location': 1},
                        'Number': m['Number'],
                    }
                    sm.SendSMS(message)
                    log.info(NAME,
                             _(u'Command') + ': ' + comm3 + ' ' + _(u'was processed and confirmation was sent as SMS to') + ': ' + m['Number'])
                    sm.DeleteSMS(m['Folder'], m['Location'])
                    log.info(NAME, _(u'Received SMS was deleted'))

                elif m['Text'] == comm4:        # If command = comm4 (reboot system)
                    log.info(NAME, _(u'Command') + ' ' + comm4 + ' ' + _(u'is processed'))
                    message = {
                        'Text': 'Command: ' + comm4 + ' was processed',
                        'SMSC': {'Location': 1},
                        'Number': m['Number'],
                    }
                    sm.SendSMS(message)
                    log.info(NAME,
                             _(u'Command') + ': ' + comm4 + ' ' + _(u'was processed and confirmation was sent as SMS to') + ': ' + m['Number'])
                    sm.DeleteSMS(m['Folder'], m['Location'])
                    log.info(NAME, _(u'Received SMS was deleted and system is now reboot'))
                    reboot()                    # restart linux system

                elif m['Text'] == comm5:        # If command = comm5 (poweroff system)
                    log.info(NAME, _('Command') + ' ' + comm5 + ' ' + _('is processed'))
                    message = {
                        'Text': 'Command: ' + comm5 + ' was processed',
                        'SMSC': {'Location': 1},
                        'Number': m['Number'],
                    }
                    sm.SendSMS(message)
                    log.info(NAME,
                             _(u'Command') + ': ' + comm5 + ' ' + _(u'was processed and confirmation was sent as SMS to') + ': ' + m['Number'])
                    sm.DeleteSMS(m['Folder'], m['Location'])
                    log.info(NAME, _(u'Received SMS was deleted and system is now poweroff'))
                    poweroff()                  # poweroff linux system

                elif m['Text'] == comm6:        # If command = comm6 (update ospi system)
                    log.info(NAME, _(u'Command') + ' ' + comm6 + ' ' + _(u'is processed'))
                    message = {
                        'Text': 'Command: ' + comm6 + ' was processed',
                        'SMSC': {'Location': 1},
                        'Number': m['Number'],
                    }
                    sm.SendSMS(message)
                    log.info(NAME,
                             _(u'Command') + ': ' + comm6 + ' ' + _(u'was processed and confirmation was sent as SMS to') + ': ' + m['Number'])
                    try:
                        from plugins.system_update import perform_update

                        perform_update()
                        log.info(NAME, _(u'Received SMS was deleted, update was performed and program will restart'))
                    except ImportError:
                        log.info(NAME, _(u'Received SMS was deleted, but could not perform update'))

                    sm.DeleteSMS(m['Folder'], m['Location'])

                elif m['Text'] == comm7:        # If command = comm7 (send email with foto from webcam)
                    log.info(NAME, _(u'Command') + ' ' + comm7 + ' ' + _(u'is processed'))
                    message = {
                        'Text': 'Command: ' + comm7 + ' was processed',
                        'SMSC': {'Location': 1},
                        'Number': m['Number'],
                    }
                    sm.SendSMS(message)
                    log.info(NAME,
                             _(u'Command') + ': ' + comm7 + ' ' + _(u'was processed and confirmation was sent as SMS to') + ': ' + m['Number'])
                    try:
                        from plugins.webcam import get_run_cam, get_image_location

                        get_run_cam() # process save foto to ./data/image.jpg
                        msg = _(u'SMS plug-in send image file from webcam.')

                        send_email(msg, attachments=get_image_location())

                    except ImportError:
                        log.info(NAME, _(u'Received SMS was deleted, but could not send email with photo from webcam'))
                        message = {
                            'Text': 'Error: not send foto from webcam',
                            'SMSC': {'Location': 1},
                            'Number': m['Number'],
                        }
                        sm.SendSMS(message)
                    sm.DeleteSMS(m['Folder'], m['Location'])

                elif m['Text'] == comm8:        # If command = comm8 (send SMS with available commands)
                    log.info(NAME, _(u'Command') + ' ' + comm8 + ' ' + _(u'is processed'))
                    message = {
                        'Text': 'Available commands: ' + comm1 + ',' + comm2 + ',' + comm3 + ',' + comm4 + ',' + comm5 + ',' + comm6 + ',' + comm7 + ',' + comm8 + ',' + comm9 + 'xx',
                        'SMSC': {'Location': 1},
                        'Number': m['Number'],
                    }
                    sm.SendSMS(message)
                    log.info(NAME,
                             _(u'Command') + ': ' + comm8 + ' ' + _(u'was processed and confirmation was sent as SMS to') + ': ' + m['Number'])
                    sm.DeleteSMS(m['Folder'], m['Location'])
                    log.info(NAME, _(u'Received SMS was deleted'))


                elif m['Text'][0:len(comm9)] == comm9:        # If command = lenght char comm9 (run now program xx)
                    num = m['Text'][len(comm9):]              # number from sms text example: run36 -> num=36
                    log.info(NAME, _(u'Command') + ' ' + comm9 + ' ' + _(u'is processed'))
                    index = int(num) if num.isdigit() else 0
                    if 1 <= index <= programs.count():             # if program number from sms text exists in program db
                        log.finish_run(None)
                        stations.clear()
                        prog = int(index - 1)
                        programs.run_now(prog)
                        log.info(NAME, _(u'Program') + ': ' + str(index) + ' ' + _(u'now run'))
                        message = {
                            'Text': 'Program: ' + str(index) + ' now run',
                            'SMSC': {'Location': 1},
                            'Number': m['Number'],
                        }
                    else:
                        message = {
                            'Text': 'Program: ' + str(index) + ' no exists!',
                            'SMSC': {'Location': 1},
                            'Number': m['Number'],
                        }

                    sm.SendSMS(message)
                    log.info(NAME,
                             _(u'Command') + ': ' + str(m['Text']) + ' ' + _(u'was processed and confirmation was sent as SMS to') + ': ' + m[
                                 'Number'])
                    sm.DeleteSMS(m['Folder'], m['Location'])
                    log.info(NAME, _(u'Received SMS was deleted'))

                else:                            # If SMS command is not defined
                    sm.DeleteSMS(m['Folder'], m['Location'])
                    log.info(NAME, _(u'Received command') + ' ' + m['Text'] + ' ' + _(u'is not defined!'))

            else:                                # If SMS was read
                sm.DeleteSMS(m['Folder'], m['Location'])
                log.info(NAME, _(u'Received SMS was deleted - SMS was read'))
        else:                          # If telephone number is not admin 1 or admin 2 phone number
            sm.DeleteSMS(m['Folder'], m['Location'])
            log.info(NAME, _(u'Received SMS was deleted - SMS was not from admin'))


def send_email(msg, attachments):
    """Send email"""
    message = datetime_string() + ': ' + str(msg)
    try:
        from plugins.email_notifications import email
        email(message, attach=attachments)
        log.info(NAME, _(u'Email was sent') + ': ' + message)
    except Exception:
        log.error(NAME, _(u'Email was not sent') + '! ' + traceback.format_exc())

################################################################################
# Web pages:                                                                   #
################################################################################
class settings_page(ProtectedPage):
    """Load an html page for entering lcd adjustments."""

    def GET(self):
        return self.plugin_render.sms_adj(sms_options, log.events(NAME))

    def POST(self):
        qdict = web.input()
        verify_csrf(qdict)
        sms_options.web_update(qdict)

        if sms_sender is not None:
            sms_sender.update()
        raise web.seeother(plugin_url(settings_page), True)


class help_page(ProtectedPage):
    """Load an html page for help page."""

    def GET(self):
        return self.plugin_render.sms_adj_help()        


class settings_json(ProtectedPage):
    """Returns plugin settings in JSON format."""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        return json.dumps(sms_options)

