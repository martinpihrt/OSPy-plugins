# -*- coding: utf-8 -*-
__author__ = 'Martin Pihrt'
# this plugins send GET data to remote web server

import json
import time
import os
import os.path
import traceback
import re
from threading import Thread, Lock

import web
from ospy.webpages import ProtectedPage
from plugins import PluginOptions, plugin_url, get_runtime
from ospy.options import options
from ospy.stations import stations
from ospy.inputs import inputs
from ospy.log import log, EVENT_FILE
from ospy.helpers import datetime_string, get_input, verify_csrf


NAME = 'Remote Notifications'
MENU =  _('Package: Remote Notifications')
LINK = 'settings_page'
HTTP_TIMEOUT = 10
ERROR_LOG_THROTTLE = 300

remote_options = PluginOptions(
    NAME,
    {
        'use': False,
        'rem_adr': 'your web server',
        'api': '123456789'
    }
)
runtime = get_runtime()
health_lock = Lock()
health_state = {
    'last_cycle': 0,
    'last_send': 0,
    'last_reply': '',
    'last_error': 0,
    'last_error_message': '',
}


################################################################################
# Main function loop:                                                          #
################################################################################
class RemoteSender(Thread):
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

    def try_send(self, text):
        log.clear(NAME)
        try:
            reply = send_data(text)  # send get data
            with health_lock:
                health_state['last_send'] = time.time()
                health_state['last_reply'] = reply[:200]
                health_state['last_error_message'] = ''
            log.info(NAME, _('Remote was sent') + ':\n' + mask_api(text))
        except Exception:
            self.log_problem(_('Remote was not sent') + '!')

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
        send_msg = False  # send get data if change (rain, end program ....
        last_rain = False 
        en_rain = True
        en_line = True
        en_line2 = True
    
        rain = 0          # rain status for rain=0 or rain=1 in get data
        lastrun = ""      # date and time for lastrun=xxxxx in get data
        tank = ""         # actual level cm in water tank
        percent = ""      # actual level % in water tank
        ping = ""         # actual level ping cm water level 
        volume=""         # actual level volume in m3 water level 
        duration = ""     # duration in last program for duration=xx:yy in get data
        station = ""      # name end station for station=abcde in get data
        humi = ""         # humidity in station for humi=xx in get data
        line = ""         # actual state from UPS plugin for line=0 or line=1 in get data
        temp1 = ""        # temperature 1 from air temp plugin DS18B20 
        temp2 = ""        # temperature 2 from air temp plugin DS18B20
        temp3 = ""        # temperature 3 from air temp plugin DS18B20
        temp4 = ""        # temperature 4 from air temp plugin DS18B20
        temp5 = ""        # temperature 5 from air temp plugin DS18B20
        temp6 = ""        # temperature 6 from air temp plugin DS18B20 
        tempDHT = ""      # temperature  from air temp plugin DHT probe
        humiDHT = ""      # humidity from air temp plugin DHT probe

        finished_count = len([run for run in log.finished_runs() if not run['blocked']]) 

        while not self._stop_event.is_set():
            try:
               
                # Send data if rain detected, power line state a new finished run is found
                if remote_options["use"]:   
                    normalize_options(remote_options)
                    ### water tank level ###
                    try:
                        from plugins import tank_monitor
                        tank = tank_monitor.get_all_values()[0]
                        percent = tank_monitor.get_all_values()[1]
                        ping = tank_monitor.get_all_values()[2]
                        volume = tank_monitor.get_all_values()[3]

                    except Exception:
                        tank = ""
                        percent = ""
                        ping = ""
                        volume = ""

                    ### power line state ###
                    try:
                       from plugins import ups_adj
                       lin = ups_adj.get_check_power() # read state power line from plugin
                       if lin==1: 
                          if en_line:  # send only if change 
                              send_msg = True 
                              en_line = False
                              en_line2 = True 
                          line = 0 # no power on web
                           
                       if lin==0:
                          if en_line2: # send only if change
                             send_msg = True
                             en_line2 = False
                             en_line = True
                          line = 1 # power ok on web

                    except Exception:
                       line = ""

                    ### rain state ###
                    if inputs.rain_sensed() and not last_rain:
                        send_msg = True
                        last_rain = inputs.rain_sensed()
                    if inputs.rain_sensed():
                        rain = 1
                        en_rain = True
                    else:
                        rain = 0 
                        if en_rain: # send data if no rain (only if change rain/norain...)
                           send_msg = True
                           en_rain = False

                    if not options.rain_sensor_enabled: # if rain sensor not used
                        rain = ""

                    ### program and station ###
                    finished = [run for run in log.finished_runs() if not run['blocked']]
                    if len(finished) > finished_count:
                        last_finished = finished[-1]
                        las = datetime_string()
                        lastrun = re.sub(" ", "_", las) # eliminate gap in the title to _
                        send_msg = True
                        ### humidity in station ###
                        try:
                            from plugins import humi_monitor
                            humi = int(humi_monitor.get_humidity((stations.get(last_finished['station']).index)+1)) # 0-7 to 1-8 humidity
                            if humi < 0:
                               humi = "" 

                        except Exception:
                            humi = ""

                        ### temperature ###
                        try:
                            from plugins import air_temp_humi
                            temp1   = air_temp_humi.DS18B20_read_probe(0)
                            temp2   = air_temp_humi.DS18B20_read_probe(1)
                            temp3   = air_temp_humi.DS18B20_read_probe(2)
                            temp4   = air_temp_humi.DS18B20_read_probe(3)
                            temp5   = air_temp_humi.DS18B20_read_probe(4)
                            temp6   = air_temp_humi.DS18B20_read_probe(5)
                            tempDHT = air_temp_humi.DHT_read_temp_value()
                            humiDHT = air_temp_humi.DHT_read_humi_value()
                        except Exception:
                            temp1 = ""
                            temp2 = ""
                            temp3 = ""
                            temp4 = ""
                            temp5 = ""
                            temp6 = ""
                            tempDHT = ""
                            humiDHT = ""
   
                        for run in finished[finished_count:]:
                            dur = (run['end'] - run['start']).total_seconds()
                            minutes, seconds = divmod(dur, 60)
                            sta = "%s" % stations.get(run['station']).name 
                            station = re.sub(" ", "_", sta)  # eliminate gap in the title to _
                            duration = "%02d:%02d" % (minutes, seconds)

                    finished_count = len(finished)

                if (send_msg): # if enabled send data
                    body =  ('tank=' + str(tank))
                    body += ('&percent=' + str(percent))
                    body += ('&ping=' + str(ping))
                    body += ('&volume=' + str(volume))
                    body += ('&rain=' + str(rain))
                    body += ('&humi=' + str(humi))
                    body += ('&line=' + str(line))
                    body += ('&lastrun=' + str(lastrun)) 
                    body += ('&station=' + sanity_msg(station))
                    body += ('&duration=' + str(duration))
                    body += ('&temp1=' + str(temp1))
                    body += ('&temp2=' + str(temp2))
                    body += ('&temp3=' + str(temp3))
                    body += ('&temp4=' + str(temp4))
                    body += ('&temp5=' + str(temp5))
                    body += ('&temp6=' + str(temp6))
                    body += ('&tempDHT=' + str(tempDHT))
                    body += ('&humiDHT=' + str(humiDHT))
                    body += ('&api=' + remote_options['api'])  # API password
                    log.clear(NAME)
                    log.info(NAME, _('Test data...'))
                    self.try_send(body)                        # Send GET data to remote server 
                    send_msg = False                           # Disable send data    
                    
                self._sleep(2)
                with health_lock:
                    health_state['last_cycle'] = time.time()

            except Exception:
                self.log_problem(_('Remote plug-in') + ':')
                self._sleep(60)


