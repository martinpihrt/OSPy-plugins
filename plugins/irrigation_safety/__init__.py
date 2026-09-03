# -*- coding: utf-8 -*-
"""Independent flow, pressure and tank safety for OSPy irrigation outputs."""

import datetime
import json
import queue
import time
import traceback
import uuid
from threading import Lock, RLock, Thread

import web

import plugins as ospy_plugins
from ospy.helpers import datetime_string, verify_csrf
from ospy.log import log
from ospy.options import options
from ospy.programs import programs
from ospy.runonce import run_once
from ospy.stations import stations
from ospy.webpages import ProtectedPage, clear_plugin_runtime_data, showInFooter
from plugins import PluginOptions, get, get_runtime, plugin_url, running
from plugins.irrigation_safety import model


NAME = 'Irrigation Safety'
MENU = _('Package: Irrigation Safety')
LINK = 'settings_page'
ERROR_LOG_THROTTLE = 300


plugin_options = PluginOptions(NAME, {
    'mode': 'off',
    'check_interval': 2,
    'data_timeout': 10,
    'history_limit': 500,
    'use_footer': True,
    'send_email': True,
    'send_push': True,
    'notify_recovery': True,
    'stop_all_outputs': True,
    'disable_scheduler': True,
    'latch_incidents': True,
    'unexpected_flow_enabled': True,
    'unexpected_flow_lpm': 0.5,
    'unexpected_flow_confirm': 20,
    'pressure_enabled': False,
    'pressure_confirm': 10,
    'tank_enabled': False,
    'tank_provider_id': 'tank_monitor',
    'tank_resource_id': 'main',
    'tank_value_id': 'fill_percent',
    'tank_minimum': 10.0,
    'tank_confirm': 10,
    'profiles': [],
    'incidents': {},
    'history': [],
    'bypass_until': 0,
})
runtime = get_runtime()
state_lock = RLock()
health_lock = Lock()
health_state = {
    'last_cycle': 0,
    'last_error': 0,
    'last_error_message': '',
    'provider_errors': 0,
    'safety_actions': 0,
    'notification_errors': 0,
}


def _safe_int(value, default=0):
    return model.safe_int(value, default)


def _safe_float(value, default=0.0):
    return model.safe_float(value, default)


def _mode():
    value = str(plugin_options.get('mode', 'off'))
    return value if value in model.MODES else 'off'


def _station_rows():
    return [
        (station.index, station.name)
        for station in stations.get()
        if station.enabled and not station.is_master and
        not station.is_master_two and not station.is_master_by_program
    ]


def _profiles(save=True):
    current = plugin_options.get('profiles', [])
    normalized = model.normalize_profiles(current, _station_rows())
    if save and normalized != current:
        plugin_options['profiles'] = normalized
    return normalized


def _profile(station_id):
    return next((item for item in _profiles()
                 if int(item['station_id']) == int(station_id)), None)


def _save_profile(updated):
    with state_lock:
        profiles = _profiles(save=False)
        for index, profile in enumerate(profiles):
            if int(profile['station_id']) == int(updated['station_id']):
                profiles[index] = updated
                break
        plugin_options['profiles'] = profiles


def _profile_from_input(qdict, current):
    updated = dict(current)
    updated.update({
        'enabled': qdict.get('enabled') == 'on',
        'minimum_flow_lpm': _safe_float(
            qdict.get('minimum_flow_lpm'), current['minimum_flow_lpm']),
        'maximum_flow_lpm': _safe_float(
            qdict.get('maximum_flow_lpm'), current['maximum_flow_lpm']),
        'startup_delay': _safe_int(
            qdict.get('startup_delay'), current['startup_delay']),
        'confirm_seconds': _safe_int(
            qdict.get('confirm_seconds'), current['confirm_seconds']),
        'learning_samples': _safe_int(
            qdict.get('learning_samples'), current['learning_samples']),
        'learning_tolerance_percent': _safe_float(
            qdict.get('learning_tolerance_percent'),
            current['learning_tolerance_percent']),
        'learning_minimum_margin_lpm': _safe_float(
            qdict.get('learning_minimum_margin_lpm'),
            current['learning_minimum_margin_lpm']),
    })
    updated = model.normalize_profile(
        updated, current['station_id'], current['name'])
    try:
        model.validate_profile(updated)
    except ValueError:
        raise ValueError(_('Minimum flow must be lower than maximum flow.'))
    return updated


