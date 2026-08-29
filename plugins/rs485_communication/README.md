# RS485 Communication

Central RS485 communication plug-in for OSPy.

The plug-in owns one serial RS485 interface and provides one public FIFO queue (`rs485_queue`) for all other OSPy plug-ins. It is intended primarily for the Waveshare industrial USB TO RS485 (B) adapter based on the WCH CH343G chip.

## Features

- Enable/disable the RS485 worker.
- Automatic Waveshare CH343G detection (USB VID:PID `1A86:55D3`).
- Manual Linux serial port selection (`/dev/ttyACM0`, `/dev/serial/by-id/...`, etc.).
- Configurable baud rate, data bits, parity, stop bits and timeouts.
- Background Modbus discovery using address 255 broadcast probes, addresses 1-254, functions 03 and 04, one- and two-register reads, common sensor baud rates and 8N1/8E1/8O1 framing, with live test details and validated response frames.
- Live state: Disabled / Waiting / OK / Communicating / Error.
- Shows detected and active port, device description, USB ID, last communication, last client plug-in and TX/RX counters.
- Safe adapter test (USB discovery + opening the selected serial port).
- Public `rs485_queue` FIFO: all clients are processed one by one by one worker.
- Queue diagnostics: waiting jobs, current client/operation, completed/error counters, peak queue depth and last queue wait time.
- Synchronous and asynchronous transaction API.
- Atomic callback API for protocols that need several write/read operations.
- OSPy `health()` diagnostics hook.
- CSRF-protected settings/actions and gettext-ready UI strings.

The serial format is a property of the complete physical bus, so every device connected to the same A/B pair normally has to use the configured values. The default is `4800 baud, 8 data bits, no parity, 1 stop bit` (`4800 8N1`), matching the factory setting documented for the ZTS-3000-FSJT wind sensor. Changing this setting changes how OSPy opens the USB adapter; it does not reconfigure a slave device. A device-specific plug-in must send the documented protocol command before both sides are switched to a new speed.

## Dependency

Requires `pyserial` (`serial` Python module). The plug-in manifest declares this dependency.

## Public API

The recommended interface is the single queue object:

```python
from plugins.rs485_communication import rs485_queue
```

### Synchronous request/response

```python
reply = rs485_queue.transaction(
    request=request_frame,
    response_length=expected_bytes,
    client='My OSPy plug-in',
    clear_input=True,
    delay=0.05,
)
```

### Asynchronous FIFO request

```python
job = rs485_queue.submit_transaction(
    request=request_frame,
    response_length=expected_bytes,
    client='My OSPy plug-in',
)

# The worker executes queued jobs in FIFO order.
reply = job.wait(timeout=3)
```

### Atomic multi-step protocol callback

```python
def protocol_exchange(ser):
    ser.reset_input_buffer()
    ser.write(frame_1)
    ser.flush()
    first = ser.read(8)

    ser.write(frame_2)
    ser.flush()
    second = ser.read(8)
    return first, second

first, second = rs485_queue.call(
    protocol_exchange,
    client='My protocol plug-in',
)
```

The callback is executed by the RS485 worker. No other queued plug-in can access the bus until it returns.

Convenience helper functions are also exported: `rs485_transaction()`, `rs485_write()`, `rs485_read()` and `rs485_call()`. They all use `rs485_queue`; they do not bypass it.

Do not open the same `/dev/tty*` interface directly from dependent plug-ins.

Frames, fixed-length reads and delimiter reads are bounded to 65,536 bytes and transaction delays are bounded to 30 seconds. These limits prevent a faulty dependent plug-in from reserving excessive memory or monopolizing the shared worker indefinitely.

## Adapter test limitation

Opening the USB serial port confirms OS/driver/permissions and serial configuration. It cannot prove RS485 A/B wiring or a slave response without transmitting a protocol-specific request. Protocol-specific tests belong in the dependent device plug-in.
