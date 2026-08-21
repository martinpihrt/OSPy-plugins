"""Pure rule normalization, evaluation and transition logic."""

import math
import re


RULE_MODES = ('all', 'any')
OPERATORS = (
    'eq', 'ne', 'gt', 'gte', 'lt', 'lte', 'between', 'not_between',
    'is_true', 'is_false',
)
SEVERITIES = ('info', 'warning', 'error', 'critical')
CHANNELS = ('home', 'browser', 'email', 'telegram', 'push')
_IDENTIFIER = re.compile(r'^[a-z0-9][a-z0-9_.-]{0,127}$')


class RuleValidationError(ValueError):
    pass


def _identifier(value, field):
    value = str(value or '').strip().lower()
    if not _IDENTIFIER.match(value):
        raise RuleValidationError('{} is not a valid identifier'.format(field))
    return value


def _integer(value, minimum, maximum, field):
    try:
        result = int(value)
    except (TypeError, ValueError):
        raise RuleValidationError('{} must be an integer'.format(field))
    if not minimum <= result <= maximum:
        raise RuleValidationError('{} is outside the allowed range'.format(field))
    return result


def normalize_condition(condition, index=0):
    if not isinstance(condition, dict):
        raise RuleValidationError('condition must be an object')
    operator = str(condition.get('operator') or '').strip().lower()
    if operator not in OPERATORS:
        raise RuleValidationError('operator is not supported')
    result = {
        'id': _identifier(condition.get('id') or 'condition-{}'.format(index + 1),
                          'condition id'),
        'provider_id': _identifier(condition.get('provider_id'), 'provider id'),
        'resource_id': _identifier(condition.get('resource_id'), 'resource id'),
        'value_id': _identifier(condition.get('value_id'), 'value id'),
        'operator': operator,
        'expected': condition.get('expected'),
    }
    if operator in ('gt', 'gte', 'lt', 'lte'):
        try:
            result['expected'] = float(result['expected'])
        except (TypeError, ValueError):
            raise RuleValidationError('expected value must be numeric')
        if not math.isfinite(result['expected']):
            raise RuleValidationError('expected value must be finite')
    elif operator in ('between', 'not_between'):
        if not isinstance(result['expected'], str) or '..' not in result['expected']:
            raise RuleValidationError('range must use start..end')
        start, end = [item.strip() for item in result['expected'].split('..', 1)]
        if not start or not end:
            raise RuleValidationError('range must contain both limits')
        result['expected'] = '{}..{}'.format(start, end)
    elif operator in ('is_true', 'is_false'):
        result['expected'] = operator == 'is_true'
    elif not isinstance(result['expected'], (str, int, float, bool)):
        raise RuleValidationError('expected value has an unsupported type')
    return result


def normalize_rule(rule):
    if not isinstance(rule, dict):
        raise RuleValidationError('rule must be an object')
    mode = str(rule.get('mode') or 'all').strip().lower()
    if mode not in RULE_MODES:
        raise RuleValidationError('rule mode is not supported')
    severity = str(rule.get('severity') or 'warning').strip().lower()
    if severity not in SEVERITIES:
        raise RuleValidationError('severity is not supported')
    name = str(rule.get('name') or '').strip()
    if not name or len(name) > 120:
        raise RuleValidationError('rule name is required and must be at most 120 characters')
    conditions = rule.get('conditions')
    if not isinstance(conditions, list) or not conditions or len(conditions) > 20:
        raise RuleValidationError('a rule must contain between 1 and 20 conditions')
    channels = []
    for channel in rule.get('channels', []):
        channel = str(channel or '').strip().lower()
        if channel in CHANNELS and channel not in channels:
            channels.append(channel)
    return {
        'id': _identifier(rule.get('id'), 'rule id'),
        'name': name,
        'enabled': bool(rule.get('enabled', True)),
        'mode': mode,
        'conditions': [normalize_condition(item, index)
                       for index, item in enumerate(conditions)],
        'hold_seconds': _integer(rule.get('hold_seconds', 0), 0, 86400,
                                 'hold_seconds'),
        'repeat_seconds': _integer(rule.get('repeat_seconds', 0), 0, 2592000,
                                   'repeat_seconds'),
        'notify_on_clear': bool(rule.get('notify_on_clear', True)),
        'severity': severity,
        'channels': channels,
    }


