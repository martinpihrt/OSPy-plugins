# -*- coding: utf-8 -*-
__author__ = u'Martin Pihrt'

import json
import time
import datetime
import traceback
import web

from blinker import signal

from ospy import helpers
from ospy.helpers import datetime_string, verify_csrf
from ospy.log import log, logEM
from threading import Thread, Lock
from plugins import PluginOptions, plugin_url, get_runtime
from ospy.webpages import ProtectedPage, showOnTimeline
from ospy.stations import stations
from ospy.options import options


NAME = 'Water Consumption Counter'  ### name for plugin in plugin manager ###
MENU =  _(u'Package: Water Consumption Counter')
LINK = 'settings_page'              ### link for page in plugin manager ###
ERROR_LOG_THROTTLE = 300
 
plugin_options = PluginOptions(
    NAME,
    { ### here is your plugin options ###
    'liter_per_sec_master_one': 0.45, # l/s  
    'liter_per_sec_master_two': 0.01, # l/s
    'last_reset': datetime_string(),  # last reset counter
    'sum_one': 0.00,                  # sum for master 1
    'sum_two': 0.00,                  # sum for master 2
    'sendeml': False,
    'emlsubject': _('Report from OSPy Water Consumption Counter plugin'),
    'eplug': 0,                       # email plugin type (email notifications or email notifications SSL)
    }
)

master_one_start = datetime.datetime.now() # start time for master 1
master_two_start = datetime.datetime.now() # start time for master 2
runtime = get_runtime()
health_lock = Lock()
health_state = {
    'last_master_event': 0,
    'last_email': 0,
    'last_error': 0,
    'last_error_message': '',
}

PLUGIN_VERSION = '1.1.1'

################################################################################
# Main function loop:                                                          #
################################################################################

class Sender(Thread):
    def __init__(self):
        Thread.__init__(self)
        self.daemon = True
        self._stop_event = runtime.stop_event
        self._sleep_time = 0
        self._last_error_log = 0
        self._timeline_entries = {}
        self._station_started = {}
        self._live_lock = Lock()
        self._live_stations = []
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

    def _log_problem(self, message):
        now = time.time()
        with health_lock:
            health_state['last_error'] = now
            health_state['last_error_message'] = str(message).splitlines()[-1]
        if now - self._last_error_log >= ERROR_LOG_THROTTLE:
            log.error(NAME, message)
            self._last_error_log = now

    def _timeline_entry(self, station_index):
        entry = self._timeline_entries.get(station_index)
        if entry is None:
            entry = showOnTimeline()
            entry.unit = station_index
            entry.val = ''
            self._timeline_entries[station_index] = entry
        return entry

    def _station_rate(self, station):
        """Return the configured flow applicable to a station."""
        rate_one = float(plugin_options['liter_per_sec_master_one'])
        rate_two = float(plugin_options['liter_per_sec_master_two'])
        if station.is_master:
            return rate_one
        if station.is_master_two:
            return rate_two
        if (station.activate_master and stations.master is not None and
                stations.get(stations.master).active):
            return rate_one
        if (station.activate_master_two and stations.master_two is not None and
                stations.get(stations.master_two).active):
            return rate_two
        if station.activate_master_by_program:
            master_one_active = (
                stations.master is not None and
                stations.get(stations.master).active
            )
            master_two_active = (
                stations.master_two is not None and
                stations.get(stations.master_two).active
            )
            if master_one_active and not master_two_active:
                return rate_one
            if master_two_active and not master_one_active:
                return rate_two
        return 0.0

    def _update_timeline(self):
        now = time.time()
        active_indexes = set()
        live_stations = []
        for station in stations.get():
            rate = self._station_rate(station)
            if not station.active or rate <= 0:
                continue
            active_indexes.add(station.index)
            started = self._station_started.setdefault(station.index, now)
            elapsed = max(0.0, now - started)
            liters = elapsed * rate
            if station.is_master:
                total = float(plugin_options['sum_one']) + liters
                value = 'Σ {:.2f} l'.format(total)
            elif station.is_master_two:
                total = float(plugin_options['sum_two']) + liters
                value = 'Σ {:.2f} l'.format(total)
            else:
                value = '{:.2f} l · {:.2f} l/s'.format(liters, rate)
            self._timeline_entry(station.index).val = value
            live_stations.append({
                'index': station.index,
                'name': station.name,
                'rate': round(rate, 2),
                'liters': round(liters, 2),
                'elapsed': int(elapsed),
                'master': bool(station.is_master or station.is_master_two),
            })

        for station_index, entry in list(self._timeline_entries.items()):
            if station_index not in active_indexes:
                entry.val = ''
                self._station_started.pop(station_index, None)
        with self._live_lock:
            self._live_stations = live_stations

    def live_stations(self):
        with self._live_lock:
            return [dict(item) for item in self._live_stations]

    def run(self):
        master_one_on = signal('master_one_on')
        master_one_off = signal('master_one_off')
        master_two_on = signal('master_two_on')
        master_two_off = signal('master_two_off')
        try:
            master_one_on.connect(notify_master_one_on)
            master_one_off.connect(notify_master_one_off)
            master_two_on.connect(notify_master_two_on)
            master_two_off.connect(notify_master_two_off)
            while not self._stop_event.wait(1):
                self._update_timeline()

        except Exception:
            log.clear(NAME)
            self._log_problem(_(u'Water Consumption Counter plug-in') + traceback.format_exc())
        finally:
            for entry in self._timeline_entries.values():
                entry.val = ''
            master_one_on.disconnect(notify_master_one_on)
            master_one_off.disconnect(notify_master_one_off)
            master_two_on.disconnect(notify_master_two_on)
            master_two_off.disconnect(notify_master_two_off)

