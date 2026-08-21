# -*- coding: utf-8 -*-
"""Graphical automation rules over cached ospy.provider.v1 snapshots."""

import json
import os
import time
import traceback
import uuid
from threading import RLock, Thread

import web

from ospy.helpers import datetime_string, verify_csrf
from ospy.log import log
from ospy.provider_contracts import validate_snapshot
from ospy.webpages import ProtectedPage, pluginScripts
from plugins import (
    PluginOptions, get, get_runtime, plugin_data_dir,
    plugin_provider_capabilities, plugin_provider_modules,
    plugin_provider_snapshots, plugin_url, running,
)

from . import engine, sensor_provider, time_provider


NAME = 'Automation Rules'
MENU = _('Package: Automation Rules')
LINK = 'settings_page'
MAX_RULES = 100
SCRIPT_PATH = 'automation_rules/static/automation_rules.js?v=1.0.6'

plugin_options = PluginOptions(NAME, {
    'enabled': False,
    'test_mode': True,
    'poll_interval': 30,
    'history_limit': 500,
})
runtime = get_runtime()
storage_lock = RLock()
health_lock = RLock()
health_state = {
    'last_cycle': 0, 'last_action': 0, 'last_error': 0,
    'last_error_message': '', 'evaluated_rules': 0,
    'active_rules': 0, 'provider_errors': 0,
}
_test_states = {}


def _data_path(name):
    return os.path.join(plugin_data_dir('automation_rules'), name)


def _read_json(name, default):
    try:
        with open(_data_path(name), encoding='utf-8') as source:
            return json.load(source)
    except (IOError, OSError, ValueError, TypeError):
        return default


def _write_json(name, value):
    directory = plugin_data_dir('automation_rules')
    os.makedirs(directory, exist_ok=True)
    target = _data_path(name)
    temporary = target + '.tmp'
    with open(temporary, 'w', encoding='utf-8') as output:
        json.dump(value, output, ensure_ascii=False, indent=2, sort_keys=True,
                  allow_nan=False)
        output.flush()
        os.fsync(output.fileno())
    os.replace(temporary, target)


def load_rules():
    with storage_lock:
        raw = _read_json('rules.json', [])
    if not isinstance(raw, list):
        return []
    result = []
    for item in raw[:MAX_RULES]:
        try:
            result.append(engine.normalize_rule(item))
        except engine.RuleValidationError:
            log.error(NAME, _('An invalid automation rule was skipped.'))
    return result


def save_rules(rules):
    normalized = [engine.normalize_rule(item) for item in rules]
    if len(normalized) > MAX_RULES:
        raise engine.RuleValidationError('too many rules')
    with storage_lock:
        _write_json('rules.json', normalized)
    return normalized


def load_states():
    with storage_lock:
        value = _read_json('states.json', {})
    return value if isinstance(value, dict) else {}


def save_states(states):
    with storage_lock:
        _write_json('states.json', states)


def load_history():
    with storage_lock:
        value = _read_json('history.json', [])
    return value if isinstance(value, list) else []


def clear_history():
    with storage_lock:
        _write_json('history.json', [])


def append_history(record):
    safe = json.loads(json.dumps(record, ensure_ascii=False, allow_nan=False))
    with storage_lock:
        history = _read_json('history.json', [])
        if not isinstance(history, list):
            history = []
        history.insert(0, safe)
        limit = max(10, min(5000, int(plugin_options.get('history_limit', 500))))
        _write_json('history.json', history[:limit])


def local_notifications():
    with storage_lock:
        records = _read_json('notifications.json', [])
    if not isinstance(records, list):
        return []
    cutoff = int(time.time()) - 86400
    return [item for item in records[:100]
            if isinstance(item, dict) and int(item.get('timestamp', 0)) >= cutoff]


def _queue_local_notification(rule, event, message, channels):
    record = {
        'id': 'automation-{}-{}'.format(rule['id'], int(time.time() * 1000)),
        'timestamp': int(time.time()), 'title': _('Automation Rules'),
        'message': message, 'severity': ('info' if event == 'cleared'
                                         else rule['severity']),
        'event': event, 'rule_id': rule['id'],
        'home': 'home' in channels, 'browser': 'browser' in channels,
    }
    with storage_lock:
        records = _read_json('notifications.json', [])
        if not isinstance(records, list):
            records = []
        records.insert(0, record)
        _write_json('notifications.json', records[:100])
    return record


