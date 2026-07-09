# -*- coding: utf-8 -*-
__author__ = u'Martin Pihrt'

import json
import time
import datetime
import traceback
from threading import Thread, Event

import web
import plugins as plugin_manager

from ospy.log import log
from plugins import PluginOptions, plugin_url
from ospy.webpages import ProtectedPage
from ospy.helpers import datetime_string, verify_csrf
from ospy.stations import stations

from ospy.webpages import showInFooter # Enable plugin to display readings in UI footer


NAME = 'Temperature Switch'
MENU =  _(u'Package: Temperature Switch')
LINK = 'settings_page'
ERROR_LOG_THROTTLE = 300
PROBE_REFRESH_INTERVAL = 10
OWN_RUN_NAMES = (
    _('Temperature Switch A'),
    _('Temperature Switch B'),
    _('Temperature Switch C'),
)


plugin_options = PluginOptions(
    NAME,
    {'enabled_a': False,   # enable or disable regulation A
     'enabled_b': False,   # enable or disable regulation B
     'enabled_c': False,   # enable or disable regulation C
     'probe_A_on': 0,      # for selector temperature probe A ON (0-5)
     'probe_B_on': 0,      # for selector temperature probe B ON (0-5)
     'probe_C_on': 0,      # for selector temperature probe C ON (0-5)
     'probe_A_off': 0,     # for selector temperature probe A OFF (0-5)
     'probe_B_off': 0,     # for selector temperature probe B OFF (0-5)
     'probe_C_off': 0,     # for selector temperature probe C OFF (0-5)
     'temp_a_on': 30,      # temperature for output A ON
     'temp_b_on': 40,      # temperature for output B ON
     'temp_c_on': 50,      # temperature for output C ON
     'temp_a_off': 25,     # temperature for output A OFF
     'temp_b_off': 35,     # temperature for output B OFF
     'temp_c_off': 45,     # temperature for output C OFF
     'control_output_A': 0,# selector for output A (0 to station count)
     'control_output_B': 1,# selector for output B (0 to station count)
     'control_output_C': 2,# selector for output C (0 to station count)
     'ds_name_0': '',      # name for DS probe 1 from air temp humi plugin
     'ds_name_1': '',      # name for DS probe 2 from air temp humi plugin
     'ds_name_2': '',      # name for DS probe 3 from air temp humi plugin
     'ds_name_3': '',      # name for DS probe 4 from air temp humi plugin
     'ds_name_4': '',      # name for DS probe 5 from air temp humi plugin
     'ds_name_5': '',      # name for DS probe 6 from air temp humi plugin
     'ds_count': 0,        # DS probe count from air temp humi plugin
     'reg_mm_a': 60,       # min for maximal runtime A
     'reg_ss_a': 0,        # sec for maximal runtime A
     'reg_mm_b': 60,       # min for maximal runtime B
     'reg_ss_b': 0,        # sec for maximal runtime B
     'reg_mm_c': 60,       # min for maximal runtime C
     'reg_ss_c': 0,        # sec for maximal runtime C
     'use_footer': True    # show data from plugin in footer on home page
     }
)

def plugin_is_running(module):
    try:
        return module in plugin_manager.running()
    except Exception:
        return False


################################################################################
# Main function loop:                                                          #
################################################################################


