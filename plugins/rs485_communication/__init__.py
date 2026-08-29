# -*- coding: utf-8 -*-
"""OSPy RS485 Communication plug-in.

Central owner of a USB/RS485 serial port. Other OSPy plug-ins communicate
through the public rs485_queue (or helper functions built on top of it), so all
traffic is serialized by one worker and one half-duplex bus owner.
"""

__author__ = 'Martin Pihrt'

import json
import queue
import os
import re
import stat
import time
import traceback
import web

from threading import Event, RLock, Thread

from ospy import helpers
from ospy.helpers import datetime_string, verify_csrf
from ospy.log import log
from ospy.webpages import ProtectedPage
from plugins import PluginOptions, get_runtime, plugin_url


NAME = 'RS485 Communication'
MENU = _('Package: RS485 Communication')
LINK = 'settings_page'

WORKER_INTERVAL = 2.0
ERROR_LOG_THROTTLE = 300
WAVESHARE_VID = 0x1A86
CH343_PID = 0x55D3
DEFAULT_BAUDRATE = 4800
MAX_PORT_LENGTH = 255
MAX_FRAME_LENGTH = 65536
MAX_TRANSACTION_DELAY = 30.0
BUS_SCAN_BAUDRATES = (1200, 2400, 4800, 9600, 19200, 38400, 57600, 115200)
BUS_SCAN_FIRST_ADDRESS = 1
BUS_SCAN_LAST_ADDRESS = 254
BUS_SCAN_TIMEOUT = 0.15
BUS_SCAN_BROADCAST_TIMEOUT = 0.75
BUS_SCAN_FORMATS = ((8, 'N', 1.0), (8, 'E', 1.0), (8, 'O', 1.0))
BUS_SCAN_BROADCAST_VARIANTS = ((0x03, 1), (0x03, 2), (0x04, 1), (0x04, 2))
BUS_SCAN_TARGET_ADDRESSES = (1,)
BUS_SCAN_DIRECT_VARIANTS = ((0x03, 1), (0x03, 2))
BUS_SCAN_TOTAL = len(BUS_SCAN_BAUDRATES) * (
    len(BUS_SCAN_FORMATS) * len(BUS_SCAN_BROADCAST_VARIANTS)
    * (1 + len(BUS_SCAN_TARGET_ADDRESSES))
    + BUS_SCAN_LAST_ADDRESS * len(BUS_SCAN_DIRECT_VARIANTS)
)


try:
    import serial
    from serial.tools import list_ports
    SERIAL_AVAILABLE = True
except Exception:
    serial = None
    list_ports = None
    SERIAL_AVAILABLE = False


plugin_options = PluginOptions(
    NAME,
    {
        'enabled': False,
        # "auto" selects a Waveshare/WCH CH343G adapter. A fixed /dev path can
        # be entered when more than one compatible adapter is connected.
        'port': 'auto',
        'baudrate': DEFAULT_BAUDRATE,
        'bytesize': 8,
        'parity': 'N',
        'stopbits': 1.0,
        'timeout': 1.0,
        'write_timeout': 1.0,
    }
)

runtime = get_runtime()
_bus_lock = RLock()
_state_lock = RLock()
_last_error_log = {}

_state = {
    'status': 'disabled',
    'summary': _('Plug-in is disabled.'),
    'configured_port': 'auto',
    'active_port': '',
    'detected_port': '',
    'description': '',
    'hwid': '',
    'vid': None,
    'pid': None,
    'manufacturer': '',
    'serial_number': '',
    'last_scan': 0,
    'last_test': 0,
    'last_test_ok': None,
    'last_test_result': '',
    'last_success': 0,
    'last_error': 0,
    'last_error_message': '',
    'last_client': '',
    'transactions': 0,
    'tx_bytes': 0,
    'rx_bytes': 0,
    'queue_depth': 0,
    'queue_peak': 0,
    'queue_completed': 0,
    'queue_failed': 0,
    'queue_current_client': '',
    'queue_current_operation': '',
    'queue_current_since': 0,
    'queue_last_wait_ms': 0,
    'scan_active': False,
    'scan_started': 0,
    'scan_finished': 0,
    'scan_baudrate': 0,
    'scan_address': 0,
    'scan_phase': '',
    'scan_bytesize': 8,
    'scan_parity': 'N',
    'scan_stopbits': 1.0,
    'scan_function': 0,
    'scan_register_count': 0,
    'scan_timeout': 0,
    'scan_request': '',
    'scan_response': '',
    'scan_completed': 0,
    'scan_total': BUS_SCAN_TOTAL,
    'scan_found': [],
    'scan_message': _('Bus scan has not been run yet.'),
    'scan_error': '',
}


def _safe_int(value, default):
    try:
        return int(value)
    except Exception:
        return default


def _safe_float(value, default):
    try:
        return float(value)
    except Exception:
        return default


def _set_option_if_changed(key, value):
    """Persist normalized settings only when their value really changed.

    PluginOptions writes the complete option dictionary on every assignment.
    The worker calls _normalize_options regularly, so unconditional assignments
    here would cause needless settings-database writes every few seconds.
    """
    if plugin_options.get(key) != value:
        plugin_options[key] = value


def _normalize_port(value):
    port = str(value or 'auto').strip() or 'auto'
    if len(port) > MAX_PORT_LENGTH:
        raise ValueError(_('The serial port path is too long.'))
    if any(ord(character) < 32 for character in port):
        raise ValueError(_('The serial port path contains invalid characters.'))
    if port.lower() == 'auto':
        return 'auto'
    if os.name == 'nt' and re.fullmatch(r'COM[1-9][0-9]*', port, re.IGNORECASE):
        return port.upper()
    if not os.path.isabs(port):
        raise ValueError(_('The serial port must be auto or an absolute device path.'))
    return port


def _normalize_options():
    """Keep persisted settings within pyserial-compatible ranges."""
    port = _normalize_port(plugin_options.get('port', 'auto'))
    _set_option_if_changed('port', port)

    baud = _safe_int(plugin_options.get('baudrate', DEFAULT_BAUDRATE), DEFAULT_BAUDRATE)
    _set_option_if_changed('baudrate', max(50, min(3000000, baud)))

    bits = _safe_int(plugin_options.get('bytesize', 8), 8)
    _set_option_if_changed('bytesize', bits if bits in (5, 6, 7, 8) else 8)

    parity = str(plugin_options.get('parity', 'N') or 'N').upper()
    _set_option_if_changed('parity', parity if parity in ('N', 'E', 'O', 'M', 'S') else 'N')

    stop = _safe_float(plugin_options.get('stopbits', 1.0), 1.0)
    _set_option_if_changed('stopbits', stop if stop in (1.0, 1.5, 2.0) else 1.0)

    timeout = max(0.05, min(30.0, _safe_float(plugin_options.get('timeout', 1.0), 1.0)))
    write_timeout = max(0.05, min(30.0, _safe_float(plugin_options.get('write_timeout', 1.0), 1.0)))
    _set_option_if_changed('timeout', timeout)
    _set_option_if_changed('write_timeout', write_timeout)