def _automation_snapshots():
    snapshots = plugin_provider_snapshots()
    providers = dict(snapshots.get('providers', {}))
    errors = dict(snapshots.get('errors', {}))
    try:
        providers[sensor_provider.PROVIDER_ID] = validate_snapshot(
            sensor_provider.provider_snapshot(), sensor_provider.PROVIDER_ID)
    except Exception as error:
        errors[sensor_provider.PROVIDER_ID] = {
            'error': type(error).__name__, 'message': str(error),
        }
    try:
        providers[time_provider.PROVIDER_ID] = validate_snapshot(
            time_provider.provider_snapshot(), time_provider.PROVIDER_ID)
    except Exception as error:
        errors[time_provider.PROVIDER_ID] = {
            'error': type(error).__name__, 'message': str(error),
        }
    return {'providers': providers, 'errors': errors}


def _sensor_value_label(identifier):
    labels = {
        'contact_state': _('Contact state'),
        'motion': _('Motion detected'),
        'moisture_percent': _('Moisture'),
        'temperature': _('Temperature'),
        'voltage': _('Voltage'),
        'humidity': _('Humidity'),
        'illuminance': _('Illuminance'),
        'volume': _('Volume'),
    }
    if identifier in labels:
        return labels[identifier]
    numbered = (
        ('contact_', _('Contact input {}')),
        ('soil_moisture_', _('Soil moisture probe {}')),
        ('output_', _('Output {}')),
        ('temperature_', _('Temperature {}')),
        ('power_', _('Power {}')),
        ('pv_power_', _('PV power {}')),
    )
    for prefix, label in numbered:
        if identifier.startswith(prefix):
            return label.format(identifier[len(prefix):])
    return identifier


def _provider_catalog():
    catalog = []
    snapshots = _automation_snapshots()
    modules = list(plugin_provider_modules()) + [
        sensor_provider.PROVIDER_ID, time_provider.PROVIDER_ID,
    ]
    for module in modules:
        try:
            capabilities = (
                sensor_provider.provider_capabilities()
                if module == sensor_provider.PROVIDER_ID else
                time_provider.provider_capabilities()
                if module == time_provider.PROVIDER_ID else
                plugin_provider_capabilities(module)
            )
            snapshot = snapshots.get('providers', {}).get(module, {})
            declared = {item['id']: item for item in capabilities.get('values', [])}
            for resource in snapshot.get('resources', []):
                for value in resource.get('values', []):
                    definition = declared.get(value.get('id'), {})
                    catalog.append({
                        'provider_id': module,
                        'provider_label': {
                            'water_meter': _('Water Meter'),
                            'pressure_monitor': _('Pressure Monitor'),
                            'tank_monitor': _('Water Tank Monitor'),
                            'current_loop_tanks_monitor': _('Current Loop Tanks Monitor'),
                            'ospy_sensors': _('OSPy Sensors'),
                            'ospy_datetime': _('Date and time'),
                        }.get(module, module),
                        'resource_id': resource.get('id', ''),
                        'resource_label': (
                            resource.get('name') if resource.get('name') else
                            _('OSPy local time')
                            if module == time_provider.PROVIDER_ID else
                            _('Sensor {}').format(
                                int(str(resource.get('id', '')).split('-')[-1]) + 1)
                            if module == sensor_provider.PROVIDER_ID and
                            str(resource.get('id', '')).startswith('sensor-') else
                            _('Main resource') if resource.get('id') == 'main' else
                            _('Tank {}').format(str(resource.get('id', '')).split('-')[-1])
                            if str(resource.get('id', '')).startswith('tank-') else
                            resource.get('id', '')
                        ),
                        'value_id': value.get('id', ''),
                        'value_label': {
                            'flow_lps': _('Flow in liters per second'),
                            'flow_lpm': _('Flow in liters per minute'),
                            'minute_volume': _('Volume in the current minute'),
                            'hour_volume': _('Volume in the current hour'),
                            'total_volume': _('Total volume'),
                            'pressure_present': _('Pressure present'),
                            'master_active': _('Master active'),
                            'level_cm': _('Water level'),
                            'fill_percent': _('Tank fill'),
                            'sensor_distance_cm': _('Sensor distance'),
                            'volume_liters': _('Volume in liters'),
                            'volume_cubic_meters': _('Volume in cubic meters'),
                            'sensor_voltage': _('Sensor voltage'),
                            'current_date': _('Current date'),
                            'current_time': _('Current time'),
                            'weekday': _('Day of week'),
                            'month': _('Month'),
                            'day_of_month': _('Day of month'),
                        }.get(value.get('id'),
                              _sensor_value_label(value.get('id', ''))
                              if module == sensor_provider.PROVIDER_ID else
                              value.get('id', '')),
                        'unit': definition.get('unit', value.get('unit', '')),
                        'value_type': definition.get('value_type',
                                                     value.get('value_type', 'string')),
                    })
        except Exception:
            log.error(NAME, _('Unable to read provider capabilities') + ': ' + module)
    return catalog