class Sender(Thread):
    
    def __init__(self):
        Thread.__init__(self)
        self.daemon = True
        self._stop_event = Event()

        self._sleep_time = 0
        self._last_error_log = 0
        self._last_air_error_log = 0
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

    def _log_problem(self, message):
        now = time.time()
        if now - self._last_error_log >= ERROR_LOG_THROTTLE:
            log.error(NAME, message)
            self._last_error_log = now

    def _log_air_problem(self, message):
        now = time.time()
        if now - self._last_air_error_log >= ERROR_LOG_THROTTLE:
            log.error(NAME, message)
            self._last_air_error_log = now

    def _own_active_run(self, sid):
        for interval in log.active_runs():
            if interval.get('station') == sid and interval.get('program_name') in OWN_RUN_NAMES:
                return interval
        return None

    def _finish_own_runs(self, sid):
        for interval in list(log.active_runs()):
            if interval.get('station') == sid and interval.get('program_name') in OWN_RUN_NAMES:
                log.finish_run(interval)

    def _station_has_other_run(self, sid):
        for interval in log.active_runs():
            if interval.get('station') == sid and interval.get('program_name') not in OWN_RUN_NAMES:
                return True
        return False

    def _read_temperatures(self):
        if not plugin_is_running('air_temp_humi'):
            raise RuntimeError(_(u'The plug-in is not running.'))

        from plugins.air_temp_humi import plugin_options as air_temp_data
        from plugins.air_temp_humi import DS18B20_read_probe

        for index in range(6):
            plugin_options['ds_name_{}'.format(index)] = air_temp_data.get('label_ds{}'.format(index), '')
        plugin_options['ds_count'] = clamp_int(air_temp_data.get('ds_used', 0), 0, 6)
        return [DS18B20_read_probe(index) for index in range(6)]

    def _start_output(self, station, minutes, seconds, program_name):
        sid = station.index
        if self._own_active_run(sid) is not None:
            return

        start = datetime.datetime.now()
        end = start + datetime.timedelta(seconds=seconds, minutes=minutes)
        new_schedule = {
            'active': True,
            'program': -1,
            'station': sid,
            'program_name': program_name,
            'fixed': True,
            'cut_off': 0,
            'manual': True,
            'blocked': False,
            'start': start,
            'original_start': start,
            'end': end,
            'uid': '%s-%s-%d' % (str(start), "Manual", sid),
            'usage': stations.get(sid).usage
        }

        log.start_run(new_schedule)
        stations.activate(new_schedule['station'])

    def _stop_output(self, station):
        sid = station.index
        self._finish_own_runs(sid)
        if not self._station_has_other_run(sid):
            stations.deactivate(sid)

    def run(self):
        temperature_ds = [-127,-127,-127,-127,-127,-127]
        msg_a_on = True
        msg_a_off = True
        msg_b_on = True
        msg_b_off = True
        msg_c_on = True
        msg_c_off = True

        temp_sw = None

        if plugin_options['use_footer']:
            temp_sw = showInFooter() #  instantiate class to enable data in footer
            temp_sw.button = "temperature_switch/settings"   # button redirect on footer
            temp_sw.label =  _(u'Temperature Switch')        # label on footer

        millis = int(round(time.time() * 1000))          # timer for clearing status on the web pages after 60 sec
        last_millis = millis

        a_state = -1                                     # for state in footer (-1 disable regulation A, 0 = Aoff, 1 = Aon)
        b_state = -1
        c_state = -1

        helper_text = ''
        next_probe_refresh = 0

        while not self._stop_event.is_set():
            try:
                normalize_options()

                if time.time() >= next_probe_refresh:
                    try:
                        temperature_ds = self._read_temperatures()
                    except Exception:
                        self._log_air_problem(_(u'Unable to load settings from Air Temperature and Humidity Monitor plugin! Is the plugin Air Temperature and Humidity Monitor installed and set up?'))
                        plugin_options['ds_count'] = 0
                        next_probe_refresh = time.time() + 60
                    else:
                        next_probe_refresh = time.time() + PROBE_REFRESH_INTERVAL

                # regulation A
                if plugin_options['enabled_a']:  
                    ds_a_on = temperature_ds[plugin_options['probe_A_on']]
                    ds_a_off = temperature_ds[plugin_options['probe_A_off']]
                    station_a = stations.get(plugin_options['control_output_A'])

                    if ds_a_on > plugin_options['temp_a_on']:    # if DSxx > temperature AON
                        a_state = 1
                        if msg_a_on:
                            msg_a_on = False
                            msg_a_off = True
                            log.info(NAME, datetime_string() + ' ' + u'%s' % station_a.name + ' ' + _(u'was turned on.'))
                            self._start_output(station_a, plugin_options['reg_mm_a'], plugin_options['reg_ss_a'], _('Temperature Switch A'))

                    if ds_a_off < plugin_options['temp_a_off']:  # if DSxx < temperature AOFF
                        a_state = 0
                        if msg_a_off:
                            msg_a_off = False
                            msg_a_on = True
                            log.info(NAME, datetime_string() + ' ' + u'%s' % station_a.name + ' ' + _(u'was turned off.'))
                            self._stop_output(station_a)
 
                else:
                    a_state = -1    

                # regulation B
                if plugin_options['enabled_b']:  
                    ds_b_on = temperature_ds[plugin_options['probe_B_on']]
                    ds_b_off = temperature_ds[plugin_options['probe_B_off']]
                    station_b = stations.get(plugin_options['control_output_B'])
                    if ds_b_on > plugin_options['temp_b_on']:    # if DSxx > temperature BON
                        b_state = 1
                        if msg_b_on:
                            msg_b_on = False
                            msg_b_off = True
                            log.info(NAME, datetime_string() + ' ' + u'%s' % station_b.name + ' ' + _(u'was turned on.'))
                            self._start_output(station_b, plugin_options['reg_mm_b'], plugin_options['reg_ss_b'], _('Temperature Switch B'))

                    if ds_b_off < plugin_options['temp_b_off']:  # if DSxx < temperature BOFF
                        b_state = 0
                        if msg_b_off:
                            msg_b_off = False
                            msg_b_on = True
                            log.info(NAME, datetime_string() + ' ' + u'%s' % station_b.name + ' ' + _(u'was turned off.'))
                            self._stop_output(station_b)
  
                else:
                    b_state = -1

                # regulation C    
                if plugin_options['enabled_c']:  
                    ds_c_on = temperature_ds[plugin_options['probe_C_on']]
                    ds_c_off = temperature_ds[plugin_options['probe_C_off']]
                    station_c = stations.get(plugin_options['control_output_C'])

                    if ds_c_on > plugin_options['temp_c_on']:    # if DSxx > temperature CON
                        c_state = 1
                        if msg_c_on:
                            msg_c_on = False
                            msg_c_off = True
                            log.info(NAME, datetime_string() + ' ' + u'%s' % station_c.name + ' ' + _(u'was turned on.'))
                            self._start_output(station_c, plugin_options['reg_mm_c'], plugin_options['reg_ss_c'], _('Temperature Switch C'))

                    if ds_c_off < plugin_options['temp_c_off']:  # if DSxx < temperature COFF
                        c_state = 0
                        if msg_c_off:
                            msg_c_off = False
                            msg_c_on = True
                            log.info(NAME, datetime_string() + ' ' + u'%s' % station_c.name + ' ' + _(u'was turned off.')) 
                            self._stop_output(station_c)
 
                else:
                    c_state = -1

                # footer text
                tempText = ' '

                if a_state == 0:
                    tempText += _(u'Regulation A set OFF') + '. '  
                if a_state == 1:
                    tempText += _(u'Regulation A set ON') + '. '     
                if b_state == 0:
                    tempText += ' ' + _(u'Regulation B set OFF') + '. '
                if b_state == 1:
                    tempText += ' ' + _(u'Regulation B set ON') + '. '   
                if c_state == 0:
                    tempText += ' ' + _(u'Regulation C set OFF') + '. ' 
                if c_state == 1:
                    tempText += ' ' + _(u'Regulation C set ON') + '. '    
                if (a_state == -1) and (b_state == -1) and (c_state == -1):
                    tempText = _(u'No change') + '. '

                if plugin_options['use_footer']:
                    if temp_sw is not None:
                        if tempText != helper_text:
                            temp_sw.val = tempText.encode('utf8').decode('utf8')    # value on footer
                            helper_text = tempText

                self._sleep(2)

                millis = int(round(time.time() * 1000))
                if (millis - last_millis) > 60000:    # 60 second to clearing status on the webpage
                    last_millis = millis
                    log.clear(NAME)
 
            except Exception:
                self._log_problem(_(u'Temperature Switch plug-in') + ':\n' + traceback.format_exc())
                self._sleep(60)
          
