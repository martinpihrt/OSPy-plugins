# -*- coding: utf-8 -*-
__author__ = 'Martin Pihrt'

import csv
import datetime
import io
import json
import os
import time
import traceback

from threading import Lock, Thread

import web

from ospy import helpers
from ospy.helpers import datetime_string, verify_csrf
from ospy.i2c_guard import i2c_transaction
from ospy.log import log
from ospy.options import options as system_options
from ospy.webpages import ProtectedPage, clear_plugin_runtime_data, showInFooter
from plugins import (
    PluginOptions,
    get_runtime,
    plugin_data_dir,
    plugin_i2c_address_error,
    plugin_url,
    select_plugin_i2c_address,
)
from .methods import decode_bcd_counter


NAME = 'Water Meter'
MENU = _('Package: Water Meter')
LINK = 'overview_page'
ERROR_LOG_THROTTLE = 300
I2C_TIMEOUT = 2.0
I2C_PRIORITY = 'normal'
SQL_TABLE = 'watermeter'

options = PluginOptions(
    NAME,
    {
        'enabled': False,
        'pulses': 10.0,
        'address': False,
        'sum': 0.0,
        'log_date_last_reset': datetime_string(),
        'use_footer': True,
        'enable_log': False,
        'en_sql_log': False,
        'type_log': 0,
        'log_records': 0,
        'log_interval': 60,
        'log_only_flow': False,
    },
)
try:
    stored_options = system_options.get(options._plugin, {})
    if 'sum' in stored_options:
        options['sum'] = float(str(stored_options['sum']).replace(',', '.'))
except (AttributeError, TypeError, ValueError):
    pass
runtime = get_runtime()
health_lock = Lock()
log_lock = Lock()
health_state = {'last_reading': 0, 'last_error': 0, 'last_error_message': ''}


def safe_float(value, default=0.0):
    try:
        return float(str(value).replace(',', '.'))
    except (TypeError, ValueError):
        return default


def safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def normalize_options():
    options['pulses'] = max(0.001, min(1000000.0, safe_float(options.get('pulses', 10.0), 10.0)))
    options['sum'] = max(0.0, safe_float(options.get('sum', 0.0), 0.0))
    options['type_log'] = 1 if safe_int(options.get('type_log', 0), 0) == 1 else 0
    options['log_records'] = max(0, min(1000000, safe_int(options.get('log_records', 0), 0)))
    options['log_interval'] = max(1, min(86400, safe_int(options.get('log_interval', 60), 60)))


def _empty_status():
    return {
        'meter': 0.0,
        'minute_rate': 0.0,
        'minute_liters': 0.0,
        'hour_liters': 0.0,
        'total_liters': round(options.get('sum', 0.0), 2),
        'last_measurement': '',
        'raw_pulses': 0,
        'measurement_error': '',
    }