def _normalize_settings():
    plugin_options['mode'] = _mode()
    plugin_options['check_interval'] = model.clamp(
        _safe_int(plugin_options.get('check_interval'), 2),
        model.MIN_CHECK_INTERVAL, model.MAX_CHECK_INTERVAL)
    plugin_options['data_timeout'] = model.clamp(
        _safe_int(plugin_options.get('data_timeout'), 10), 3, 3600)
    plugin_options['history_limit'] = model.clamp(
        _safe_int(plugin_options.get('history_limit'), 500), 10, model.MAX_HISTORY)
    plugin_options['unexpected_flow_lpm'] = model.clamp(
        _safe_float(plugin_options.get('unexpected_flow_lpm'), 0.5),
        0.01, 1000000.0)
    plugin_options['unexpected_flow_confirm'] = model.clamp(
        _safe_int(plugin_options.get('unexpected_flow_confirm'), 20), 1, 3600)
    plugin_options['pressure_confirm'] = model.clamp(
        _safe_int(plugin_options.get('pressure_confirm'), 10), 1, 3600)
    plugin_options['tank_minimum'] = model.clamp(
        _safe_float(plugin_options.get('tank_minimum'), 10.0), 0.0, 1000000.0)
    plugin_options['tank_confirm'] = model.clamp(
        _safe_int(plugin_options.get('tank_confirm'), 10), 1, 3600)
    plugin_options['bypass_until'] = max(
        0, _safe_int(plugin_options.get('bypass_until'), 0))
    _profiles()


def _iso_epoch(value):
    try:
        text = str(value or '')
        if text.endswith('Z'):
            text = text[:-1] + '+00:00'
        parsed = datetime.datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=datetime.timezone.utc)
        return parsed.timestamp()
    except (TypeError, ValueError, OverflowError):
        return 0


def _snapshot_value(snapshots, provider_id, resource_id, value_id, now=None):
    now = time.time() if now is None else now
    provider = snapshots.get('providers', {}).get(provider_id)
    if not isinstance(provider, dict) or provider.get('status') != 'ok':
        return None, '', 'unavailable'
    resource = next((item for item in provider.get('resources', [])
                     if str(item.get('id')) == str(resource_id)), None)
    if not resource or resource.get('status') != 'ok':
        return None, '', 'unavailable'
    value = next((item for item in resource.get('values', [])
                  if str(item.get('id')) == str(value_id)), None)
    if not value or value.get('value') is None:
        return None, '', 'unavailable'
    observed_at = value.get('observed_at') or resource.get('observed_at') or provider.get('observed_at')
    observed_epoch = _iso_epoch(observed_at)
    if not observed_epoch or now - observed_epoch > plugin_options['data_timeout']:
        return None, value.get('unit', ''), 'stale'
    return value.get('value'), value.get('unit', ''), 'ok'


def _active_station_ids():
    active = stations.active()
    return [
        station.index for station in stations.get()
        if station.index < len(active) and active[station.index] and station.enabled and
        not station.is_master and not station.is_master_two and
        not station.is_master_by_program
    ]


def _master_active(snapshots, now):
    value, _unit, status = _snapshot_value(
        snapshots, 'pressure_monitor', 'main', 'master_active', now)
    if status == 'ok':
        return bool(value), status
    master_ids = [value for value in (
        getattr(stations, 'master', None), getattr(stations, 'master_two', None),
        getattr(stations, 'master_by_program', None)) if isinstance(value, int)]
    return any(stations.active(value) for value in master_ids), status


def _provider_snapshots():
    collector = getattr(ospy_plugins, 'plugin_provider_snapshots', None)
    if not callable(collector):
        return {'providers': {}, 'errors': {'ospy': 'provider contract unavailable'}}
    return collector()


def _relevant_provider_errors(snapshots):
    relevant = {'water_meter'}
    if plugin_options.get('pressure_enabled'):
        relevant.add('pressure_monitor')
    if plugin_options.get('tank_enabled'):
        relevant.add(str(plugin_options.get('tank_provider_id', 'tank_monitor')))
    return {
        key: value for key, value in snapshots.get('errors', {}).items()
        if key in relevant
    }


def _flow_reading(snapshots, now):
    value, unit, status = _snapshot_value(
        snapshots, 'water_meter', 'main', 'flow_lpm', now)
    return (_safe_float(value, None) if status == 'ok' else None), unit or 'L/min', status


def _tank_reading(snapshots, now):
    return _snapshot_value(
        snapshots,
        str(plugin_options.get('tank_provider_id', 'tank_monitor')),
        str(plugin_options.get('tank_resource_id', 'main')),
        str(plugin_options.get('tank_value_id', 'fill_percent')),
        now,
    )


def _fault_label(code):
    return {
        'flow_unavailable': _('Water flow measurement is unavailable'),
        'no_flow': _('No water flow was detected'),
        'low_flow': _('Water flow is below the expected range'),
        'high_flow': _('Water flow is above the expected range'),
        'unexpected_flow': _('Water is flowing while no irrigation station is active'),
        'pressure_unavailable': _('Pressure measurement is unavailable'),
        'pressure_missing': _('Pressure was not established'),
        'tank_unavailable': _('Tank level measurement is unavailable'),
        'tank_low': _('Tank level is below the safety limit'),
    }.get(code, _('Irrigation safety fault'))