remote_sender = None


################################################################################
# Helper functions:                                                            #
################################################################################
def start():
    global remote_sender
    if remote_sender is None:
        remote_sender = RemoteSender()


def stop():
    global remote_sender
    if remote_sender is not None:
        remote_sender.stop()
        remote_sender.join(15)
        if remote_sender.is_alive():
            log.error(NAME, _('The plug-in worker did not stop within the timeout.'))
        else:
            remote_sender = None


def health():
    """Return remote notification state without exposing the API key."""
    with health_lock:
        state = dict(health_state)
    worker_running = remote_sender is not None and remote_sender.is_alive()
    details = {
        _('Worker thread'): _('Running') if worker_running else _('Stopped'),
        _('Remote notifications enabled'): _('Yes') if remote_options['use'] else _('No'),
        _('Remote server'): remote_options['rem_adr'] or _('Not configured'),
        _('API key configured'): _('Yes') if remote_options['api'] else _('No'),
        _('Last successful cycle'): (
            datetime_string(time.localtime(state['last_cycle']))
            if state['last_cycle'] else _('Not available')
        ),
        _('Last successful notification'): (
            datetime_string(time.localtime(state['last_send']))
            if state['last_send'] else _('Not available')
        ),
        _('Last server reply'): state['last_reply'] or _('Not available'),
    }
    if state['last_error_message']:
        details[_('Last error')] = state['last_error_message']
    if not worker_running:
        return {
            'status': 'error',
            'summary': _('Remote Notifications worker is not running.'),
            'details': details,
        }
    if not remote_options['use']:
        return {
            'status': 'unknown',
            'summary': _('Remote notifications are disabled.'),
            'details': details,
        }
    if state['last_error'] and state['last_error'] >= state['last_send']:
        return {
            'status': 'error',
            'summary': state['last_error_message'],
            'details': details,
        }
    if not state['last_send']:
        return {
            'status': 'unknown',
            'summary': _('Remote Notifications is waiting for a state change to send.'),
            'details': details,
        }
    return {
        'status': 'ok',
        'summary': _('Remote Notifications is responding.'),
        'details': details,
    }