class WaterSender(Thread):
    def __init__(self):
        Thread.__init__(self)
        self.daemon = True
        self._stop_event = runtime.stop_event
        self.bus = None
        self.pcf = None
        self.status = _empty_status()
        self._last_error_log = 0
        self._footer = None
        self._reopen_requested = False
        self.start()
        runtime.register_thread(self)

    def stop(self):
        self._stop_event.set()

    def update(self):
        normalize_options()
        self._reopen_requested = True

    def _sleep(self, seconds):
        self._stop_event.wait(seconds)

    def _log_problem(self, message):
        now = time.time()
        with health_lock:
            health_state['last_error'] = now
            health_state['last_error_message'] = str(message).splitlines()[-1]
        if now - self._last_error_log >= ERROR_LOG_THROTTLE:
            log.error(NAME, message)
            self._last_error_log = now

    def _open_bus(self):
        bus = None
        try:
            import smbus
            bus = smbus.SMBus(0 if helpers.get_rpi_revision() == 1 else 1)
            if not set_counter(bus):
                raise IOError(_('Could not initialize PCF8583.'))
            self.bus = bus
            self.pcf = True
            self.status['measurement_error'] = ''
        except ImportError:
            log.warning(NAME, _('Could not import smbus.'))
            self.bus = None
            self.pcf = None
            self.status['measurement_error'] = _('Could not import smbus.')
        except Exception:
            if bus is not None:
                try:
                    bus.close()
                except (AttributeError, OSError):
                    pass
            self.bus = None
            self.pcf = None
            self.status['measurement_error'] = traceback.format_exc().splitlines()[-1]
            self._log_problem(_('Water Meter plug-in') + ':\n' + traceback.format_exc())

    def close_bus(self):
        bus = self.bus
        self.bus = None
        self.pcf = None
        if bus is not None:
            try:
                bus.close()
            except (AttributeError, OSError):
                pass

    def _sync_footer(self):
        if options['use_footer']:
            if self._footer is None:
                self._footer = showInFooter(
                    label=_('Water flow'),
                    val='---',
                    button='water_meter/overview',
                )
            self._footer.val = '{:.2f} {} ({:.2f} {})'.format(
                self.status['meter'], _('l/s'), self.status['minute_rate'], _('l/min'))
        elif self._footer is not None:
            clear_plugin_runtime_data('water_meter')
            self._footer = None

    def _persist_total(self):
        qdict = {'sum': round(self.status['total_liters'], 3)}
        if options['enabled']:
            qdict['enabled'] = 'on'
        if options['address']:
            qdict['address'] = 'on'
        if options['use_footer']:
            qdict['use_footer'] = 'on'
        if options['enable_log']:
            qdict['enable_log'] = 'on'
        if options['en_sql_log']:
            qdict['en_sql_log'] = 'on'
        if options['log_only_flow']:
            qdict['log_only_flow'] = 'on'
        qdict.update({
            'pulses': options['pulses'],
            'type_log': options['type_log'],
            'log_records': options['log_records'],
            'log_interval': options['log_interval'],
            'log_date_last_reset': options['log_date_last_reset'],
        })
        options.web_update(qdict)

    def run(self):
        self._open_bus()
        last_log = time.monotonic()
        last_persist = time.monotonic()
        minute_started = time.monotonic()
        hour_started = minute_started
        enabled_logged = None
        try:
            while not self._stop_event.is_set():
                try:
                    normalize_options()
                    if self._reopen_requested:
                        self._reopen_requested = False
                        self.close_bus()
                    self._sync_footer()
                    if not options['enabled']:
                        self.status.update(_empty_status())
                        self._sync_footer()
                        if enabled_logged is not False:
                            log.clear(NAME)
                            log.info(NAME, _('Water Meter plug-in is disabled.'))
                            enabled_logged = False
                        self._sleep(1)
                        continue
                    if enabled_logged is not True:
                        log.clear(NAME)
                        log.info(NAME, _('Water Meter plug-in is enabled.'))
                        enabled_logged = True
                    if self.bus is None:
                        self._open_bus()
                    if self.bus is None or self.pcf is None:
                        self._sleep(5)
                        continue

                    measurement = counter(self.bus, self._stop_event)
                    if measurement is None:
                        continue
                    raw_pulses, elapsed = measurement
                    liters = raw_pulses / options['pulses']
                    flow = liters / max(elapsed, 0.001)
                    now = time.monotonic()
                    if now - minute_started >= 60:
                        minute_started = now
                        self.status['minute_liters'] = 0.0
                    if now - hour_started >= 3600:
                        hour_started = now
                        self.status['hour_liters'] = 0.0
                    self.status['raw_pulses'] = raw_pulses
                    self.status['meter'] = round(flow, 3)
                    self.status['minute_rate'] = round(flow * 60.0, 3)
                    self.status['minute_liters'] = round(self.status['minute_liters'] + liters, 3)
                    self.status['hour_liters'] = round(self.status['hour_liters'] + liters, 3)
                    self.status['total_liters'] = round(self.status['total_liters'] + liters, 3)
                    self.status['last_measurement'] = datetime_string()
                    self.status['measurement_error'] = ''
                    with health_lock:
                        health_state['last_reading'] = time.time()
                    self._sync_footer()

                    if now - last_persist >= 60:
                        last_persist = now
                        self._persist_total()
                    if now - last_log >= options['log_interval']:
                        last_log = now
                        if not options['log_only_flow'] or flow > 0:
                            update_log(self.status)
                except Exception:
                    self.status['measurement_error'] = traceback.format_exc().splitlines()[-1]
                    self.close_bus()
                    self._log_problem(_('Water Meter plug-in') + ':\n' + traceback.format_exc())
                    self._sleep(5)
        finally:
            try:
                self._persist_total()
            except Exception:
                pass
            self.close_bus()


water_sender = None


def start():
    global water_sender
    if water_sender is None:
        preferred = '0x51' if options['address'] else '0x50'
        selected = select_plugin_i2c_address('water_meter', preferred)
        if not selected:
            raise RuntimeError(_('No non-conflicting I2C address is available for Water Meter.'))
        options['address'] = selected == '0x51'
        water_sender = WaterSender()