def _history_event_label(event):
    return {
        'triggered': _('Incident triggered'),
        'cleared': _('Condition returned to normal'),
        'acknowledged': _('Incidents acknowledged'),
        'notification': _('Notification delivery'),
        'learning_started': _('Automatic learning started'),
        'learning_completed': _('Automatic learning completed'),
        'bypass_started': _('Temporary bypass started'),
        'bypass_cancelled': _('Temporary bypass cancelled'),
    }.get(event, _('Irrigation Safety event'))


def _mode_label(mode):
    return {
        'off': _('Off'), 'monitor': _('Monitor only'),
        'protect': _('Active protection'),
    }.get(mode, _('Off'))


def _append_history(event, code='', detail='', action='', severity='info'):
    with state_lock:
        records = list(plugin_options.get('history', []))
        records.insert(0, {
            'id': uuid.uuid4().hex,
            'timestamp': int(time.time()),
            'datetime': datetime_string(),
            'event': event,
            'event_label': _history_event_label(event),
            'code': code,
            'label': _fault_label(code) if code else '',
            'detail': str(detail),
            'action': str(action),
            'severity': severity,
        })
        plugin_options['history'] = records[:plugin_options['history_limit']]


def _stop_outputs():
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


def _execute_safety_actions():
    actions = []
    if plugin_options.get('stop_all_outputs', True):
        _stop_outputs()
        actions.append(_('All outputs stopped'))
    if plugin_options.get('disable_scheduler', True):
        options.scheduler_enabled = False
        actions.append(_('Scheduler disabled'))
    with health_lock:
        health_state['safety_actions'] += 1
    return '; '.join(actions) if actions else _('No control action configured')


class NotificationWorker(Thread):
    def __init__(self):
        Thread.__init__(self)
        self.daemon = True
        self._stop_event = runtime.stop_event
        self._queue = queue.Queue(maxsize=64)
        self.start()
        runtime.register_thread(self)

    def submit(self, event, incident, test=False):
        try:
            self._queue.put_nowait((event, dict(incident), bool(test)))
            return True
        except queue.Full:
            with health_lock:
                health_state['notification_errors'] += 1
            return False

    def stop(self):
        self._stop_event.set()

    def run(self):
        while not self._stop_event.is_set():
            try:
                item = self._queue.get(timeout=1)
            except queue.Empty:
                continue
            try:
                _deliver_notifications(*item)
            except Exception:
                with health_lock:
                    health_state['notification_errors'] += 1
                log.error(NAME, _('Irrigation Safety notification failed') + ':\n' +
                          traceback.format_exc())


def _notification_message(event, incident):
    if event == 'test':
        return _('This is a test notification from Irrigation Safety.')
    if event == 'cleared':
        return _('Irrigation safety condition returned to normal: {}.').format(
            incident.get('label', _fault_label(incident.get('code', ''))))
    message = _('Irrigation safety incident: {}.').format(
        incident.get('label', _fault_label(incident.get('code', ''))))
    if incident.get('detail'):
        message += ' ' + str(incident['detail'])
    if incident.get('action'):
        message += ' ' + _('Action: {}.').format(incident['action'])
    return message


def _deliver_notifications(event, incident, test=False):
    message = _notification_message('test' if test else event, incident)
    title = _('Irrigation Safety')
    results = []
    if plugin_options.get('send_email'):
        result = {'channel': 'email', 'status': 'unavailable'}
        for module in ('email_notifications_ssl', 'email_notifications'):
            if module not in running():
                continue
            method = getattr(get(module), 'try_mail', None)
            if callable(method):
                sent = method(message, message, attachment=None, subject=title)
                result = {'channel': 'email',
                          'status': 'sent' if sent is not False else 'error',
                          'provider': module}
                break
        results.append(result)
    if plugin_options.get('send_push'):
        try:
            from api.v1.push import push_dispatcher
            code = 'irrigation_safety_{}'.format('test' if test else event)
            queued = push_dispatcher.enqueue_notification({
                'id': 'irrigation-safety-{}-{}'.format(
                    incident.get('id', 'test'), int(time.time() * 1000)),
                'event_type': 'automation',
                'severity': 'info' if event in ('cleared', 'test') else 'critical',
                'code': code, 'title': title, 'message': message,
                'data': {
                    'source': 'irrigation_safety',
                    'event': event,
                    'incident_id': incident.get('id', ''),
                    'fault_code': incident.get('code', ''),
                },
            })
            results.append({'channel': 'push',
                            'status': 'queued' if queued else 'unavailable'})
        except Exception as error:
            results.append({'channel': 'push', 'status': 'error',
                            'error': type(error).__name__})
    if any(item.get('status') == 'error' for item in results):
        with health_lock:
            health_state['notification_errors'] += 1
    _append_history('notification', incident.get('code', ''),
                    json.dumps(results, ensure_ascii=False), '', 'info')


