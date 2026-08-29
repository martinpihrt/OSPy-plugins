import ast
import json
import os
import pathlib
import queue
import re
import threading
import time
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
PLUGIN = ROOT / 'plugins' / 'rs485_communication'
SOURCE_PATH = PLUGIN / '__init__.py'
SOURCE = SOURCE_PATH.read_text(encoding='utf-8-sig')


def load_selected_symbols(names, extra_globals=None):
    tree = ast.parse(SOURCE, filename=str(SOURCE_PATH))
    selected = [
        node for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in names
    ]
    namespace = {
        '__builtins__': __builtins__,
        '_': lambda value: value,
        'os': os,
        're': re,
        'queue': queue,
        'time': time,
        'Event': threading.Event,
        'RLock': threading.RLock,
        'DEFAULT_BAUDRATE': 4800,
        'MAX_PORT_LENGTH': 255,
        'MAX_FRAME_LENGTH': 65536,
        'MAX_TRANSACTION_DELAY': 30.0,
    }
    if extra_globals:
        namespace.update(extra_globals)
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(SOURCE_PATH), 'exec'), namespace)
    return namespace


class AliveWorker:
    @staticmethod
    def is_alive():
        return True


class TrackingOptions(dict):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.assignments = 0

    def __setitem__(self, key, value):
        self.assignments += 1
        super().__setitem__(key, value)