def _format_usb_id(value):
    if value is None:
        return ''
    try:
        return '{:04X}'.format(int(value))
    except Exception:
        return str(value)


def _port_to_dict(port):
    """Convert pyserial ListPortInfo to a JSON/template-safe dictionary."""
    vid = getattr(port, 'vid', None)
    pid = getattr(port, 'pid', None)
    description = getattr(port, 'description', '') or ''
    manufacturer = getattr(port, 'manufacturer', '') or ''
    hwid = getattr(port, 'hwid', '') or ''
    product = getattr(port, 'product', '') or ''
    serial_number = getattr(port, 'serial_number', '') or ''

    text = ' '.join([description, manufacturer, hwid, product]).upper()
    exact_ch343 = (vid == WAVESHARE_VID and pid == CH343_PID)
    ch343_text = 'CH343' in text
    waveshare_text = 'WAVESHARE' in text

    # Exact CH343 USB ID wins. Text matching is retained for systems where the
    # kernel/driver does not expose VID/PID through list_ports.
    score = 0
    if exact_ch343:
        score = 100
    elif ch343_text:
        score = 90
    elif waveshare_text and ('RS485' in text or 'RS-485' in text):
        score = 80

    return {
        'device': getattr(port, 'device', '') or '',
        'name': getattr(port, 'name', '') or '',
        'description': description,
        'hwid': hwid,
        'vid': vid,
        'pid': pid,
        'vid_text': _format_usb_id(vid),
        'pid_text': _format_usb_id(pid),
        'manufacturer': manufacturer,
        'product': product,
        'serial_number': serial_number,
        'waveshare_score': score,
        'is_waveshare': score > 0,
    }


def get_serial_ports():
    """Return all serial devices currently reported by pyserial."""
    if not SERIAL_AVAILABLE or list_ports is None:
        return []
    try:
        ports = [_port_to_dict(item) for item in list_ports.comports()]
        ports.sort(key=lambda item: item['device'])
        return ports
    except Exception:
        _record_error('scan', _('Unable to enumerate serial ports: {}').format(traceback.format_exc().splitlines()[-1]))
        return []


def _find_port_info(device, ports=None):
    ports = get_serial_ports() if ports is None else ports
    normalized = os.path.realpath(device) if device else ''
    for item in ports:
        candidate = item.get('device', '')
        if candidate == device:
            return item
        try:
            if normalized and os.path.realpath(candidate) == normalized:
                return item
        except Exception:
            pass
    return None


def detect_waveshare_adapter():
    """Find the most likely Waveshare USB TO RS485 (B) / CH343G adapter."""
    ports = get_serial_ports()
    candidates = [item for item in ports if item.get('waveshare_score', 0) > 0]
    candidates.sort(key=lambda item: (-item['waveshare_score'], item['device']))
    found = candidates[0] if candidates else None

    with _state_lock:
        _state['last_scan'] = time.time()
        _state['detected_port'] = found['device'] if found else ''
        if found:
            _copy_port_info_to_state(found)
    return found


def _copy_port_info_to_state(info):
    if not info:
        return
    _state['description'] = info.get('description', '')
    _state['hwid'] = info.get('hwid', '')
    _state['vid'] = info.get('vid')
    _state['pid'] = info.get('pid')
    _state['manufacturer'] = info.get('manufacturer', '')
    _state['serial_number'] = info.get('serial_number', '')


def _resolve_selected_port():
    _normalize_options()
    configured = str(plugin_options['port']).strip()
    with _state_lock:
        _state['configured_port'] = configured

    if configured.lower() == 'auto':
        found = detect_waveshare_adapter()
        return found['device'] if found else ''

    info = _find_port_info(configured)
    safe_device = False
    if info:
        safe_device = True
    elif os.name != 'nt' and configured.startswith('/dev/'):
        try:
            resolved = os.path.realpath(configured)
            safe_device = resolved.startswith('/dev/') and stat.S_ISCHR(os.stat(resolved).st_mode)
        except (OSError, ValueError):
            safe_device = False
    with _state_lock:
        if info:
            _copy_port_info_to_state(info)
            _state['detected_port'] = info['device']
        elif safe_device:
            _state['detected_port'] = configured
    return configured if safe_device else ''


def _set_status(status, summary, active_port=None):
    with _state_lock:
        _state['status'] = status
        _state['summary'] = str(summary)
        if active_port is not None:
            _state['active_port'] = active_port


def _record_success(client='', tx=0, rx=0):
    with _state_lock:
        _state['last_success'] = time.time()
        _state['last_error_message'] = ''
        _state['last_client'] = str(client or '')[:120]
        _state['transactions'] += 1
        _state['tx_bytes'] += int(tx or 0)
        _state['rx_bytes'] += int(rx or 0)


def _record_failed_transfer(client='', tx=0, rx=0):
    """Account for bytes transferred by an unsuccessful transaction."""
    with _state_lock:
        _state['last_client'] = str(client or '')[:120]
        _state['transactions'] += 1
        _state['tx_bytes'] += int(tx or 0)
        _state['rx_bytes'] += int(rx or 0)


def _record_error(key, message):
    now = time.time()
    text = str(message).splitlines()[-1] if message else _('Unknown serial error.')
    with _state_lock:
        _state['last_error'] = now
        _state['last_error_message'] = text
    last = _last_error_log.get(key, 0)
    if now - last >= ERROR_LOG_THROTTLE:
        _last_error_log[key] = now
        log.error(NAME, text)


def _status_label(status):
    labels = {
        'disabled': _('Disabled'),
        'waiting': _('Waiting'),
        'ok': _('OK'),
        'communicating': _('Communicating'),
        'scanning': _('Scanning'),
        'error': _('Error'),
        'dependency_error': _('Dependency error'),
    }
    return labels.get(status, str(status))