notification_worker = None


class SafetyWorker(Thread):
    def __init__(self):
        Thread.__init__(self)
        self.daemon = True
        self._stop_event = runtime.stop_event
        self.candidate_since = {}
        self.active_signature = ()
        self.active_since = 0
        self.learning_samples = {}
        self.current = self._empty_status()
        self.footer = None
        self._last_error_log = 0
        self.start()
        runtime.register_thread(self)

    @staticmethod
    def _empty_status():
        return {
            'updated': 0, 'mode': _mode(), 'flow_lpm': None,
            'flow_status': 'unavailable', 'active_stations': [],
            'expected_minimum': None, 'expected_maximum': None,
            'pressure': None, 'pressure_status': 'disabled',
            'tank': None, 'tank_unit': '', 'tank_status': 'disabled',
            'bypass': False, 'learning': {}, 'provider_errors': {},
        }

    def stop(self):
        self._stop_event.set()

    def update(self):
        self._stop_event.wait(0.01)

    def _log_problem(self, message):
        now = time.time()
        with health_lock:
            health_state['last_error'] = now
            health_state['last_error_message'] = str(message).splitlines()[-1]
        if now - self._last_error_log >= ERROR_LOG_THROTTLE:
            log.error(NAME, message)
            self._last_error_log = now

    def _sync_footer(self):
        if plugin_options.get('use_footer'):
            if self.footer is None:
                self.footer = showInFooter(
                    label=_('Irrigation Safety'), val='---',
                    button='irrigation_safety/settings')
            incidents = _incidents()
            locked = sum(1 for item in incidents.values() if item.get('latched'))
            if locked:
                self.footer.val = '{}: {}'.format(_('Locked incidents'), locked)
            elif self.current.get('flow_lpm') is not None:
                self.footer.val = '{}: {:.2f} L/min'.format(
                    _mode_label(_mode()), self.current['flow_lpm'])
            else:
                self.footer.val = _mode_label(_mode())
        elif self.footer is not None:
            clear_plugin_runtime_data('irrigation_safety')
            self.footer = None

    def _update_active_timing(self, active, now):
        signature = tuple(sorted(active))
        if signature != self.active_signature:
            self.active_signature = signature
            self.active_since = now if signature else 0
            self.candidate_since = {
                key: value for key, value in self.candidate_since.items()
                if key.startswith('unexpected_flow:')
            }

    def _candidate(self, result, code, scope, detail, confirm_seconds):
        key = '{}:{}'.format(code, scope)
        result[key] = {
            'key': key, 'code': code, 'scope': scope,
            'label': _fault_label(code), 'detail': detail,
            'confirm_seconds': int(confirm_seconds),
        }

    def _evaluate(self, snapshots, active, profiles, now):
        candidates = {}
        flow, flow_unit, flow_status = _flow_reading(snapshots, now)
        expected = model.expected_range(active, profiles)
        active_names = [stations.get(value).name for value in active]
        active_age = now - self.active_since if self.active_since else 0
        scope = ','.join(str(value) for value in sorted(active)) or 'none'
        learning_ids = {
            int(profile['station_id']) for profile in profiles
            if profile.get('learning')
        }

        if active and expected and active_age >= expected['startup_delay']:
            detail_range = _('Flow: {} L/min; expected: {} to {} L/min; stations: {}.').format(
                '---' if flow is None else round(flow, 3),
                round(expected['minimum'], 3), round(expected['maximum'], 3),
                ', '.join(active_names))
            if flow_status != 'ok':
                self._candidate(candidates, 'flow_unavailable', scope,
                                detail_range, expected['confirm_seconds'])
            else:
                fault = model.flow_fault(flow, expected)
                if fault and not (learning_ids.intersection(active)
                                  and fault in ('low_flow', 'high_flow')):
                    self._candidate(candidates, fault, scope, detail_range,
                                    expected['confirm_seconds'])
        elif (not active and plugin_options.get('unexpected_flow_enabled') and
              flow_status == 'ok' and flow is not None and
              flow >= plugin_options['unexpected_flow_lpm']):
            self._candidate(
                candidates, 'unexpected_flow', 'none',
                _('Flow: {} L/min; limit: {} L/min.').format(
                    round(flow, 3), plugin_options['unexpected_flow_lpm']),
                plugin_options['unexpected_flow_confirm'])

        pressure, pressure_status = None, 'disabled'
        if plugin_options.get('pressure_enabled') and active:
            master, master_status = _master_active(snapshots, now)
            pressure, _unit, pressure_status = _snapshot_value(
                snapshots, 'pressure_monitor', 'main', 'pressure_present', now)
            if active_age >= (expected['startup_delay'] if expected else 0):
                if pressure_status != 'ok' or master_status not in ('ok', 'unavailable'):
                    self._candidate(candidates, 'pressure_unavailable', scope,
                                    _('Pressure data is not current.'),
                                    plugin_options['pressure_confirm'])
                elif master and not bool(pressure):
                    self._candidate(candidates, 'pressure_missing', scope,
                                    _('The master output is active but pressure is absent.'),
                                    plugin_options['pressure_confirm'])

        tank, tank_unit, tank_status = None, '', 'disabled'
        if (plugin_options.get('tank_enabled') and active and
                active_age >= (expected['startup_delay'] if expected else 0)):
            tank, tank_unit, tank_status = _tank_reading(snapshots, now)
            if tank_status != 'ok':
                self._candidate(candidates, 'tank_unavailable', scope,
                                _('Tank data is not current.'),
                                plugin_options['tank_confirm'])
            elif _safe_float(tank, 0.0) < plugin_options['tank_minimum']:
                self._candidate(
                    candidates, 'tank_low', scope,
                    _('Tank value: {} {}; safety limit: {} {}.').format(
                        round(_safe_float(tank), 3), tank_unit,
                        plugin_options['tank_minimum'], tank_unit),
                    plugin_options['tank_confirm'])

        self.current = {
            'updated': int(now), 'mode': _mode(), 'flow_lpm': flow,
            'flow_status': flow_status, 'active_stations': active_names,
            'active_station_ids': active,
            'expected_minimum': expected['minimum'] if expected else None,
            'expected_maximum': expected['maximum'] if expected else None,
            'pressure': pressure, 'pressure_status': pressure_status,
            'tank': tank, 'tank_unit': tank_unit, 'tank_status': tank_status,
            'bypass': _bypass_active(now),
            'bypass_until': plugin_options.get('bypass_until', 0),
            'learning': self._learning_status(profiles),
            'provider_errors': _relevant_provider_errors(snapshots),
        }
        return candidates, flow, flow_status

    def _learning_status(self, profiles):
        return {
            str(profile['station_id']): {
                'active': bool(profile.get('learning')),
                'samples': len(self.learning_samples.get(
                    int(profile['station_id']), [])),
                'required': profile['learning_samples'],
            }
            for profile in profiles
        }

    def _learn(self, active, profiles, flow, flow_status, now):
        if len(active) != 1 or flow_status != 'ok' or flow is None or flow <= 0:
            return
        station_id = int(active[0])
        profile = next((item for item in profiles
                        if int(item['station_id']) == station_id), None)
        if not profile or not profile.get('learning'):
            return
        if now - self.active_since < profile['startup_delay']:
            return
        samples = self.learning_samples.setdefault(station_id, [])
        samples.append(float(flow))
        if len(samples) < profile['learning_samples']:
            return
        learned = model.learned_range(
            samples, profile['learning_tolerance_percent'],
            profile['learning_minimum_margin_lpm'])
        profile = dict(profile)
        profile['minimum_flow_lpm'] = learned['minimum']
        profile['maximum_flow_lpm'] = learned['maximum']
        profile['learning'] = False
        profile['enabled'] = True
        _save_profile(profile)
        self.learning_samples.pop(station_id, None)
        detail = _('Station {} learned a median flow of {} L/min and a safe range of {} to {} L/min from {} samples.').format(
            profile['name'], learned['median'], learned['minimum'],
            learned['maximum'], learned['samples'])
        _append_history('learning_completed', '', detail)
        log.info(NAME, detail)

    def _reconcile_incidents(self, candidates, now):
        incidents = _incidents()
        changed = False
        for key, candidate in candidates.items():
            since = self.candidate_since.setdefault(key, now)
            if not model.confirmed(since, now, candidate['confirm_seconds']):
                continue
            incident = incidents.get(key)
            if incident and incident.get('condition_active'):
                continue
            action = ''
            bypass = _bypass_active(now)
            if _mode() == 'protect' and not bypass:
                action = _execute_safety_actions()
            elif _mode() == 'protect' and bypass:
                action = _('Temporary bypass is active; control action was not executed')
            else:
                action = _('Monitor-only mode; control action was not executed')
            incident = {
                'id': uuid.uuid4().hex, 'key': key,
                'code': candidate['code'], 'scope': candidate['scope'],
                'label': candidate['label'], 'detail': candidate['detail'],
                'opened_at': int(now), 'condition_active': True,
                'latched': bool(plugin_options.get('latch_incidents', True)),
                'action': action,
            }
            incidents[key] = incident
            _append_history('triggered', candidate['code'],
                            candidate['detail'], action, 'critical')
            log.error(NAME, '{}: {}'.format(candidate['label'], candidate['detail']))
            if notification_worker is not None:
                notification_worker.submit('triggered', incident)
            changed = True

        for key, incident in list(incidents.items()):
            if not incident.get('condition_active') or key in candidates:
                continue
            incident = dict(incident)
            incident['condition_active'] = False
            incident['cleared_at'] = int(now)
            if not incident.get('latched'):
                incidents.pop(key, None)
            else:
                incidents[key] = incident
            _append_history('cleared', incident.get('code', ''),
                            incident.get('detail', ''), '', 'info')
            log.info(NAME, '{}: {}'.format(
                _('Irrigation safety condition returned to normal'),
                incident.get('label', '')))
            if plugin_options.get('notify_recovery') and notification_worker is not None:
                notification_worker.submit('cleared', incident)
            changed = True

        self.candidate_since = {
            key: since for key, since in self.candidate_since.items()
            if key in candidates
        }
        if changed:
            with state_lock:
                plugin_options['incidents'] = incidents

    def _enforce_lock(self):
        if _mode() != 'protect' or _bypass_active() or not any(
                item.get('latched') for item in _incidents().values()):
            return
        if _active_station_ids() or any(stations.active(value) for value in (
                getattr(stations, 'master', None),
                getattr(stations, 'master_two', None)) if isinstance(value, int)):
            _stop_outputs()

    def run(self):
        while not self._stop_event.is_set():
            try:
                _normalize_settings()
                mode = _mode()
                if mode == 'off':
                    self.current = self._empty_status()
                    self.current['mode'] = mode
                    self._sync_footer()
                    self._stop_event.wait(plugin_options['check_interval'])
                    continue
                now = time.time()
                snapshots = _provider_snapshots()
                active = _active_station_ids()
                profiles = _profiles()
                self._update_active_timing(active, now)
                candidates, flow, flow_status = self._evaluate(
                    snapshots, active, profiles, now)
                self._learn(active, profiles, flow, flow_status, now)
                self._reconcile_incidents(candidates, now)
                self._enforce_lock()
                self._sync_footer()
                with health_lock:
                    health_state['last_cycle'] = now
                    health_state['provider_errors'] = len(
                        _relevant_provider_errors(snapshots))
                    health_state['last_error_message'] = ''
                self._stop_event.wait(plugin_options['check_interval'])
            except Exception:
                self._log_problem(_('Irrigation Safety evaluation failed') + ':\n' +
                                  traceback.format_exc())
                self._stop_event.wait(5)


