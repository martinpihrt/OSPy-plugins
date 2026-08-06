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
from .methods import (
    ETO_FAO56,
    MULTI_DAY,
    ZIMMERMAN,
    calculate_eto,
    calculate_multi_day,
    calculate_zimmerman,
    humidity_percent,
    normalize_method,
)


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
        'calculation_method': MULTI_DAY,
        'wl_min': 0,
        'wl_max': 200,
        'base_mm_per_day': 4.0,
        'days_history': 3,
        'days_forecast': 3,
        'zimmerman_reference_temp_c': 21.1,
        'zimmerman_reference_humidity': 30.0,
        'eto_days': 3,
        'eto_crop_coefficient': 1.0,
        'eto_irrigation_efficiency': 100.0,
        'eto_effective_rain': 100.0,
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
    'method': plugin_options['calculation_method'],
    'method_label': _(u'Multi-day weather balance'),
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
    'stale': False,
    'data_missing': False,
}
successful_details = {}
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


def _method_label(method):
    if method == ZIMMERMAN:
        return _(u'Zimmerman method')
    if method == ETO_FAO56:
        return _(u'FAO-56 ETo method')
    return _(u'Multi-day weather balance')


def _local_temperature(temp_c):
    if temp_c is None:
        return None
    return temp_c if options.temp_unit == 'C' else 32.0 + 9.0 / 5.0 * temp_c


def _weather_day(offset, include_eto=False):
    check_date = datetime.date.today() + datetime.timedelta(days=offset)
    hourly_data = weather.get_hourly_data(check_date) or []
    rain_mm = weather.get_rain(check_date)
    result = {
        'offset': offset,
        'date': check_date.strftime('%Y-%m-%d'),
        'hourly': hourly_data,
        'rain_mm': rain_mm,
    }
    if include_eto and hourly_data:
        try:
            result['eto'] = weather.get_eto(check_date)
        except (KeyError, TypeError, ValueError, ZeroDivisionError):
            result['eto'] = None
    return result


def _multi_day_rows(days):
    rows = []
    for day in days:
        hourly_data = day['hourly']
        avg_temp_c = _mean([val['temperature'] for val in hourly_data])
        avg_wind_ms = _mean([val['windSpeed'] for val in hourly_data])
        avg_humidity = _mean([humidity_percent(val['humidity']) for val in hourly_data])
        rows.append({
            'offset': day['offset'],
            'label': _day_name(day['offset']),
            'type': _day_type(day['offset']),
            'date': day['date'],
            'hours': len(hourly_data),
            'rain_mm': round(day['rain_mm'], 1),
            'temp': round(_local_temperature(avg_temp_c), 1) if avg_temp_c is not None else None,
            'wind_ms': round(avg_wind_ms, 1) if avg_wind_ms is not None else None,
            'humidity': round(avg_humidity, 1) if avg_humidity is not None else None,
            'used': bool(hourly_data),
            'note': _day_note(
                hourly_data, day['rain_mm'], avg_temp_c, avg_wind_ms, avg_humidity),
        })
    return rows


def _calculate_weather_adjustment(method):
    minimum = plugin_options['wl_min']
    maximum = plugin_options['wl_max']
    if method == ZIMMERMAN:
        yesterday = _weather_day(-1)
        today = _weather_day(0)
        result = calculate_zimmerman(
            yesterday,
            today,
            plugin_options['zimmerman_reference_temp_c'],
            plugin_options['zimmerman_reference_humidity'],
            minimum,
            maximum,
        )
        result['rows'] = [{
            'date': yesterday['date'],
            'temperature': round(_local_temperature(result['average_temperature_c']), 1),
            'humidity': round(result['average_humidity'], 1),
            'rain_yesterday': result['rain_yesterday'],
            'rain_today': result['rain_today'],
            'temperature_factor': result['temperature_factor'],
            'humidity_factor': result['humidity_factor'],
            'rain_factor': result['rain_factor'],
        }]
        result['days_history'] = 1
        result['days_forecast'] = 0
        return result

    if method == ETO_FAO56:
        eto_days = [
            _weather_day(offset, include_eto=True)
            for offset in range(-plugin_options['eto_days'], 0)
        ]
        today = _weather_day(0)
        result = calculate_eto(
            eto_days,
            today['rain_mm'],
            plugin_options['eto_crop_coefficient'],
            plugin_options['base_mm_per_day'],
            plugin_options['eto_irrigation_efficiency'],
            plugin_options['eto_effective_rain'],
            minimum,
            maximum,
        )
        result['days_history'] = plugin_options['eto_days']
        result['days_forecast'] = 0
        result['today_rain'] = round(today['rain_mm'], 2)
        return result

    days = [
        _weather_day(offset)
        for offset in range(-plugin_options['days_history'], plugin_options['days_forecast'] + 1)
    ]
    result = calculate_multi_day(
        days,
        plugin_options['base_mm_per_day'],
        minimum,
        maximum,
    )
    result['rows'] = _multi_day_rows(days)
    result['days_history'] = plugin_options['days_history']
    result['days_forecast'] = plugin_options['days_forecast']
    return result