def get_rs485_status():
    """Public status API for other OSPy plug-ins and the web page."""
    with _state_lock:
        state = dict(_state)
    state['enabled'] = bool(plugin_options.get('enabled', False))
    state['serial_available'] = SERIAL_AVAILABLE
    state['status_label'] = _status_label(state.get('status'))
    state['usb_id'] = '{}:{}'.format(_format_usb_id(state.get('vid')), _format_usb_id(state.get('pid'))).strip(':')
    state['last_scan_text'] = _time_text(state.get('last_scan'))
    state['last_test_text'] = _time_text(state.get('last_test'))
    state['last_success_text'] = _time_text(state.get('last_success'))
    state['last_error_text'] = _time_text(state.get('last_error'))
    state['settings'] = {
        'baudrate': plugin_options.get('baudrate', DEFAULT_BAUDRATE),
        'bytesize': plugin_options.get('bytesize', 8),
        'parity': plugin_options.get('parity', 'N'),
        'stopbits': plugin_options.get('stopbits', 1.0),
        'timeout': plugin_options.get('timeout', 1.0),
    }
    return state


def _time_text(timestamp):
    if not timestamp:
        return _('Not available')
    try:
        return datetime_string(time.localtime(timestamp))
    except Exception:
        return str(timestamp)


class AdapterNotFoundError(RuntimeError):
    pass


class RS485Bus(object):
    """Owns the selected serial device and serializes access to the RS485 bus."""

    def __init__(self):
        self._serial = None
        self._port = ''
        self._signature = None

    def _settings_signature(self, port):
        return (
            port,
            int(plugin_options['baudrate']),
            int(plugin_options['bytesize']),
            str(plugin_options['parity']),
            float(plugin_options['stopbits']),
            float(plugin_options['timeout']),
            float(plugin_options['write_timeout']),
        )

    def _serial_kwargs(self, port):
        return {
            'port': port,
            'baudrate': int(plugin_options['baudrate']),
            'bytesize': int(plugin_options['bytesize']),
            'parity': str(plugin_options['parity']),
            'stopbits': float(plugin_options['stopbits']),
            'timeout': float(plugin_options['timeout']),
            'write_timeout': float(plugin_options['write_timeout']),
            'xonxoff': False,
            'rtscts': False,
            'dsrdtr': False,
        }

    def close(self):
        with _bus_lock:
            self._close_locked()

    def _close_locked(self):
        if self._serial is not None:
            try:
                self._serial.close()
            except Exception:
                pass
        self._serial = None
        self._port = ''
        self._signature = None

    def refresh(self):
        """Force close; worker or next client call will reopen with new settings."""
        with _bus_lock:
            self._close_locked()

    def _ensure_open_locked(self):
        if not plugin_options.get('enabled', False):
            raise RuntimeError(_('RS485 Communication plug-in is disabled.'))
        if not SERIAL_AVAILABLE:
            raise RuntimeError(_('Python serial module is not installed. Install pyserial and restart OSPy.'))

        port = _resolve_selected_port()
        if not port:
            raise AdapterNotFoundError(_('Waveshare CH343G adapter was not found.'))

        signature = self._settings_signature(port)
        if self._serial is not None and self._signature == signature:
            try:
                if self._serial.is_open:
                    return self._serial
            except Exception:
                pass
            self._close_locked()

        self._close_locked()
        try:
            self._serial = serial.Serial(**self._serial_kwargs(port))
            self._port = port
            self._signature = signature
            with _state_lock:
                _state['active_port'] = port
            return self._serial
        except TypeError:
            # Compatibility fallback for older pyserial builds.
            kwargs = self._serial_kwargs(port)
            kwargs.pop('write_timeout', None)
            self._serial = serial.Serial(**kwargs)
            self._port = port
            self._signature = signature
            with _state_lock:
                _state['active_port'] = port
            return self._serial

    def ensure_ready(self):
        """Open the configured port and return its active device path."""
        with _bus_lock:
            ser = self._ensure_open_locked()
            return getattr(ser, 'port', self._port)

    def write(self, data, client='OSPy plug-in', flush=True):
        payload = _as_bytes(data)
        with _bus_lock:
            ser = self._ensure_open_locked()
            port = getattr(ser, 'port', self._port)
            _set_status('communicating', _('Sending data on {}.').format(port), port)
            try:
                count = ser.write(payload)
                if flush:
                    ser.flush()
                _record_success(client=client, tx=count)
                _set_status('ok', _('Adapter is ready on {}.').format(port), port)
                return count
            except Exception as err:
                message = _('RS485 write error: {}').format(err)
                _record_error('write', message)
                _set_status('error', message, port)
                self._close_locked()
                raise

    def read(self, size=1, client='OSPy plug-in'):
        size = _bounded_length(size, _('RS485 read size'))
        with _bus_lock:
            ser = self._ensure_open_locked()
            port = getattr(ser, 'port', self._port)
            _set_status('communicating', _('Receiving data on {}.').format(port), port)
            try:
                data = ser.read(size)
                _record_success(client=client, rx=len(data))
                _set_status('ok', _('Adapter is ready on {}.').format(port), port)
                return data
            except Exception as err:
                message = _('RS485 read error: {}').format(err)
                _record_error('read', message)
                _set_status('error', message, port)
                self._close_locked()
                raise

    def transaction(self, request, response_length=0, client='OSPy plug-in',
                    clear_input=True, delay=0.0, read_until=None, max_read=4096):
        """Atomically write one frame and optionally read its response.

        Args:
            request: bytes/bytearray/list[int] frame to send.
            response_length: exact number of bytes to read. 0 means no fixed read.
            client: human-readable consumer plug-in name for diagnostics.
            clear_input: clear stale input before sending.
            delay: optional delay after write before reading, in seconds.
            read_until: optional bytes terminator used when response_length == 0.
            max_read: maximum read_until size.
        """
        payload = _as_bytes(request)
        response_length = _bounded_length(response_length, _('RS485 response length'))
        delay = max(0.0, float(delay or 0.0))
        if delay > MAX_TRANSACTION_DELAY:
            raise ValueError(_('RS485 transaction delay is too long.'))
        max_read = _bounded_length(max_read, _('RS485 maximum read size'), minimum=1)

        with _bus_lock:
            ser = self._ensure_open_locked()
            port = getattr(ser, 'port', self._port)
            _set_status('communicating', _('Communication in progress on {}.').format(port), port)
            written = 0
            response = b''
            try:
                if clear_input:
                    try:
                        ser.reset_input_buffer()
                    except Exception:
                        pass

                written = ser.write(payload)
                ser.flush()
                if delay:
                    time.sleep(delay)

                if response_length > 0:
                    response = ser.read(response_length)
                elif read_until is not None:
                    terminator = _as_bytes(read_until)
                    try:
                        response = ser.read_until(terminator, size=max(1, int(max_read)))
                    except AttributeError:
                        response = _read_until_compat(ser, terminator, max(1, int(max_read)))

                if response_length > 0 and len(response) != response_length:
                    _record_failed_transfer(
                        client=client, tx=written, rx=len(response))
                    raise RuntimeError(_(
                        'RS485 response timeout: expected {} bytes, received {}.'
                    ).format(response_length, len(response)))

                _record_success(client=client, tx=written, rx=len(response))
                _set_status('ok', _('Adapter is ready on {}.').format(port), port)
                return response
            except Exception as err:
                message = _('RS485 transaction error: {}').format(err)
                _record_error('transaction', message)
                _set_status('error', message, port)
                self._close_locked()
                raise

    def call(self, callback, client='OSPy plug-in'):
        """Run a protocol-specific callback atomically on the RS485 worker.

        The callback receives the already opened pyserial object. It may perform
        several write/read steps; no other queued client can access the bus until
        the callback returns.
        """
        if not callable(callback):
            raise TypeError(_('RS485 callback must be callable.'))

        with _bus_lock:
            ser = self._ensure_open_locked()
            port = getattr(ser, 'port', self._port)
            _set_status('communicating', _('Communication in progress on {}.').format(port), port)
            try:
                result = callback(ser)
                _record_success(client=client)
                _set_status('ok', _('Adapter is ready on {}.').format(port), port)
                return result
            except Exception as err:
                message = _('RS485 callback error: {}').format(err)
                _record_error('callback', message)
                _set_status('error', message, port)
                self._close_locked()
                raise


