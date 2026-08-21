# -*- coding: utf-8 -*-
"""Multi-meter electricity monitoring for local Shelly EM devices."""

import csv
import datetime
import io
import json
import time
import traceback
import uuid
from threading import Lock, Thread

import requests
import web

from ospy.helpers import verify_csrf
from ospy.log import log
from ospy.webpages import ProtectedPage, clear_plugin_runtime_data, showInFooter
from plugins import PluginOptions, get_runtime, plugin_data_dir, plugin_url

from .model import make_interval, normalized_reading, period_bounds, price_interval, selected_day_bounds, solar_summary, tariff_at
from .sources import IntegratorMeterDisabled, IntegratorMeterError, IntegratorMeterOffline, IntegratorMeterUnavailable, IntegratorReadingPending, read_direct, read_integrator
from .storage import JsonStore


NAME = 'Energy Meter'
MENU = _('Package: Energy Meter')
LINK = 'overview_page'
SQL_TABLE = 'energy_meter_history'
runtime = get_runtime()
lock = Lock()
options = PluginOptions(NAME, {'enabled': False, 'use_footer': True, 'sample_interval': 60, 'max_records': 200000, 'storage': 'local', 'currency': 'CZK', 'default_import_price': 0.0, 'default_export_price': 0.0, 'meters_json': '[]', 'tariffs_json': '[]'})
_store_cache = None
_store_cache_key = None


def safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def safe_float(value, default=0.0):
    try:
        return float(str(value).replace(',', '.'))
    except (TypeError, ValueError):
        return default


def parse_json_option(name, default):
    try:
        value = json.loads(options.get(name, ''))
        return value if isinstance(value, type(default)) else default
    except (TypeError, ValueError):
        return default


def meters():
    result = []
    for index, meter in enumerate(parse_json_option('meters_json', [])):
        if not isinstance(meter, dict):
            continue
        item = dict(meter)
        item['id'] = str(item.get('id') or uuid.uuid4().hex)
        item['label'] = str(item.get('label') or _('Meter {}').format(index + 1))
        item['role'] = item.get('role') if item.get('role') in ('grid', 'production', 'load', 'auxiliary') else 'grid'
        item['source'] = 'integrator' if item.get('source') == 'integrator' else 'direct'
        item['enabled'] = bool(item.get('enabled', True))
        item['role_label'] = role_label(item['role'])
        item['source_label'] = source_label(item['source'])
        result.append(item)
    return result


def role_label(role):
    return {'grid': _('Grid connection'), 'production': _('Solar production'), 'load': _('Load / consumption'), 'auxiliary': _('Auxiliary meter')}.get(role, _('Grid connection'))


def source_label(source):
    return _('Shelly Cloud Integration') if source == 'integrator' else _('Direct LAN / IP')


def tariffs():
    return parse_json_option('tariffs_json', [])


def store():
    global _store_cache, _store_cache_key
    key = (plugin_data_dir('energy_meter'), safe_int(options.get('max_records'), 0))
    if _store_cache is None or _store_cache_key != key:
        _store_cache = JsonStore(key[0], key[1])
        _store_cache_key = key
    return _store_cache


def local_history():
    with lock:
        return store().history()


def sql_enabled():
    return options.get('storage') in ('sql', 'both')


def local_enabled():
    return options.get('storage') in ('local', 'both')


def save_sql(records):
    if not records:
        return
    from plugins.database_connector import execute_db, table_exists
    if not table_exists(SQL_TABLE):
        execute_db('CREATE TABLE IF NOT EXISTS energy_meter_history (id INT NOT NULL AUTO_INCREMENT PRIMARY KEY, ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP, payload TEXT NOT NULL)', test=False, commit=False)
    for record in records:
        payload = json.dumps(record, ensure_ascii=False).replace("'", "''")
        execute_db("INSERT INTO energy_meter_history (payload) VALUES ('{}')".format(payload), test=False, commit=True)
    limit = safe_int(options.get('max_records'), 0)
    if limit:
        execute_db('DELETE FROM energy_meter_history WHERE id NOT IN (SELECT id FROM (SELECT id FROM energy_meter_history ORDER BY id DESC LIMIT {}) retained)'.format(limit), test=False, commit=True)


def sql_history():
    try:
        from plugins.database_connector import execute_db
        rows = execute_db('SELECT payload FROM energy_meter_history ORDER BY id ASC', test=False, commit=False, fetch=True) or []
        return [json.loads(row[0]) for row in rows]
    except Exception:
        return []


