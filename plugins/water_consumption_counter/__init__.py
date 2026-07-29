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
from queue import Queue, Empty
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
master_checkpoint = {1: None, 2: None}
last_master_run = {1: 0.0, 2: 0.0}
runtime = get_runtime()
health_lock = Lock()
counter_lock = Lock()
health_state = {
    'last_master_event': 0,
    'last_email': 0,
    'last_error': 0,
    'last_error_message': '',
}

COUNTER_CHECKPOINT_INTERVAL = 10

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
        self._master_events = Queue()
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
                total = _master_live_values(
                    1, datetime.datetime.fromtimestamp(now)
                )['total']
                value = 'Σ {}'.format(format_volume(total))
            elif station.is_master_two:
                total = _master_live_values(
                    2, datetime.datetime.fromtimestamp(now)
                )['total']
                value = 'Σ {}'.format(format_volume(total))
            else:
                value = '+ {}'.format(format_volume(liters))
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

    def queue_master_event(self, master_number, active, occurred=None):
        self._master_events.put((
            int(master_number),
            bool(active),
            occurred if isinstance(occurred, datetime.datetime)
            else datetime.datetime.now(),
        ))

    def _drain_master_events(self):
        while True:
            try:
                master_number, active, occurred = \
                    self._master_events.get_nowait()
            except Empty:
                return
            try:
                if master_number == 1:
                    if active:
                        _handle_master_one_on(occurred)
                    else:
                        _handle_master_one_off(occurred)
                elif master_number == 2:
                    if active:
                        _handle_master_two_on(occurred)
                    else:
                        _handle_master_two_off(occurred)
            except Exception:
                self._log_problem(
                    _(u'Water Consumption Counter plug-in') + ':\n' +
                    traceback.format_exc()
                )

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
            next_timeline = 0
            next_checkpoint = 0
            _initialize_active_masters()
            while not self._stop_event.wait(0.2):
                self._drain_master_events()
                current = time.time()
                if current >= next_timeline:
                    self._update_timeline()
                    next_timeline = current + 1
                if current >= next_checkpoint:
                    _checkpoint_active_masters()
                    next_checkpoint = current + COUNTER_CHECKPOINT_INTERVAL

        except Exception:
            log.clear(NAME)
            self._log_problem(_(u'Water Consumption Counter plug-in') + traceback.format_exc())
        finally:
            try:
                self._drain_master_events()
                _checkpoint_active_masters(force=True)
            except Exception:
                self._log_problem(
                    _(u'Water Consumption Counter plug-in') + ':\n' +
                    traceback.format_exc()
                )
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


def format_volume(liters):
    """Format liters for compact Home and e-mail presentation."""
    try:
        liters = max(0.0, float(liters))
    except (TypeError, ValueError):
        liters = 0.0
    if liters >= 1000.0:
        return '{:.2f} m³'.format(liters / 1000.0)
    return '{:.2f} l'.format(liters)


def _master_number_for_run(station, control_master=None):
    """Resolve which virtual master meter applies to a station run."""
    if station.is_master or station.activate_master:
        return 1
    if station.is_master_two or station.activate_master_two:
        return 2
    if station.activate_master_by_program:
        selected = safe_int(control_master, 0)
        if selected in (1, 2):
            return selected
        master_one_active = (
            stations.master is not None and
            stations.get(stations.master).active
        )
        master_two_active = (
            stations.master_two is not None and
            stations.get(stations.master_two).active
        )
        if master_one_active != master_two_active:
            return 1 if master_one_active else 2
    return None


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


def _handle_master_one_on(occurred):
    global master_one_start
    log.clear(NAME)
    log.info(NAME, datetime_string() + ': ' + _(u'Master station 1 running, please wait...'))
    with counter_lock:
        master_one_start = occurred
        master_checkpoint[1] = occurred
        last_master_run[1] = 0.0
    with health_lock:
        health_state['last_master_event'] = time.time()


def _handle_master_one_off(occurred):
    global last_master_run
    normalize_options()
    log.info(NAME, datetime_string() + ': ' + _(u'Master station 1 stopped, counter finished...')) 
    _checkpoint_master(1, occurred, force=True)
    with counter_lock:
        master_one_time_delta = max(
            0.0, (occurred - master_one_start).total_seconds()
        )
        difference = (
            to_decimal(master_one_time_delta) *
            to_decimal(plugin_options['liter_per_sec_master_one'])
        )
        last_master_run[1] = float(difference)
        master_checkpoint[1] = None
    with health_lock:
        health_state['last_master_event'] = time.time()

    msg = '<b>' + _(u'Water Consumption Counter plug-in') + '</b> ' + '<br><p style="color:green;">' + _(u'Water Consumption') + ' ' + str(round(difference,2)) + ' ' + _(u'liter') + '</p>'
    msglog = _(u'Water Consumption Counter plug-in') + ': ' + _(u'Water Consumption for master 1') + ': ' + str(round(difference,2)) + ' ' + _(u'liter')
    try:
        if plugin_options['sendeml']:
           send_email(msg, msglog)
    except Exception:
        log.error(NAME, _(u'Email was not sent') + '! '  + traceback.format_exc())

