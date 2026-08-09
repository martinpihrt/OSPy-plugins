"""Reading adapters for local Shelly RPC and Shelly Cloud Integration cache."""

import re
import time
import ipaddress

from .model import number


HOST_RE = re.compile(r'^[A-Za-z0-9](?:[A-Za-z0-9.:-]{0,251}[A-Za-z0-9])?$')


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
    from plugins.shelly_cloud_integrator import shelly_devices
    selected = str(meter.get('device_id', ''))
    for device in shelly_devices.devices():
        if str(device.get('id', '')) == selected or str(device.get('label', '')) == selected:
            if not device.get('online', False):
                raise RuntimeError('Selected Shelly meter is offline')
            return {'import_kwh': device.get('energy', [0, 0, 0]), 'export_kwh': device.get('returned_energy', [0, 0, 0]), 'power_w': device.get('power', [0, 0, 0]), 'online': True, 'identity': str(device.get('id', '')), 'updated': device.get('updated', time.time())}
    raise RuntimeError('Selected Shelly meter is not available in Shelly Cloud Integration')