def stop():
    global water_sender
    if water_sender is not None:
        water_sender.stop()
        runtime.request_stop()
        water_sender.close_bus()
        water_sender.join(15)
        if not water_sender.is_alive():
            water_sender = None
    clear_plugin_runtime_data('water_meter')


def try_io(call, tries=3):
    error = None
    for _unused in range(tries):
        try:
            return call()
        except IOError as current_error:
            error = current_error
            time.sleep(0.01)
    raise error


def _address():
    return 0x51 if options['address'] else 0x50


def set_counter(i2cbus):
    try:
        with i2c_transaction(timeout=I2C_TIMEOUT, priority=I2C_PRIORITY):
            try_io(lambda: i2cbus.write_byte_data(_address(), 0x00, 0x20))
            for register in (0x01, 0x02, 0x03):
                try_io(lambda register=register: i2cbus.write_byte_data(_address(), register, 0x00))
        log.debug(NAME, _('Setup PCF8583 as event counter is OK'))
        return True
    except Exception:
        log.debug(NAME, _('Water Meter plug-in') + ':\n' + _('Setup PCF8583 as event counter - FAULT'))
        return None


def counter(i2cbus, stop_event=None):
    with i2c_transaction(timeout=I2C_TIMEOUT, priority=I2C_PRIORITY):
        for register in (0x01, 0x02, 0x03):
            try_io(lambda register=register: i2cbus.write_byte_data(_address(), register, 0x00))
    started = time.monotonic()
    if stop_event is not None:
        if stop_event.wait(1.0):
            return None
    else:
        time.sleep(1.0)
    elapsed = time.monotonic() - started
    with i2c_transaction(timeout=I2C_TIMEOUT, priority=I2C_PRIORITY):
        raw = try_io(lambda: i2cbus.read_i2c_block_data(_address(), 0x01, 3))
    if len(raw) < 3:
        raise IOError(_('PCF8583 returned an incomplete counter value.'))
    try:
        pulses = decode_bcd_counter(raw)
    except ValueError:
        raise ValueError(_('PCF8583 returned an invalid counter value.'))
    return pulses, elapsed


def get_all_values():
    status = water_sender.status if water_sender is not None else _empty_status()
    return round(status['total_liters'], 2), options['log_date_last_reset']


def _provider_timestamp(epoch):
    return (datetime.datetime.utcfromtimestamp(epoch).isoformat() + 'Z') if epoch else None


def provider_capabilities():
    """Describe cached measurements exposed through ospy.provider.v1."""
    return {
        'contract': 'ospy.provider.v1',
        'provider_id': 'water_meter',
        'resource_types': ['water_meter'],
        'values': [
            {'id': 'flow_lps', 'quantity': 'volume_flow_rate', 'unit': 'L/s', 'value_type': 'number'},
            {'id': 'flow_lpm', 'quantity': 'volume_flow_rate', 'unit': 'L/min', 'value_type': 'number'},
            {'id': 'minute_volume', 'quantity': 'volume', 'unit': 'L', 'value_type': 'number'},
            {'id': 'hour_volume', 'quantity': 'volume', 'unit': 'L', 'value_type': 'number'},
            {'id': 'total_volume', 'quantity': 'volume', 'unit': 'L', 'value_type': 'number'},
        ],
        'events': [{'code': 'water_meter.measurement'}],
        'alerts': [{'code': 'water_meter.sensor_error'}],
        'actions': [{
            'id': 'reset_total_consumption',
            'risk': 'control',
            'parameters': {},
        }],
    }