sender = None

################################################################################
# Helper functions:                                                            #
################################################################################

### start ###
def start():
    global sender
    if sender is None:
        normalize_options()
        sender = Sender()
 
### stop ###
def stop():
    global sender
    if sender is not None:
        sender.stop()
        runtime.request_stop()
        sender.join(15)
        if not sender.is_alive():
            sender = None


### convert number to decimal ###
def to_decimal(number):
    try:
        import decimal
        return decimal.Decimal(float(number))

    except Exception:
        return decimal.Decimal('0.0')


def safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def normalize_options():
    plugin_options['liter_per_sec_master_one'] = max(0, float(to_decimal(plugin_options.get('liter_per_sec_master_one', 0.45))))
    plugin_options['liter_per_sec_master_two'] = max(0, float(to_decimal(plugin_options.get('liter_per_sec_master_two', 0.01))))
    plugin_options['sum_one'] = max(0, float(to_decimal(plugin_options.get('sum_one', 0))))
    plugin_options['sum_two'] = max(0, float(to_decimal(plugin_options.get('sum_two', 0))))
    plugin_options['eplug'] = 1 if safe_int(plugin_options.get('eplug', 0), 0) == 1 else 0
    plugin_options['emlsubject'] = str(plugin_options.get('emlsubject') or _('Report from OSPy Water Consumption Counter plugin')).strip()

### send email ###
def send_email(msg, msglog):
    normalize_options()
    message = datetime_string() + ': ' + msg
    Subject = plugin_options['emlsubject']
    try:
        email = None
        if plugin_options['eplug'] == 0: # email_notifications
            from plugins.email_notifications import email
        if plugin_options['eplug'] == 1: # email_notifications SSL
            from plugins.email_notifications_ssl import email
        if email is not None:        
            email(message, subject=Subject)
            with health_lock:
                health_state['last_email'] = time.time()
            if not options.run_logEM:
                log.info(NAME, _(u'Email logging is disabled in options...'))
            else:
                logEM.save_email_log(Subject, msglog, _('Sent'))
            log.info(NAME, _(u'Email was sent') + ': ' + msglog)

    except Exception:
        with health_lock:
            health_state['last_error'] = time.time()
            health_state['last_error_message'] = _('Email was not sent')
        if not options.run_logEM:
           log.info(NAME, _(u'Email logging is disabled in options...'))
        else:
           logEM.save_email_log(Subject, msglog, _('Email was not sent'))

        log.info(NAME, _(u'Email was not sent') + '! ' + traceback.format_exc())


