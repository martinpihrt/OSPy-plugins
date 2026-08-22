# -*- coding: utf-8 -*-
"""Graphical automation rules over cached ospy.provider.v1 snapshots."""

import datetime
import json
import os
import time
import traceback
import uuid
from threading import RLock, Thread

import web
import plugins as ospy_plugins

from ospy.helpers import datetime_string, verify_csrf
from ospy.log import log
from ospy.provider_contracts import validate_snapshot
from ospy.webpages import ProtectedPage, pluginScripts
from plugins import (
    PluginOptions, get, get_runtime, plugin_data_dir,
    plugin_provider_capabilities, plugin_provider_modules,
    plugin_provider_snapshots, plugin_url, running,
)

from . import engine, sensor_provider, system_provider, time_provider


NAME = 'Automation Rules'
MENU = _('Package: Automation Rules')
LINK = 'settings_page'
MAX_RULES = 100
SCRIPT_PATH = 'automation_rules/static/automation_rules.js?v=1.1.0'

plugin_options = PluginOptions(NAME, {
    'enabled': False,
    'test_mode': True,
    'control_enabled': False,
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
    'control_actions': 0, 'control_errors': 0,
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
    try:
        providers[system_provider.PROVIDER_ID] = validate_snapshot(
            system_provider.provider_snapshot(), system_provider.PROVIDER_ID)
    except Exception as error:
        errors[system_provider.PROVIDER_ID] = {
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


def _provider_catalog(snapshots=None):
    catalog = []
    if snapshots is None:
        snapshots = _automation_snapshots()
    modules = list(plugin_provider_modules()) + [
        sensor_provider.PROVIDER_ID, time_provider.PROVIDER_ID,
        system_provider.PROVIDER_ID,
    ]
    for module in modules:
        try:
            capabilities = (
                sensor_provider.provider_capabilities()
                if module == sensor_provider.PROVIDER_ID else
                time_provider.provider_capabilities()
                if module == time_provider.PROVIDER_ID else
                system_provider.provider_capabilities()
                if module == system_provider.PROVIDER_ID else
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
                            'ospy_system': _('OSPy status'),
                        }.get(module, module),
                        'resource_id': resource.get('id', ''),
                        'resource_label': (
                            resource.get('name') if resource.get('name') else
                            _('OSPy local time')
                            if module == time_provider.PROVIDER_ID else
                            _('OSPy system')
                            if module == system_provider.PROVIDER_ID else
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
                            'scheduler_enabled': _('Scheduler enabled'),
                            'manual_mode': _('Manual mode'),
                            'scheduled_mode': _('Scheduled mode'),
                            'water_level_percent': _('Water level adjustment'),
                            'rain_delay_seconds': _('Rain delay remaining'),
                            'rain_sensor_enabled': _('Rain sensor enabled'),
                            'rain_sensor_active': _('Rain sensor active'),
                            'ospy_update_available': _('OSPy update available'),
                            'plugin_update_available': _('Plug-in update available'),
                            'plugin_update_count': _('Available plug-in updates'),
                            'any_update_available': _('Any update available'),
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


def _action_catalog(snapshots=None):
    """Return built-in and provider-declared actions for the graphical editor."""
    from ospy.programs import programs
    from ospy.stations import stations

    station_targets = [
        {'value': str(station.index),
         'label': '{}. {}'.format(station.index + 1, station.name)}
        for station in stations.get()
        if not station.is_master and not station.is_master_two and
        not station.is_master_by_program
    ]
    program_targets = [{'value': '*', 'label': _('Every running program')}]
    program_targets.extend({
        'value': str(index),
        'label': '{}. {}'.format(index + 1, program.name),
    } for index, program in enumerate(programs.get()))
    result = [
        {'key': 'stop_station', 'type': 'stop_station',
         'label': _('Stop selected station'), 'targets': station_targets,
         'target_label': _('Station'), 'value_kind': 'none'},
        {'key': 'stop_all_outputs', 'type': 'stop_all_outputs',
         'label': _('Stop all outputs'), 'targets': [],
         'target_label': '', 'value_kind': 'none'},
        {'key': 'disable_scheduler', 'type': 'disable_scheduler',
         'label': _('Disable scheduler'), 'targets': [],
         'target_label': '', 'value_kind': 'none'},
        {'key': 'stop_program', 'type': 'stop_program',
         'label': _('Stop running program'), 'targets': program_targets,
         'target_label': _('Program'), 'value_kind': 'none'},
        {'key': 'output_on', 'type': 'output_on',
         'label': _('Turn output on'), 'targets': station_targets,
         'target_label': _('Output'), 'value_kind': 'duration',
         'value_label': _('Duration in seconds')},
        {'key': 'output_off', 'type': 'output_off',
         'label': _('Turn output off'), 'targets': station_targets,
         'target_label': _('Output'), 'value_kind': 'none'},
        {'key': 'set_water_level', 'type': 'set_water_level',
         'label': _('Set water level adjustment'), 'targets': [],
         'target_label': '', 'value_kind': 'percent',
         'value_label': _('Water level percent')},
    ]
    snapshots = _automation_snapshots() if snapshots is None else snapshots
    for module in plugin_provider_modules():
        try:
            capabilities = plugin_provider_capabilities(module)
            resources = snapshots.get('providers', {}).get(module, {}).get(
                'resources', [])
            targets = [{'value': item.get('id', ''),
                        'label': item.get('name') or item.get('id', '')}
                       for item in resources if item.get('id')]
            targets.insert(0, {'value': '', 'label': _('Provider default')})
            for action in capabilities.get('actions', []):
                action_id = action.get('id', '')
                result.append({
                    'key': 'provider::{}::{}'.format(module, action_id),
                    'type': 'provider_action',
                    'provider_id': module, 'provider_action_id': action_id,
                    'label': '{} – {}'.format(module, action_id),
                    'targets': targets, 'target_label': _('Resource'),
                    'value_kind': 'parameters',
                    'value_label': _('Parameters (JSON object)'),
                    'risk': action.get('risk', 'control'),
                })
        except Exception:
            log.error(NAME, _('Unable to read provider actions') + ': ' + module)
    return result


def _configured_action_key(action):
    if action.get('type') == 'provider_action':
        return 'provider::{}::{}'.format(
            action.get('provider_id', ''), action.get('provider_action_id', ''))
    return action.get('type', '')


def _display_history():
    event_labels = {
        'triggered': _('Triggered'), 'repeated': _('Repeated'),
        'cleared': _('Returned to normal'),
        'test_matched': _('Test matched'),
        'test_not_matched': _('Test did not match'),
        'notification_test': _('Test notification'),
        'unlocked': _('Incident unlocked'),
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
        'simulated': _('Simulated'), 'blocked': _('Blocked'),
        'executed': _('Executed'),
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
        record['actions_text'] = ', '.join(
            '{}: {}'.format(value.get('label', value.get('type', _('Unknown'))),
                            status_labels.get(value.get('status'), _('Unknown')))
            for value in item.get('action_results', [])
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


def _condition_definitions(catalog):
    return {
        (item['provider_id'], item['resource_id'], item['value_id']): item
        for item in catalog
    }


def _configured_condition_text(condition, definitions):
    operators = {
        'eq': '=', 'ne': '!=', 'gt': '>', 'gte': '>=', 'lt': '<', 'lte': '<=',
        'between': _('is in range'), 'not_between': _('is outside range'),
        'is_true': _('is active'), 'is_false': _('is inactive'),
    }
    definition = definitions.get((
        condition.get('provider_id'), condition.get('resource_id'),
        condition.get('value_id'),
    ), {})
    resource = definition.get('resource_label') or condition.get('resource_id', '')
    value = definition.get('value_label') or condition.get('value_id', '')
    label = '{} – {}'.format(resource, value) if resource else value
    operator = condition.get('operator', 'eq')
    operator_label = operators.get(operator, operator)
    if operator in ('is_true', 'is_false'):
        return '{} {}'.format(label, operator_label)
    expected = condition.get('expected', '')
    if operator in ('between', 'not_between'):
        expected = str(expected).replace('..', ' – ')
    else:
        expected = _display_value(expected, definition.get('unit', ''))
    return '{} {} {}'.format(label, operator_label, expected)


def _rule_header_summary(rule, catalog=None):
    """Describe configured conditions and notification channels for a card header."""
    definitions = _condition_definitions(
        catalog if catalog is not None else _provider_catalog())
    conditions = [
        _configured_condition_text(condition, definitions)
        for condition in rule.get('conditions', [])
    ]

    connector = ' {} '.format(_('AND') if rule.get('mode') == 'all' else _('OR'))
    condition_text = connector.join(conditions)
    channel_labels = {
        'home': _('OSPy Home window'), 'browser': _('Browser notification'),
        'email': _('E-mail'), 'telegram': _('Telegram'),
        'push': _('Push notification'),
    }
    channels = [channel_labels.get(channel, channel)
                for channel in rule.get('channels', [])]
    notification_text = (', '.join(channels) if channels else
                         _('no notification channel'))
    action_labels = {
        'stop_station': _('stop station'),
        'stop_all_outputs': _('stop all outputs'),
        'disable_scheduler': _('disable scheduler'),
        'stop_program': _('stop program'),
        'output_on': _('turn output on'), 'output_off': _('turn output off'),
        'set_water_level': _('set water level'),
        'provider_action': _('run provider action'),
    }
    actions = [action_labels.get(item.get('type'), item.get('type', ''))
               for item in rule.get('actions', [])]
    outcome = '{} {}'.format(_('notify via'), notification_text)
    if actions:
        outcome += '; {} {}'.format(_('perform'), ', '.join(actions))
    if rule.get('latch_incident'):
        outcome += '; ' + _('lock incident')
    return '{} → {}'.format(condition_text, outcome)


def _rules_for_display(rules, catalog):
    result = []
    for rule in rules:
        displayed = dict(rule)
        displayed['header_summary'] = _rule_header_summary(rule, catalog)
        displayed['actions'] = []
        for action in rule.get('actions', []):
            editor_action = dict(action)
            editor_action['editor_key'] = _configured_action_key(action)
            editor_action['editor_value'] = (
                json.dumps(action.get('parameters', {}), ensure_ascii=False)
                if action.get('type') == 'provider_action' else
                action.get('value', ''))
            displayed['actions'].append(editor_action)
        result.append(displayed)
    return result


def _mobile_rule_card(rule, evaluation, state, catalog, automation_enabled=True):
    definitions = _condition_definitions(catalog)
    results = {
        item.get('id'): item for item in (evaluation or {}).get('conditions', [])
    }
    if not automation_enabled:
        card_status, state_text = 'unknown', _('Automation disabled')
    elif not rule.get('enabled'):
        card_status, state_text = 'unknown', _('Disabled')
    elif not evaluation or not evaluation.get('available'):
        card_status, state_text = 'warning', _('Unavailable')
    elif state.get('active'):
        card_status = ('error' if rule.get('severity') in ('error', 'critical')
                       else 'warning')
        state_text = _('Triggered')
    elif evaluation.get('matched'):
        card_status, state_text = 'warning', _('Conditions active')
    else:
        card_status, state_text = 'ok', _('Ready')

    metrics = [
        {'id': 'enabled', 'label': _('Enabled'),
         'value': _('Yes') if rule.get('enabled') else _('No'), 'unit': ''},
        {'id': 'state', 'label': _('Rule state'), 'value': state_text, 'unit': ''},
        {'id': 'incident_locked', 'label': _('Incident locked'),
         'value': _('Yes') if state.get('latched') else _('No'), 'unit': ''},
        {'id': 'control_actions', 'label': _('Configured control actions'),
         'value': len(rule.get('actions', [])), 'unit': ''},
    ]
    for index, condition in enumerate(rule.get('conditions', [])):
        result = results.get(condition.get('id'), {})
        if not automation_enabled or not rule.get('enabled'):
            condition_state = _('Not evaluated')
        elif not result.get('available'):
            condition_state = _('Unavailable')
        elif result.get('matched'):
            condition_state = _('Active')
        else:
            condition_state = _('Inactive')
        metrics.append({
            'id': 'condition_{}'.format(index + 1),
            'label': _configured_condition_text(condition, definitions),
            'value': condition_state, 'unit': '',
        })
    if state.get('last_evaluation'):
        metrics.append({
            'id': 'last_evaluation', 'label': _('Last evaluation'),
            'value': datetime_string(time.localtime(state['last_evaluation'])),
            'unit': '',
        })
    return {
        'id': 'rule_{}'.format(rule['id']), 'kind': 'metrics',
        'title': rule['name'], 'status': card_status,
        'summary': state_text, 'metrics': metrics,
    }


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


def _action_label(action):
    labels = {
        'stop_station': _('Stop selected station'),
        'stop_all_outputs': _('Stop all outputs'),
        'disable_scheduler': _('Disable scheduler'),
        'stop_program': _('Stop running program'),
        'output_on': _('Turn output on'),
        'output_off': _('Turn output off'),
        'set_water_level': _('Set water level adjustment'),
        'provider_action': _('Provider action'),
    }
    return labels.get(action.get('type'), action.get('type', _('Unknown')))


def _finish_station_runs(station_ids):
    from ospy.stations import stations

    station_ids = set(station_ids)
    for interval in list(log.active_runs()):
        if interval.get('station') in station_ids:
            log.finish_run(interval)
    for station_id in station_ids:
        stations.deactivate(station_id)


def _execute_control_action(action):
    """Execute one normalized action and return a JSON-safe result."""
    from ospy.options import options
    from ospy.programs import programs
    from ospy.runonce import run_once
    from ospy.stations import stations

    action_type = action['type']
    if action_type == 'stop_station':
        station_id = int(action['target'])
        if not 0 <= station_id < stations.count():
            raise ValueError(_('Selected station does not exist.'))
        _finish_station_runs([station_id])
        detail = stations.get(station_id).name
    elif action_type == 'stop_all_outputs':
        programs.run_now_program = None
        run_once.clear()
        log.finish_run(None)
        stations.clear()
        try:
            from ospy.outputs import outputs
            outputs.relay_output = False
        except Exception:
            log.error(NAME, _('Unable to switch off the master relay.') + '\n' +
                      traceback.format_exc())
        detail = _('All outputs stopped')
    elif action_type == 'disable_scheduler':
        options.scheduler_enabled = False
        detail = _('Scheduler disabled')
    elif action_type == 'stop_program':
        target = action['target']
        matched = []
        for interval in list(log.active_runs()):
            if target == '*' or interval.get('program') == int(target):
                matched.append(interval.get('station'))
                log.finish_run(interval)
        for station_id in set(item for item in matched if isinstance(item, int)):
            stations.deactivate(station_id)
        running_program = programs.run_now_program
        if running_program is not None and (
                target == '*' or getattr(running_program, 'index', None) == int(target)):
            programs.run_now_program = None
        if target == '*':
            run_once.clear()
        detail = _('Stopped active program runs')
    elif action_type == 'output_off':
        station_id = int(action['target'])
        if not 0 <= station_id < stations.count():
            raise ValueError(_('Selected output does not exist.'))
        _finish_station_runs([station_id])
        detail = stations.get(station_id).name
    elif action_type == 'output_on':
        station_id = int(action['target'])
        if not options.manual_mode:
            raise RuntimeError(_('Manual mode is required before an automation can turn on an output.'))
        if not 0 <= station_id < stations.count():
            raise ValueError(_('Selected output does not exist.'))
        station = stations.get(station_id)
        if (not station.enabled or station.is_master or station.is_master_two or
                station.is_master_by_program):
            raise RuntimeError(_('The selected output cannot be started directly.'))
        start = datetime.datetime.now()
        duration = int(action['value'])
        interval = {
            'active': True, 'program': -1, 'station': station_id,
            'program_name': _('Automation Rules'), 'fixed': True,
            'cut_off': 0, 'manual': True, 'blocked': False,
            'start': start, 'original_start': start,
            'end': start + datetime.timedelta(seconds=duration),
            'uid': '{}-automation-{}-{}'.format(start, station_id, action['id']),
            'usage': station.usage,
        }
        log.start_run(interval)
        stations.activate(station_id)
        detail = '{} ({} {})'.format(station.name, duration, _('seconds'))
    elif action_type == 'set_water_level':
        options.level_adjustment = float(action['value']) / 100.0
        detail = '{} %'.format(_display_value(float(action['value'])))
    elif action_type == 'provider_action':
        execute = getattr(ospy_plugins, 'plugin_provider_execute_action', None)
        if not callable(execute):
            raise RuntimeError(_('This OSPy version does not support provider actions.'))
        provider_result = execute(
            action['provider_id'], action['provider_action_id'],
            action.get('resource_id', ''), action.get('parameters', {}))
        if provider_result.get('status') not in ('ok', 'executed', 'success'):
            raise RuntimeError(str(provider_result.get('message') or
                                   provider_result.get('status') or
                                   _('Provider action failed.')))
        detail = str(provider_result.get('message') or action['provider_action_id'])
    else:
        raise ValueError(_('Unsupported control action.'))
    return {'action_id': action['id'], 'type': action_type,
            'label': _action_label(action), 'status': 'executed',
            'detail': detail}


def execute_control_actions(rule, test_mode=False):
    results = []
    for action in rule.get('actions', []):
        if test_mode:
            results.append({'action_id': action['id'], 'type': action['type'],
                            'label': _action_label(action),
                            'status': 'simulated'})
            continue
        if not plugin_options.get('control_enabled', False):
            results.append({'action_id': action['id'], 'type': action['type'],
                            'label': _action_label(action),
                            'status': 'blocked',
                            'detail': _('Control actions are disabled.')})
            continue
        try:
            results.append(_execute_control_action(action))
            with health_lock:
                health_state['control_actions'] += 1
        except Exception as error:
            results.append({'action_id': action['id'], 'type': action['type'],
                            'label': _action_label(action), 'status': 'error',
                            'error': type(error).__name__, 'detail': str(error)})
            with health_lock:
                health_state['control_errors'] += 1
                health_state['last_error'] = time.time()
                health_state['last_error_message'] = '{}: {}'.format(
                    type(error).__name__, error)
            log.error(NAME, _('Automation control action failed') + ': ' +
                      '{}\n{}'.format(_action_label(action), traceback.format_exc()))
    return results


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


def _history_record(rule, event, evaluation, results, test_mode,
                    action_results=None):
    return {
        'timestamp': int(time.time()), 'datetime': datetime_string(),
        'rule_id': rule['id'], 'rule_name': rule['name'], 'event': event,
        'matched': bool(evaluation.get('matched')),
        'available': bool(evaluation.get('available')),
        'test_mode': bool(test_mode), 'results': results,
        'action_results': list(action_results or []),
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
    cycle_action_error = False
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
            action_results = (execute_control_actions(rule, test_mode=is_test)
                              if event == 'triggered' else [])
            cycle_action_error = cycle_action_error or any(
                item.get('status') == 'error' for item in action_results)
            results = dispatch_notifications(
                rule, event, test_mode=is_test, evaluation=evaluation)
            append_history(_history_record(
                rule, event, evaluation, results, is_test, action_results))
            with health_lock:
                health_state['last_action'] = time.time()
    if is_test:
        _test_states = states
    else:
        save_states(states)
    with health_lock:
        health_state['last_cycle'] = time.time()
        if not cycle_action_error:
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
    action_results = (execute_control_actions(rule, test_mode=True)
                      if evaluation['matched'] else [])
    append_history(_history_record(rule, event, evaluation, [
        {'channel': channel, 'status': 'test'} for channel in rule['channels']
    ], True, action_results))
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


def unlock_incident(rule_id):
    rules = {item['id']: item for item in load_rules()}
    rule = rules.get(rule_id)
    if rule is None:
        raise engine.RuleValidationError('rule was not found')
    evaluation = engine.evaluate_rule(rule, _automation_snapshots())
    if not evaluation.get('available'):
        raise engine.RuleValidationError(
            _('The incident cannot be unlocked while a condition is unavailable.'))
    if evaluation.get('matched'):
        raise engine.RuleValidationError(
            _('The incident cannot be unlocked while its conditions are still active.'))
    states = load_states()
    state = dict(states.get(rule_id, {}))
    state.update({'active': False, 'latched': False, 'matched_since': 0,
                  'last_trigger': 0, 'last_evaluation': int(time.time())})
    states[rule_id] = state
    save_states(states)
    append_history(_history_record(rule, 'unlocked', evaluation, [], False))


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
        _('Control actions enabled'): (_('Yes') if plugin_options.get('control_enabled')
                                       else _('No')),
        _('Saved rules'): len(load_rules()),
        _('Evaluated rules'): state['evaluated_rules'],
        _('Active rules'): state['active_rules'],
        _('Provider errors'): state['provider_errors'],
        _('Executed control actions'): state['control_actions'],
        _('Control action errors'): state['control_errors'],
        _('Locked incidents'): sum(1 for value in load_states().values()
                                   if value.get('latched')),
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


def mobile_status():
    result = health()
    return {
        'status': result.get('status', 'unknown'),
        'title': _('Automation Rules'),
        'summary': result.get('summary', ''),
        'updated': datetime_string(),
    }


def mobile_cards(**_kwargs):
    """Expose each rule and every current condition result without changing state."""
    rules = load_rules()
    states = load_states()
    automation_enabled = bool(plugin_options.get('enabled'))
    snapshots = {'providers': {}, 'errors': {}}
    catalog = []
    if automation_enabled:
        try:
            snapshots = _automation_snapshots()
            catalog = _provider_catalog(snapshots)
        except Exception:
            snapshots = {'providers': {}, 'errors': {}}
    cards = []
    for rule in rules:
        evaluation = None
        if automation_enabled and rule.get('enabled'):
            try:
                evaluation = engine.evaluate_rule(rule, snapshots)
            except Exception:
                evaluation = {
                    'available': False, 'matched': False, 'conditions': [],
                }
        cards.append(_mobile_rule_card(
            rule, evaluation, states.get(rule['id'], {}), catalog,
            automation_enabled=automation_enabled))
    return cards


def _new_rule():
    return {
        'id': uuid.uuid4().hex, 'name': '', 'enabled': True, 'mode': 'all',
        'conditions': [{
            'id': uuid.uuid4().hex, 'provider_id': '', 'resource_id': '',
            'value_id': '', 'operator': 'lte', 'expected': 0,
        }],
        'hold_seconds': 0, 'repeat_seconds': 0,
        'notify_on_clear': True, 'severity': 'warning', 'channels': [],
        'actions': [], 'latch_incident': False,
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
    action_count = max(0, min(20, int(qdict.get('action_count', 0))))
    actions = []
    for index in range(action_count):
        action_key = str(qdict.get('action_key_{}'.format(index), '')).strip()
        if not action_key:
            continue
        provider_id = ''
        provider_action_id = ''
        action_type = action_key
        if action_key.startswith('provider::'):
            parts = action_key.split('::', 2)
            if len(parts) != 3:
                raise engine.RuleValidationError('invalid provider action')
            action_type = 'provider_action'
            provider_id, provider_action_id = parts[1], parts[2]
        parameters_text = str(
            qdict.get('action_value_{}'.format(index), '') or '').strip()
        parameters = {}
        value = parameters_text
        if action_type == 'provider_action':
            try:
                parameters = json.loads(parameters_text or '{}')
            except (TypeError, ValueError):
                raise engine.RuleValidationError('provider action parameters must be valid JSON')
        actions.append({
            'id': qdict.get('action_id_{}'.format(index)) or uuid.uuid4().hex,
            'type': action_type,
            'target': qdict.get('action_target_{}'.format(index), ''),
            'value': value, 'provider_id': provider_id,
            'provider_action_id': provider_action_id,
            'resource_id': (qdict.get('action_target_{}'.format(index), '')
                            if action_type == 'provider_action' else ''),
            'parameters': parameters,
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
        'actions': actions,
        'latch_incident': qdict.get('latch_incident') == 'on',
    })


class settings_page(ProtectedPage):
    def GET(self):
        request = web.input(open_rule='')
        catalog = _provider_catalog()
        return self.plugin_render.automation_rules(
            plugin_options, _rules_for_display(load_rules(), catalog),
            _new_rule(), _display_history(), catalog, _action_catalog(), load_states(),
            log.events(NAME), '', str(request.get('open_rule', '')))

    def POST(self):
        from ospy import server

        qdict = web.input()
        verify_csrf(qdict)
        action = qdict.get('action', '')
        error = ''
        open_rule = ''
        try:
            if action == 'save_settings':
                requested_control = qdict.get('control_enabled') == 'on'
                if (requested_control != plugin_options.get('control_enabled', False)
                        and server.session.get('category') != 'admin'):
                    raise engine.RuleValidationError(
                        _('Only an administrator can change control action settings.'))
                plugin_options['enabled'] = qdict.get('enabled') == 'on'
                plugin_options['test_mode'] = qdict.get('test_mode') == 'on'
                plugin_options['control_enabled'] = requested_control
                plugin_options['poll_interval'] = max(
                    5, min(3600, int(qdict.get('poll_interval', 30))))
                plugin_options['history_limit'] = max(
                    10, min(5000, int(qdict.get('history_limit', 500))))
            elif action == 'save_rule':
                saved = _rule_from_input(qdict)
                if ((saved.get('actions') or saved.get('latch_incident')) and
                        server.session.get('category') != 'admin'):
                    raise engine.RuleValidationError(
                        _('Only an administrator can configure control actions.'))
                rules = load_rules()
                for index, rule in enumerate(rules):
                    if rule['id'] == saved['id']:
                        rules[index] = saved
                        break
                else:
                    rules.append(saved)
                save_rules(rules)
                open_rule = saved['id']
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
            elif action == 'unlock_incident':
                if server.session.get('category') != 'admin':
                    raise engine.RuleValidationError(
                        _('Only an administrator can unlock an incident.'))
                unlock_incident(str(qdict.get('rule_id', '')))
                open_rule = str(qdict.get('rule_id', ''))
            elif action == 'clear_history':
                clear_history()
        except (ValueError, TypeError, engine.RuleValidationError) as exception:
            error = str(exception)
        if not error:
            target = plugin_url(settings_page)
            if open_rule:
                target += '?open_rule={}'.format(open_rule)
            raise web.seeother(target, True)
        catalog = _provider_catalog()
        return self.plugin_render.automation_rules(
            plugin_options, _rules_for_display(load_rules(), catalog),
            _new_rule(), _display_history(), catalog, _action_catalog(), load_states(),
            log.events(NAME), error, str(qdict.get('rule_id', '')))


class notifications_json(ProtectedPage):
    def GET(self):
        web.header('Content-Type', 'application/json; charset=utf-8')
        return json.dumps({'notifications': local_notifications()},
                          ensure_ascii=False, allow_nan=False)


class help_page(ProtectedPage):
    def GET(self):
        return self.plugin_render.automation_rules_help()