def provider_snapshot():
    """Return the last cached reading without accessing the I2C counter."""
    current = dict(water_sender.status) if water_sender is not None else _empty_status()
    with health_lock:
        state = dict(health_state)
    observed_at = _provider_timestamp(state['last_reading'])
    if not options.get('enabled', False):
        provider_status = 'disabled'
    elif water_sender is None or not water_sender.is_alive():
        provider_status = 'unavailable'
    elif state['last_error'] and state['last_error'] > state['last_reading']:
        provider_status = 'error'
    elif not state['last_reading']:
        provider_status = 'stale'
    else:
        provider_status = 'ok'
    values = [
        ('flow_lps', 'volume_flow_rate', current.get('meter'), 'L/s', 'measured'),
        ('flow_lpm', 'volume_flow_rate', current.get('minute_rate'), 'L/min', 'derived'),
        ('minute_volume', 'volume', current.get('minute_liters'), 'L', 'derived'),
        ('hour_volume', 'volume', current.get('hour_liters'), 'L', 'derived'),
        ('total_volume', 'volume', current.get('total_liters'), 'L', 'measured'),
    ]
    alerts = []
    if state['last_error'] and state['last_error'] > state['last_reading']:
        alerts.append({
            'id': 'water-meter.sensor-error', 'code': 'water_meter.sensor_error',
            'severity': 'error', 'state': 'active',
            'opened_at': _provider_timestamp(state['last_error']),
        })
    return {
        'contract': 'ospy.provider.v1', 'provider_id': 'water_meter',
        'status': provider_status, 'observed_at': observed_at,
        'resources': [{
            'id': 'main', 'type': 'water_meter', 'status': provider_status,
            'values': [{
                'id': item[0], 'quantity': item[1],
                'value': (float(item[2] or 0)
                          if observed_at or item[0] == 'total_volume' else None),
                'unit': item[3], 'value_type': 'number', 'quality': item[4],
                'observed_at': observed_at,
            } for item in values],
            'alerts': list(alerts),
        }],
        'events': [], 'alerts': alerts,
    }


def _reset_total_consumption():
    """Reset the same counters as the protected overview action."""
    previous_total = float(
        water_sender.status.get('total_liters', 0.0)
        if water_sender is not None else options.get('sum', 0.0))
    options['sum'] = 0.0
    options['log_date_last_reset'] = datetime_string()
    if water_sender is not None:
        water_sender.status['total_liters'] = 0.0
        water_sender.status['minute_liters'] = 0.0
        water_sender.status['hour_liters'] = 0.0
        water_sender._persist_total()
    log.info(NAME, _('Total consumption was reset.'))
    return previous_total


def provider_execute_action(action_id, resource_id='', parameters=None):
    """Execute an explicitly declared Water Meter provider action."""
    parameters = {} if parameters is None else parameters
    if action_id != 'reset_total_consumption':
        raise ValueError(_('Unsupported Water Meter provider action.'))
    if resource_id not in ('', 'main'):
        raise ValueError(_('Selected Water Meter resource does not exist.'))
    if not isinstance(parameters, dict) or parameters:
        raise ValueError(_('Reset total consumption does not accept parameters.'))
    previous_total = _reset_total_consumption()
    return {
        'status': 'ok',
        'message': _('Water Meter total consumption was reset.'),
        'data': {'previous_total_liters': previous_total,
                 'total_liters': 0.0},
    }


def _log_path():
    return os.path.join(plugin_data_dir('water_meter'), 'log.json')


def read_log():
    try:
        with open(_log_path(), encoding='utf-8') as log_file:
            data = json.load(log_file)
            return data if isinstance(data, list) else []
    except (IOError, ValueError):
        return []


def write_log(records):
    with open(_log_path(), 'w', encoding='utf-8') as log_file:
        json.dump(records, log_file, ensure_ascii=False)


def _record(status):
    return {
        'timestamp': int(time.time()),
        'datetime': datetime_string(),
        'flow_lps': round(status['meter'], 3),
        'flow_lpm': round(status['minute_rate'], 3),
        'total_liters': round(status['total_liters'], 3),
    }


def update_log(status):
    record = _record(status)
    if options['enable_log']:
        with log_lock:
            records = read_log()
            records.insert(0, record)
            if options['log_records'] > 0:
                records = records[:options['log_records']]
            write_log(records)
        log.info(NAME, _('Saving to log file OK'))
    if options['en_sql_log']:
        try:
            from plugins.database_connector import execute_db, table_exists
            if not table_exists(SQL_TABLE):
                execute_db('CREATE TABLE IF NOT EXISTS watermeter (id INT NOT NULL AUTO_INCREMENT PRIMARY KEY, ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP, flow_lps DECIMAL(12,3), flow_lpm DECIMAL(12,3), total_liters DECIMAL(16,3))', test=False, commit=False)
            execute_db("INSERT INTO watermeter (flow_lps, flow_lpm, total_liters) VALUES ('{:.3f}','{:.3f}','{:.3f}')".format(record['flow_lps'], record['flow_lpm'], record['total_liters']), test=False, commit=True)
            if options['log_records'] > 0:
                execute_db('DELETE FROM watermeter WHERE id NOT IN (SELECT id FROM (SELECT id FROM watermeter ORDER BY id DESC LIMIT {}) retained)'.format(options['log_records']), test=False, commit=True)
            log.info(NAME, _('Saving to SQL database.'))
        except Exception:
            log.error(NAME, _('Water Meter plug-in') + ':\n' + traceback.format_exc())