class RS485CommunicationTests(unittest.TestCase):
    def test_manifest_declares_required_serial_dependency_and_permission(self):
        manifest = json.loads((PLUGIN / 'plugin.json').read_text(encoding='utf-8'))
        self.assertEqual(manifest['version'], '1.0.3')
        self.assertIn('system', manifest['permissions'])
        self.assertIn(
            {'module': 'serial', 'package': 'pyserial', 'required': True},
            manifest['requirements'],
        )

    def test_settings_actions_are_post_and_csrf_protected(self):
        template = (PLUGIN / 'templates' / 'rs485_communication.html').read_text(encoding='utf-8')
        self.assertIn('method="post"', template)
        self.assertIn('$:csrf_input()', template)
        csrf = SOURCE.index('verify_csrf(qdict)')
        action = SOURCE.index("if action == 'scan':")
        mutation = SOURCE.index("plugin_options['enabled'] =", action)
        self.assertLess(csrf, action)
        self.assertLess(csrf, mutation)
        self.assertIn('except web.HTTPError:', SOURCE)

    def test_serial_defaults_match_zts_sensor_and_speed_is_editable(self):
        template = (PLUGIN / 'templates' / 'rs485_communication.html').read_text(encoding='utf-8')
        self.assertIn('DEFAULT_BAUDRATE = 4800', SOURCE)
        self.assertIn('name="baudrate"', template)
        self.assertIn('4800', template)
        self.assertIn('9600', template)

    def test_bus_scan_is_background_bounded_and_visible(self):
        template = (PLUGIN / 'templates' / 'rs485_communication.html').read_text(encoding='utf-8')
        self.assertIn("action not in ('save', 'scan', 'test', 'scan_bus')", SOURCE)
        self.assertIn('def start_bus_scan():', SOURCE)
        self.assertIn('BUS_SCAN_BAUDRATES = (1200, 2400, 4800, 9600, 19200, 38400, 57600, 115200)', SOURCE)
        self.assertIn('BUS_SCAN_LAST_ADDRESS = 254', SOURCE)
        self.assertIn('BUS_SCAN_BROADCAST_VARIANTS', SOURCE)
        self.assertIn('BUS_SCAN_TARGET_ADDRESSES = (1,)', SOURCE)
        self.assertIn("BUS_SCAN_FORMATS = ((8, 'N', 1.0), (8, 'E', 1.0), (8, 'O', 1.0))", SOURCE)
        self.assertIn("rs485_queue._enqueue('bus_scan'", SOURCE)
        self.assertIn('id="scanBusButton"', template)
        self.assertIn('id="busScanProgress"', template)
        self.assertIn('id="busScanFound"', template)

    def test_bus_scan_validates_frames_and_restores_serial_settings(self):
        state = {
            'transactions': 0,
            'tx_bytes': 0,
            'rx_bytes': 0,
            'last_client': '',
            'scan_baudrate': 0,
            'scan_address': 0,
            'scan_completed': 0,
        }
        runtime = type('Runtime', (), {'stop_event': threading.Event()})()
        symbols = load_selected_symbols(
            {
                '_modbus_crc16', '_scan_request', '_valid_scan_response',
                '_hex_frame', '_scan_probe', '_scan_bus_serial',
            },
            {
                '_state': state,
                '_state_lock': threading.RLock(),
                'runtime': runtime,
                'BUS_SCAN_BAUDRATES': (4800, 9600),
                'BUS_SCAN_FIRST_ADDRESS': 1,
                'BUS_SCAN_LAST_ADDRESS': 10,
                'BUS_SCAN_TIMEOUT': 0.01,
                'BUS_SCAN_BROADCAST_TIMEOUT': 0.01,
                'BUS_SCAN_FORMATS': ((8, 'N', 1.0),),
                'BUS_SCAN_BROADCAST_VARIANTS': ((0x03, 1),),
                'BUS_SCAN_TARGET_ADDRESSES': (1,),
                'BUS_SCAN_DIRECT_VARIANTS': ((0x03, 1),),
            },
        )

        class FakeSerial:
            def __init__(self):
                self.baudrate = 4800
                self.timeout = 1.0
                self.bytesize = 7
                self.parity = 'E'
                self.stopbits = 2.0
                self.request = b''

            def reset_input_buffer(self):
                pass

            def write(self, request):
                self.request = request
                return len(request)

            def flush(self):
                pass

            def read(self, _size):
                if self.baudrate == 9600 and self.request[0] == 7:
                    frame = bytearray((7, 3, 2, 0, 36))
                    crc = symbols['_modbus_crc16'](frame)
                    frame.extend((crc & 0xFF, crc >> 8))
                    return bytes(frame)
                return b''

        serial_port = FakeSerial()
        found = symbols['_scan_bus_serial'](serial_port)
        self.assertEqual(found[0]['address'], 7)
        self.assertEqual(found[0]['baudrate'], 9600)
        self.assertEqual(serial_port.baudrate, 4800)
        self.assertEqual(serial_port.timeout, 1.0)
        self.assertEqual(serial_port.bytesize, 7)
        self.assertEqual(serial_port.parity, 'E')
        self.assertEqual(serial_port.stopbits, 2.0)

    def test_settings_use_standard_plugin_switch_without_text_labels(self):
        template = (PLUGIN / 'templates' / 'rs485_communication.html').read_text(encoding='utf-8')
        css = (PLUGIN / 'static' / 'rs485_communication.css').read_text(encoding='utf-8')
        self.assertIn('class="switch"', template)
        self.assertIn('name="enabled" type="checkbox"', template)
        self.assertIn('class="slider"', template)
        self.assertNotIn('id="enabledToggle"', template)
        self.assertNotIn('class="toggleleft"', template)
        self.assertIn('.switch input:checked + .slider', css)
        self.assertIn('class="alert ', template)
        self.assertIn('class="optionList"', template)

    def test_frame_and_read_sizes_are_bounded(self):
        symbols = load_selected_symbols({'_as_bytes', '_bounded_length'})
        as_bytes = symbols['_as_bytes']
        bounded_length = symbols['_bounded_length']
        self.assertEqual(as_bytes([1, 2, 255]), b'\x01\x02\xff')
        self.assertEqual(bounded_length(65536, 'read'), 65536)
        with self.assertRaises(ValueError):
            as_bytes(b'x' * 65537)
        with self.assertRaises(ValueError):
            bounded_length(65537, 'read')
        with self.assertRaises(ValueError):
            bounded_length(-1, 'read')

    def test_fixed_length_transaction_rejects_short_response(self):
        self.assertIn('len(response) != response_length', SOURCE)
        self.assertIn('RS485 response timeout:', SOURCE)
        self.assertIn('_record_failed_transfer(', SOURCE)

    def test_manual_port_validation_rejects_relative_and_control_paths(self):
        symbols = load_selected_symbols({'_normalize_port'})
        normalize_port = symbols['_normalize_port']
        self.assertEqual(normalize_port(' auto '), 'auto')
        with self.assertRaises(ValueError):
            normalize_port('ttyUSB0')
        with self.assertRaises(ValueError):
            normalize_port('/dev/ttyUSB0\nignored')

    def test_normalization_does_not_rewrite_unchanged_options(self):
        options = TrackingOptions({
            'port': 'auto',
            'baudrate': 4800,
            'bytesize': 8,
            'parity': 'N',
            'stopbits': 1.0,
            'timeout': 1.0,
            'write_timeout': 1.0,
        })
        symbols = load_selected_symbols(
            {
                '_safe_int', '_safe_float', '_set_option_if_changed',
                '_normalize_port', '_normalize_options',
            },
            {'plugin_options': options},
        )
        symbols['_normalize_options']()
        self.assertEqual(options.assignments, 0)
        dict.__setitem__(options, 'parity', 'invalid')
        symbols['_normalize_options']()
        self.assertEqual(options['parity'], 'N')
        self.assertEqual(options.assignments, 1)

    def test_queue_is_fifo_and_rejects_work_while_disabled(self):
        state = {
            'queue_depth': 0,
            'queue_peak': 0,
            'queue_completed': 0,
            'queue_failed': 0,
            'queue_current_client': '',
            'queue_current_operation': '',
            'queue_current_since': 0,
            'queue_last_wait_ms': 0,
        }
        options = {'enabled': True}
        symbols = load_selected_symbols(
            {'_as_bytes', 'RS485QueueJob', 'RS485Queue'},
            {
                '_state': state,
                '_state_lock': threading.RLock(),
                'plugin_options': options,
                'worker': AliveWorker(),
            },
        )
        rs485_queue = symbols['RS485Queue'](maxsize=2)
        first = rs485_queue.submit_write(b'first', client='first')
        second = rs485_queue.submit_write(b'second', client='second')
        self.assertEqual(rs485_queue._get_next(timeout=0).id, first.id)
        self.assertEqual(rs485_queue._get_next(timeout=0).id, second.id)
        options['enabled'] = False
        with self.assertRaises(RuntimeError):
            rs485_queue.submit_write(b'third')

    def test_json_status_endpoints_are_protected_and_not_cached(self):
        self.assertIn('class status_json(ProtectedPage):', SOURCE)
        self.assertIn('class ports_json(ProtectedPage):', SOURCE)
        self.assertGreaterEqual(SOURCE.count("web.header('Cache-Control', 'no-store')"), 2)

    def test_help_uses_local_adapter_images_and_vendor_product_link(self):
        help_template = (
            PLUGIN / 'templates' / 'rs485_communication_help.html'
        ).read_text(encoding='utf-8')
        for image in (
            'Waveshare-USB-to-RS485-1.webp',
            'Waveshare-USB-to-RS485-2.webp',
            'Waveshare-USB-to-RS485-detail.gif',
        ):
            self.assertTrue((PLUGIN / 'static' / 'images' / image).is_file())
            self.assertIn('/plugins/rs485_communication/static/images/' + image, help_template)
        self.assertIn('rpishop.cz/datove-redukce/5360-', help_template)
        self.assertIn('rel="noopener noreferrer"', help_template)


if __name__ == '__main__':
    unittest.main()
