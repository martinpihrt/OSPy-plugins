# !/usr/bin/env python3
# -*- coding: utf-8 -*-

__author__ = 'Martin Pihrt'

import web                                                       # Framework web.py
import traceback                                                 # For Errors listing via callback where the event occurred
import json
import time
import subprocess
import datetime
import ipaddress
import os
import re
import socket

from threading import Thread
from concurrent.futures import ThreadPoolExecutor, as_completed

from ospy.webpages import ProtectedPage                          # For check user login permissions
from ospy.helpers import verify_csrf
from ospy import helpers
from ospy.log import log
from plugins import get_runtime

find_now = False
scan_common_web_ports = False
msg = []
scan_data = {
    'running': False,
    'last_scan': '',
    'os_ip': '',
    'interface': '',
    'network': '',
    'gateway': '',
    'device_count': 0,
    'ports_checked': False,
    'error': '',
    'devices': [],
}

COMMON_WEB_PORTS = (80, 443, 8080, 8081)
MAX_SCAN_HOSTS = 512
runtime = get_runtime()


def _run_command(command, timeout=5):
    try:
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, check=False)
        return result.stdout.decode('utf-8', errors='ignore')
    except Exception:
        return ''


def _local_network_info(stop_event=None):
    ospy_ip = helpers.get_ip()
    info = {
        'ip': ospy_ip,
        'interface': '',
        'network': '',
        'gateway': '',
    }

    route_output = _run_command(['ip', 'route', 'show', 'default'])
    route_match = re.search(r'default\s+via\s+(\S+)\s+dev\s+(\S+)', route_output)
    if route_match:
        info['gateway'] = route_match.group(1)
        info['interface'] = route_match.group(2)

    if stop_event is not None and stop_event.is_set():
        return info

    addr_output = _run_command(['ip', '-o', '-f', 'inet', 'addr', 'show'])
    for line in addr_output.splitlines():
        parts = line.split()
        if len(parts) < 4:
            continue
        interface = parts[1]
        cidr = parts[3]
        if cidr.startswith(ospy_ip + '/'):
            info['interface'] = interface
            try:
                info['network'] = str(ipaddress.ip_interface(cidr).network)
            except Exception:
                pass
            break

    if not info['network'] and ospy_ip:
        try:
            info['network'] = str(ipaddress.ip_network(ospy_ip + '/24', strict=False))
        except Exception:
            pass

    return info


def _ping(ip, stop_event=None):
    if stop_event is not None and stop_event.is_set():
        return False
    ip = str(ip)
    if os.name == 'nt':
        command = ['ping', '-n', '1', '-w', '700', ip]
    else:
        command = ['ping', '-c', '1', '-W', '1', ip]
    try:
        result = subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2, check=False)
        return result.returncode == 0
    except Exception:
        return False


def _read_neighbors(stop_event=None):
    neighbors = {}
    output = _run_command(['ip', 'neigh', 'show'])
    for line in output.splitlines():
        parts = line.split()
        if len(parts) < 5 or 'lladdr' not in parts:
            continue
        ip = parts[0]
        mac = parts[parts.index('lladdr') + 1]
        state = parts[-1]
        if mac != '00:00:00:00:00:00':
            neighbors[ip] = {'mac': mac, 'state': state}

    if neighbors:
        return neighbors

    if stop_event is not None and stop_event.is_set():
        return neighbors

    output = _run_command(['arp', '-n'])
    for line in output.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 3 and re.match(r'\d+\.\d+\.\d+\.\d+', parts[0]):
            neighbors[parts[0]] = {'mac': parts[2], 'state': ''}
    return neighbors


def _hostname(ip):
    previous_timeout = socket.getdefaulttimeout()
    try:
        socket.setdefaulttimeout(0.4)
        return socket.gethostbyaddr(str(ip))[0]
    except Exception:
        return ''
    finally:
        socket.setdefaulttimeout(previous_timeout)


def _vendor(mac):
    prefix = mac.upper().replace('-', ':')[:8]
    vendors = {
        'B8:27:EB': 'Raspberry Pi',
        'DC:A6:32': 'Raspberry Pi',
        'E4:5F:01': 'Raspberry Pi',
        'D8:3A:DD': 'Raspberry Pi',
        '2C:CF:67': 'Raspberry Pi',
        '24:0A:C4': 'Espressif',
        '30:AE:A4': 'Espressif',
        '3C:61:05': 'Espressif',
        '40:91:51': 'Espressif',
        '7C:DF:A1': 'Espressif',
        '84:F3:EB': 'Espressif',
        'A4:CF:12': 'Espressif',
        'C8:C9:A3': 'Espressif',
        'EC:FA:BC': 'Espressif',
        '18:FE:34': 'Espressif',
    }
    return vendors.get(prefix, '')