def _display_history():
    event_labels = {
        'triggered': _('Triggered'), 'repeated': _('Repeated'),
        'cleared': _('Returned to normal'),
        'test_matched': _('Test matched'),
        'test_not_matched': _('Test did not match'),
        'notification_test': _('Test notification'),
    }
    channel_labels = {
        'home': _('OSPy Home window'), 'browser': _('Browser notification'),
        'email': _('E-mail'), 'telegram': _('Telegram'),
        'push': _('Push notification'),
    }
    status_labels = {
        'test': _('Test only'), 'queued': _('Queued'), 'sent': _('Sent'),
        'unavailable': _('Unavailable'), 'unsupported': _('Unsupported'),
        'error': _('Error'),
    }
    result = []
    for item in load_history():
        record = dict(item)
        record['event_text'] = event_labels.get(item.get('event'), _('Unknown'))
        record['mode_text'] = (_('Notification test')
                               if item.get('event') == 'notification_test' else
                               _('Test') if item.get('test_mode') else _('Live'))
        record['results_text'] = ', '.join(
            '{}: {}'.format(channel_labels.get(value.get('channel'), _('Unknown')),
                            status_labels.get(value.get('status'), _('Unknown')))
            for value in item.get('results', [])
        )
        result.append(record)
    return result


def _event_text(rule, event):
    if event == 'notification_test':
        return _('Automation Rules test notification: {}').format(rule['name'])
    if event == 'cleared':
        return _('Automation rule returned to normal: {}').format(rule['name'])
    if event == 'repeated':
        return _('Automation rule is still active: {}').format(rule['name'])
    return _('Automation rule was triggered: {}').format(rule['name'])


def _display_value(value, unit=''):
    if isinstance(value, bool):
        result = _('Active') if value else _('Inactive')
    elif isinstance(value, float):
        result = ('{:.3f}'.format(value)).rstrip('0').rstrip('.')
    else:
        result = str(value)
    return '{} {}'.format(result, unit).strip()


def _condition_summary(rule, evaluation):
    if not isinstance(evaluation, dict):
        return ''
    catalog = {
        (item['provider_id'], item['resource_id'], item['value_id']): item
        for item in _provider_catalog()
    }
    results = {item.get('id'): item
               for item in evaluation.get('conditions', [])}
    operators = {
        'eq': '=', 'ne': '!=', 'gt': '>', 'gte': '>=', 'lt': '<', 'lte': '<=',
        'between': _('is in range'), 'not_between': _('is outside range'),
        'is_true': _('is active'), 'is_false': _('is inactive'),
    }
    lines = []
    for condition in rule.get('conditions', []):
        result = results.get(condition.get('id'), {})
        definition = catalog.get((
            condition.get('provider_id'), condition.get('resource_id'),
            condition.get('value_id'),
        ), {})
        label = definition.get('value_label') or condition.get('value_id', '')
        resource = definition.get('resource_label', '')
        prefix = '{} – {}'.format(resource, label) if resource else label
        if not result.get('available'):
            lines.append('{}: {}'.format(prefix, _('value unavailable')))
            continue
        unit = result.get('unit', '')
        operator = condition.get('operator', 'eq')
        actual = _display_value(result.get('actual'), unit)
        if operator in ('is_true', 'is_false'):
            lines.append('{}: {} ({})'.format(
                prefix, actual, operators.get(operator, operator)))
            continue
        expected = result.get('expected', condition.get('expected'))
        if operator in ('between', 'not_between'):
            expected = str(expected).replace('..', ' – ')
        else:
            expected = _display_value(expected, unit)
        lines.append('{}: {} {} {}'.format(
            prefix, actual, operators.get(operator, operator), expected))
    return '\n'.join(lines)


