# OSPy-plugins

[![Plugins](https://img.shields.io/github/directory-file-count/martinpihrt/OSPy-plugins/plugins?type=dir&label=plugins&logo=github)](https://github.com/martinpihrt/OSPy-plugins/tree/master/plugins)
[![Tests](https://img.shields.io/github/actions/workflow/status/martinpihrt/OSPy-plugins/tests.yml?branch=master&event=push&label=tests&logo=githubactions)](https://github.com/martinpihrt/OSPy-plugins/actions/workflows/tests.yml?query=branch%3Amaster)
[![Master updated](https://img.shields.io/github/last-commit/martinpihrt/OSPy-plugins/master?label=master%20updated&logo=github)](https://github.com/martinpihrt/OSPy-plugins/commits/master)
[![License](https://img.shields.io/github/license/martinpihrt/OSPy-plugins?label=license)](LICENSE)

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

Irrigation Safety v1.0.0 is a dedicated protection layer over Water Meter, optional Pressure Monitor and optional tank providers. It learns a robust expected flow range for each OSPy station while that station runs alone, combines configured ranges for simultaneous stations and detects missing, low, high or unexpected flow, missing pressure, low tank level and unavailable measurements. Off, Monitor only and Active protection modes support safe commissioning. A confirmed live incident is recorded before asynchronous e-mail and mobile push delivery; Active protection can immediately stop all outputs, disable the scheduler and enforce a persistent lock until an administrator acknowledges the cleared fault. A bounded temporary bypass suppresses control actions without stopping monitoring. The responsive page uses OSPy slider switches and cards and refreshes measurements, active stations, learning progress, incidents and history in the background.

Automation Rules v1.1.2 builds collapsible responsive graphical AND/OR conditions over cached `ospy.provider.v1` values, enabled built-in OSPy sensors from Pihrt or Shelly, local date/time ranges and read-only OSPy operating states. OSPy conditions include scheduler and operating modes, water-level adjustment, rain delay, rain-sensor state and cached system or plug-in update availability without starting a network check. Ultrasonic sensors provide distance, water level, fill and volume conditions. Trigger, repeat and recovery messages include actual values, operators and limits. Browser permission performs an immediate visible test, Firefox and other capable browsers use Service Worker delivery first, the direct Notification API remains a fallback, and client delivery errors are shown on the settings page. It also supports confirmation and repeat intervals, recovery notices, a separate default-on test state, bounded action history, Home popups, e-mail, Telegram and mobile push. A separate default-off control switch enables actions that stop stations, outputs or programs, disable the scheduler, operate a specific output once or in a bounded run/pause cycle, change the water level or invoke a declared provider action. Every cycle start, pause, resumed run, failure and final stop is recorded with its reason. Water Meter 1.2.1 supplies the first concrete provider action by allowing a rule to reset its accumulated counters. Cycles continue only while conditions are available and matched and stop safely when configuration, manual mode or control permission changes. Test mode only simulates actions, while optional incident locking requires safe administrator acknowledgement after conditions become normal. Version 1.1.2 requires OSPy 3.0.354 or newer so the core control contract is installed before this plug-in.

Energy Meter v1.0.7 monitors multiple Shelly Pro 3EM and Shelly 3EM-63T Gen3 meters over direct local RPC by IP address or DNS name, or optionally through Shelly Cloud Integration. Per-meter Phase-by-phase and Net / vector sum accounting supports both independent phase billing and utility meters that compensate simultaneous import and export across phases inside each sampling interval, while preserving raw L1-L3 history and the applied accounting mode for auditability. It recognizes configured Integrator devices while their first reading is still loading and retries only those meters every five seconds without producing a failure traceback or changing other meter intervals. Grid, Solar production, Load and Auxiliary roles keep import, export and generation distinct; history supports restart-safe counters, meter replacement, time tariffs, costs and feed-in income in every overview period, a selectable retained calendar day, photovoltaic self-consumption and savings, append-only local history or optional SQL, CSV, separate energy and power graphs, explicitly documented history deletion, Home, diagnostics and mobile API cards. See [the Energy Meter README](plugins/energy_meter/README.md) for configuration and formulas.

Shelly Cloud Integration v1.0.8 manages devices individually through Add, Edit and confirmed Delete actions while retaining the backward-compatible configuration consumed by other plug-ins. Existing device order and settings migrate with stable internal identifiers, administrators can save either a compact list or responsive card overview, and local device previews link to the matching official Shelly Knowledge Base page without affecting measurements or cached device IDs. Its device service safely exposes both configured identities and cached readings so dependent plug-ins can handle startup warm-up correctly. Shelly 2.5 roller and switch status now consistently uses its shared voltage and correct local Wi-Fi data, while Add-on status lines report RSSI and update time in the proper fields.

Venetian Blind v1.2.7 manages blinds individually in list or card form, stores only its complete structured Gen1, Gen2 or custom configuration through OSPy `PluginOptions`, persists all four tilt settings across restarts and updates, and provides native Mobile API v1 cards and Automation Rules provider actions for every enabled blind. Mobile cards expose Open, Stop, Close and tilt 1–4 command captions with the configured tilt labels and a stable `blind_uid` payload. Automatic wind opening and temperature closing now remain pending until all Shelly devices confirm the requested end position; after a minimum 60-second verification delay, a failed or unconfirmed result is retried while its conditions remain valid, without overlapping an active or queued program. Continuous strong-wind protection counts unique accepted exceedances inside a configurable minute interval, while completed Run-Now programs are released so raising and lowering can alternate without restarting OSPy.

## Available plug-ins

This table is generated from the `name`, `version` and `description` fields in every official `plugin.json`. Run `python tools/generate_plugin_table.py` after changing a manifest and `python tools/generate_plugin_table.py --check` to verify that the README is current.

<!-- plugin-table:start -->
| Plug-in | Version | Description |
| --- | --- | --- |
| [**Air Temperature and Humidity Monitor**](plugins/air_temp_humi/) | `1.0.7` | Monitors DHT temperature and humidity and optional DS18B20 sensors through an external I2C board. |
| [**Astro Sunrise and Sunset**](plugins/sunrise_and_sunset/) | `1.0.6` | Calculates astronomical dawn, sunrise, noon, sunset and dusk times for OSPy programs and mobile clients. |
| [**Automation Rules**](plugins/automation_rules/) | `1.1.4` | Builds graphical AND/OR rules over cached provider and OSPy values, sends detailed notifications and optionally performs guarded control actions with incident locking. |
| [**Button Control**](plugins/button_control/) | `1.0.0` | Controls OSPy functions through eight MCP23017 I2C buttons and indicator LEDs. |
| [**CHMI**](plugins/chmi/) | `1.0.7` | Downloads CHMI or SHMU radar data, detects local rain and optionally controls a hardware map. |
| [**CLI Control**](plugins/cli_control/) | `1.0.0` | Runs administrator-configured shell commands when OSPy station states change. |
| [**Current Loop Tanks Monitor**](plugins/current_loop_tanks_monitor/) | `1.1.1` | Monitors up to four water tanks through an ADS1115 and 4-20 mA pressure sensors. |
| [**Database Connector**](plugins/database_connector/) | `1.1.3` | Provides shared MySQL access, backup and durable queued writes for OSPy plug-ins. |
| [**Direct 16 Relay Outputs**](plugins/relay_16/) | `1.0.0` | Controls up to 16 direct Raspberry Pi GPIO relay outputs with configurable trigger polarity. |
| [**Door Opening**](plugins/door_opening/) | `1.0.0` | Activates a selected OSPy station for a bounded door or gate opening interval. |
| [**E-mail Notifications**](plugins/email_notifications/) | `1.0.1` | Sends OSPy event notifications through a STARTTLS SMTP server with an optional retry queue. |
| [**E-mail Notifications SSL**](plugins/email_notifications_ssl/) | `1.1.6` | Sends OSPy event and login notifications through SMTP over SSL with an optional retry queue. |
| [**E-mail Reader**](plugins/email_reader/) | `1.0.0` | Reads authenticated IMAP commands and controls OSPy programs, stations and system functions. |
| [**Energy Meter**](plugins/energy_meter/) | `1.0.7` | Monitors Shelly three-phase electricity meters and stores import, export, tariff, cost and solar calculations. |
| [**Home Assistant**](plugins/mqtt_home_assistant/) | `1.0.1` | Publishes OSPy devices, controls and sensor values through Home Assistant MQTT Discovery. |
| [**IP Cam**](plugins/ip_cam/) | `1.0.0` | Downloads, caches and proxies JPEG, GIF and MJPEG images from IP cameras. |
| [**IP Scanner**](plugins/ip_scanner/) | `1.0.0` | Scans the local network for devices, names, MAC addresses and common web services. |
| [**Irrigation Safety**](plugins/irrigation_safety/) | `1.0.0` | Monitors irrigation flow, pressure and tank level, learns station flow ranges and can stop outputs and disable the scheduler when a confirmed fault occurs. |
| [**Label Maker**](plugins/labelmaker/) | `1.0.0` | Generates EAN13 barcodes and configurable QR code images. |
| [**LCD Display**](plugins/lcd_display/) | `1.0.2` | Displays OSPy status information on a 16x2 HD44780 LCD through a PCF8574 I2C expander. |
| [**Modbus Stations**](plugins/modbus_stations/) | `1.0.0` | Controls OSPy station outputs through Modbus RTU serial relay boards. |
| [**Monthly Water Level**](plugins/monthly_water_level/) | `1.0.1` | Applies a configurable irrigation percentage adjustment for each calendar month. |
| [**MQTT**](plugins/mqtt/) | `1.0.1` | Shared MQTT client, status publishing and remote OSPy control. |
| [**Network Ping Monitor**](plugins/network_ping_monitor/) | `1.0.2` | Monitors three network targets through ICMP and optionally logs availability and latency. |
| [**OSPy package Backup**](plugins/ospy_backup/) | `1.0.5` | Creates downloadable ZIP archives of installed plug-in data directories. |
| [**Photovoltaic Boiler**](plugins/photovoltaic_boiler/) | `1.0.0` | Controls boiler heating between photovoltaic surplus and the public grid using configured temperature sources. |
| [**Ping Monitor**](plugins/ping_monitor/) | `1.0.0` | Monitors host reachability, logs outages and can notify or restart a device after repeated failures. |
| [**Pool Heating**](plugins/pool_heating/) | `1.0.0` | Controls a pool circulation pump from pool and solar collector temperatures. |
| [**Pressure Monitor**](plugins/pressure_monitor/) | `1.1.1` | Checks binary pipe pressure while the master station runs and can stop irrigation when pressure is missing. |
| [**Pressurizer**](plugins/pressurizer/) | `1.0.0` | Pre-runs the master pump to build pressure before selected irrigation stations start. |
| [**Proto**](plugins/proto/) | `1.0.0` | Provides a minimal working example and starting point for developing OSPy plug-ins. |
| [**Pulse Output Test**](plugins/pulse/) | `1.0.0` | Pulses a selected OSPy station at 1 Hz for a bounded valve-location test. |
| [**Real Time and NTP time**](plugins/real_time/) | `1.0.1` | Synchronizes system time with NTP and supported I2C real-time clocks. |
| [**Relay Test**](plugins/relay/) | `1.0.0` | Runs a bounded test of the OSPy relay output. |
| [**Remote FTP Control**](plugins/remote_ftp_control/) | `1.0.0` | Exchanges command and status files through FTP for legacy remote control of OSPy. |
| [**Remote Notifications**](plugins/remote_notifications/) | `1.0.0` | Sends OSPy status and event notifications to a configured remote PHP and SQL web service. |
| [**RS485 Communication**](plugins/rs485_communication/) | `1.0.3` | Provides a central RS485 worker and FIFO rs485_queue for OSPy plug-ins, with Waveshare CH343G auto-detection, status monitoring and adapter testing. |
| [**Shelly Cloud Integration**](plugins/shelly_cloud_integrator/) | `1.0.8` | Loads and caches configured Shelly device states from the Shelly Cloud API for OSPy and other plug-ins. |
| [**Signaling Examples**](plugins/signaling_examples/) | `1.0.0` | Demonstrates OSPy and plug-in signal subscriptions and records received events. |
| [**SMS Modem**](plugins/sms_adj/) | `1.0.0` | Receives authorized SMS commands through a Gammu-compatible modem and returns OSPy status by SMS. |
| [**Speed Monitor**](plugins/speed_monitor/) | `1.0.0` | Measures and logs Internet ping, download and upload performance at scheduled intervals. |
| [**System Debug Information**](plugins/system_debug/) | `1.0.1` | Displays, downloads and clears the OSPy technical debug log. |
| [**System Information**](plugins/system_info/) | `1.0.1` | Displays operating-system, hardware, network, process, storage, USB, serial and optional I2C information. |
| [**System Update**](plugins/system_update/) | `1.2.8` | Checks, installs and safely rolls back OSPy updates from stable or beta Git branches with backup and watchdog protection. |
| [**System Watchdog**](plugins/system_watchdog/) | `1.0.0` | Configures and monitors the Raspberry Pi hardware watchdog to recover from system lockups. |
| [**Telegram Bot**](plugins/telegram_bot/) | `1.0.1` | Sends Telegram notifications and accepts a limited set of OSPy control commands from subscribed chats. |
| [**Temperature Switch**](plugins/temperature_switch/) | `1.0.0` | Starts and stops OSPy programs from configured temperature sources and hysteresis limits. |
| [**Thermostat**](plugins/thermostat/) | `1.1.1` | Controls up to 20 OSPy programs from independent temperature sources, hysteresis limits and operating windows. |
| [**UPS Monitor**](plugins/ups_adj/) | `1.0.5` | Monitors mains power and can notify, shut down OSPy and switch off a UPS after a sustained outage. |
| [**Usage Statistics**](plugins/usage_statistics/) | `1.0.1` | Downloads and displays anonymized public OSPy usage statistics. |
| [**Venetian Blind**](plugins/venetian_blind/) | `1.2.8` | Controls configured Shelly or compatible blinds, including tilt positions, automation rules and mobile actions. |
| [**Voice Notification**](plugins/voice_notification/) | `1.0.0` | Plays scheduled voice announcements before configured OSPy program and station events. |
| [**Voice Station**](plugins/voice_station/) | `1.0.0` | Queues and plays audio when station outputs change, regardless of what triggered the station. |
| [**Voltage and Temperature Monitor**](plugins/volt_temp_da/) | `1.0.0` | Measures and logs voltages or LM35 temperatures through a PCF8591 I2C converter. |
| [**Water Consumption Counter**](plugins/water_consumption_counter/) | `1.2.7` | Estimates and reports water consumption from configured station flow rates and master-station runtime. |
| [**Water Meter**](plugins/water_meter/) | `1.2.1` | Measures pulse-output water meters through a PCF8583 counter with live flow, history, CSV and optional SQL logging. |
| [**Water Tank Monitor**](plugins/tank_monitor/) | `1.1.1` | Measures ultrasonic tank level and volume, blocks irrigation on low water and exposes tank provider actions. |
| [**Weather Dashboard**](plugins/weather_dashboard/) | `1.0.2` | Displays selected OSPy sensor and plug-in values as configurable gauges or text. |
| [**Weather Stations**](plugins/weather_stations/) | `1.0.0` | Displays selected OSPy sensor and plug-in values as configurable gauges or text. |
| [**Weather-based Rain Delay**](plugins/weather_based_rain_delay/) | `1.0.0` | Sets OSPy rain delay from measured or Netatmo rainfall and configured weather thresholds. |
| [**Weather-based Water Level**](plugins/weather_based_water_level/) | `1.1.2` | Calculates hourly OSPy water-level adjustment from weather balance, Zimmerman or evapotranspiration methods. |
| [**Weather-based Water Level Netatmo**](plugins/weather_based_water_level_netatmo/) | `1.0.0` | Adjusts OSPy water level using rainfall history from a configured Netatmo rain module. |
| [**Webcam Monitor**](plugins/webcam/) | `1.0.0` | Captures and serves snapshots from a Linux USB webcam using fswebcam. |
| [**Wind Speed Monitor**](plugins/wind_monitor/) | `1.2.3` | Measures wind through PCF8583 or Modbus sensors and can log, notify or run safety actions. |
<!-- plugin-table:end -->
