# -*- coding: utf-8 -*-
__author__ = u'Rimco'  
# Martin Pihrt add i18n language support

import datetime
from threading import Thread, Lock
import traceback
import json
import time

import web
from ospy.log import log
from ospy.options import options
from ospy.options import level_adjustments
from ospy.webpages import ProtectedPage, showInFooter, clear_plugin_runtime_data
from ospy.runonce import run_once
from ospy.stations import stations
from ospy.weather import weather
from plugins import PluginOptions, plugin_url, get_runtime
from ospy.helpers import verify_csrf


NAME = 'Weather-based Water Level'
MENU =  _(u'Package: Weather-based Water Level')
LINK = 'settings_page'
WEATHER_CALC_INTERVAL = 3600
WEATHER_ERROR_RETRY_INTERVAL = 900
WEATHER_ERROR_LOG_THROTTLE = 900

plugin_options = PluginOptions(
    NAME,
    {
        'enabled': False,
        'wl_min': 0,
        'wl_max': 200,
        'days_history': 3,
        'days_forecast': 3,
        'protect_enabled': False,
        'protect_temp': 2.0 if options.temp_unit == "C" else 35.6,
        'protect_minutes': 10,
        'protect_stations': [],
        'protect_months': [],
        'use_footer': False,
    })

last_detail = {
    'calculated_at': None,
    'enabled': False,
    'message': _(u'No calculation has been run yet.'),
    'days_used': 0,
    'days_history': plugin_options['days_history'],
    'days_forecast': plugin_options['days_forecast'],
    'rain_mm': 0.0,
    'water_needed': 0.0,
    'water_left': 0.0,
    'water_adjustment': None,
    'raw_water_adjustment': None,
    'limited_by_min': False,
    'limited_by_max': False,
    'rows': [],
}
runtime = get_runtime()
health_lock = Lock()
health_state = {
    'last_success': 0,
    'last_error': 0,
    'last_error_message': '',
}


def _day_name(offset):
    if offset == -1:
        return _(u'Yesterday')
    if offset == 0:
        return _(u'Today')
    if offset == 1:
        return _(u'Tomorrow')
    if offset < 0:
        return _(u'History')
    return _(u'Forecast')


def _day_type(offset):
    if offset < 0:
        return _(u'History')
    if offset == 0:
        return _(u'Today')
    return _(u'Forecast')


def _mean(values):
    return sum(values) / len(values) if values else None


def _day_note(hourly_data, rain_mm, avg_temp_c, avg_wind_ms, avg_humidity):
    if not hourly_data:
        return _(u'No usable weather data for this day.')

    notes = []
    if rain_mm > 0:
        notes.append(_(u'rain lowers irrigation need'))
    if avg_temp_c is not None and avg_temp_c > 25:
        notes.append(_(u'high temperature raises irrigation need'))
    elif avg_temp_c is not None and avg_temp_c < 10:
        notes.append(_(u'low temperature lowers irrigation need'))
    if avg_wind_ms is not None and avg_wind_ms > 5:
        notes.append(_(u'wind raises irrigation need'))
    if avg_humidity is not None and avg_humidity > 70:
        notes.append(_(u'humidity lowers irrigation need'))
    elif avg_humidity is not None and avg_humidity < 40:
        notes.append(_(u'dry air raises irrigation need'))

    return ', '.join(notes) if notes else _(u'normal weather influence')