sender = None

################################################################################
# Helper functions:                                                            #
################################################################################
def start():
    global sender
    if sender is None:
        sender = Sender()
       

def stop():
    global sender
    if sender is not None:
        sender.stop()
        sender.join(15)
        sender = None


def clamp_int(value, minimum, maximum):
    try:
        value = int(value)
    except (TypeError, ValueError):
        value = minimum
    return max(minimum, min(maximum, value))


def clamp_float(value, minimum, maximum):
    try:
        value = float(value)
    except (TypeError, ValueError):
        value = minimum
    return max(minimum, min(maximum, value))


def normalize_options(values=None):
    opts = values if values is not None else plugin_options
    station_count = max(1, len(stations.get()))
    ds_count = clamp_int(plugin_options.get('ds_count', 0), 0, 6)
    max_probe = max(0, ds_count - 1)

    for key in ('probe_A_on', 'probe_B_on', 'probe_C_on', 'probe_A_off', 'probe_B_off', 'probe_C_off'):
        opts[key] = clamp_int(opts.get(key, 0), 0, max_probe)
    for key in ('control_output_A', 'control_output_B', 'control_output_C'):
        opts[key] = clamp_int(opts.get(key, 0), 0, station_count - 1)
    for key in ('temp_a_on', 'temp_b_on', 'temp_c_on', 'temp_a_off', 'temp_b_off', 'temp_c_off'):
        opts[key] = clamp_float(opts.get(key, 0), -100, 100)
    for key in ('reg_mm_a', 'reg_mm_b', 'reg_mm_c'):
        opts[key] = clamp_int(opts.get(key, 0), 0, 999)
    for key in ('reg_ss_a', 'reg_ss_b', 'reg_ss_c'):
        opts[key] = clamp_int(opts.get(key, 0), 0, 59)
    return opts


################################################################################
# Web pages:                                                                   #
################################################################################

class settings_page(ProtectedPage):
    """Load an html page for entering adjustments and deleting logs"""

    def GET(self):
        return self.plugin_render.temperature_switch(plugin_options, log.events(NAME))

    def POST(self):
        qdict = web.input()
        verify_csrf(qdict)
        normalize_options(qdict)
        plugin_options.web_update(qdict)

        if sender is not None:
            sender.update()                
        raise web.seeother(plugin_url(settings_page), True)


class help_page(ProtectedPage):
    """Load an html page for help page."""

    def GET(self):
        return self.plugin_render.temperature_switch_help()         


class settings_json(ProtectedPage):
    """Returns plugin settings in JSON format."""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        return json.dumps(plugin_options)