def _handle_master_two_on(occurred):
    global master_two_start
    log.clear(NAME)
    log.info(NAME, datetime_string() + ': ' + _(u'Master station 2 running, please wait...'))
    with counter_lock:
        master_two_start = occurred
        master_checkpoint[2] = occurred
        last_master_run[2] = 0.0
    with health_lock:
        health_state['last_master_event'] = time.time()


def _handle_master_two_off(occurred):
    global last_master_run
    normalize_options()
    log.info(NAME, datetime_string() + ': ' + _(u'Master station 2 stopped, counter finished...')) 
    _checkpoint_master(2, occurred, force=True)
    with counter_lock:
        master_two_time_delta = max(
            0.0, (occurred - master_two_start).total_seconds()
        )
        difference = (
            to_decimal(master_two_time_delta) *
            to_decimal(plugin_options['liter_per_sec_master_two'])
        )
        last_master_run[2] = float(difference)
        master_checkpoint[2] = None
    with health_lock:
        health_state['last_master_event'] = time.time()
  
    msg = '<b>' + _(u'Water Consumption Counter plug-in') + '</b> ' + '<br><p style="color:green;">' + _(u'Water Consumption') + ' ' + str(round(difference,2)) + ' ' + _(u'liter') + '</p>'
    msglog = _(u'Water Consumption Counter plug-in') + ': ' + _(u'Water Consumption for master 2') + ': ' + str(round(difference,2)) + ' ' + _(u'liter')
    try:
        if plugin_options['sendeml']:
            send_email(msg, msglog)
    except Exception:
        log.error(NAME, _('Email was not sent') + '! '  + traceback.format_exc())


### Master callbacks only enqueue work.  They run synchronously in the OSPy
### scheduler thread, so persistence or SMTP must never happen here.
def notify_master_one_on(name, **kw):
    if sender is not None:
        sender.queue_master_event(1, True, kw.get('occurred_at'))


def notify_master_one_off(name, **kw):
    if sender is not None:
        sender.queue_master_event(1, False, kw.get('occurred_at'))


def notify_master_two_on(name, **kw):
    if sender is not None:
        sender.queue_master_event(2, True, kw.get('occurred_at'))


def notify_master_two_off(name, **kw):
    if sender is not None:
        sender.queue_master_event(2, False, kw.get('occurred_at'))


def _master_is_active(master_number):
    index = stations.master if master_number == 1 else stations.master_two
    return index is not None and stations.get(index).active


def _initialize_active_masters():
    """Start a recoverable checkpoint if the plug-in starts during irrigation."""
    now = datetime.datetime.now()
    if _master_is_active(1):
        _handle_master_one_on(now)
    if _master_is_active(2):
        _handle_master_two_on(now)


def _checkpoint_master(master_number, occurred=None, force=False):
    """Persist the unaccounted part of one active master run."""
    occurred = occurred or datetime.datetime.now()
    key = 'sum_one' if master_number == 1 else 'sum_two'
    rate_key = (
        'liter_per_sec_master_one'
        if master_number == 1 else 'liter_per_sec_master_two'
    )
    with counter_lock:
        checkpoint = master_checkpoint.get(master_number)
        if checkpoint is None:
            return 0.0
        elapsed = max(0.0, (occurred - checkpoint).total_seconds())
        if elapsed <= 0:
            return 0.0
        if not force and elapsed < COUNTER_CHECKPOINT_INTERVAL:
            return 0.0
        increment = elapsed * float(plugin_options[rate_key])
        plugin_options[key] = float(plugin_options[key]) + increment
        master_checkpoint[master_number] = occurred
        return increment


def _checkpoint_active_masters(force=False):
    now = datetime.datetime.now()
    for master_number in (1, 2):
        if _master_is_active(master_number):
            _checkpoint_master(master_number, now, force=force)


def _master_live_values(master_number, now):
    key = 'sum_one' if master_number == 1 else 'sum_two'
    rate_key = (
        'liter_per_sec_master_one'
        if master_number == 1 else 'liter_per_sec_master_two'
    )
    start = master_one_start if master_number == 1 else master_two_start
    with counter_lock:
        checkpoint = master_checkpoint.get(master_number)
        active = _master_is_active(master_number)
        rate = float(plugin_options[rate_key])
        persisted = float(plugin_options[key])
        current = (
            max(0.0, (now - start).total_seconds()) * rate
            if active else 0.0
        )
        pending = (
            max(0.0, (now - checkpoint).total_seconds()) * rate
            if active and checkpoint is not None else 0.0
        )
    return {
        'active': active,
        'rate': rate,
        'current': round(current, 2),
        'total': round(persisted + pending, 2),
    }


