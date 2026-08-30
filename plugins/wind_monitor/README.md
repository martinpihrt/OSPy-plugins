# Wind Speed Monitor

Tested with Python 3.8+.

The plug-in measures an anemometer from either the original PCF8583 event counter on I2C address `0x50` or `0x51`, or a ZTS-3000-FSJT wind sensor using Modbus RTU through the shared RS485 Communication plug-in. It can display and log wind, stop selected running stations, send an e-mail, start a configured program after validated wind thresholds are exceeded, or run a separate safety program once when measurement fails repeatedly.

## Measurement

The original PCF8583 source is an external pulse counter connected to the Raspberry Pi I2C bus, not a direct Raspberry Pi GPIO pulse input. The pulses-per-rotation and speed-per-rotation calibration fields apply only to this source.

For every measurement the plug-in:

1. verifies that the PCF8583 is in event-counter mode;
2. clears registers `0x01` to `0x03`;
3. waits approximately ten seconds;
4. reads the three counter registers as one I2C block;
5. validates every BCD digit;
6. calculates the pulse rate from the actual monotonic elapsed time;
7. calculates wind speed from the configured pulses and speed per rotation.

Using the actual interval is important. If another I2C device temporarily holds the shared bus after the nominal ten-second wait, the counter continues counting. Older versions always divided by ten and could therefore report an artificially high speed.

```text
pulses per second = raw pulse count / actual elapsed seconds
speed in m/s      = pulses per second / pulses per rotation × speed per rotation
speed in km/h     = speed in m/s × 3.6
```

Calibration and threshold fields accept both a decimal point and a decimal comma.

For the RS485 source, Wind Monitor sends `01 03 00 00 00 02 C4 0B` at the default device address 1 and validates the returned address, function, byte count and Modbus CRC. Register 0 is decoded in tenths of a meter per second and register 1 contains wind force. The ZTS-3000-FSJT factory settings documented by its manufacturer are address 1, 4800 baud and 8N1.

Wind Monitor uses the public FIFO transaction queue from RS485 Communication and never opens the serial port itself. The RS485 Communication plug-in is an optional manifest dependency: it must be installed, enabled and running when the RS485 source and wind measurement are enabled, but it is not required for the PCF8583 source. Communication speed, framing and serial-port selection are configured centrally in RS485 Communication because all devices on one bus share those settings.

## Overview and trend

The overview page contains the current and maximum speed, operational status, a graph, and a one-minute trend. Live values refresh through a JSON endpoint without reloading the page. The trend compares older and newer accepted readings and reports rising, falling, steady, or waiting for sufficient data.

The mobile API returns the stable trend codes `up`, `down`, `steady` and `unknown`. The OSPy mobile application renders these codes as localized rising, falling, steady and waiting states and refreshes the expanded operating-data panel automatically.

## Plausibility and action protection

The plausibility filter rejects an accepted-speed candidate above the configured maximum. Rejected readings:

- do not replace the current speed;
- do not change the stored maximum;
- are not written to the measurement graph or database;
- cannot stop stations, send e-mail, or start a program.

Station stopping and its e-mail notification require the configured number of consecutive accepted measurements above the stop threshold. This avoids an immediate action after one isolated pulse spike. Program actions retain their existing repetition and interval configuration and only receive accepted measurements.

The default filter limit is 40 m/s (144 km/h), and the default station/e-mail confirmation count is two measurements.

## Error e-mail notifications

The E-mail section in settings contains the shared message subject and e-mail plug-in selection. The existing station-protection switch controls the hazard message sent after confirmed excessive wind, while Send measurement errors by e-mail independently controls technical fault notifications.

When technical notifications are enabled, the plug-in sends an e-mail for a failed I2C bus open, PCF8583 setup or counter read, a missing or stopped RS485 Communication dependency, RS485 queue or serial failure, timeout, invalid address, function, response length or CRC, rejected implausible measurement, and an unexpected measurement-worker error. A valid accepted measurement, including zero wind speed, is not an error.

The first failure starts one fault incident and sends one message immediately. Repeated failures belonging to the active incident do not send another message until the configurable reminder interval expires, which defaults to six hours and can be set from one to 168 hours. The first accepted measurement closes the incident, allowing a later independent failure to send a new immediate notification. Delivery failures are written to the OSPy log and Diagnostics state and retried after the reminder interval; a failed attempt is not recorded as a successfully sent fault e-mail.

## Sensor-failure safety program

The sensor-failure program is independent of the wind-threshold program. When enabled, it counts consecutive failed or rejected measurements and starts the separately selected OSPy program when the configured count is reached. The default confirmation count is three and the accepted range is one to 100 failures.

Only one start is attempted during a continuous fault incident. Further failure actions remain blocked regardless of subsequent error count or e-mail reminders. One valid accepted measurement, including zero wind speed, closes the incident and arms the action for a future independent failure. An intentional RS485 device scan pauses measurement and does not increment the failure counter or start the safety program.

While measurement is unavailable, ordinary Wind Monitor threshold actions cannot be evaluated. Venetian Blind temperature shading independently requires fresh accepted safe-wind samples, so it does not lower blinds until valid wind measurements resume.

## Measurement diagnostic log

Diagnostic logging is intended for temporary troubleshooting. It writes bounded JSON lines to the OSPy plug-in data directory and rotates the file at approximately 1 MB. The diagnostic page can display, download, refresh, and delete the log.

PCF8583 records include:

- PCF8583 setup and control-register confirmation;
- I2C retry errors;
- selected I2C address;
- raw counter bytes and decoded pulse count;
- I2C lock wait and actual measurement duration;
- pulse rate and calculated speed;
- whether the reading was accepted and any rejection reason.

RS485 records include the selected Modbus address, complete response data, decoded speed, wind force, CRC validation and any queue, serial or protocol error.

Disable diagnostic logging after the problem has been captured.

## Logging and actions

Accepted measurements can be written to the local graph files or through the optional Database Connector plug-in. A configured maximum can be reset manually or after an interval. Selected running stations can be stopped after the stop threshold is confirmed, and an optional e-mail can be sent. A separate program action uses its own threshold, repetition count, interval, and suppression period.

The plug-in declares SMBus and RS485 Communication as optional dependencies, uses the shared OSPy worker lifecycle, closes its I2C handle during shutdown, and reports source-specific measurement, active fault, bounded error-notification, filter and diagnostic state through the Diagnostics health interface.

## Hardware

For the PCF8583 source, the I2C bus must be enabled and the counter connected correctly. The original wiring diagram remains available at:

Addresses `0x50` and `0x51` are alternatives; the plug-in occupies only the address selected in its settings. OSPy can install and run Wind Speed Monitor beside another selectable-address plug-in when each receives a different address. If the preferred address is occupied during activation, the plug-in selects the free alternative. The settings page refuses an address currently used by another enabled plug-in, keeps the preceding settings and displays the conflict in a red status bar without leaving the page.

`/plugins/wind_monitor/static/images/schematics.png`

Visit [Martin Pihrt's blog](https://pihrt.com/clanky/moje-raspberry-pi-plugin-prutokomer) for additional hardware information.

For the RS485 source, connect the ZTS-3000-FSJT to the adapter with the correct A/B polarity and common reference according to the hardware manuals. Configure the shared serial port and baud rate in RS485 Communication before enabling RS485 measurement in Wind Monitor.

Sensor product page: [ZTS-3000-FSJT RS485 wind speed sensor](https://www.laskakit.cz/yoc-fs-cidlo-rychlosti-vetru-anemometr/?variantId=12676)
