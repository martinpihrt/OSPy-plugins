"""Reading adapters for local Shelly RPC and Shelly Cloud Integration cache."""

import re
import time
import ipaddress

from .model import number


HOST_RE = re.compile(r'^[A-Za-z0-9](?:[A-Za-z0-9.:-]{0,251}[A-Za-z0-9])?$')


class IntegratorMeterError(RuntimeError):
    """Base class for expected Shelly Cloud Integration states."""


class IntegratorReadingPending(IntegratorMeterError):
    """The configured integrator device has not produced its first cached reading."""


class IntegratorMeterOffline(IntegratorMeterError):
    """The selected cached meter reports that it is offline."""


class IntegratorMeterDisabled(IntegratorMeterError):
    """The selected configured meter is disabled."""


class IntegratorMeterUnavailable(IntegratorMeterError):
    """No configured or cached meter matches the selected identity."""


def _matches_integrator_device(device, selected):
    selected = str(selected or '').strip()
    device_id = str(device.get('id', '') or '').strip()
    label = str(device.get('label', '') or '').strip()
    return (device_id and device_id.casefold() == selected.casefold()) or (label and label == selected)


def select_integrator_device(cached_devices, configured_devices, selected):
    """Find a cached reading or distinguish warm-up from a missing configuration."""
    selected = str(selected or '').strip()
    for device in cached_devices or []:
        if _matches_integrator_device(device, selected):
            if not device.get('online', False):
                raise IntegratorMeterOffline(selected)
            return device
    for device in configured_devices or []:
        if _matches_integrator_device(device, selected):
            if not device.get('enabled', False):
                raise IntegratorMeterDisabled(selected)
            raise IntegratorReadingPending(selected)
    raise IntegratorMeterUnavailable(selected)


def legacy_integrator_configuration(options):
    """Read the parallel-list configuration exposed by older integrator versions."""
    try:
        count = max(0, int(options.get('number_sensors', 0)))
    except (TypeError, ValueError):
        count = 0

    def item(name, index, default):
        values = options.get(name, [])
        return values[index] if isinstance(values, (list, tuple)) and index < len(values) else default

    return [
        {
            'id': str(item('sensor_id', index, '') or '').strip(),
            'label': str(item('sensor_label', index, '') or '').strip(),
            'enabled': bool(item('use_sensor', index, False)),
            'type': item('sensor_type', index, 0),
        }
        for index in range(count)
    ]


def normalized_host(value):
    host = str(value or '').strip()
    for prefix in ('http://', 'https://'):
        if host.lower().startswith(prefix):
            host = host[len(prefix):]
    host = host.rstrip('/')
    if '/' in host:
        raise ValueError('Invalid Shelly host or IP address')
    if host.startswith('['):
        closing = host.find(']')
        if closing < 0:
            raise ValueError('Invalid Shelly host or IP address')
        ipaddress.ip_address(host[1:closing])
        if host[closing + 1:] and not re.match(r'^:\d{1,5}$', host[closing + 1:]):
            raise ValueError('Invalid Shelly host or IP address')
        return host
    if host.count(':') > 1:
        ipaddress.ip_address(host)
        return '[{}]'.format(host)
    if not HOST_RE.match(host):
        raise ValueError('Invalid Shelly host or IP address')
    return host


def parse_status(payload):
    em = payload.get('em:0')
    emdata = payload.get('emdata:0', {})
    if not isinstance(em, dict):
        raise ValueError('Shelly status does not contain em:0')
    phases = ('a', 'b', 'c')
    imported = [number(emdata.get('{}_total_act_energy'.format(phase))) / 1000.0 for phase in phases]
    exported = [number(emdata.get('{}_total_act_ret_energy'.format(phase))) / 1000.0 for phase in phases]
    powers = [number(em.get('{}_act_power'.format(phase))) for phase in phases]
    identity = payload.get('sys', {}).get('mac', '') if isinstance(payload.get('sys'), dict) else ''
    return {'import_kwh': imported, 'export_kwh': exported, 'power_w': powers, 'online': True, 'identity': identity, 'updated': time.time()}


def read_direct(meter, session):
    host = normalized_host(meter.get('host'))
    auth = None
    if meter.get('password'):
        from requests.auth import HTTPDigestAuth
        auth = HTTPDigestAuth(meter.get('username') or 'admin', meter['password'])
    response = session.get('http://{}/rpc/Shelly.GetStatus'.format(host), timeout=max(2, min(30, int(meter.get('timeout', 5)))), auth=auth)
    response.raise_for_status()
    return parse_status(response.json())


def read_integrator(meter):
    from plugins import shelly_cloud_integrator
    shelly_devices = shelly_cloud_integrator.shelly_devices
    configured = shelly_devices.configured() if hasattr(shelly_devices, 'configured') else legacy_integrator_configuration(shelly_cloud_integrator.plugin_options)
    device = select_integrator_device(shelly_devices.devices(), configured, meter.get('device_id', ''))
    return {'import_kwh': device.get('energy', [0, 0, 0]), 'export_kwh': device.get('returned_energy', [0, 0, 0]), 'power_w': device.get('power', [0, 0, 0]), 'online': True, 'identity': str(device.get('id', '')), 'updated': device.get('updated', time.time())}