def _empty_detail(method, message, stale=False):
    return {
        'calculated_at': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'enabled': bool(plugin_options['enabled']),
        'method': method,
        'method_label': _method_label(method),
        'message': message,
        'days_used': 0,
        'days_history': plugin_options['days_history'] if method == MULTI_DAY else 0,
        'days_forecast': plugin_options['days_forecast'] if method == MULTI_DAY else 0,
        'rain_mm': 0.0,
        'water_needed': 0.0,
        'water_left': 0.0,
        'water_adjustment': None,
        'raw_water_adjustment': None,
        'limited_by_min': False,
        'limited_by_max': False,
        'rows': [],
        'stale': stale,
        'data_missing': False,
    }


def _missing_data_message(error):
    code = str(error)
    if code == 'missing_yesterday_weather_data':
        return _(u'Yesterday weather data required by the Zimmerman method is unavailable.')
    if code == 'missing_eto_data':
        return _(u'No complete historical ETo data is available for the selected period.')
    if code == 'invalid_irrigation_efficiency':
        return _(u'Irrigation efficiency must be greater than zero.')
    return _(u'No usable weather information is available yet.')


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

                    method = plugin_options['calculation_method']
                    try:
                        result = _calculate_weather_adjustment(method)
                    except ValueError as error:
                        msg = _missing_data_message(error)
                        previous = successful_details.get(method)
                        if previous:
                            last_detail = dict(previous)
                            last_detail.update({
                                'calculated_at': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                                'message': msg + ' ' + _(u'The last successful result from the same method remains active.'),
                                'stale': True,
                                'data_missing': True,
                            })
                            level_adjustments[NAME] = previous['water_adjustment'] / 100.0
                        else:
                            last_detail = _empty_detail(method, msg)
                            last_detail['water_adjustment'] = 100.0
                            last_detail['raw_water_adjustment'] = 100.0
                            last_detail['data_missing'] = True
                            level_adjustments[NAME] = 1.0
                        log.info(NAME, msg)
                        update_footer(datetime.datetime.now().strftime('%d.%m. %H:%M') + ' ' + _(u'No weather data'))
                        self._sleep(WEATHER_CALC_INTERVAL)
                        continue

                    result.update({
                        'calculated_at': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        'enabled': True,
                        'method': method,
                        'method_label': _method_label(method),
                        'message': _(u'Calculation finished successfully.'),
                        'stale': False,
                        'data_missing': False,
                    })
                    last_detail = result
                    successful_details[method] = dict(result)
                    water_adjustment = result['water_adjustment']
                    log.info(NAME, _(u'Calculation method') + ': ' + _method_label(method))
                    log.info(NAME, _(u'Using') + ' %d ' % result['days_used'] + _(u'days of information.'))
                    log.info(NAME, _(u'Total rainfall') + ': %.1fmm' % result['rain_mm'])
                    log.info(NAME, u'_______________________________')
                    log.info(NAME, _(u'Irrigation needed') + ': %.1fmm' % result['water_left'])
                    log.info(NAME, _(u'Weather Adjustment') + ': %.1f%%' % water_adjustment)
                    with health_lock:
                        health_state['last_success'] = time.time()
                        health_state['last_error_message'] = ''
                    update_footer(
                        datetime.datetime.now().strftime('%d.%m. %H:%M')
                        + ' ' + _method_label(method) + ', %.0f%%' % water_adjustment)
                    level_adjustments[NAME] = water_adjustment / 100.0

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
                    last_detail = _empty_detail(
                        plugin_options['calculation_method'], _(u'Plug-in is disabled.'))
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
    plugin_options['calculation_method'] = normalize_method(
        plugin_options.get('calculation_method', MULTI_DAY))
    plugin_options['wl_min'] = max(0, min(200, safe_int(plugin_options.get('wl_min', 0), 0)))
    plugin_options['wl_max'] = max(plugin_options['wl_min'], min(200, safe_int(plugin_options.get('wl_max', 200), 200)))
    plugin_options['base_mm_per_day'] = max(0.1, min(50.0, safe_float(plugin_options.get('base_mm_per_day', 4.0), 4.0)))
    plugin_options['days_history'] = max(0, min(14, safe_int(plugin_options.get('days_history', 3), 3)))
    plugin_options['days_forecast'] = max(0, min(14, safe_int(plugin_options.get('days_forecast', 3), 3)))
    plugin_options['zimmerman_reference_temp_c'] = max(-30.0, min(60.0, safe_float(
        plugin_options.get('zimmerman_reference_temp_c', 21.1), 21.1)))
    plugin_options['zimmerman_reference_humidity'] = max(0.0, min(100.0, safe_float(
        plugin_options.get('zimmerman_reference_humidity', 30.0), 30.0)))
    plugin_options['eto_days'] = max(1, min(7, safe_int(plugin_options.get('eto_days', 3), 3)))
    plugin_options['eto_crop_coefficient'] = max(0.1, min(2.0, safe_float(
        plugin_options.get('eto_crop_coefficient', 1.0), 1.0)))
    plugin_options['eto_irrigation_efficiency'] = max(1.0, min(100.0, safe_float(
        plugin_options.get('eto_irrigation_efficiency', 100.0), 100.0)))
    plugin_options['eto_effective_rain'] = max(0.0, min(100.0, safe_float(
        plugin_options.get('eto_effective_rain', 100.0), 100.0)))
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
        global last_detail
        old_method = plugin_options.get('calculation_method', MULTI_DAY)
        qdict = web.input(**plugin_options)
        verify_csrf(qdict)
        plugin_options.web_update(qdict)
        normalize_options()
        if old_method != plugin_options['calculation_method']:
            last_detail = _empty_detail(
                plugin_options['calculation_method'],
                _(u'Waiting for the first calculation with the selected method.'))
            if NAME in level_adjustments:
                del level_adjustments[NAME]
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
        'method': _method_label(plugin_options.get('calculation_method', MULTI_DAY)),
        'days_used': last_detail.get('days_used', 0),
        'rain_mm': last_detail.get('rain_mm', 0),
        'water_needed_mm': last_detail.get('water_needed', 0),
        'water_adjustment_percent': last_detail.get('water_adjustment'),
        'active_adjustment': adjustment,
        'freeze_protection': bool(plugin_options.get('protect_enabled', False)),
        'last_calculation': last_detail.get('calculated_at'),
        'last_success': state['last_success'],
        'last_error': state['last_error'],
        'stale': bool(last_detail.get('stale', False)),
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
    elif last_detail.get('stale'):
        status = 'warning'
        summary = _('The last successful weather adjustment is temporarily being retained.')
    elif last_detail.get('data_missing'):
        status = 'warning'
        summary = _('The selected weather calculation method has no usable data.')
    elif state['last_error'] and state['last_error'] > state['last_success']:
        status = 'warning'
        summary = _('Weather-based water level reported an error.')
    else:
        status = 'ok'
        summary = _('Weather-based water level is active.')
    return {'status': status, 'summary': summary, 'details': details}


