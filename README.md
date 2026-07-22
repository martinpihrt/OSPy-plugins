# OSPy-plugins
### A collection of user contributed plugins for the Raspberry Pi based irrigation controll software OSPy - Open Sprinkler Python (OSPy).

Please note: Unless otherwise stated: This is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.

## Stable and test channels

The `master` branch is the stable channel selected by OSPy by default. New
plug-in changes are developed and verified in the `beta` branch first. After
successful practical and automated testing, the same commits can be promoted
from `beta` to `master` without rebuilding or changing them.

GitHub Actions runs the OSPy test suite on every push and pull request to
`beta` or `master`. The tested plug-in revision is checked against both the
OSPy `master` and OSPy `beta` branches on Python 3.11 and Python 3.14. All four
jobs must pass before a beta change is promoted to the stable channel. Python
3.11 remains the Raspberry Pi OS Bookworm baseline and Python 3.14 verifies
compatibility with the latest stable Python feature release.

## Declared permission approval

Every `plugin.json` must declare only the permissions the plug-in actually
uses: `network`, `files`, `i2c`, `gpio`, `email`, `subprocess` and/or `system`.
Starting with OSPy 3.0.294, newly installed plug-ins require explicit
administrator approval of that complete set before their Python code starts.
An update with the same or fewer permissions keeps its approval. Adding a
permission requires a new approval and is skipped by automatic update until it
has been reviewed. Existing installed plug-ins are approved once during the
backward-compatible OSPy upgrade migration, including disabled plug-ins.

This is administrative consent and an audit record, not operating-system
sandboxing. Plug-in authors must increase the manifest version whenever code
or declared requirements change and must never omit a permission merely to
avoid the approval prompt.

These programs are distributed in the hope that they will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details. http://opensource.org/licenses/gpl-3.0.html

Theses I2C addresses is used in available plugins:
* air_temp_humi	0x03<br>
* tank_monitor 	0x04<br>
* button_contr	0x27<br>
* lcd_display 	0x20-0x27, 0x38-0x3F<br>
* real_time 	0x68<br>
* volt_temp_da 	0x48<br>
* water_meter 	0x50, 0x51<br>
* wind_monitor 	0x50, 0x51<br>
* current_loop_tanks_monitor 0x48, 0x49, 0x4A, 0x4B<br> 

Available plugins:
* Usage Statistics  
* LCD Display  
* Pressure Monitor  
* Voice Notification  
* Pulse Output Test  
* Button Control  
* CLI Control  
* System Watchdog  
* Voltage and Temperature Monitor  
* Remote Notifications  
* System Information  
* Air Temperature and Humidity Monitor  
* Wind Speed Monitor  
* Weather-based Rain Delay  
* Relay Test  
* UPS Monitor  
* Water Consumption Counter  
* SMS Modem  
* Signaling Examples  
* E-mail Notifications  
* Remote FTP Control  
* System Update  
* Water Meter  
* Webcam Monitor  
* Weather-based Water Level Netatmo  
* Direct 16 Relay Outputs  
* MQTT
* System Debug Information  
* Weather-based Water Level  
* Real Time and NTP time  
* Water Tank  
* Monthly Water Level  
* Pressurizer  
* Ping monitor  
* Temperature Switch  
* Thermostat
* Pool Heating  
* E-mail Reader  
* Weather Stations  
* Telegram Bot  
* Door Opening  
* Voice Station  
* Venetian Blind  
* Speed Monitor  
* E-mail Notifications SSL  
* Astro Sunrise and Sunset  
* Photovoltaic Boiler  
* IP CAM  
* Modbus stations
* CHMI meteo radar
* Proto
* Label Maker
* IP Scanner
* Database Connector
* OSPy Backup
* MQTT Home Assistant
* Shelly Cloud Integration
* Current Loop Tanks Monitor
* Network Ping Monitor
* Weather Dashboard
* Thermostat