def _reset_counters():
    global master_one_start, master_two_start
    reset_time = datetime.datetime.now()
    master_one_active = _master_is_active(1)
    master_two_active = _master_is_active(2)
    with counter_lock:
        plugin_options['sum_one'] = 0
        plugin_options['sum_two'] = 0
        plugin_options['last_reset'] = datetime_string()
        if master_one_active:
            master_checkpoint[1] = reset_time
            master_one_start = reset_time
        if master_two_active:
            master_checkpoint[2] = reset_time
            master_two_start = reset_time


### return all consum counter as summar ###
def get_all_values():
    return plugin_options['last_reset'], round(to_decimal(plugin_options['sum_one']), 2), round(to_decimal(plugin_options['sum_two']), 2)


def get_run_report(station_index, duration_seconds, control_master=None):
    """Return virtual-meter values for one completed station run.

    The function is intentionally read-only so notification plug-ins can use it
    without changing or resetting either master counter.
    """
    normalize_options()
    try:
        station = stations.get(int(station_index))
    except (IndexError, TypeError, ValueError):
        return None
    master_number = _master_number_for_run(station, control_master)
    if master_number not in (1, 2):
        return None

    duration = max(0.0, float(duration_seconds or 0))
    live_status = get_live_status()
    master_key = 'master_one' if master_number == 1 else 'master_two'
    master_label = _('Master Station') if master_number == 1 else _('Second Master Station')
    rate = float(plugin_options[
        'liter_per_sec_master_one' if master_number == 1 else
        'liter_per_sec_master_two'
    ])
    station_run_liters = duration * rate
    if live_status[master_key]['active']:
        master_run_liters = float(live_status[master_key]['current'])
    else:
        master_run_liters = float(last_master_run[master_number])
    total_liters = float(live_status[master_key]['total'])

    # A completed-run e-mail can be assembled just before the master OFF
    # receiver stores its final value (or after a plug-in restart that missed
    # the corresponding ON event). Use the station-duration estimate as a
    # display-only fallback instead of reporting a misleading 0.00 l. Neither
    # persistent master counter is modified here.
    if master_run_liters <= 0.0 and station_run_liters > 0.0:
        master_run_liters = station_run_liters
        total_liters += station_run_liters
    return {
        'master': master_number,
        'master_name': master_label,
        'master_run_liters': round(master_run_liters, 2),
        'master_run_display': format_volume(master_run_liters),
        'master_total_liters': round(total_liters, 2),
        'master_total_display': format_volume(total_liters),
        'station': station.index,
        'station_name': station.name,
        'station_run_liters': round(station_run_liters, 2),
        'station_run_display': format_volume(station_run_liters),
    }


def get_live_status():
    """Return display-only values for the settings overview."""
    normalize_options()
    now = datetime.datetime.now()
    live_stations = sender.live_stations() if sender is not None else []
    return {
        'master_one': _master_live_values(1, now),
        'master_two': _master_live_values(2, now),
        'stations': [item for item in live_stations if not item['master']],
    }


def mobile_status():
    """Return the counter health without changing stored totals."""
    result = health()
    return {
        'status': result.get('status', 'unknown'),
        'title': _('Water Consumption Counter'),
        'summary': result.get('summary', ''),
        'updated': datetime_string(),
    }


def mobile_cards():
    """Return master totals and incremental station consumption."""
    live = get_live_status()
    metrics = []
    for master in (live.get('master_one'), live.get('master_two')):
        if not master:
            continue
        metrics.extend([
            {
                'label': '{} - {}'.format(
                    master.get('master_name', _('Master station')),
                    _('Current consumption')),
                'value': master.get('master_run_liters', 0),
                'unit': 'l',
            },
            {
                'label': '{} - {}'.format(
                    master.get('master_name', _('Master station')),
                    _('Total consumption')),
                'value': master.get('master_total_liters', 0),
                'unit': 'l',
            },
        ])
    station_metrics = [{
        'label': item.get('station_name', ''),
        'value': item.get('station_run_liters', 0),
        'unit': 'l',
    } for item in live.get('stations', [])]
    cards = [{
        'id': 'masters',
        'title': _('Master station consumption'),
        'metrics': metrics,
        'series': [],
    }]
    if station_metrics:
        cards.append({
            'id': 'stations',
            'title': _('Running station consumption'),
            'metrics': station_metrics,
            'series': [],
        })
    return cards


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
            _reset_counters()

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


class live_json(ProtectedPage):
    """Return current counters for the settings page without a full reload."""

    def GET(self):
        web.header('Content-Type', 'application/json')
        return json.dumps(get_live_status())


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