def clear_sql_history():
    try:
        from plugins.database_connector import execute_db, table_exists
        if table_exists(SQL_TABLE):
            execute_db('DELETE FROM energy_meter_history', test=False, commit=True)
    except Exception:
        log.error(NAME, _('Clearing Energy Meter SQL history failed') + ':\n' + traceback.format_exc())
        raise


def selected_history():
    return sql_history() if options.get('storage') == 'sql' else local_history()


def current_summary(selected_date=None):
    now = datetime.datetime.now()
    bounds = period_bounds(now)
    selected = selected_day_bounds(selected_date, now)
    history = selected_history()
    currency = str(options.get('currency', 'CZK'))
    summary = solar_summary(history, bounds['today'], bounds['now'], currency)
    summary['selected_date'] = selected['date']
    summary['current_date'] = selected['current_date']
    summary['selected_is_today'] = selected['is_today']
    summary['periods'] = {}
    for name, start_value, end_value in (('today', bounds['today'], bounds['now']), ('yesterday', bounds['yesterday'], bounds['today']), ('month', bounds['month'], bounds['now']), ('year', bounds['year'], bounds['now'])):
        summary['periods'][name] = solar_summary(history, start_value, end_value, currency)
    summary['periods']['selected'] = solar_summary(history, selected['start'], selected['end'], currency)
    return summary


class EnergyWorker(Thread):
    def __init__(self):
        Thread.__init__(self)
        self.daemon = True
        self.stop_event = runtime.stop_event
        self.session = requests.Session()
        self.status = {'last_success': 0, 'last_error': 0, 'error': '', 'meters': {}, 'resets': 0}
        self.reset_requests = set()
        self.pending_integrator_meters = set()
        self.footer = None
        self.start()
        runtime.register_thread(self)

    def stop(self):
        self.stop_event.set()

    def request_reset(self, meter_id):
        with lock:
            self.reset_requests.add(meter_id)

    def _sync_footer(self):
        if options.get('use_footer'):
            if self.footer is None:
                self.footer = showInFooter(label=_('Energy'), val='---', button='energy_meter/overview')
            summary = current_summary()
            self.footer.val = '{:.3f} {} / {:.3f} {}'.format(summary.get('grid_import_kwh', 0), _('kWh import today'), summary.get('grid_export_kwh', 0), _('kWh export today'))
        elif self.footer is not None:
            clear_plugin_runtime_data('energy_meter')
            self.footer = None

    def run(self):
        while not self.stop_event.is_set():
            self._sync_footer()
            if not options.get('enabled'):
                self.stop_event.wait(2)
                continue
            started = time.time()
            states = store().states()
            records = []
            retry_only = set(self.pending_integrator_meters)
            pending_integrator_meters = set()
            cycle_error = ''
            for meter in meters():
                if not meter['enabled']:
                    continue
                if retry_only and meter['id'] not in retry_only:
                    continue
                try:
                    reading = read_integrator(meter) if meter['source'] == 'integrator' else read_direct(meter, self.session)
                    reading = normalized_reading(reading, bool(meter.get('invert')))
                    ended = time.time()
                    previous = states.get(meter['id'])
                    with lock:
                        reset_requested = meter['id'] in self.reset_requests
                        if reset_requested:
                            self.reset_requests.discard(meter['id'])
                    identity_changed = previous and previous.get('identity') and reading.get('identity') and previous.get('identity') != reading.get('identity')
                    if reset_requested or identity_changed:
                        previous = None
                        states.pop(meter['id'], None)
                        self.status['resets'] += 1
                    interval_started = previous.get('timestamp', started) if previous else started
                    configured_tariffs = tariffs()
                    tariff = tariff_at(datetime.datetime.fromtimestamp(ended), configured_tariffs, options.get('default_import_price', 0), options.get('default_export_price', 0))
                    interval, state = make_interval(meter, reading, previous, interval_started, ended, tariff)
                    interval = price_interval(interval, configured_tariffs, options.get('default_import_price', 0), options.get('default_export_price', 0))
                    interval['currency'] = str(options.get('currency', 'CZK'))
                    states[meter['id']] = state
                    self.status['meters'][meter['id']] = {'label': meter['label'], 'role': meter['role'], 'source': meter['source'], 'online': True, 'power_w': interval['power_w'], 'power_l1_w': interval['power_l1_w'], 'power_l2_w': interval['power_l2_w'], 'power_l3_w': interval['power_l3_w'], 'updated': ended, 'error': ''}
                    if previous:
                        records.append(interval)
                    if interval['counter_reset']:
                        self.status['resets'] += 1
                    self.status['last_success'] = ended
                except IntegratorReadingPending:
                    message = _('Waiting for the selected Shelly meter to provide its first reading.')
                    pending_integrator_meters.add(meter['id'])
                    self.status['meters'][meter['id']] = {'label': meter['label'], 'role': meter['role'], 'source': meter['source'], 'online': False, 'power_w': 0, 'updated': time.time(), 'error': message, 'pending': True}
                    cycle_error = cycle_error or message
                except IntegratorMeterError as error:
                    if isinstance(error, IntegratorMeterOffline):
                        message = _('The selected Shelly meter is offline.')
                    elif isinstance(error, IntegratorMeterDisabled):
                        message = _('The selected Shelly meter is disabled in Shelly Cloud Integration.')
                    elif isinstance(error, IntegratorMeterUnavailable):
                        message = _('The selected Shelly meter is not available in Shelly Cloud Integration.')
                    else:
                        message = _('The selected Shelly meter could not be read.')
                    self.status['last_error'] = time.time()
                    cycle_error = message
                    self.status['meters'][meter['id']] = {'label': meter['label'], 'role': meter['role'], 'source': meter['source'], 'online': False, 'power_w': 0, 'updated': time.time(), 'error': message}
                    log.error(NAME, message)
                except Exception as error:
                    self.status['last_error'] = time.time()
                    cycle_error = str(error)
                    self.status['meters'][meter['id']] = {'label': meter['label'], 'role': meter['role'], 'source': meter['source'], 'online': False, 'power_w': 0, 'updated': time.time(), 'error': str(error)}
                    log.error(NAME, _('Energy Meter reading failed') + ':\n' + traceback.format_exc())
            self.pending_integrator_meters = pending_integrator_meters
            self.status['error'] = cycle_error
            with lock:
                current_store = store()
                current_store.save_state(states)
                if records and local_enabled():
                    current_store.append(records)
            if records and sql_enabled():
                try:
                    save_sql(records)
                except Exception:
                    log.error(NAME, _('Saving Energy Meter history to SQL failed') + ':\n' + traceback.format_exc())
            self._sync_footer()
            wait_seconds = 5 if pending_integrator_meters else max(5, min(3600, safe_int(options.get('sample_interval'), 60)))
            self.stop_event.wait(wait_seconds)