def _read_until_compat(ser, terminator, max_read):
    data = bytearray()
    terminator = bytes(terminator)
    while len(data) < max_read:
        chunk = ser.read(1)
        if not chunk:
            break
        data.extend(chunk)
        if terminator and data.endswith(terminator):
            break
    return bytes(data)


def _as_bytes(data):
    try:
        if isinstance(data, bytes):
            result = data
        elif isinstance(data, bytearray):
            result = bytes(data)
        elif isinstance(data, str):
            result = data.encode('latin-1')
        else:
            result = bytes(bytearray(data))
    except (TypeError, ValueError, UnicodeError):
        raise TypeError(_('RS485 data must be bytes, bytearray, string, or an iterable of byte values.'))
    if len(result) > MAX_FRAME_LENGTH:
        raise ValueError(_('RS485 frame is too large.'))
    return result


def _bounded_length(value, label, minimum=0):
    try:
        result = int(value or 0)
    except (TypeError, ValueError):
        raise ValueError(_('{} is invalid.').format(label))
    if result < minimum or result > MAX_FRAME_LENGTH:
        raise ValueError(_('{} must be between {} and {} bytes.').format(
            label, minimum, MAX_FRAME_LENGTH))
    return result


rs485_bus = RS485Bus()


class RS485QueueJob(object):
    """One queued RS485 operation and its completion result."""

    def __init__(self, job_id, operation, client, runner):
        self.id = int(job_id)
        self.operation = str(operation)
        self.client = str(client or 'OSPy plug-in')[:120]
        self.created = time.time()
        self.started = 0
        self.finished = 0
        self.result = None
        self.error = None
        self._runner = runner
        self._done = Event()

    def done(self):
        return self._done.is_set()

    def wait(self, timeout=None):
        """Wait for completion and return the result or re-raise the job error."""
        if not self._done.wait(timeout):
            raise TimeoutError(_('Timed out waiting for RS485 queue job {}.').format(self.id))
        if self.error is not None:
            raise self.error
        return self.result


class RS485Queue(object):
    """FIFO queue used by every OSPy plug-in that needs the shared RS485 bus."""

    def __init__(self, maxsize=100):
        self._queue = queue.Queue(maxsize=max(1, int(maxsize)))
        self._counter = 0
        self._lock = RLock()

    def _next_id(self):
        with self._lock:
            self._counter += 1
            return self._counter

    def qsize(self):
        return self._queue.qsize()

    def empty(self):
        return self._queue.empty()

    def _update_depth_state(self):
        depth = self._queue.qsize()
        with _state_lock:
            _state['queue_depth'] = depth
            if depth > _state['queue_peak']:
                _state['queue_peak'] = depth

    def _enqueue(self, operation, client, runner, queue_timeout=0.0):
        if not plugin_options.get('enabled', False):
            raise RuntimeError(_('RS485 Communication plug-in is disabled.'))

        current_worker = globals().get('worker')
        if current_worker is None or not current_worker.is_alive():
            raise RuntimeError(_('RS485 worker is not running.'))
        with _state_lock:
            scan_active = bool(_state.get('scan_active', False))
        if scan_active and operation != 'bus_scan':
            raise RuntimeError(_('RS485 bus scan is in progress.'))

        job = RS485QueueJob(self._next_id(), operation, client, runner)
        try:
            queue_timeout = float(queue_timeout or 0.0)
            if queue_timeout > 0:
                self._queue.put(job, True, queue_timeout)
            else:
                self._queue.put_nowait(job)
        except queue.Full:
            raise RuntimeError(_('RS485 queue is full.'))

        self._update_depth_state()
        return job

    def submit_transaction(self, request, response_length=0, client='OSPy plug-in',
                           clear_input=True, delay=0.0, read_until=None, max_read=4096,
                           queue_timeout=0.0):
        """Enqueue one atomic TX/RX transaction and return an RS485QueueJob."""
        payload = _as_bytes(request)

        def runner(bus):
            return bus.transaction(
                request=payload,
                response_length=response_length,
                client=client,
                clear_input=clear_input,
                delay=delay,
                read_until=read_until,
                max_read=max_read,
            )

        return self._enqueue('transaction', client, runner, queue_timeout)

    def transaction(self, request, response_length=0, client='OSPy plug-in',
                    clear_input=True, delay=0.0, read_until=None, max_read=4096,
                    queue_timeout=0.0, wait_timeout=None):
        """Enqueue a TX/RX transaction, wait for it, and return the response."""
        job = self.submit_transaction(
            request=request,
            response_length=response_length,
            client=client,
            clear_input=clear_input,
            delay=delay,
            read_until=read_until,
            max_read=max_read,
            queue_timeout=queue_timeout,
        )
        return job.wait(wait_timeout)

    def submit_write(self, data, client='OSPy plug-in', flush=True, queue_timeout=0.0):
        """Enqueue a write and return an RS485QueueJob."""
        payload = _as_bytes(data)

        def runner(bus):
            return bus.write(payload, client=client, flush=flush)

        return self._enqueue('write', client, runner, queue_timeout)

    def write(self, data, client='OSPy plug-in', flush=True,
              queue_timeout=0.0, wait_timeout=None):
        return self.submit_write(
            data=data,
            client=client,
            flush=flush,
            queue_timeout=queue_timeout,
        ).wait(wait_timeout)

    def submit_read(self, size=1, client='OSPy plug-in', queue_timeout=0.0):
        """Enqueue a read and return an RS485QueueJob."""
        size = _bounded_length(size, _('RS485 read size'))

        def runner(bus):
            return bus.read(size=size, client=client)

        return self._enqueue('read', client, runner, queue_timeout)

    def read(self, size=1, client='OSPy plug-in',
             queue_timeout=0.0, wait_timeout=None):
        return self.submit_read(
            size=size,
            client=client,
            queue_timeout=queue_timeout,
        ).wait(wait_timeout)

    def submit_call(self, callback, client='OSPy plug-in', queue_timeout=0.0):
        """Enqueue an atomic protocol callback and return an RS485QueueJob."""
        if not callable(callback):
            raise TypeError(_('RS485 callback must be callable.'))

        def runner(bus):
            return bus.call(callback, client=client)

        return self._enqueue('callback', client, runner, queue_timeout)

    def call(self, callback, client='OSPy plug-in',
             queue_timeout=0.0, wait_timeout=None):
        """Execute a multi-step protocol callback atomically via the queue."""
        return self.submit_call(
            callback=callback,
            client=client,
            queue_timeout=queue_timeout,
        ).wait(wait_timeout)

    def _get_next(self, timeout=0.25):
        try:
            job = self._queue.get(True, timeout)
        except queue.Empty:
            return None

        job.started = time.time()
        with _state_lock:
            _state['queue_depth'] = self._queue.qsize()
            _state['queue_current_client'] = job.client
            _state['queue_current_operation'] = job.operation
            _state['queue_current_since'] = job.started
            _state['queue_last_wait_ms'] = int(max(0.0, job.started - job.created) * 1000)
        return job

    def _finish(self, job, result=None, error=None):
        job.result = result
        job.error = error
        job.finished = time.time()
        with _state_lock:
            if error is None:
                _state['queue_completed'] += 1
            else:
                _state['queue_failed'] += 1
            _state['queue_current_client'] = ''
            _state['queue_current_operation'] = ''
            _state['queue_current_since'] = 0
            _state['queue_depth'] = self._queue.qsize()
        job._done.set()
        try:
            self._queue.task_done()
        except Exception:
            pass

    def fail_pending(self, error):
        """Fail all jobs still waiting in the queue, for example on shutdown."""
        while True:
            try:
                job = self._queue.get_nowait()
            except queue.Empty:
                break
            self._finish(job, error=error)
        self._update_depth_state()