safety_worker = None


def _incidents():
    with state_lock:
        value = plugin_options.get('incidents', {})
        return dict(value) if isinstance(value, dict) else {}


def _bypass_active(now=None):
    now = time.time() if now is None else now
    return _safe_int(plugin_options.get('bypass_until'), 0) > now


def start():
    global safety_worker, notification_worker
    _normalize_settings()
    if notification_worker is None:
        notification_worker = NotificationWorker()
    if safety_worker is None:
        safety_worker = SafetyWorker()


def stop():
    global safety_worker, notification_worker
    for worker in (safety_worker, notification_worker):
        if worker is not None:
            worker.stop()
    for worker in (safety_worker, notification_worker):
        if worker is not None:
            worker.join(15)
    safety_worker = None
    notification_worker = None
    clear_plugin_runtime_data('irrigation_safety')


def acknowledge_incidents():
    incidents = _incidents()
    active = [item for item in incidents.values() if item.get('condition_active')]
    if active:
        raise ValueError(_('An incident cannot be acknowledged while its fault condition is active.'))
    count = len(incidents)
    with state_lock:
        plugin_options['incidents'] = {}
    _append_history('acknowledged', '',
                    _('Administrator acknowledged {} incident(s).').format(count))
    return count


def _tank_sources():
    sources = []
    try:
        snapshots = _provider_snapshots().get('providers', {})
        for provider_id in ('tank_monitor', 'current_loop_tanks_monitor'):
            provider = snapshots.get(provider_id, {})
            for resource in provider.get('resources', []):
                for value in resource.get('values', []):
                    if value.get('id') not in ('fill_percent', 'level_cm'):
                        continue
                    sources.append({
                        'provider_id': provider_id,
                        'resource_id': str(resource.get('id', '')),
                        'value_id': str(value.get('id', '')),
                        'label': '{} / {} / {} ({})'.format(
                            provider_id, resource.get('name') or resource.get('id'),
                            value.get('id'), value.get('unit', '')),
                    })
    except Exception:
        pass
    selected = {
        'provider_id': str(plugin_options.get('tank_provider_id', 'tank_monitor')),
        'resource_id': str(plugin_options.get('tank_resource_id', 'main')),
        'value_id': str(plugin_options.get('tank_value_id', 'fill_percent')),
    }
    if not any(all(item.get(key) == value for key, value in selected.items())
               for item in sources):
        selected['label'] = '{} / {} / {}'.format(
            selected['provider_id'], selected['resource_id'], selected['value_id'])
        sources.append(selected)
    return sources