def _send_email(title, message):
    for module in ('email_notifications_ssl', 'email_notifications'):
        if module not in running():
            continue
        method = getattr(get(module), 'try_mail', None)
        if callable(method):
            sent = method(message, message, attachment=None, subject=title)
            return {'channel': 'email',
                    'status': 'sent' if sent is not False else 'error',
                    'provider': module}
    return {'channel': 'email', 'status': 'unavailable'}


def _send_telegram(title, message):
    if 'telegram_bot' not in running():
        return {'channel': 'telegram', 'status': 'unavailable'}
    method = getattr(get('telegram_bot'), 'send_notification', None)
    if not callable(method):
        return {'channel': 'telegram', 'status': 'unsupported'}
    sent = method('{}\n{}'.format(title, message))
    return {'channel': 'telegram', 'status': 'sent' if sent else 'unavailable'}


def _send_push(rule, event, message, condition_summary=''):
    try:
        from api.v1.push import push_dispatcher
        queued = push_dispatcher.enqueue_notification({
            'id': 'automation-{}-{}'.format(rule['id'], int(time.time() * 1000)),
            'event_type': 'automation',
            'severity': 'info' if event == 'cleared' else rule['severity'],
            'code': 'automation_rule_{}'.format(event),
            'title': _('Automation Rules'), 'message': message,
            'data': {
                'rule_id': rule['id'], 'rule_name': rule['name'],
                'event': event, 'condition_summary': condition_summary,
            },
        })
        return {'channel': 'push', 'status': 'queued' if queued else 'unavailable'}
    except Exception as error:
        return {'channel': 'push', 'status': 'error',
                'error': type(error).__name__}


def dispatch_notifications(rule, event, test_mode=False, evaluation=None):
    message = _event_text(rule, event)
    condition_summary = _condition_summary(rule, evaluation)
    if condition_summary:
        message += '\n' + condition_summary
    title = _('Automation Rules')
    results = []
    local_channels = [channel for channel in rule['channels']
                      if channel in ('home', 'browser')]
    if local_channels:
        if test_mode:
            results.extend({'channel': channel, 'status': 'test'}
                           for channel in local_channels)
        else:
            _queue_local_notification(rule, event, message, local_channels)
            results.extend({'channel': channel, 'status': 'queued'}
                           for channel in local_channels)
    for channel in rule['channels']:
        if channel in ('home', 'browser'):
            continue
        if test_mode:
            results.append({'channel': channel, 'status': 'test'})
            continue
        try:
            if channel == 'email':
                results.append(_send_email(title, message))
            elif channel == 'telegram':
                results.append(_send_telegram(title, message))
            elif channel == 'push':
                results.append(_send_push(
                    rule, event, message, condition_summary))
        except Exception as error:
            results.append({'channel': channel, 'status': 'error',
                            'error': type(error).__name__})
            log.error(NAME, _('Automation notification failed') + ': ' +
                      '{} {}'.format(channel, type(error).__name__))
    return results


def _history_record(rule, event, evaluation, results, test_mode):
    return {
        'timestamp': int(time.time()), 'datetime': datetime_string(),
        'rule_id': rule['id'], 'rule_name': rule['name'], 'event': event,
        'matched': bool(evaluation.get('matched')),
        'available': bool(evaluation.get('available')),
        'test_mode': bool(test_mode), 'results': results,
        'conditions': [{
            'id': item.get('id'), 'matched': bool(item.get('matched')),
            'available': bool(item.get('available')), 'actual': item.get('actual'),
            'expected': item.get('expected'), 'unit': item.get('unit', ''),
            'reason': item.get('reason', ''),
            'operator': next((condition.get('operator')
                              for condition in rule.get('conditions', [])
                              if condition.get('id') == item.get('id')), ''),
        } for item in evaluation.get('conditions', [])],
    }


def evaluate_once(test_mode=None):
    """Evaluate every enabled rule against one consistent snapshot set."""
    global _test_states
    rules = load_rules()
    snapshots = _automation_snapshots()
    now = int(time.time())
    is_test = bool(plugin_options.get('test_mode', True)
                   if test_mode is None else test_mode)
    states = _test_states if is_test else load_states()
    evaluated = 0
    for rule in rules:
        if not rule['enabled']:
            continue
        evaluated += 1
        evaluation = engine.evaluate_rule(rule, snapshots)
        next_state, event = engine.transition(rule, evaluation,
                                              states.get(rule['id']), now)
        states[rule['id']] = next_state
        should_notify = event in ('triggered', 'repeated') or (
            event == 'cleared' and rule['notify_on_clear'])
        if should_notify:
            results = dispatch_notifications(
                rule, event, test_mode=is_test, evaluation=evaluation)
            append_history(_history_record(rule, event, evaluation, results, is_test))
            with health_lock:
                health_state['last_action'] = time.time()
    if is_test:
        _test_states = states
    else:
        save_states(states)
    with health_lock:
        health_state['last_cycle'] = time.time()
        health_state['last_error_message'] = ''
        health_state['evaluated_rules'] = evaluated
        health_state['active_rules'] = sum(1 for value in states.values()
                                           if value.get('active'))
        health_state['provider_errors'] = len(snapshots.get('errors', {}))
    return {'rules': evaluated, 'snapshots': snapshots, 'states': states}