# Public FIFO queue. Dependent plug-ins should use this object instead of
# opening /dev/tty* directly.
rs485_queue = RS485Queue(maxsize=100)


def _modbus_crc16(data):
    """Return a Modbus RTU CRC-16 for discovery requests and responses."""
    crc = 0xFFFF
    for byte in bytes(bytearray(data)):
        crc ^= byte
        for _unused in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc


def _scan_request(address, function_code=0x03, register_count=1):
    frame = bytearray((
        int(address), int(function_code), 0x00, 0x00,
        (int(register_count) >> 8) & 0xFF, int(register_count) & 0xFF,
    ))
    crc = _modbus_crc16(frame)
    frame.extend((crc & 0xFF, (crc >> 8) & 0xFF))
    return bytes(frame)


def _valid_scan_response(response, address, function_code=0x03,
                         register_count=1, allow_any_address=False):
    """Accept a valid normal or Modbus exception response from this address."""
    frame = bytes(response or b'')
    if len(frame) < 5:
        return False
    if allow_any_address:
        if frame[0] < 1 or frame[0] > 0xFF:
            return False
    elif frame[0] != int(address):
        return False
    expected = _modbus_crc16(frame[:-2])
    received = frame[-2] | (frame[-1] << 8)
    if expected != received:
        return False
    if frame[1] == (int(function_code) | 0x80):
        return len(frame) == 5
    byte_count = int(register_count) * 2
    return (
        len(frame) == byte_count + 5
        and frame[1] == int(function_code)
        and frame[2] == byte_count
    )


def _hex_frame(data):
    return ' '.join('{:02X}'.format(value) for value in bytes(data or b''))


def _scan_probe(ser, phase, baudrate, serial_format, address,
                function_code, register_count, timeout, completed,
                allow_any_address=False):
    bytesize, parity, stopbits = serial_format
    request = _scan_request(address, function_code, register_count)
    with _state_lock:
        _state['scan_phase'] = phase
        _state['scan_baudrate'] = baudrate
        _state['scan_address'] = address
        _state['scan_bytesize'] = bytesize
        _state['scan_parity'] = parity
        _state['scan_stopbits'] = stopbits
        _state['scan_function'] = function_code
        _state['scan_register_count'] = register_count
        _state['scan_timeout'] = timeout
        _state['scan_request'] = _hex_frame(request)
        _state['scan_completed'] = completed
        _state['scan_message'] = _(
            '{}: {} baud, {}{}{}, address {}, function {}, {} register(s).'
        ).format(
            phase, baudrate, bytesize, parity, stopbits, address,
            function_code, register_count,
        )
    try:
        ser.reset_input_buffer()
    except Exception:
        pass
    ser.timeout = timeout
    written = ser.write(request)
    ser.flush()
    response = ser.read(5 + int(register_count) * 2)
    completed += 1
    response_hex = _hex_frame(response)
    with _state_lock:
        _state['transactions'] += 1
        _state['tx_bytes'] += int(written or 0)
        _state['rx_bytes'] += len(response)
        _state['last_client'] = _('RS485 bus scan')
        _state['scan_completed'] = completed
        if response_hex:
            _state['scan_response'] = response_hex
    valid = _valid_scan_response(
        response, address, function_code, register_count,
        allow_any_address=allow_any_address,
    )
    return completed, response, valid


