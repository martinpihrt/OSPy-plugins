# Wind Speed Monitor

Tested with Python 3.8+.

The plug-in measures an anemometer through a PCF8583 event counter on I2C address `0x50` or `0x51`. It can display and log wind, stop selected running stations, send an e-mail, or start a configured program after validated wind thresholds are exceeded.

## Measurement

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

## Overview and trend

The overview page contains the current and maximum speed, operational status, a graph, and a one-minute trend. Live values refresh through a JSON endpoint without reloading the page. The trend compares older and newer accepted readings and reports rising, falling, steady, or waiting for sufficient data.

## Plausibility and action protection

The plausibility filter rejects an accepted-speed candidate above the configured maximum. Rejected readings:

- do not replace the current speed;
- do not change the stored maximum;
- are not written to the measurement graph or database;
- cannot stop stations, send e-mail, or start a program.

Station stopping and its e-mail notification require the configured number of consecutive accepted measurements above the stop threshold. This avoids an immediate action after one isolated pulse spike. Program actions retain their existing repetition and interval configuration and only receive accepted measurements.

The default filter limit is 40 m/s (144 km/h), and the default station/e-mail confirmation count is two measurements.

## I2C diagnostic log

Diagnostic logging is intended for temporary troubleshooting. It writes bounded JSON lines to the OSPy plug-in data directory and rotates the file at approximately 1 MB. The diagnostic page can display, download, refresh, and delete the log.

Records include:

- PCF8583 setup and control-register confirmation;
- I2C retry errors;
- selected I2C address;
- raw counter bytes and decoded pulse count;
- I2C lock wait and actual measurement duration;
- pulse rate and calculated speed;
- whether the reading was accepted and any rejection reason.

Disable diagnostic logging after the problem has been captured.

## Logging and actions

Accepted measurements can be written to the local graph files or through the optional Database Connector plug-in. A configured maximum can be reset manually or after an interval. Selected running stations can be stopped after the stop threshold is confirmed, and an optional e-mail can be sent. A separate program action uses its own threshold, repetition count, interval, and suppression period.

The plug-in declares SMBus, I2C, e-mail, file and scheduler-control permissions, uses the shared OSPy worker lifecycle, closes its I2C handle during shutdown, and reports measurement, filter and diagnostic state through the Diagnostics health interface.

## Hardware

The I2C bus must be enabled and the PCF8583 connected correctly. The original wiring diagram remains available at:

`/plugins/wind_monitor/static/images/schematics.png`

Visit [Martin Pihrt's blog](https://pihrt.com/clanky/moje-raspberry-pi-plugin-prutokomer) for additional hardware information.