def _web_data():
    return {
        'modes': [('off', _('Off')), ('monitor', _('Monitor only')),
                  ('protect', _('Active protection'))],
        'profiles': _profiles(),
        'tank_sources': _tank_sources(),
        'incidents': list(_incidents().values()),
        'history': list(plugin_options.get('history', []))[:100],
    }


def _public_status():
    current = dict(safety_worker.current) if safety_worker is not None else SafetyWorker._empty_status()
    incidents = list(_incidents().values())
    current.update({
        'mode_label': _mode_label(_mode()),
        'incidents': incidents,
        'locked_incidents': sum(1 for item in incidents if item.get('latched')),
        'active_incidents': sum(1 for item in incidents if item.get('condition_active')),
        'history': list(plugin_options.get('history', []))[:100],
        'worker_running': safety_worker is not None and safety_worker.is_alive(),
    })
    return current


def health():
    with health_lock:
        state = dict(health_state)
    worker_running = safety_worker is not None and safety_worker.is_alive()
    details = {
        _('Worker thread'): _('Running') if worker_running else _('Stopped'),
        _('Safety mode'): _mode_label(_mode()),
        _('Active incidents'): len([item for item in _incidents().values()
                                    if item.get('condition_active')]),
        _('Locked incidents'): len([item for item in _incidents().values()
                                    if item.get('latched')]),
        _('Safety actions'): state['safety_actions'],
        _('Provider errors'): state['provider_errors'],
        _('Notification errors'): state['notification_errors'],
        _('Last successful cycle'): (
            datetime_string(time.localtime(state['last_cycle']))
            if state['last_cycle'] else _('Not available')),
    }
    if state['last_error_message']:
        details[_('Last error')] = state['last_error_message']
    if not worker_running:
        return {'status': 'error',
                'summary': _('Irrigation Safety worker is stopped.'),
                'details': details}
    if _mode() == 'off':
        return {'status': 'unknown', 'summary': _('Irrigation Safety is off.'),
                'details': details}
    if any(item.get('condition_active') for item in _incidents().values()):
        return {'status': 'error',
                'summary': _('An irrigation safety incident is active.'),
                'details': details}
    if state['last_error_message'] or state['provider_errors']:
        return {'status': 'warning',
                'summary': _('Irrigation Safety has unavailable data.'),
                'details': details}
    return {'status': 'ok', 'summary': _('Irrigation Safety is monitoring.'),
            'details': details}