def mobile_status():
    result = health()
    return {
        'status': result.get('status', 'unknown'),
        'title': _('Weather-based Water Level'),
        'summary': result.get('summary', ''),
        'updated': last_detail.get('calculated_at') or '',
    }


def mobile_cards(**_kwargs):
    """Expose the latest calculation inputs and result without settings controls."""
    detail = dict(last_detail)
    metrics = [
        {'id': 'method', 'label': _('Calculation method'),
         'value': detail.get('method_label') or _method_label(detail.get('method')), 'unit': ''},
        {'id': 'calculated_at', 'label': _('Calculated at'),
         'value': detail.get('calculated_at') or _('Not available'), 'unit': ''},
        {'id': 'days_used', 'label': _('Used days'), 'value': detail.get('days_used', 0), 'unit': ''},
        {'id': 'rain', 'label': _('Total rainfall'), 'value': detail.get('rain_mm', 0), 'unit': 'mm'},
        {'id': 'water_needed', 'label': _('Irrigation needed'),
         'value': detail.get('water_needed', 0), 'unit': 'mm'},
        {'id': 'water_left', 'label': _('Remaining irrigation need'),
         'value': detail.get('water_left', 0), 'unit': 'mm'},
        {'id': 'adjustment', 'label': _('Weather Adjustment'),
         'value': detail.get('water_adjustment') if detail.get('water_adjustment') is not None else _('Not available'),
         'unit': '%' if detail.get('water_adjustment') is not None else ''},
    ]
    optional_metrics = (
        ('raw_water_adjustment', _('Unrestricted weather adjustment'), '%'),
        ('average_temperature_c', _('Average temperature'), '°C'),
        ('average_humidity', _('Average humidity'), '%'),
        ('rain_yesterday', _('Yesterday rainfall'), 'mm'),
        ('rain_today', _('Today rainfall'), 'mm'),
        ('total_eto', _('Total ETo'), 'mm'),
        ('total_etc', _('Crop evapotranspiration'), 'mm'),
        ('effective_rain_mm', _('Effective rainfall'), 'mm'),
        ('net_irrigation_mm', _('Net irrigation'), 'mm'),
        ('gross_irrigation_mm', _('Gross irrigation'), 'mm'),
    )
    for key, label, unit in optional_metrics:
        if detail.get(key) is not None:
            metrics.append({'id': key, 'label': label, 'value': detail.get(key), 'unit': unit})
    if detail.get('limited_by_min'):
        metrics.append({'id': 'limit', 'label': _('Limit'), 'value': _('Minimum limit applied'), 'unit': ''})
    elif detail.get('limited_by_max'):
        metrics.append({'id': 'limit', 'label': _('Limit'), 'value': _('Maximum limit applied'), 'unit': ''})
    rows = []
    for index, row in enumerate(detail.get('rows') or []):
        row_metrics = []
        for key, label, unit in (
                ('rain_mm', _('Rain'), 'mm'), ('temp', _('Temperature'), '°{}'.format(options.temp_unit)),
                ('temperature', _('Temperature'), '°{}'.format(options.temp_unit)),
                ('humidity', _('Humidity'), '%'), ('wind_ms', _('Wind speed'), 'm/s'),
                ('eto', _('ETo'), 'mm'), ('etc', _('Crop evapotranspiration'), 'mm'),
                ('rain_yesterday', _('Yesterday rainfall'), 'mm'),
                ('rain_today', _('Today rainfall'), 'mm'),
                ('temperature_factor', _('Temperature factor'), '%'),
                ('humidity_factor', _('Humidity factor'), '%'),
                ('rain_factor', _('Rain factor'), '%')):
            if row.get(key) is not None:
                row_metrics.append({'id': key, 'label': label, 'value': row.get(key), 'unit': unit})
        if row.get('note'):
            row_metrics.append({'id': 'note', 'label': _('Influence'), 'value': row['note'], 'unit': ''})
        rows.append({'id': 'day_{}'.format(index),
                     'title': '{} {}'.format(row.get('label', ''), row.get('date', '')).strip(),
                     'metrics': row_metrics})
    return [{'id': 'calculation', 'title': _('Weather calculation'),
             'metrics': metrics}] + rows