def _scan_bus_serial(ser):
    """Run broadcast and direct Modbus discovery with visible live progress."""
    original_baudrate = ser.baudrate
    original_timeout = ser.timeout
    original_bytesize = ser.bytesize
    original_parity = ser.parity
    original_stopbits = ser.stopbits
    found = []
    found_keys = set()
    completed = 0
    try:
        # Some ZTS and compatible sensor firmware supports address 0xFF when
        # the configured slave address is unknown. Try the likely frame and
        # protocol variants slowly before the exhaustive direct-address pass.
        for baudrate in BUS_SCAN_BAUDRATES:
            if runtime.stop_event.is_set():
                raise RuntimeError(_('RS485 bus scan was stopped.'))
            for serial_format in BUS_SCAN_FORMATS:
                ser.baudrate = baudrate
                ser.bytesize, ser.parity, ser.stopbits = serial_format
                time.sleep(0.05)
                for function_code, register_count in BUS_SCAN_BROADCAST_VARIANTS:
                    completed, response, valid = _scan_probe(
                        ser=ser,
                        phase=_('Broadcast discovery'),
                        baudrate=baudrate,
                        serial_format=serial_format,
                        address=0xFF,
                        function_code=function_code,
                        register_count=register_count,
                        timeout=BUS_SCAN_BROADCAST_TIMEOUT,
                        completed=completed,
                        allow_any_address=True,
                    )
                    if valid:
                        actual_address = response[0]
                        key = (actual_address, baudrate) + tuple(serial_format)
                        if key not in found_keys:
                            found_keys.add(key)
                            found.append({
                                'address': actual_address,
                                'probe_address': 0xFF,
                                'baudrate': baudrate,
                                'bytesize': serial_format[0],
                                'parity': serial_format[1],
                                'stopbits': serial_format[2],
                                'function': function_code,
                                'register_count': register_count,
                                'response': _hex_frame(response),
                            })
                            with _state_lock:
                                _state['scan_found'] = list(found)

        # Repeat the broad protocol/framing matrix for the documented factory
        # address. This covers devices that do not implement address 0xFF and
        # devices whose response begins later than the fast exhaustive timeout.
        for baudrate in BUS_SCAN_BAUDRATES:
            if runtime.stop_event.is_set():
                raise RuntimeError(_('RS485 bus scan was stopped.'))
            for serial_format in BUS_SCAN_FORMATS:
                ser.baudrate = baudrate
                ser.bytesize, ser.parity, ser.stopbits = serial_format
                time.sleep(0.05)
                for address in BUS_SCAN_TARGET_ADDRESSES:
                    for function_code, register_count in BUS_SCAN_BROADCAST_VARIANTS:
                        completed, response, valid = _scan_probe(
                            ser=ser,
                            phase=_('Likely address discovery'),
                            baudrate=baudrate,
                            serial_format=serial_format,
                            address=address,
                            function_code=function_code,
                            register_count=register_count,
                            timeout=BUS_SCAN_BROADCAST_TIMEOUT,
                            completed=completed,
                        )
                        if valid:
                            key = (address, baudrate) + tuple(serial_format)
                            if key not in found_keys:
                                found_keys.add(key)
                                found.append({
                                    'address': address,
                                    'probe_address': address,
                                    'baudrate': baudrate,
                                    'bytesize': serial_format[0],
                                    'parity': serial_format[1],
                                    'stopbits': serial_format[2],
                                    'function': function_code,
                                    'register_count': register_count,
                                    'response': _hex_frame(response),
                                })
                                with _state_lock:
                                    _state['scan_found'] = list(found)

        # Direct scanning covers firmware that does not implement the 0xFF
        # discovery extension. ZTS speed sensors use function 03 with either
        # one speed register or two speed/force registers depending on model.
        serial_format = (8, 'N', 1.0)
        ser.bytesize, ser.parity, ser.stopbits = serial_format
        for baudrate in BUS_SCAN_BAUDRATES:
            if runtime.stop_event.is_set():
                raise RuntimeError(_('RS485 bus scan was stopped.'))
            ser.baudrate = baudrate
            time.sleep(0.05)
            for address in range(BUS_SCAN_FIRST_ADDRESS, BUS_SCAN_LAST_ADDRESS + 1):
                if runtime.stop_event.is_set():
                    raise RuntimeError(_('RS485 bus scan was stopped.'))
                for function_code, register_count in BUS_SCAN_DIRECT_VARIANTS:
                    completed, response, valid = _scan_probe(
                        ser=ser,
                        phase=_('Direct address scan'),
                        baudrate=baudrate,
                        serial_format=serial_format,
                        address=address,
                        function_code=function_code,
                        register_count=register_count,
                        timeout=BUS_SCAN_TIMEOUT,
                        completed=completed,
                    )
                    if valid:
                        key = (address, baudrate) + tuple(serial_format)
                        if key not in found_keys:
                            found_keys.add(key)
                            found.append({
                                'address': address,
                                'probe_address': address,
                                'baudrate': baudrate,
                                'bytesize': serial_format[0],
                                'parity': serial_format[1],
                                'stopbits': serial_format[2],
                                'function': function_code,
                                'register_count': register_count,
                                'response': _hex_frame(response),
                            })
                            with _state_lock:
                                _state['scan_found'] = list(found)
        return found
    finally:
        try:
            ser.baudrate = original_baudrate
            ser.bytesize = original_bytesize
            ser.parity = original_parity
            ser.stopbits = original_stopbits
            ser.timeout = original_timeout
            ser.reset_input_buffer()
        except Exception:
            pass


def start_bus_scan():
    """Queue a non-blocking exclusive Modbus bus scan."""
    if not plugin_options.get('enabled', False):
        return False, _('Enable and save the RS485 worker before scanning the bus.')
    if not SERIAL_AVAILABLE:
        return False, _('Python serial module is not installed.')
    current_worker = globals().get('worker')
    if current_worker is None or not current_worker.is_alive():
        return False, _('RS485 worker is not running.')

    with _state_lock:
        if _state.get('scan_active', False):
            return False, _('RS485 bus scan is already in progress.')
        _state['scan_active'] = True
        _state['scan_started'] = time.time()
        _state['scan_finished'] = 0
        _state['scan_baudrate'] = 0
        _state['scan_address'] = 0
        _state['scan_phase'] = ''
        _state['scan_bytesize'] = 8
        _state['scan_parity'] = 'N'
        _state['scan_stopbits'] = 1.0
        _state['scan_function'] = 0
        _state['scan_register_count'] = 0
        _state['scan_timeout'] = 0
        _state['scan_request'] = ''
        _state['scan_response'] = ''
        _state['scan_completed'] = 0
        _state['scan_total'] = BUS_SCAN_TOTAL
        _state['scan_found'] = []
        _state['scan_error'] = ''
        _state['scan_message'] = _('Scanning RS485 bus for Modbus devices...')

    def runner(bus):
        error = None
        found = []
        try:
            found = bus.call(_scan_bus_serial, client=_('RS485 bus scan'))
            return found
        except Exception as err:
            error = err
            raise
        finally:
            with _state_lock:
                _state['scan_active'] = False
                _state['scan_finished'] = time.time()
                if error is not None:
                    _state['scan_error'] = str(error)
                    _state['scan_message'] = _('RS485 bus scan failed: {}').format(error)
                elif found:
                    _state['scan_message'] = _(
                        'RS485 bus scan completed; {} device(s) found.'
                    ).format(len(found))
                else:
                    _state['scan_message'] = _(
                        'RS485 bus scan completed; no Modbus device responded.'
                    )

    try:
        rs485_queue._enqueue('bus_scan', _('RS485 bus scan'), runner, 0.0)
    except Exception as err:
        with _state_lock:
            _state['scan_active'] = False
            _state['scan_finished'] = time.time()
            _state['scan_error'] = str(err)
            _state['scan_message'] = _('Unable to start RS485 bus scan: {}').format(err)
        return False, str(err)
    return True, _('RS485 bus scan started.')