### master one on ###
def notify_master_one_on(name, **kw):
    global master_one_start
    log.clear(NAME)
    log.info(NAME, datetime_string() + ': ' + _(u'Master station 1 running, please wait...'))
    master_one_start = datetime.datetime.now()
    with health_lock:
        health_state['last_master_event'] = time.time()

### master one off ###
def notify_master_one_off(name, **kw):
    normalize_options()
    log.info(NAME, datetime_string() + ': ' + _(u'Master station 1 stopped, counter finished...')) 
    master_one_stop  = datetime.datetime.now()
    master_one_time_delta  = (master_one_stop - master_one_start).total_seconds() # run time in seconds
    difference = to_decimal(master_one_time_delta) * to_decimal(plugin_options['liter_per_sec_master_one'])

    _sum = round(to_decimal(plugin_options['sum_one']), 2) + round(difference, 2)  # to 2 places
    plugin_options.__setitem__('sum_one', _sum)  
    with health_lock:
        health_state['last_master_event'] = time.time()

    msg = '<b>' + _(u'Water Consumption Counter plug-in') + '</b> ' + '<br><p style="color:green;">' + _(u'Water Consumption') + ' ' + str(round(difference,2)) + ' ' + _(u'liter') + '</p>'
    msglog = _(u'Water Consumption Counter plug-in') + ': ' + _(u'Water Consumption for master 1') + ': ' + str(round(difference,2)) + ' ' + _(u'liter')
    try:
        if plugin_options['sendeml']:
           send_email(msg, msglog)
    except Exception:
        log.error(NAME, _(u'Email was not sent') + '! '  + traceback.format_exc())

### master two on ###
def notify_master_two_on(name, **kw):
    global master_two_start
    log.clear(NAME)
    log.info(NAME, datetime_string() + ': ' + _(u'Master station 2 running, please wait...'))
    master_two_start = datetime.datetime.now()  
    with health_lock:
        health_state['last_master_event'] = time.time()

### master two off ###
def notify_master_two_off(name, **kw):
    normalize_options()
    log.info(NAME, datetime_string() + ': ' + _(u'Master station 2 stopped, counter finished...')) 
    master_two_stop  = datetime.datetime.now()
    master_two_time_delta  = (master_two_stop - master_two_start).total_seconds() 
    difference = to_decimal(master_two_time_delta) * to_decimal(plugin_options['liter_per_sec_master_two'])

    _sum = round(to_decimal(plugin_options['sum_two']), 2) + round(difference, 2)  # to 2 places
    plugin_options.__setitem__('sum_two', _sum)
    with health_lock:
        health_state['last_master_event'] = time.time()
  
    msg = '<b>' + _(u'Water Consumption Counter plug-in') + '</b> ' + '<br><p style="color:green;">' + _(u'Water Consumption') + ' ' + str(round(difference,2)) + ' ' + _(u'liter') + '</p>'
    msglog = _(u'Water Consumption Counter plug-in') + ': ' + _(u'Water Consumption for master 2') + ': ' + str(round(difference,2)) + ' ' + _(u'liter')
    try:
        if plugin_options['sendeml']:
            send_email(msg, msglog)
    except Exception:
        log.error(NAME, _('Email was not sent') + '! '  + traceback.format_exc())


### return all consum counter as summar ###
def get_all_values():
    return plugin_options['last_reset'], round(to_decimal(plugin_options['sum_one']), 2), round(to_decimal(plugin_options['sum_two']), 2)