worker = None


def start():
    global worker
    if worker is None:
        worker = EnergyWorker()


def stop():
    global worker
    if worker is not None:
        worker.stop()
        runtime.request_stop()
        worker.join(15)
        if not worker.is_alive():
            worker = None
    clear_plugin_runtime_data('energy_meter')


class overview_page(ProtectedPage):
    def GET(self):
        qdict = web.input(date='')
        return self.plugin_render.energy_meter(options, meters(), current_summary(qdict.get('date')), worker.status if worker else {}, options.get('currency', 'CZK'))


class settings_page(ProtectedPage):
    def GET(self):
        return self.plugin_render.energy_meter_settings(options, meters(), tariffs(), None)

    def POST(self):
        qdict = web.input()
        verify_csrf(qdict)
        try:
            json.loads(qdict.get('meters_json', '[]'))
            json.loads(qdict.get('tariffs_json', '[]'))
        except ValueError:
            return self.plugin_render.energy_meter_settings(options, meters(), tariffs(), _('Meter or tariff configuration is not valid JSON.'))
        options.web_update(qdict)
        raise web.seeother(plugin_url(overview_page), True)


class help_page(ProtectedPage):
    def GET(self):
        return self.plugin_render.energy_meter_help()


class log_page(ProtectedPage):
    def GET(self):
        records = []
        for record in selected_history():
            item = dict(record)
            item['role_label'] = role_label(item.get('role'))
            records.append(item)
        return self.plugin_render.energy_meter_log(records, options)


class status_json(ProtectedPage):
    def GET(self):
        web.header('Content-Type', 'application/json')
        return json.dumps({'enabled': bool(options.get('enabled')), 'meters': worker.status.get('meters', {}) if worker else {}, 'summary': current_summary(), 'currency': options.get('currency', 'CZK')})


