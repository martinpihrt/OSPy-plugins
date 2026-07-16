Current Loop Tanks Monitor Readme
====

Tested in Python 3+

This plug-in module measures the water level in 4 tanks. A differential pressure sensor with a 4-20mA/24V current loop (e.g. TL-136) is used for the measurement.
Visit [Martin Pihrt's blog](https://pihrt.com/clanky/mereni-vysky-tl136) for more information.

The measurement interval is configurable in seconds. Longer intervals reduce CPU usage and I2C bus load. The plug-in reads only tanks that are enabled or needed by regulation, stop-station or e-mail rules.