def test_rule(rule_id):
    rules = {item['id']: item for item in load_rules()}
    rule = rules.get(rule_id)
    if rule is None:
        raise engine.RuleValidationError('rule was not found')
    evaluation = engine.evaluate_rule(rule, _automation_snapshots())
    event = 'test_matched' if evaluation['matched'] else 'test_not_matched'
    append_history(_history_record(rule, event, evaluation, [
        {'channel': channel, 'status': 'test'} for channel in rule['channels']
    ], True))
    return evaluation


def send_test_notifications(rule):
    """Send one explicit test without evaluating or changing rule state."""
    rule = engine.normalize_rule(rule)
    evaluation = engine.evaluate_rule(rule, _automation_snapshots())
    results = dispatch_notifications(
        rule, 'notification_test', test_mode=False, evaluation=evaluation)
    append_history(_history_record(
        rule, 'notification_test', evaluation, results, False))
    return results


class AutomationWorker(Thread):
    def __init__(self):
        Thread.__init__(self)
        self.daemon = True
        self._stop_event = runtime.stop_event
        self.start()
        runtime.register_thread(self)

    def stop(self):
        self._stop_event.set()

    def run(self):
        while not self._stop_event.is_set():
            if not plugin_options.get('enabled', False):
                self._stop_event.wait(2)
                continue
            try:
                evaluate_once()
            except Exception:
                with health_lock:
                    health_state['last_error'] = time.time()
                    health_state['last_error_message'] = traceback.format_exc().splitlines()[-1]
                log.error(NAME, _('Automation Rules evaluation failed') + ':\n' +
                          traceback.format_exc())
            interval = max(5, min(3600,
                                  int(plugin_options.get('poll_interval', 30))))
            self._stop_event.wait(interval)


worker = None


def start():
    global worker
    if SCRIPT_PATH not in pluginScripts:
        pluginScripts.append(SCRIPT_PATH)
    if worker is None:
        worker = AutomationWorker()


def stop():
    global worker
    if worker is not None:
        worker.stop()
        worker.join(15)
        if not worker.is_alive():
            worker = None
    if SCRIPT_PATH in pluginScripts:
        pluginScripts.remove(SCRIPT_PATH)


def health():
    with health_lock:
        state = dict(health_state)
    worker_running = worker is not None and worker.is_alive()
    details = {
        _('Worker thread'): _('Running') if worker_running else _('Stopped'),
        _('Automation enabled'): _('Yes') if plugin_options.get('enabled') else _('No'),
        _('Test mode'): _('Yes') if plugin_options.get('test_mode') else _('No'),
        _('Saved rules'): len(load_rules()),
        _('Evaluated rules'): state['evaluated_rules'],
        _('Active rules'): state['active_rules'],
        _('Provider errors'): state['provider_errors'],
        _('Last evaluation'): (datetime_string(time.localtime(state['last_cycle']))
                               if state['last_cycle'] else _('Not available')),
        _('Last action'): (datetime_string(time.localtime(state['last_action']))
                           if state['last_action'] else _('Not available')),
    }
    if state['last_error_message']:
        details[_('Last error')] = state['last_error_message']
    if not worker_running:
        return {'status': 'error', 'summary': _('Automation Rules worker is stopped.'),
                'details': details}
    if not plugin_options.get('enabled'):
        return {'status': 'unknown', 'summary': _('Automation Rules are disabled.'),
                'details': details}
    if state['last_error'] and state['last_error'] >= state['last_cycle']:
        return {'status': 'error', 'summary': _('Automation Rules evaluation failed.'),
                'details': details}
    if not state['last_cycle']:
        return {'status': 'unknown',
                'summary': _('Automation Rules are waiting for the first evaluation.'),
                'details': details}
    if state['provider_errors']:
        return {'status': 'warning',
                'summary': _('One or more automation providers reported an error.'),
                'details': details}
    return {'status': 'ok', 'summary': _('Automation Rules are responding.'),
            'details': details}