class graph_json(ProtectedPage):
    def GET(self):
        qdict = web.input()
        start_value = safe_int(qdict.get('from'), 0)
        end_value = safe_int(qdict.get('to'), int(time.time()))
        records = [record for record in selected_history() if safe_float(record.get('ended')) >= start_value and safe_float(record.get('started')) <= end_value]
        web.header('Content-Type', 'application/json')
        return json.dumps(records)


class clear_history_page(ProtectedPage):
    def POST(self):
        from ospy.server import session

        qdict = web.input()
        verify_csrf(qdict)
        if session.get('category') != 'admin':
            raise web.forbidden()
        with lock:
            if local_enabled():
                store().clear_history()
            if sql_enabled():
                clear_sql_history()
        log.info(NAME, _('Energy Meter history was cleared.'))
        raise web.seeother(plugin_url(log_page), True)


class reset_meter_page(ProtectedPage):
    def POST(self):
        qdict = web.input()
        verify_csrf(qdict)
        meter_id = str(qdict.get('meter_id', ''))
        if meter_id:
            if worker is not None:
                worker.request_reset(meter_id)
            with lock:
                store().reset_meter(meter_id)
        raise web.seeother(plugin_url(overview_page), True)


class log_csv(ProtectedPage):
    def GET(self):
        output = io.StringIO()
        fields = ['started', 'ended', 'meter_id', 'label', 'role', 'import_l1_kwh', 'import_l2_kwh', 'import_l3_kwh', 'import_kwh', 'export_l1_kwh', 'export_l2_kwh', 'export_l3_kwh', 'export_kwh', 'power_l1_w', 'power_l2_w', 'power_l3_w', 'power_w', 'tariff_name', 'currency', 'import_price', 'export_price', 'cost', 'income', 'counter_reset']
        writer = csv.DictWriter(output, fieldnames=fields, extrasaction='ignore', delimiter=';')
        writer.writeheader()
        writer.writerows(selected_history())
        web.header('Content-Type', 'text/csv; charset=utf-8')
        web.header('Content-Disposition', 'attachment; filename="energy_meter_{}.csv"'.format(time.strftime('%Y%m%d-%H%M%S')))
        return output.getvalue()


def health():
    details = dict(worker.status) if worker else {}
    if worker is None or not worker.is_alive():
        return {'status': 'error', 'summary': _('Energy Meter worker is not running.'), 'details': details}
    if not options.get('enabled'):
        return {'status': 'unknown', 'summary': _('Energy Meter is disabled.'), 'details': details}
    online = [value for value in worker.status.get('meters', {}).values() if value.get('online')]
    if not online:
        if any(value.get('pending') for value in worker.status.get('meters', {}).values()):
            return {'status': 'unknown', 'summary': _('Energy Meter is waiting for its first Shelly reading.'), 'details': details}
        return {'status': 'error', 'summary': _('No configured electricity meter is available.'), 'details': details}
    return {'status': 'ok', 'summary': _('Energy Meter is collecting data.'), 'details': details}


def mobile_status():
    result = health()
    return {'status': result['status'], 'title': _('Energy Meter'), 'summary': result['summary'], 'updated': worker.status.get('last_success', 0) if worker else 0}


def mobile_cards(from_time=None, to_time=None, max_points=400):
    today = current_summary()['periods']['today']
    metrics = []
    for key, label in (('grid_import_kwh', _('Grid import today')), ('grid_export_kwh', _('Grid export today')), ('production_kwh', _('Solar production today')), ('house_consumption_kwh', _('House consumption today'))):
        if key in today and (key not in ('production_kwh', 'house_consumption_kwh') or today.get('production_available')):
            metrics.append({'id': key, 'label': label, 'value': round(today[key], 3), 'unit': 'kWh'})
    for meter_id, value in (worker.status.get('meters', {}) if worker else {}).items():
        metrics.append({'id': 'power_' + meter_id, 'label': _('{} power').format(value.get('label', meter_id)), 'value': round(safe_float(value.get('power_w')), 1), 'unit': 'W'})
    from .mobile_history import mobile_history
    source = 'sql' if options.get('storage') == 'sql' else 'local'
    series, history = mobile_history(selected_history(), meters(), from_time, to_time, max_points, source)
    return [{'id': 'energy', 'kind': 'chart', 'title': _('Energy Meter'), 'metrics': metrics, 'history': history, 'series': series}]