def mobile_status():
    result = health()
    return {'status': result['status'], 'title': _('Irrigation Safety'),
            'summary': result['summary'], 'updated': datetime_string()}


def mobile_cards(**_kwargs):
    status = _public_status()
    flow = status.get('flow_lpm')
    return [{
        'id': 'irrigation_safety', 'kind': 'metrics',
        'title': _('Irrigation Safety'),
        'status': health().get('status', 'unknown'),
        'summary': health().get('summary', ''),
        'metrics': [
            {'id': 'mode', 'label': _('Safety mode'),
             'value': status['mode_label'], 'unit': ''},
            {'id': 'flow', 'label': _('Current flow'),
             'value': '---' if flow is None else round(flow, 3), 'unit': 'L/min'},
            {'id': 'active_stations', 'label': _('Active stations'),
             'value': ', '.join(status.get('active_stations', [])) or _('None'),
             'unit': ''},
            {'id': 'active_incidents', 'label': _('Active incidents'),
             'value': status['active_incidents'], 'unit': ''},
            {'id': 'locked_incidents', 'label': _('Locked incidents'),
             'value': status['locked_incidents'], 'unit': ''},
        ],
    }]


def provider_capabilities():
    return {
        'contract': 'ospy.provider.v1',
        'provider_id': 'irrigation_safety',
        'resource_types': ['irrigation_safety'],
        'values': [
            {'id': 'protection_active', 'quantity': 'state', 'unit': '',
             'value_type': 'boolean'},
            {'id': 'monitoring_active', 'quantity': 'state', 'unit': '',
             'value_type': 'boolean'},
            {'id': 'active_incidents', 'quantity': 'count', 'unit': '',
             'value_type': 'integer'},
            {'id': 'locked_incidents', 'quantity': 'count', 'unit': '',
             'value_type': 'integer'},
        ],
        'events': [{'code': 'irrigation_safety.incident'}],
        'alerts': [{'code': 'irrigation_safety.active_incident'}],
        'actions': [],
    }


def provider_snapshot():
    status = _public_status()
    observed = datetime.datetime.utcfromtimestamp(
        status.get('updated') or time.time()).isoformat() + 'Z'
    values = [
        ('protection_active', _mode() == 'protect', 'boolean'),
        ('monitoring_active', _mode() in ('monitor', 'protect'), 'boolean'),
        ('active_incidents', status['active_incidents'], 'integer'),
        ('locked_incidents', status['locked_incidents'], 'integer'),
    ]
    alerts = [{
        'id': 'irrigation-safety.active-incident',
        'code': 'irrigation_safety.active_incident',
        'severity': 'critical', 'state': 'active', 'opened_at': observed,
    }] if status['active_incidents'] else []
    return {
        'contract': 'ospy.provider.v1',
        'provider_id': 'irrigation_safety',
        'status': 'ok' if status['worker_running'] else 'unavailable',
        'observed_at': observed,
        'resources': [{
            'id': 'main', 'type': 'irrigation_safety',
            'status': 'ok' if status['worker_running'] else 'unavailable',
            'values': [{
                'id': value_id, 'quantity': 'state' if value_type == 'boolean' else 'count',
                'value': value, 'unit': '', 'value_type': value_type,
                'quality': 'derived', 'observed_at': observed,
            } for value_id, value, value_type in values],
            'alerts': alerts,
        }],
        'events': [], 'alerts': alerts,
    }