################################################################################
# Main function loop:                                                          #
################################################################################
class WeatherLevelChecker(Thread):
    def __init__(self):
        Thread.__init__(self)
        self.daemon = True
        self._stop_event = runtime.stop_event

        self._sleep_time = 0
        self._force_update = True
        self._last_calculation = 0
        self._last_error_log = 0
        self.start()
        runtime.register_thread(self)

    def stop(self):
        self._stop_event.set()

    def update(self):
        self._force_update = True
        self._sleep_time = 0

    def weather_update(self):
        self._sleep_time = 0

    def _sleep(self, secs):
        self._sleep_time = secs
        while self._sleep_time > 0 and not self._stop_event.is_set():
            time.sleep(1)
            self._sleep_time -= 1

    def run(self):
        weather_mon = None
        global last_detail

        def update_footer(message):
            nonlocal weather_mon
            if plugin_options['use_footer']:
                if weather_mon is None:
                    weather_mon = showInFooter()
                    weather_mon.label = _(u'Water Level')
                    weather_mon.button = "weather_based_water_level/settings"
                weather_mon.val = message.encode('utf8').decode('utf8')
            else:
                clear_plugin_runtime_data('weather_based_water_level')
                weather_mon = None

        weather.add_callback(self.weather_update)
        self._sleep(10)  # Wait for weather callback before starting
        disabled_logged = False
        while not self._stop_event.is_set():
            try:
                normalize_options()
                if plugin_options['enabled']:
                    disabled_logged = False
                    now = time.time()
                    if not self._force_update and self._last_calculation and now - self._last_calculation < WEATHER_CALC_INTERVAL:
                        self._sleep(min(WEATHER_CALC_INTERVAL - (now - self._last_calculation), WEATHER_CALC_INTERVAL))
                        continue

                    self._force_update = False
                    self._last_calculation = now
                    log.clear(NAME)
                    log.debug(NAME,  _(u'Checking weather status') + '...')

                    info = []
                    rows = []
                    days = 0
                    total_info = {'rain_mm': 0.0}
                    for day in range(-plugin_options['days_history'], plugin_options['days_forecast']+1):
                        check_date = datetime.date.today() + datetime.timedelta(days=day)
                        hourly_data = weather.get_hourly_data(check_date) or []
                        rain_mm = weather.get_rain(check_date)
                        if hourly_data:
                            days += 1
                        info += hourly_data

                        total_info['rain_mm'] += rain_mm

                        avg_temp_c = _mean([val['temperature'] for val in hourly_data])
                        avg_wind_ms = _mean([val['windSpeed'] for val in hourly_data])
                        avg_humidity = _mean([val['humidity'] for val in hourly_data])
                        avg_temp = None
                        if avg_temp_c is not None:
                            avg_temp = avg_temp_c if options.temp_unit == "C" else 32.0 + 9.0 / 5.0 * avg_temp_c
                        rows.append({
                            'offset': day,
                            'label': _day_name(day),
                            'type': _day_type(day),
                            'date': check_date.strftime('%Y-%m-%d'),
                            'hours': len(hourly_data),
                            'rain_mm': round(rain_mm, 1),
                            'temp': round(avg_temp, 1) if avg_temp is not None else None,
                            'wind_ms': round(avg_wind_ms, 1) if avg_wind_ms is not None else None,
                            'humidity': round(avg_humidity, 1) if avg_humidity is not None else None,
                            'used': bool(hourly_data),
                            'note': _day_note(hourly_data, rain_mm, avg_temp_c, avg_wind_ms, avg_humidity),
                        })

                    log.info(NAME, _(u'Using') + ' %d ' % days + _(u'days of information.'))

                    if not info or days < 1:
                        if NAME in level_adjustments:
                            del level_adjustments[NAME]
                        msg = _(u'No usable weather information is available yet.')
                        log.info(NAME, msg)
                        log.info(NAME, _(u'Water level adjustment was not changed.'))
                        last_detail = {
                            'calculated_at': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                            'enabled': True,
                            'message': msg,
                            'days_used': days,
                            'days_history': plugin_options['days_history'],
                            'days_forecast': plugin_options['days_forecast'],
                            'rain_mm': round(total_info['rain_mm'], 1),
                            'water_needed': 0.0,
                            'water_left': 0.0,
                            'water_adjustment': None,
                            'raw_water_adjustment': None,
                            'limited_by_min': False,
                            'limited_by_max': False,
                            'rows': rows,
                        }
                        update_footer(datetime.datetime.now().strftime('%d.%m. %H:%M') + ' ' + _(u'No weather data'))
                        self._sleep(WEATHER_CALC_INTERVAL)
                        continue

                    total_info.update({
                        'temp_c': sum([val['temperature'] for val in info]) / len(info),
                        'wind_ms': sum([val['windSpeed'] for val in info]) / len(info),
                        'humidity': sum([val['humidity'] for val in info]) / len(info)
                    })                    

                    # We assume that the default 100% provides 4mm water per day (normal need)
                    # We calculate what we will need to provide using the mean data of X days around today

                    water_needed = 4 * days                                     # 4mm per day
                    water_needed *= 1 + (total_info['temp_c'] - 20) / 15        # 5 => 0%, 35 => 200%
                    water_needed *= 1 + (total_info['wind_ms'] / 100)           # 0 => 100%, 20 => 120%
                    water_needed *= 1 - (total_info['humidity'] - 50) / 200     # 0 => 125%, 100 => 75%
                    water_needed = round(water_needed, 1)

                    water_left = water_needed - total_info['rain_mm']
                    water_left = round(max(0, min(100, water_left)), 1)

                    raw_water_adjustment = round((water_left / (4 * days)) * 100, 1)

                    water_adjustment = float(
                        max(plugin_options['wl_min'], min(plugin_options['wl_max'], raw_water_adjustment)))

                    log.info(NAME, _(u'Water needed') + ' %d ' % days + _('days') + ': %.1fmm' % water_needed)
                    log.info(NAME, _(u'Total rainfall') + ': %.1fmm' % total_info['rain_mm'])
                    log.info(NAME, u'_______________________________')
                    log.info(NAME, _(u'Irrigation needed') +  ': %.1fmm' % water_left)
                    log.info(NAME, _(u'Weather Adjustment') + ': %.1f%%' % water_adjustment)
                    last_detail = {
                        'calculated_at': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        'enabled': True,
                        'message': _(u'Calculation finished successfully.'),
                        'days_used': days,
                        'days_history': plugin_options['days_history'],
                        'days_forecast': plugin_options['days_forecast'],
                        'rain_mm': round(total_info['rain_mm'], 1),
                        'water_needed': water_needed,
                        'water_left': water_left,
                        'water_adjustment': water_adjustment,
                        'raw_water_adjustment': raw_water_adjustment,
                        'limited_by_min': raw_water_adjustment < plugin_options['wl_min'],
                        'limited_by_max': raw_water_adjustment > plugin_options['wl_max'],
                        'rows': rows,
                    }
                    with health_lock:
                        health_state['last_success'] = time.time()
                    update_footer(datetime.datetime.now().strftime('%d.%m. %H:%M') + ' ' + _(u'Missing') + ' %.1fmm, %.0f%%' % (water_left, water_adjustment))

                    level_adjustments[NAME] = water_adjustment / 100

                    if plugin_options['protect_enabled']:
                        current_data = weather.get_current_data() or {}
                        if 'temperature' in current_data:
                            temp_local_unit = current_data['temperature'] if options.temp_unit == "C" else 32.0 + 9.0 / 5.0 * current_data['temperature']
                            log.debug(NAME, _(u'Temperature') + ': %.1f %s' % (temp_local_unit, options.temp_unit))
                            month = time.localtime().tm_mon  # Current month.
                            if temp_local_unit < plugin_options['protect_temp'] and month in plugin_options['protect_months']:
                                station_seconds = {}
                                for station in stations.enabled_stations():
                                    if station.index in plugin_options['protect_stations']:
                                        station_seconds[station.index] = plugin_options['protect_minutes'] * 60
                                    else:
                                        station_seconds[station.index] = 0

                                for station in stations.enabled_stations():
                                    if run_once.is_active(datetime.datetime.now(), station.index):
                                        break
                                else:
                                    log.debug(NAME, _(u'Protection activated.'))
                                    run_once.set(station_seconds)
                        else:
                            log_weather_problem(_(u'Protection skipped because current weather temperature is not available.'))

                    self._sleep(WEATHER_CALC_INTERVAL)

                else:
                    if self._force_update or not disabled_logged:
                        self._force_update = False
                        disabled_logged = True
                        log.clear(NAME)
                        log.info(NAME, _(u'Plug-in is disabled.'))
                        update_footer(datetime.datetime.now().strftime('%d.%m. %H:%M') + ' ' + _(u'Plug-in is disabled.'))
                    if NAME in level_adjustments:
                        del level_adjustments[NAME]
                    last_detail = {
                        'calculated_at': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        'enabled': False,
                        'message': _(u'Plug-in is disabled.'),
                        'days_used': 0,
                        'days_history': plugin_options['days_history'],
                        'days_forecast': plugin_options['days_forecast'],
                        'rain_mm': 0.0,
                        'water_needed': 0.0,
                        'water_left': 0.0,
                        'water_adjustment': None,
                        'raw_water_adjustment': None,
                        'limited_by_min': False,
                        'limited_by_max': False,
                        'rows': [],
                    }
                    self._sleep(24*3600)

            except Exception:
                log_weather_problem(_(u'Weather-based water level plug-in') + ': ' + traceback.format_exc().splitlines()[-1])
                self._last_calculation = time.time() - WEATHER_CALC_INTERVAL + WEATHER_ERROR_RETRY_INTERVAL
                self._sleep(WEATHER_ERROR_RETRY_INTERVAL)
        weather.remove_callback(self.weather_update)