# -----------------------------------------------------------------------------
# Public helper API for dependent OSPy plug-ins
# -----------------------------------------------------------------------------

def rs485_transaction(request, response_length=0, client='OSPy plug-in',
                      clear_input=True, delay=0.0, read_until=None, max_read=4096,
                      queue_timeout=0.0, wait_timeout=None):
    return rs485_queue.transaction(
        request=request,
        response_length=response_length,
        client=client,
        clear_input=clear_input,
        delay=delay,
        read_until=read_until,
        max_read=max_read,
        queue_timeout=queue_timeout,
        wait_timeout=wait_timeout,
    )


def rs485_write(data, client='OSPy plug-in', flush=True,
                queue_timeout=0.0, wait_timeout=None):
    return rs485_queue.write(
        data=data,
        client=client,
        flush=flush,
        queue_timeout=queue_timeout,
        wait_timeout=wait_timeout,
    )


def rs485_read(size=1, client='OSPy plug-in',
               queue_timeout=0.0, wait_timeout=None):
    return rs485_queue.read(
        size=size,
        client=client,
        queue_timeout=queue_timeout,
        wait_timeout=wait_timeout,
    )


def rs485_call(callback, client='OSPy plug-in',
               queue_timeout=0.0, wait_timeout=None):
    return rs485_queue.call(
        callback=callback,
        client=client,
        queue_timeout=queue_timeout,
        wait_timeout=wait_timeout,
    )


class RS485Worker(Thread):
    """Own the serial port and execute queued requests in FIFO order."""

    def __init__(self):
        Thread.__init__(self)
        self.daemon = True
        self._stop_event = runtime.stop_event
        self.start()

    def stop(self):
        self._stop_event.set()

    def _process_job(self, job):
        try:
            result = job._runner(rs485_bus)
            rs485_queue._finish(job, result=result)
        except AdapterNotFoundError as err:
            rs485_bus.close()
            _set_status('waiting', str(err), '')
            rs485_queue._finish(job, error=err)
        except Exception as err:
            current = get_rs485_status()
            if current.get('status') not in ('error', 'dependency_error'):
                message = _('RS485 queue operation failed: {}').format(err)
                _set_status('error', message, current.get('active_port') or '')
                _record_error('queue_job', message)
            rs485_queue._finish(job, error=err)

    def run(self):
        disabled_logged = False
        dependency_logged = False
        next_probe = 0

        while not self._stop_event.is_set():
            try:
                _normalize_options()

                if not plugin_options.get('enabled', False):
                    rs485_bus.close()
                    rs485_queue.fail_pending(RuntimeError(_('RS485 Communication plug-in is disabled.')))
                    _set_status('disabled', _('Plug-in is disabled.'), '')
                    if not disabled_logged:
                        log.info(NAME, _('RS485 Communication plug-in is disabled.'))
                        disabled_logged = True
                    self._stop_event.wait(0.25)
                    continue

                disabled_logged = False

                if not SERIAL_AVAILABLE:
                    rs485_bus.close()
                    error = RuntimeError(_('Python serial module is not installed. Install pyserial and restart OSPy.'))
                    rs485_queue.fail_pending(error)
                    message = str(error)
                    _set_status('dependency_error', message, '')
                    if not dependency_logged:
                        log.error(NAME, message)
                        dependency_logged = True
                    self._stop_event.wait(0.25)
                    continue

                dependency_logged = False

                # Queue traffic has priority. A short timeout keeps request
                # latency low while still letting the worker monitor the adapter.
                job = rs485_queue._get_next(timeout=0.25)
                if job is not None:
                    self._process_job(job)
                    next_probe = time.time() + WORKER_INTERVAL
                    continue

                now = time.time()
                if now < next_probe:
                    continue
                next_probe = now + WORKER_INTERVAL

                try:
                    port = rs485_bus.ensure_ready()
                    current = get_rs485_status()
                    if current.get('status') != 'communicating':
                        _set_status('ok', _('Adapter is ready on {}.').format(port), port)
                except AdapterNotFoundError as err:
                    rs485_bus.close()
                    _set_status('waiting', str(err), '')
                except Exception as err:
                    rs485_bus.close()
                    message = str(err)
                    _set_status('error', message, '')
                    _record_error('worker', message)

            except Exception:
                message = _('RS485 worker error: {}').format(traceback.format_exc().splitlines()[-1])
                _set_status('error', message, '')
                _record_error('worker_outer', message)
                self._stop_event.wait(0.25)

        rs485_queue.fail_pending(RuntimeError(_('RS485 worker has stopped.')))
        rs485_bus.close()


worker = None


def start():
    global worker
    if worker is None:
        worker = RS485Worker()


def stop():
    global worker
    rs485_queue.fail_pending(RuntimeError(_('RS485 worker is stopping.')))
    if worker is not None:
        worker.stop()
        worker.join(10)
        if worker.is_alive():
            log.error(NAME, _('The RS485 worker did not stop within the timeout.'))
        else:
            worker = None
    else:
        rs485_bus.close()


def health():
    """OSPy plug-in diagnostics hook."""
    state = get_rs485_status()
    worker_running = worker is not None and worker.is_alive()
    details = {
        _('Worker thread'): _('Running') if worker_running else _('Stopped'),
        _('Enabled'): _('Yes') if plugin_options.get('enabled', False) else _('No'),
        _('Configured port'): plugin_options.get('port', 'auto'),
        _('Active port'): state.get('active_port') or _('Not available'),
        _('Detected port'): state.get('detected_port') or _('Not available'),
        _('Serial dependency'): _('Available') if SERIAL_AVAILABLE else _('Missing'),
        _('Communication speed'): plugin_options.get('baudrate', DEFAULT_BAUDRATE),
        _('Transactions'): state.get('transactions', 0),
        _('TX bytes'): state.get('tx_bytes', 0),
        _('RX bytes'): state.get('rx_bytes', 0),
        _('Queue waiting'): state.get('queue_depth', 0),
        _('Queue peak'): state.get('queue_peak', 0),
        _('Queue completed'): state.get('queue_completed', 0),
        _('Queue errors'): state.get('queue_failed', 0),
        _('Last communication'): state.get('last_success_text'),
    }
    if state.get('usb_id'):
        details[_('USB ID')] = state['usb_id']
    if state.get('description'):
        details[_('Device description')] = state['description']
    if state.get('last_error_message'):
        details[_('Last error')] = state['last_error_message']

    if not plugin_options.get('enabled', False):
        return {'status': 'unknown', 'summary': _('RS485 Communication is disabled.'), 'details': details}
    if not worker_running:
        return {'status': 'error', 'summary': _('RS485 worker is stopped.'), 'details': details}
    if not SERIAL_AVAILABLE:
        return {'status': 'error', 'summary': _('Python serial module is not installed.'), 'details': details}
    if state.get('status') == 'error' or state.get('status') == 'dependency_error':
        return {'status': 'error', 'summary': state.get('summary'), 'details': details}
    if state.get('status') == 'waiting':
        return {'status': 'warning', 'summary': state.get('summary'), 'details': details}
    return {'status': 'ok', 'summary': state.get('summary'), 'details': details}


