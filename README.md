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
* water_meter 	one selectable address: 0x50 or 0x51<br>
* wind_monitor 	one selectable address: 0x50 or 0x51<br>
* current_loop_tanks_monitor 0x48, 0x49, 0x4A, 0x4B<br> 

OSPy treats the Water Meter and Wind Speed Monitor declarations as one selectable I2C resource each. Both plug-ins can therefore be installed from the repository or a custom ZIP and run together when they use different addresses. Activation selects a free alternative when necessary, and either settings page rejects an address already used by another enabled plug-in, preserves the previous settings and displays the conflict in a red status bar.

Water Meter v1.2.1 uses uninterrupted one-second measurements and separates its live overview from configuration. It can log flow to a bounded or unlimited local JSON file and optionally to SQL through Database Connector, omit zero-flow samples, select the graph/log source, download CSV history, and display current `l/s` with the equivalent `l/min` on Home. PCF8583 data is read explicitly from registers `0x01–0x03`; initialization and measurement failures close and retry the bus and are shown on the overview. Its provider adapter exposes cached flow and volume values without another hardware read and declares an explicit action for resetting its accumulated counters.

Automation Rules v1.1.3 also discovers concrete provider actions from Venetian Blind 1.2.7, Water Tank Monitor 1.1.1, Current Loop Tanks Monitor 1.1.1 and OSPy Backup 1.0.5. Rules can operate one configured blind, stop regulation belonging to a selected tank or all tanks, reset the ultrasonic tank extrema and create a plug-in data backup through each provider's existing guarded implementation. OSPy Backup also declares native mobile creation and download of its latest plug-in-data ZIP, while Venetian Blind exposes the same per-blind movement and configured tilt actions on mobile cards.

Automation Rules v1.1.2 builds collapsible responsive graphical AND/OR conditions over cached `ospy.provider.v1` values, enabled built-in OSPy sensors from Pihrt or Shelly, local date/time ranges and read-only OSPy operating states. OSPy conditions include scheduler and operating modes, water-level adjustment, rain delay, rain-sensor state and cached system or plug-in update availability without starting a network check. Ultrasonic sensors provide distance, water level, fill and volume conditions. Trigger, repeat and recovery messages include actual values, operators and limits. Browser permission performs an immediate visible test, Firefox and other capable browsers use Service Worker delivery first, the direct Notification API remains a fallback, and client delivery errors are shown on the settings page. It also supports confirmation and repeat intervals, recovery notices, a separate default-on test state, bounded action history, Home popups, e-mail, Telegram and mobile push. A separate default-off control switch enables actions that stop stations, outputs or programs, disable the scheduler, operate a specific output once or in a bounded run/pause cycle, change the water level or invoke a declared provider action. Every cycle start, pause, resumed run, failure and final stop is recorded with its reason. Water Meter 1.2.1 supplies the first concrete provider action by allowing a rule to reset its accumulated counters. Cycles continue only while conditions are available and matched and stop safely when configuration, manual mode or control permission changes. Test mode only simulates actions, while optional incident locking requires safe administrator acknowledgement after conditions become normal. Version 1.1.2 requires OSPy 3.0.354 or newer so the core control contract is installed before this plug-in.

Energy Meter v1.0.6 monitors multiple Shelly Pro 3EM and Shelly 3EM-63T Gen3 meters over direct local RPC by IP address or DNS name, or optionally through Shelly Cloud Integration. It recognizes configured Integrator devices while their first reading is still loading and retries only those meters every five seconds without producing a failure traceback or changing other meter intervals. Grid, Solar production, Load and Auxiliary roles keep import, export and generation distinct; phase and total history supports restart-safe counters, meter replacement, time tariffs, costs and feed-in income in every overview period, a selectable retained calendar day, photovoltaic self-consumption and savings, append-only local history or optional SQL, CSV, separate energy and power graphs, explicitly documented history deletion, Home, diagnostics and mobile API cards. See [the Energy Meter README](plugins/energy_meter/README.md) for configuration and formulas.

Shelly Cloud Integration v1.0.8 manages devices individually through Add, Edit and confirmed Delete actions while retaining the backward-compatible configuration consumed by other plug-ins. Existing device order and settings migrate with stable internal identifiers, administrators can save either a compact list or responsive card overview, and local device previews link to the matching official Shelly Knowledge Base page without affecting measurements or cached device IDs. Its device service safely exposes both configured identities and cached readings so dependent plug-ins can handle startup warm-up correctly. Shelly 2.5 roller and switch status now consistently uses its shared voltage and correct local Wi-Fi data, while Add-on status lines report RSSI and update time in the proper fields.

Venetian Blind v1.2.7 manages blinds individually in list or card form, stores only its complete structured Gen1, Gen2 or custom configuration through OSPy `PluginOptions`, persists all four tilt settings across restarts and updates, and provides native Mobile API v1 cards and Automation Rules provider actions for every enabled blind. Mobile cards expose Open, Stop, Close and tilt 1–4 command captions with the configured tilt labels and a stable `blind_uid` payload. Automatic wind opening and temperature closing now remain pending until all Shelly devices confirm the requested end position; after a minimum 60-second verification delay, a failed or unconfirmed result is retried while its conditions remain valid, without overlapping an active or queued program. Continuous strong-wind protection counts unique accepted exceedances inside a configurable minute interval, while completed Run-Now programs are released so raising and lowering can alternate without restarting OSPy.

Available plugins:
* Automation Rules
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
* Energy Meter
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
* RS485 Communication
* Shelly Cloud Integration
* Current Loop Tanks Monitor
* Network Ping Monitor
* Weather Dashboard
* Thermostat