checker = None


################################################################################
# Helper functions:                                                            #
################################################################################

def start():
    global checker
    if checker is None:
        checker = WeatherLevelChecker()


def stop():
    global checker
    if checker is not None:
        checker.stop()
        runtime.request_stop()
        checker.join(15)
        if not checker.is_alive():
            checker = None
    if NAME in level_adjustments:
        del level_adjustments[NAME]
    clear_plugin_runtime_data('weather_based_water_level')


def log_weather_problem(message):
    now = time.time()
    with health_lock:
        health_state['last_error'] = now
        health_state['last_error_message'] = str(message).splitlines()[-1]
    if checker is None or now - checker._last_error_log >= WEATHER_ERROR_LOG_THROTTLE:
        if checker is not None:
            checker._last_error_log = now
        log.error(NAME, message)


def safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def normalize_options():
    plugin_options['wl_min'] = max(0, min(200, safe_int(plugin_options.get('wl_min', 0), 0)))
    plugin_options['wl_max'] = max(plugin_options['wl_min'], min(200, safe_int(plugin_options.get('wl_max', 200), 200)))
    plugin_options['days_history'] = max(0, min(14, safe_int(plugin_options.get('days_history', 3), 3)))
    plugin_options['days_forecast'] = max(0, min(14, safe_int(plugin_options.get('days_forecast', 3), 3)))
    plugin_options['protect_temp'] = safe_float(plugin_options.get('protect_temp', 2.0), 2.0)
    plugin_options['protect_minutes'] = max(1, min(240, safe_int(plugin_options.get('protect_minutes', 10), 10)))
    plugin_options['protect_stations'] = [safe_int(station, -1) for station in plugin_options.get('protect_stations', []) if safe_int(station, -1) >= 0]
    plugin_options['protect_months'] = [safe_int(month, -1) for month in plugin_options.get('protect_months', []) if 1 <= safe_int(month, -1) <= 12]