def test_adapter():
    """Test USB discovery and whether the selected serial port can be opened.

    This intentionally does not transmit arbitrary bytes onto the RS485 bus.
    A true A/B line test needs a responding RS485 device or a second adapter.
    The port-open test also works while the worker is disabled.
    """
    with _state_lock:
        _state['last_test'] = time.time()

    if not SERIAL_AVAILABLE:
        message = _('Test failed: Python serial module is not installed.')
        with _state_lock:
            _state['last_test_ok'] = False
            _state['last_test_result'] = message
        _set_status('dependency_error', message, '')
        _record_error('test_dependency', message)
        return False, message

    try:
        with _bus_lock:
            port = _resolve_selected_port()
            if not port:
                raise AdapterNotFoundError(_('Waveshare CH343G adapter was not found.'))

            if plugin_options.get('enabled', False):
                ser = rs485_bus._ensure_open_locked()
                if not getattr(ser, 'is_open', True):
                    raise RuntimeError(_('Serial port is not open.'))
            else:
                # When disabled, do a temporary open/close test without starting
                # the worker or changing the saved enabled setting.
                temp = None
                try:
                    temp = serial.Serial(**rs485_bus._serial_kwargs(port))
                    if not getattr(temp, 'is_open', True):
                        raise RuntimeError(_('Serial port is not open.'))
                finally:
                    if temp is not None:
                        try:
                            temp.close()
                        except Exception:
                            pass

        info = _find_port_info(port)
        if info:
            with _state_lock:
                _copy_port_info_to_state(info)
        message = _('Test OK: adapter found and serial port {} can be opened.').format(port)
        with _state_lock:
            _state['last_test_ok'] = True
            _state['last_test_result'] = message
        if plugin_options.get('enabled', False):
            _set_status('ok', message, port)
        log.info(NAME, message)
        return True, message
    except Exception as err:
        message = _('Adapter test failed: {}').format(err)
        with _state_lock:
            _state['last_test_ok'] = False
            _state['last_test_result'] = message
        if plugin_options.get('enabled', False):
            _set_status('error', message, '')
        _record_error('test', message)
        return False, message


# -----------------------------------------------------------------------------
# Web pages
# -----------------------------------------------------------------------------

class settings_page(ProtectedPage):
    def GET(self):
        try:
            ports = get_serial_ports()
            state = get_rs485_status()
            return self.plugin_render.rs485_communication(plugin_options, ports, state, log.events(NAME))
        except Exception:
            log.error(NAME, _('RS485 Communication plug-in') + ':\n' + traceback.format_exc())
            msg = _('An internal error was found in the system, see the error log for more information.')
            return self.core_render.notice('/', msg)

    def POST(self):
        try:
            qdict = web.input()
            verify_csrf(qdict)
            action = str(qdict.get('action', 'save'))
            if action not in ('save', 'scan', 'test', 'scan_bus'):
                raise web.badrequest(_('Unknown RS485 settings action.'))

            if action == 'scan_bus':
                started, message = start_bus_scan()
                if started:
                    log.info(NAME, message)
                else:
                    log.error(NAME, message)
                raise web.seeother(plugin_url(settings_page), True)

            if action == 'scan':
                found = detect_waveshare_adapter()
                if found:
                    message = _('Waveshare CH343G adapter found on {}.').format(found['device'])
                    _set_status('ok', message, found['device'])
                    log.info(NAME, message)
                else:
                    message = _('Waveshare CH343G adapter was not found.')
                    _set_status('waiting', message, '')
                    log.info(NAME, message)
                raise web.seeother(plugin_url(settings_page), True)

            if action == 'test':
                test_adapter()
                raise web.seeother(plugin_url(settings_page), True)

            # Save settings. Explicit checkbox handling mirrors older OSPy
            # plug-ins and avoids dependence on web.py's absent-checkbox rules.
            plugin_options['enabled'] = ('enabled' in qdict and str(qdict.get('enabled')).lower() in ('on', 'true', '1', 'yes'))
            plugin_options['port'] = _normalize_port(qdict.get('port', plugin_options.get('port', 'auto')))
            plugin_options['baudrate'] = _safe_int(qdict.get('baudrate', plugin_options.get('baudrate', DEFAULT_BAUDRATE)), DEFAULT_BAUDRATE)
            plugin_options['bytesize'] = _safe_int(qdict.get('bytesize', plugin_options.get('bytesize', 8)), 8)
            plugin_options['parity'] = str(qdict.get('parity', plugin_options.get('parity', 'N'))).upper()
            plugin_options['stopbits'] = _safe_float(qdict.get('stopbits', plugin_options.get('stopbits', 1.0)), 1.0)
            plugin_options['timeout'] = _safe_float(qdict.get('timeout', plugin_options.get('timeout', 1.0)), 1.0)
            plugin_options['write_timeout'] = _safe_float(qdict.get('write_timeout', plugin_options.get('write_timeout', 1.0)), 1.0)
            _normalize_options()
            rs485_bus.refresh()
            message = _('RS485 Communication settings updated successfully.')
            log.info(NAME, message)
            raise web.seeother(plugin_url(settings_page), True)
        except web.HTTPError:
            raise
        except Exception:
            log.error(NAME, _('RS485 Communication plug-in') + ':\n' + traceback.format_exc())
            msg = _('An internal error was found in the system, see the error log for more information.')
            return self.core_render.notice('/', msg)


class help_page(ProtectedPage):
    def GET(self):
        return self.plugin_render.rs485_communication_help()


class status_json(ProtectedPage):
    def GET(self):
        web.header('Content-Type', 'application/json; charset=utf-8')
        web.header('Cache-Control', 'no-store')
        return json.dumps(get_rs485_status(), ensure_ascii=False)


class ports_json(ProtectedPage):
    def GET(self):
        web.header('Content-Type', 'application/json; charset=utf-8')
        web.header('Cache-Control', 'no-store')
        return json.dumps(get_serial_ports(), ensure_ascii=False)