class settings_page(ProtectedPage):
    def GET(self):
        _normalize_settings()
        return self.plugin_render.irrigation_safety(
            plugin_options, _web_data(), '')

    def POST(self):
        from ospy import server

        qdict = web.input()
        verify_csrf(qdict)
        error = ''
        try:
            if server.session.get('category') != 'admin':
                raise ValueError(_('Only an administrator can change irrigation safety settings.'))
            action = str(qdict.get('action', ''))
            if action == 'save_settings':
                mode = str(qdict.get('mode', 'off'))
                if mode not in model.MODES:
                    raise ValueError(_('Select a valid safety mode.'))
                plugin_options['mode'] = mode
                for key in (
                        'use_footer', 'send_email', 'send_push', 'notify_recovery',
                        'stop_all_outputs', 'disable_scheduler', 'latch_incidents',
                        'unexpected_flow_enabled', 'pressure_enabled', 'tank_enabled'):
                    plugin_options[key] = qdict.get(key) == 'on'
                for key in ('check_interval', 'data_timeout', 'history_limit',
                            'unexpected_flow_confirm', 'pressure_confirm',
                            'tank_confirm'):
                    plugin_options[key] = _safe_int(qdict.get(key), plugin_options[key])
                for key in ('unexpected_flow_lpm', 'tank_minimum'):
                    plugin_options[key] = _safe_float(qdict.get(key), plugin_options[key])
                tank_source = str(qdict.get('tank_source', ''))
                parts = tank_source.split('|', 2)
                if len(parts) == 3:
                    plugin_options['tank_provider_id'] = parts[0]
                    plugin_options['tank_resource_id'] = parts[1]
                    plugin_options['tank_value_id'] = parts[2]
                _normalize_settings()
            elif action == 'save_profile':
                station_id = _safe_int(qdict.get('station_id'), -1)
                profile = _profile(station_id)
                if profile is None:
                    raise ValueError(_('Selected station does not exist.'))
                _save_profile(_profile_from_input(qdict, profile))
            elif action == 'start_learning':
                station_id = _safe_int(qdict.get('station_id'), -1)
                profile = _profile(station_id)
                if profile is None:
                    raise ValueError(_('Selected station does not exist.'))
                profile = _profile_from_input(qdict, profile)
                profile['learning'] = True
                profile['enabled'] = True
                _save_profile(profile)
                if safety_worker is not None:
                    safety_worker.learning_samples[station_id] = []
                _append_history('learning_started', '',
                                _('Automatic flow learning started for station {}.').format(profile['name']))
            elif action == 'stop_learning':
                station_id = _safe_int(qdict.get('station_id'), -1)
                profile = _profile(station_id)
                if profile is not None:
                    profile = dict(profile)
                    profile['learning'] = False
                    _save_profile(profile)
                if safety_worker is not None:
                    safety_worker.learning_samples.pop(station_id, None)
            elif action == 'acknowledge':
                acknowledge_incidents()
            elif action == 'start_bypass':
                minutes = model.clamp(_safe_int(qdict.get('bypass_minutes'), 15), 1, 1440)
                plugin_options['bypass_until'] = int(time.time()) + minutes * 60
                _append_history('bypass_started', '',
                                _('Temporary bypass started for {} minutes.').format(minutes))
            elif action == 'cancel_bypass':
                plugin_options['bypass_until'] = 0
                _append_history('bypass_cancelled', '', _('Temporary bypass was cancelled.'))
            elif action == 'test_notifications':
                if notification_worker is not None:
                    notification_worker.submit('test', {'id': 'test', 'code': ''}, True)
            elif action == 'clear_history':
                plugin_options['history'] = []
        except (TypeError, ValueError) as exception:
            error = str(exception)
        if not error:
            raise web.seeother(plugin_url(settings_page), True)
        return self.plugin_render.irrigation_safety(
            plugin_options, _web_data(), error)


class status_json(ProtectedPage):
    def GET(self):
        web.header('Content-Type', 'application/json; charset=utf-8')
        return json.dumps(_public_status(), ensure_ascii=False, allow_nan=False)


class help_page(ProtectedPage):
    def GET(self):
        return self.plugin_render.irrigation_safety_help()