def _new_rule():
    return {
        'id': uuid.uuid4().hex, 'name': '', 'enabled': True, 'mode': 'all',
        'conditions': [{
            'id': uuid.uuid4().hex, 'provider_id': '', 'resource_id': '',
            'value_id': '', 'operator': 'lte', 'expected': 0,
        }],
        'hold_seconds': 0, 'repeat_seconds': 0,
        'notify_on_clear': True, 'severity': 'warning', 'channels': [],
    }


def _rule_from_input(qdict):
    condition_count = max(1, min(20, int(qdict.get('condition_count', 1))))
    conditions = []
    for index in range(condition_count):
        provider_id = str(qdict.get('provider_id_{}'.format(index), '')).strip()
        resource_id = str(qdict.get('resource_id_{}'.format(index), '')).strip()
        value_id = str(qdict.get('value_id_{}'.format(index), '')).strip()
        if not provider_id and not resource_id and not value_id:
            continue
        conditions.append({
            'id': qdict.get('condition_id_{}'.format(index)) or uuid.uuid4().hex,
            'provider_id': provider_id, 'resource_id': resource_id,
            'value_id': value_id,
            'operator': qdict.get('operator_{}'.format(index), 'eq'),
            'expected': qdict.get('expected_{}'.format(index), ''),
        })
    return engine.normalize_rule({
        'id': qdict.get('rule_id') or uuid.uuid4().hex,
        'name': qdict.get('name', ''), 'enabled': qdict.get('enabled') == 'on',
        'mode': qdict.get('mode', 'all'), 'conditions': conditions,
        'hold_seconds': qdict.get('hold_seconds', 0),
        'repeat_seconds': qdict.get('repeat_seconds', 0),
        'notify_on_clear': qdict.get('notify_on_clear') == 'on',
        'severity': qdict.get('severity', 'warning'),
        'channels': [channel for channel in engine.CHANNELS
                     if qdict.get('channel_' + channel) == 'on'],
    })


class settings_page(ProtectedPage):
    def GET(self):
        return self.plugin_render.automation_rules(
            plugin_options, load_rules(), _new_rule(), _display_history(),
            _provider_catalog(), load_states(), log.events(NAME), '')

    def POST(self):
        qdict = web.input()
        verify_csrf(qdict)
        action = qdict.get('action', '')
        error = ''
        try:
            if action == 'save_settings':
                plugin_options['enabled'] = qdict.get('enabled') == 'on'
                plugin_options['test_mode'] = qdict.get('test_mode') == 'on'
                plugin_options['poll_interval'] = max(
                    5, min(3600, int(qdict.get('poll_interval', 30))))
                plugin_options['history_limit'] = max(
                    10, min(5000, int(qdict.get('history_limit', 500))))
            elif action == 'save_rule':
                saved = _rule_from_input(qdict)
                rules = load_rules()
                for index, rule in enumerate(rules):
                    if rule['id'] == saved['id']:
                        rules[index] = saved
                        break
                else:
                    rules.append(saved)
                save_rules(rules)
            elif action == 'delete_rule':
                rule_id = str(qdict.get('rule_id', ''))
                save_rules([item for item in load_rules()
                            if item['id'] != rule_id])
                states = load_states()
                states.pop(rule_id, None)
                save_states(states)
            elif action == 'test_rule':
                test_rule(str(qdict.get('rule_id', '')))
            elif action == 'test_notifications':
                send_test_notifications(_rule_from_input(qdict))
            elif action == 'clear_history':
                clear_history()
        except (ValueError, TypeError, engine.RuleValidationError) as exception:
            error = str(exception)
        if not error:
            raise web.seeother(plugin_url(settings_page), True)
        return self.plugin_render.automation_rules(
            plugin_options, load_rules(), _new_rule(), _display_history(),
            _provider_catalog(), load_states(), log.events(NAME), error)


class notifications_json(ProtectedPage):
    def GET(self):
        web.header('Content-Type', 'application/json; charset=utf-8')
        return json.dumps({'notifications': local_notifications()},
                          ensure_ascii=False, allow_nan=False)


class help_page(ProtectedPage):
    def GET(self):
        return self.plugin_render.automation_rules_help()