def get_live_status():
    """Return display-only values for the settings overview."""
    normalize_options()
    now = datetime.datetime.now()
    master_one_active = (
        stations.master is not None and stations.get(stations.master).active
    )
    master_two_active = (
        stations.master_two is not None and
        stations.get(stations.master_two).active
    )
    current_one = 0.0
    current_two = 0.0
    if master_one_active:
        current_one = max(
            0.0, (now - master_one_start).total_seconds()
        ) * float(plugin_options['liter_per_sec_master_one'])
    if master_two_active:
        current_two = max(
            0.0, (now - master_two_start).total_seconds()
        ) * float(plugin_options['liter_per_sec_master_two'])
    live_stations = sender.live_stations() if sender is not None else []
    return {
        'version': PLUGIN_VERSION,
        'master_one': {
            'active': master_one_active,
            'rate': plugin_options['liter_per_sec_master_one'],
            'current': round(current_one, 2),
            'total': round(float(plugin_options['sum_one']) + current_one, 2),
        },
        'master_two': {
            'active': master_two_active,
            'rate': plugin_options['liter_per_sec_master_two'],
            'current': round(current_two, 2),
            'total': round(float(plugin_options['sum_two']) + current_two, 2),
        },
        'stations': [item for item in live_stations if not item['master']],
    }


################################################################################
# Web pages:                                                                   #
################################################################################

class settings_page(ProtectedPage):
    """Load an html page for entering adjustments."""

    def GET(self):
        global sender, status

        normalize_options()
        qdict = web.input()
        reset = helpers.get_input(qdict, 'reset', False, lambda x: True)
        if sender is not None and reset:
            verify_csrf(qdict)
            plugin_options.__setitem__('sum_one', 0)
            plugin_options.__setitem__('sum_two', 0)
            plugin_options.__setitem__('last_reset', datetime_string())

            log.clear(NAME)
            log.info(NAME, datetime_string() + ': ' + _(u'Counter has reseted'))
            raise web.seeother(plugin_url(settings_page), True)

        return self.plugin_render.water_consumption_counter(
            plugin_options, log.events(NAME), get_live_status()
        )

    def POST(self):
        qdict = web.input()
        verify_csrf(qdict)
        plugin_options.web_update(qdict) ### update options from web ###
        normalize_options()

        if sender is not None:
            sender.update()
        raise web.seeother(plugin_url(settings_page), True)


class help_page(ProtectedPage):
    """Load an html page for help page."""

    def GET(self):
        return self.plugin_render.water_consumption_counter_help()
        

class settings_json(ProtectedPage):            ### return plugin_options as JSON data ###
    """Returns plugin settings in JSON format."""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        return json.dumps(plugin_options)


def health():
    """Return a compact status for the OSPy diagnostics page."""
    worker_alive = sender is not None and sender.is_alive()
    with health_lock:
        state = dict(health_state)
    details = {
        'worker': _('Running') if worker_alive else _('Stopped'),
        'master_one_liters': float(to_decimal(plugin_options.get('sum_one', 0))),
        'master_two_liters': float(to_decimal(plugin_options.get('sum_two', 0))),
        'last_reset': plugin_options.get('last_reset', ''),
        'email_enabled': bool(plugin_options.get('sendeml', False)),
        'last_master_event': state['last_master_event'],
        'last_email': state['last_email'],
        'last_error': state['last_error'],
    }
    if state['last_error_message']:
        details['error'] = state['last_error_message']
    if not worker_alive:
        status = 'error'
        summary = _('Water consumption counter is not monitoring master stations.')
    elif state['last_error'] and state['last_error'] > state['last_master_event']:
        status = 'warning'
        summary = _('Water consumption counter reported an error.')
    else:
        status = 'ok'
        summary = _('Water consumption counter is monitoring master stations.')
    return {'status': status, 'summary': summary, 'details': details}