def read_sql_log():
    try:
        from plugins.database_connector import execute_db
        return execute_db('SELECT id, ts, flow_lps, flow_lpm, total_liters FROM watermeter ORDER BY id DESC', test=False, commit=False, fetch=True) or []
    except Exception:
        return []


def record_timestamp(value):
    if hasattr(value, 'timestamp'):
        return int(value.timestamp())
    try:
        return int(datetime.datetime.fromisoformat(str(value)).timestamp())
    except (TypeError, ValueError, OSError):
        return 0


def selected_records():
    if options['type_log'] == 1:
        return [
            {'id': row[0], 'datetime': str(row[1]), 'timestamp': record_timestamp(row[1]), 'flow_lps': float(row[2]), 'flow_lpm': float(row[3]), 'total_liters': float(row[4])}
            for row in read_sql_log()
        ]
    return read_log()


def delete_sql_log():
    try:
        from plugins.database_connector import execute_db
        execute_db('DROP TABLE IF EXISTS watermeter', test=False, commit=False)
        log.info(NAME, _('Deleting the watermeter table from the database.'))
    except Exception:
        log.error(NAME, _('Water Meter plug-in') + ':\n' + traceback.format_exc())


class overview_page(ProtectedPage):
    def GET(self):
        qdict = web.input()
        if helpers.get_input(qdict, 'reset', False, lambda value: True):
            verify_csrf(qdict)
            _reset_total_consumption()
            raise web.seeother(plugin_url(overview_page), True)
        status = water_sender.status if water_sender is not None else _empty_status()
        return self.plugin_render.water_meter(options, status, log.events(NAME))


class settings_page(ProtectedPage):
    def GET(self):
        qdict = web.input()
        if helpers.get_input(qdict, 'delSQL', False, lambda value: True):
            verify_csrf(qdict)
            delete_sql_log()
        normalize_options()
        return self.plugin_render.water_meter_settings(options)

    def POST(self):
        qdict = web.input()
        verify_csrf(qdict)
        requested_address = '0x51' if qdict.get('address', 'off') == 'on' else '0x50'
        address_error = plugin_i2c_address_error('water_meter', requested_address)
        if address_error:
            return self.plugin_render.water_meter_settings(options, address_error)
        qdict['pulses'] = safe_float(qdict.get('pulses'), options['pulses'])
        options.web_update(qdict)
        normalize_options()
        if water_sender is not None:
            water_sender.update()
        raise web.seeother(plugin_url(overview_page), True)


class log_page(ProtectedPage):
    def GET(self):
        qdict = web.input()
        if helpers.get_input(qdict, 'delete', False, lambda value: True):
            verify_csrf(qdict)
            write_log([])
        if helpers.get_input(qdict, 'delSQL', False, lambda value: True):
            verify_csrf(qdict)
            delete_sql_log()
        return self.plugin_render.water_meter_log(selected_records(), options)


class help_page(ProtectedPage):
    def GET(self):
        return self.plugin_render.water_meter_help()


class settings_json(ProtectedPage):
    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        normalize_options()
        return json.dumps(options)


class water_json(ProtectedPage):
    def GET(self):
        web.header('Access-Control-Allow-Origin', '*')
        web.header('Content-Type', 'application/json')
        status = water_sender.status if water_sender is not None else _empty_status()
        data = dict(status)
        data['sec_water'] = status['meter']
        data['enabled'] = bool(options['enabled'])
        if not options['enabled']:
            data['status'] = _('Disabled')
        elif water_sender is None:
            data['status'] = _('Stopped')
        elif water_sender.bus is None or not water_sender.pcf:
            data['status'] = _('I2C error')
        else:
            data['status'] = _('Running')
        data['error'] = status.get('measurement_error', '')
        data['address'] = '0x51' if options['address'] else '0x50'
        data['activity'] = '\n'.join(str(event) for event in log.events(NAME))
        return json.dumps(data)


