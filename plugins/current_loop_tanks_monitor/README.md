Current Loop Tanks Monitor Readme
====

Tested in Python 3+

This plug-in module measures the water level in 4 tanks. A differential pressure sensor with a 4-20mA/24V current loop (e.g. TL-136) is used for the measurement.
Visit [Martin Pihrt's blog](https://pihrt.com/clanky/mereni-vysky-tl136) for more information.

The measurement interval is configurable in seconds. Longer intervals reduce CPU usage and I2C bus load. The plug-in reads only tanks that are enabled or needed by regulation, stop-station or e-mail rules.

Version 1.1.1 adds an explicit Automation Rules provider action for safely stopping regulation runs belonging to one selected tank or all configured tanks. Version 1.1.0 implements the read-only `ospy.provider.v1` contract. Every enabled 4–20 mA channel is a separate tank resource with cached level, fill, volume and sensor voltage; provider reads never start an ADS1115 conversion.

The plug-in includes an OSPy `plugin.json` manifest, registers its measurement
worker with the shared plug-in runtime, uses the common stop signal, and
implements `health()`. Diagnostics reports configured tanks, worker state,
ADS1115 address, latest successful measurement, and I2C or ADC errors.