################################################################################
# Web pages:                                                                   #
################################################################################
class settings_page(ProtectedPage):
    """Load an html page for entering weather-based irrigation adjustments"""

    def GET(self):
        normalize_options()
        return self.plugin_render.weather_based_water_level(plugin_options, log.events(NAME))

    def POST(self):
        qdict = web.input(**plugin_options)
        verify_csrf(qdict)
        plugin_options.web_update(qdict)
        normalize_options()
        if checker is not None:
            checker.update()
        raise web.seeother(plugin_url(settings_page), True)


class help_page(ProtectedPage):
    """Load an html page for help page."""

    def GET(self):
        return self.plugin_render.weather_based_water_level_help()        


class details_page(ProtectedPage):
    """Load an html page with the last weather calculation details."""

    def GET(self):
        return self.plugin_render.weather_based_water_level_details(last_detail)

    def POST(self):
        qdict = web.input()
        verify_csrf(qdict)
        if checker is not None:
            checker.update()
        raise web.seeother(plugin_url(details_page), True)


class settings_json(ProtectedPage):
    """Returns plugin settings in JSON format"""

    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        return json.dumps(plugin_options)


def health():
    """Return a compact status for the OSPy diagnostics page."""
    worker_alive = checker is not None and checker.is_alive()
    with health_lock:
        state = dict(health_state)
    adjustment = level_adjustments.get(NAME)
    details = {
        'worker': _('Running') if worker_alive else _('Stopped'),
        'enabled': bool(plugin_options.get('enabled', False)),
        'days_used': last_detail.get('days_used', 0),
        'rain_mm': last_detail.get('rain_mm', 0),
        'water_needed_mm': last_detail.get('water_needed', 0),
        'water_adjustment_percent': last_detail.get('water_adjustment'),
        'active_adjustment': adjustment,
        'freeze_protection': bool(plugin_options.get('protect_enabled', False)),
        'last_calculation': last_detail.get('calculated_at'),
        'last_success': state['last_success'],
        'last_error': state['last_error'],
    }
    if state['last_error_message']:
        details['error'] = state['last_error_message']
    if not worker_alive:
        status = 'error'
        summary = _('Weather-based water level worker is not running.')
    elif not plugin_options.get('enabled', False):
        status = 'unknown'
        summary = _('Weather-based water level is disabled.')
    elif last_detail.get('water_adjustment') is None:
        status = 'warning'
        summary = _('No usable weather calculation is available.')
    elif state['last_error'] and state['last_error'] > state['last_success']:
        status = 'warning'
        summary = _('Weather-based water level reported an error.')
    else:
        status = 'ok'
        summary = _('Weather-based water level is active.')
    return {'status': status, 'summary': summary, 'details': details}