class graph_json(ProtectedPage):
    def GET(self):
        qdict = web.input()
        start_value = safe_int(qdict.get('from'), 0)
        end_value = safe_int(qdict.get('to'), int(time.time()))
        balances = {}
        for record in reversed(selected_records()):
            timestamp = safe_int(record.get('timestamp'), 0)
            if start_value <= timestamp <= end_value:
                balances[str(timestamp)] = {'total': safe_float(record.get('flow_lps'), 0.0)}
        web.header('Content-Type', 'application/json')
        return json.dumps([{'station': _('Flow (l/s)'), 'balances': balances}])


class log_csv(ProtectedPage):
    def GET(self):
        output = io.StringIO()
        writer = csv.writer(output, delimiter=';')
        writer.writerow([_('Date Time'), _('Flow (l/s)'), _('Flow (l/min)'), _('Total liters')])
        for record in selected_records():
            writer.writerow([record.get('datetime', ''), record.get('flow_lps', 0), record.get('flow_lpm', 0), record.get('total_liters', 0)])
        web.header('Content-Type', 'text/csv; charset=utf-8')
        web.header('Content-Disposition', 'attachment; filename="water_meter_{}.csv"'.format(time.strftime('%Y%m%d-%H%M%S')))
        return output.getvalue()


def health():
    worker_alive = water_sender is not None and water_sender.is_alive()
    bus_open = water_sender is not None and water_sender.bus is not None
    counter_ready = water_sender is not None and bool(water_sender.pcf)
    status_data = water_sender.status if water_sender is not None else _empty_status()
    with health_lock:
        state = dict(health_state)
    details = {
        'worker': _('Running') if worker_alive else _('Stopped'),
        'enabled': bool(options.get('enabled', False)),
        'i2c_address': '0x51' if options.get('address', False) else '0x50',
        'i2c_bus': _('Open') if bus_open else _('Unavailable'),
        'counter': _('Ready') if counter_ready else _('Unavailable'),
        'liters_per_second': status_data['meter'],
        'liters_per_minute': status_data['minute_rate'],
        'total_liters': status_data['total_liters'],
        'last_reading': state['last_reading'],
        'last_error': state['last_error'],
    }
    if state['last_error_message']:
        details['error'] = state['last_error_message']
    if not worker_alive:
        return {'status': 'error', 'summary': _('Water Meter worker is not running.'), 'details': details}
    if not options.get('enabled', False):
        return {'status': 'unknown', 'summary': _('Water Meter is disabled.'), 'details': details}
    if not bus_open or not counter_ready:
        return {'status': 'error', 'summary': _('PCF8583 is not available.'), 'details': details}
    if state['last_error'] and state['last_error'] > state['last_reading']:
        return {'status': 'warning', 'summary': _('Water Meter reported an error.'), 'details': details}
    return {'status': 'ok', 'summary': _('Water Meter is reading pulses.'), 'details': details}


def mobile_status():
    """Return current Water Meter state without triggering a measurement."""
    result = health()
    current = water_sender.status if water_sender is not None else _empty_status()
    return {
        'status': result.get('status', 'unknown'),
        'title': _('Water Meter'),
        'summary': result.get('summary', ''),
        'updated': current.get('last_measurement', ''),
    }


def mobile_cards(from_time=None, to_time=None, max_points=400):
    """Return live consumption metrics and bounded flow history."""
    from plugins.water_meter.mobile_history import mobile_history
    current = dict(water_sender.status) if water_sender is not None else _empty_status()
    source = 'sql' if options.get('type_log', 0) == 1 else 'local'
    series, history = mobile_history(selected_records(), from_time, to_time, max_points, source)
    series[0]['label'] = _('Flow')
    series[0]['unit'] = _('l/s')
    return [{
        'id': 'water',
        'title': _('Water flow'),
        'metrics': [
            {'id': 'flow_lps', 'label': _('Current flow'), 'value': round(float(current.get('meter', 0)), 3), 'unit': _('l/s')},
            {'id': 'flow_lpm', 'label': _('Per-minute flow'), 'value': round(float(current.get('minute_rate', 0)), 3), 'unit': _('l/min')},
            {'id': 'minute_liters', 'label': _('Current minute'), 'value': round(float(current.get('minute_liters', 0)), 3), 'unit': _('liters')},
            {'id': 'hour_liters', 'label': _('Current hour'), 'value': round(float(current.get('hour_liters', 0)), 3), 'unit': _('liters')},
            {'id': 'total_liters', 'label': _('Total consumption'), 'value': round(float(current.get('total_liters', 0)), 3), 'unit': _('liters')},
        ],
        'series': series,
        'history': history,
    }]