def _check_port(ip, port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(0.35)
    try:
        return sock.connect_ex((str(ip), port)) == 0
    except Exception:
        return False
    finally:
        sock.close()


def _scan_network(check_ports=False, stop_event=None):
    if stop_event is not None and stop_event.is_set():
        return None
    info = _local_network_info(stop_event)
    devices_by_ip = {}
    alive_ips = set()

    if stop_event is not None and stop_event.is_set():
        return None

    if info['network']:
        network = ipaddress.ip_network(info['network'], strict=False)
        if network.num_addresses > MAX_SCAN_HOSTS + 2 and info['ip']:
            network = ipaddress.ip_network(info['ip'] + '/24', strict=False)
            info['network'] = str(network)
        hosts = list(network.hosts())
        if len(hosts) > MAX_SCAN_HOSTS:
            hosts = hosts[:MAX_SCAN_HOSTS]
        with ThreadPoolExecutor(max_workers=32) as executor:
            futures = {
                executor.submit(_ping, ip, stop_event): str(ip)
                for ip in hosts
            }
            for future in as_completed(futures):
                if future.result():
                    alive_ips.add(futures[future])

    if stop_event is not None and stop_event.is_set():
        return None

    neighbors = _read_neighbors(stop_event)
    if stop_event is not None and stop_event.is_set():
        return None
    for ip, neighbor in neighbors.items():
        if info['network']:
            try:
                if ipaddress.ip_address(ip) not in ipaddress.ip_network(info['network'], strict=False):
                    continue
            except Exception:
                pass
        devices_by_ip[ip] = {
            'ip': ip,
            'mac': neighbor.get('mac', ''),
            'hostname': '',
            'vendor': '',
            'state': neighbor.get('state', ''),
            'online': ip in alive_ips or neighbor.get('state', '').upper() in ('REACHABLE', 'STALE', 'DELAY', 'PROBE', ''),
            'ports': [],
            'note': '',
        }

    for ip in alive_ips:
        devices_by_ip.setdefault(ip, {
            'ip': ip,
            'mac': '',
            'hostname': '',
            'vendor': '',
            'state': '',
            'online': True,
            'ports': [],
            'note': '',
        })

    for ip, device in devices_by_ip.items():
        if stop_event is not None and stop_event.is_set():
            return None
        device['hostname'] = _hostname(ip)
        device['vendor'] = _vendor(device['mac'])
        notes = []
        if ip == info['ip']:
            notes.append(_('This OSPy'))
        if ip == info['gateway']:
            notes.append(_('Gateway'))
        if device['vendor'] == 'Espressif':
            notes.append(_('Sensor candidate'))
        if check_ports:
            open_ports = [port for port in COMMON_WEB_PORTS if _check_port(ip, port)]
            device['ports'] = open_ports
            if open_ports:
                notes.append(_('Web service'))
        device['note'] = ', '.join(notes)

    devices = sorted(devices_by_ip.values(), key=lambda item: tuple(int(part) for part in item['ip'].split('.')))
    return {
        'running': False,
        'last_scan': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'os_ip': info['ip'],
        'interface': info['interface'],
        'network': info['network'],
        'gateway': info['gateway'],
        'device_count': len(devices),
        'ports_checked': check_ports,
        'error': '',
        'devices': devices,
    }


def _scan_text(data):
    lines = [
        _('My OSPy IP address') + ': {}'.format(data.get('os_ip') or '-'),
        _('Network') + ': {}'.format(data.get('network') or '-'),
        _('Gateway') + ': {}'.format(data.get('gateway') or '-'),
        _('Found devices') + ': {}'.format(data.get('device_count', 0)),
        '',
        _('IP Address') + '\t\t' + _('MAC Address') + '\t\t' + _('Hostname'),
    ]
    for device in data.get('devices', []):
        lines.append('{}\t\t{}\t\t{}'.format(device['ip'], device.get('mac') or '-', device.get('hostname') or '-'))
    return lines

################################################################################
# Plugin name, translated name, link for web page in init, plugin options      #
################################################################################
NAME = 'IP Scanner'                                              # The unique name of the plugin listed in the plugin manager
MENU =  _('Package: IP Scanner')                                 # The name of the plugin that will be visible in the running plugins tab and will be translated
LINK = 'status_page'                                             # The default webpage when loading the plugin will be the settings page class


################################################################################
# Main function loop:                                                          #
################################################################################

class MSGSender(Thread):
    def __init__(self):
        Thread.__init__(self)
        self.daemon = True
        self._stop_event = runtime.stop_event
        self._sleep_time = 0
        self.start()

    def stop(self):
        self._stop_event.set()

    def update(self):
        self._sleep_time = 0

    def _sleep(self, secs):
        self._sleep_time = secs
        while self._sleep_time > 0 and not self._stop_event.is_set():
            time.sleep(1)
            self._sleep_time -= 1

    def run(self):
        global find_now, scan_common_web_ports, msg, scan_data
        while not self._stop_event.is_set():
            try:
                if find_now:
                    check_ports = scan_common_web_ports
                    find_now = False
                    scan_data = dict(scan_data)
                    scan_data['running'] = True
                    scan_data['error'] = ''
                    msg = [_('Processing...')]
                    result = _scan_network(check_ports, self._stop_event)
                    if result is None:
                        scan_data = dict(scan_data)
                        scan_data['running'] = False
                        break
                    scan_data = result
                    msg = _scan_text(scan_data)

                self._sleep(2)

            except Exception:
                scan_data = dict(scan_data)
                scan_data['running'] = False
                scan_data['error'] = traceback.format_exc()
                log.error(NAME, _('IP Scanner plug-in') + ': \n' + traceback.format_exc())
                self._sleep(60)

msg_sender = None

################################################################################
# Helper functions:                                                            #
################################################################################
def start():
    global msg_sender
    if msg_sender is None:
        msg_sender = MSGSender()
        runtime.register_thread(msg_sender)


def stop():
    global msg_sender
    worker = msg_sender
    if worker is not None:
        worker.stop()
        worker.join(15)
        if msg_sender is worker and not worker.is_alive():
            msg_sender = None


def health():
    """Return scanner worker and latest network scan state."""
    worker_alive = msg_sender is not None and msg_sender.is_alive()
    data = dict(scan_data)
    details = {
        _('Worker thread'): _('Running') if worker_alive else _('Stopped'),
        _('Scan in progress'): _('Yes') if data.get('running') else _('No'),
        _('Network'): data.get('network') or _('Not available'),
        _('Network interface'): data.get('interface') or _('Not available'),
        _('Last scan'): data.get('last_scan') or _('Not available'),
        _('Found devices'): data.get('device_count', 0),
        _('Common web ports'): (
            _('Checked') if data.get('ports_checked') else _('Not checked')
        ),
    }
    if data.get('error'):
        details[_('Last error')] = str(data['error']).splitlines()[-1]
    if not worker_alive:
        return {
            'status': 'error',
            'summary': _('IP Scanner worker is stopped.'),
            'details': details,
        }
    if data.get('error'):
        return {
            'status': 'error',
            'summary': str(data['error']).splitlines()[-1],
            'details': details,
        }
    if data.get('running'):
        return {
            'status': 'warning',
            'summary': _('Network scan is in progress.'),
            'details': details,
        }
    if not data.get('last_scan'):
        return {
            'status': 'warning',
            'summary': _('No network scan has been completed yet.'),
            'details': details,
        }
    return {
        'status': 'ok',
        'summary': _('The last network scan completed successfully.'),
        'details': details,
    }


################################################################################
# Web pages:                                                                   #
################################################################################

class status_page(ProtectedPage):
    """Load an html page for entering adjustments."""

    def GET(self):
        try:
            global find_now, scan_common_web_ports

            qdict = web.input()
            find = helpers.get_input(qdict, 'find', False, lambda x: True)
            if find:
                verify_csrf(qdict)
                scan_common_web_ports = qdict.get('ports') == '1'
                find_now = True
            return self.plugin_render.ip_scanner()

        except:
            log.error(NAME, _('IP Scanner plug-in') + ':\n' + traceback.format_exc())
            msg = _('An internal error was found in the system, see the error log for more information. The error is in part:') + ' '
            msg += _('ip_scanner -> status_page GET')
            return self.core_render.notice('/', msg)


class msg_json(ProtectedPage):
    """Returns plugin data in JSON format."""

    def GET(self):
        data = {}
        try:
            global msg, scan_data
            web.header('Access-Control-Allow-Origin', '*')
            web.header('Content-Type', 'application/json')
            data['msg'] = msg
            data['scan'] = scan_data
            return json.dumps(data)
        except:
            return data