def _find_value(snapshots, condition):
    providers = snapshots.get('providers', {}) if isinstance(snapshots, dict) else {}
    provider = providers.get(condition['provider_id'])
    if not isinstance(provider, dict):
        return None, None, 'provider_unavailable'
    if provider.get('status') != 'ok':
        return None, None, 'provider_not_ready'
    resource = next((item for item in provider.get('resources', [])
                     if item.get('id') == condition['resource_id']), None)
    if not isinstance(resource, dict):
        return None, None, 'resource_unavailable'
    if resource.get('status') != 'ok':
        return None, None, 'resource_not_ready'
    value = next((item for item in resource.get('values', [])
                  if item.get('id') == condition['value_id']), None)
    if not isinstance(value, dict) or value.get('value') is None:
        return None, None, 'value_unavailable'
    return value.get('value'), value.get('unit', ''), ''


def _coerce_expected(actual, expected):
    if isinstance(actual, bool):
        if isinstance(expected, str):
            return expected.strip().lower() in ('1', 'true', 'yes', 'on')
        return bool(expected)
    if isinstance(actual, (int, float)) and not isinstance(actual, bool):
        return float(expected)
    return str(expected)


def evaluate_condition(condition, snapshots):
    condition = normalize_condition(condition)
    actual, unit, reason = _find_value(snapshots, condition)
    if reason:
        return {
            'id': condition['id'], 'available': False, 'matched': False,
            'actual': None, 'expected': condition['expected'], 'unit': unit or '',
            'reason': reason,
        }
    operator = condition['operator']
    expected = _coerce_expected(actual, condition['expected'])
    try:
        if operator == 'eq':
            matched = actual == expected
        elif operator == 'ne':
            matched = actual != expected
        elif operator == 'gt':
            matched = actual > expected
        elif operator == 'gte':
            matched = actual >= expected
        elif operator == 'lt':
            matched = actual < expected
        elif operator == 'lte':
            matched = actual <= expected
        elif operator in ('between', 'not_between'):
            start, end = expected.split('..', 1)
            start = _coerce_expected(actual, start)
            end = _coerce_expected(actual, end)
            inside = (start <= actual <= end if start <= end else
                      actual >= start or actual <= end)
            matched = inside if operator == 'between' else not inside
        elif operator == 'is_true':
            matched = actual is True
        else:
            matched = actual is False
    except (TypeError, ValueError, OverflowError):
        return {
            'id': condition['id'], 'available': False, 'matched': False,
            'actual': actual, 'expected': expected, 'unit': unit,
            'reason': 'value_type_mismatch',
        }
    return {
        'id': condition['id'], 'available': True, 'matched': bool(matched),
        'actual': actual, 'expected': expected, 'unit': unit, 'reason': '',
    }


def evaluate_rule(rule, snapshots):
    rule = normalize_rule(rule)
    results = [evaluate_condition(item, snapshots) for item in rule['conditions']]
    if rule['mode'] == 'all':
        matched = all(item['available'] and item['matched'] for item in results)
        available = all(item['available'] for item in results)
    else:
        matched = any(item['available'] and item['matched'] for item in results)
        available = matched or all(item['available'] for item in results)
    return {
        'rule_id': rule['id'], 'available': available,
        'matched': matched, 'mode': rule['mode'], 'conditions': results,
    }


def transition(rule, evaluation, state=None, now=0):
    """Return the next persisted state and edge/reminder event."""
    rule = normalize_rule(rule)
    state = dict(state or {})
    state.setdefault('active', False)
    state.setdefault('matched_since', 0)
    state.setdefault('last_trigger', 0)
    event = 'none'
    if not evaluation.get('available'):
        event = 'unavailable'
    elif evaluation.get('matched'):
        if not state['matched_since']:
            state['matched_since'] = now
        held = now - state['matched_since'] >= rule['hold_seconds']
        if held and not state['active']:
            state['active'] = True
            state['last_trigger'] = now
            event = 'triggered'
        elif (held and state['active'] and rule['repeat_seconds'] and
              now - state['last_trigger'] >= rule['repeat_seconds']):
            state['last_trigger'] = now
            event = 'repeated'
    else:
        state['matched_since'] = 0
        if state['active']:
            state['active'] = False
            event = 'cleared'
    state['last_evaluation'] = now
    return state, event