def sanity_msg(msg):
     msg = re.sub(r"[^A-Za-z0-9-+]+", '_', msg)
     return msg


def normalize_options(values):
    values['rem_adr'] = (values.get('rem_adr') or '').strip().replace('\r', '').replace('\n', '')
    if values['rem_adr'] and not values['rem_adr'].endswith('/'):
        values['rem_adr'] += '/'
    values['api'] = (values.get('api') or '').strip().replace('\r', '').replace('\n', '')
    return values


def mask_api(text):
    api = remote_options.get('api')
    if api:
        return text.replace('api=' + api, 'api=********')
    return text


def safe_settings_json():
    data = dict(remote_options)
    if data.get('api'):
        data['api'] = '********'
    return data


def send_data(text):
    """Send GET data"""
    if remote_options['use'] != '' and remote_options['api'] != '' and remote_options['rem_adr'] != '':
        from urllib.request import urlopen

        url = remote_options['rem_adr'] + 'save.php/?' + text 
        with urlopen(url, timeout=HTTP_TIMEOUT) as data:
            reply = data.read().decode('utf-8')
        log.info(NAME, _('Remote server reply') + ':\n' + reply)
        return reply
    else:
        raise Exception(_('Remote plug-in is not properly configured') + '!')


################################################################################
# Web pages:                                                                   #
################################################################################
class settings_page(ProtectedPage):
    """Load an html page for entering remote adjustments."""

    def GET(self):
        try:
            return self.plugin_render.remote_notifications(remote_options, log.events(NAME))

        except:
            log.error(NAME, _('Remote plug-in') + ':\n' + traceback.format_exc())
            msg = _('An internal error was found in the system, see the error log for more information. The error is in part:') + ' '
            msg += _('remote_notifications -> settings_page GET')
            return self.core_render.notice('/', msg)

    def POST(self):
        try:
            qdict = web.input()
            verify_csrf(qdict)
            normalize_options(qdict)
            remote_options.web_update(qdict)
            test = get_input(qdict, 'test', False, lambda x: True)

            if remote_sender is not None:
                remote_sender.update()

                if test:
                    body  = ('tank=256')
                    body += ('&percent=100')
                    body += ('&ping=25')
                    body += ('&volume=10.2')
                    body += ('&rain=0')
                    body += ('&humi=25')
                    body += ('&line=1')
                    body += ('&lastrun=2019-09-06_08:00:00')
                    body += ('&station=test')
                    body += ('&duration=00:59')
                    body += ('&program=test_data')
                    body += ('&temp1=28.5')
                    body += ('&temp2=12')
                    body += ('&temp3=-51')
                    body += ('&temp4=23.5')
                    body += ('&temp5=45')
                    body += ('&temp6=-127')
                    body += ('&tempDHT=27')
                    body += ('&humiDHT=50')
                    body += ('&api=' + remote_options['api'])  # API password

                    remote_sender.try_send(body)

        except:
            log.error(NAME, _('Remote plug-in') + ':\n' + traceback.format_exc())
            msg = _('An internal error was found in the system, see the error log for more information. The error is in part:') + ' '
            msg += _('remote_notifications -> settings_page POST')
            return self.core_render.notice('/', msg)
        raise web.seeother(plugin_url(settings_page), True)


class help_page(ProtectedPage):
    """Load an html page for help page."""

    def GET(self):
        try:
            return self.plugin_render.remote_notifications_help()

        except:
            log.error(NAME, _('Remote plug-in') + ':\n' + traceback.format_exc())
            msg = _('An internal error was found in the system, see the error log for more information. The error is in part:') + ' '
            msg += _('remote_notifications -> help_page GET')
            return self.core_render.notice('/', msg)


class settings_json(ProtectedPage):
    """Returns plugin settings in JSON format."""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        try:
            return json.dumps(safe_settings_json())
        except:
            return {}
