# OSPy-plugins

[![Plugins](https://img.shields.io/github/directory-file-count/martinpihrt/OSPy-plugins/plugins?type=dir&label=plugins&logo=github)](https://github.com/martinpihrt/OSPy-plugins/tree/master/plugins)
[![Tests](https://img.shields.io/github/actions/workflow/status/martinpihrt/OSPy-plugins/tests.yml?branch=master&event=push&label=tests&logo=githubactions)](https://github.com/martinpihrt/OSPy-plugins/actions/workflows/tests.yml?query=branch%3Amaster)
[![Master updated](https://img.shields.io/github/last-commit/martinpihrt/OSPy-plugins/master?label=master%20updated&logo=github)](https://github.com/martinpihrt/OSPy-plugins/commits/master)
[![License](https://img.shields.io/github/license/martinpihrt/OSPy-plugins?label=license)](LICENSE)

### A collection of user contributed plugins for the Raspberry Pi based irrigation controll software OSPy - Open Sprinkler Python (OSPy).

Please note: Unless otherwise stated: This is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.

## Documentation

The complete [OSPy-plugins Wiki](https://github.com/martinpihrt/OSPy-plugins/wiki) explains what every official plug-in is for, how it works, how to install and configure it, its dependencies, hardware, permissions and troubleshooting steps. Start with [Getting started](https://github.com/martinpihrt/OSPy-plugins/wiki/Getting-Started) or browse the [plug-in catalog](https://github.com/martinpihrt/OSPy-plugins/wiki/Plugin-Catalog).

## Stable and test channels

The `master` branch is the stable channel selected by OSPy by default. New plug-in changes are developed and verified in the `beta` branch first. After successful practical and automated testing, the same commits can be promoted from `beta` to `master` without rebuilding or changing them.

GitHub Actions runs the OSPy test suite on every push and pull request to `beta` or `master`. The tested plug-in revision is checked against both the OSPy `master` and OSPy `beta` branches on Python 3.11 and Python 3.14. All four jobs must pass before a beta change is promoted to the stable channel. Python 3.11 remains the Raspberry Pi OS Bookworm baseline and Python 3.14 verifies compatibility with the latest stable Python feature release.

## Declared permission approval

Every `plugin.json` must declare only the permissions the plug-in actually uses: `network`, `files`, `i2c`, `gpio`, `email`, `subprocess` and/or `system`. Starting with OSPy 3.0.294, newly installed plug-ins require explicit administrator approval of that complete set before their Python code starts. An update with the same or fewer permissions keeps its approval. Adding a permission requires a new approval and is skipped by automatic update until it has been reviewed. Existing installed plug-ins are approved once during the backward-compatible OSPy upgrade migration, including disabled plug-ins.

This is administrative consent and an audit record, not operating-system sandboxing. Plug-in authors must increase the manifest version whenever code or declared requirements change and must never omit a permission merely to avoid the approval prompt.

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

Address conflicts, selectable alternatives and wiring requirements are documented in [Hardware and I²C](https://github.com/martinpihrt/OSPy-plugins/wiki/Hardware-and-I2C) and on the individual plug-in pages.

## Available plug-ins

This table is generated from the `name`, `version` and `description` fields in every official `plugin.json`. Run `python tools/generate_plugin_table.py` after changing a manifest and `python tools/generate_plugin_table.py --check` to verify that the README is current.

<!-- plugin-table:start -->
| Plug-in | Version | Description |
| --- | --- | --- |
| [**Air Temperature and Humidity Monitor**](https://github.com/martinpihrt/OSPy-plugins/wiki/Plugin-air-temp-humi) | `1.0.7` | Monitors DHT temperature and humidity and optional DS18B20 sensors through an external I2C board. |
| [**Astro Sunrise and Sunset**](https://github.com/martinpihrt/OSPy-plugins/wiki/Plugin-sunrise-and-sunset) | `1.0.6` | Calculates astronomical dawn, sunrise, noon, sunset and dusk times for OSPy programs and mobile clients. |
| [**Automation Rules**](https://github.com/martinpihrt/OSPy-plugins/wiki/Plugin-automation-rules) | `1.1.4` | Builds graphical AND/OR rules over cached provider and OSPy values, sends detailed notifications and optionally performs guarded control actions with incident locking. |
| [**Button Control**](https://github.com/martinpihrt/OSPy-plugins/wiki/Plugin-button-control) | `1.0.0` | Controls OSPy functions through eight MCP23017 I2C buttons and indicator LEDs. |
| [**CHMI**](https://github.com/martinpihrt/OSPy-plugins/wiki/Plugin-chmi) | `1.0.7` | Downloads CHMI or SHMU radar data, detects local rain and optionally controls a hardware map. |
| [**CLI Control**](https://github.com/martinpihrt/OSPy-plugins/wiki/Plugin-cli-control) | `1.0.0` | Runs administrator-configured shell commands when OSPy station states change. |
| [**Current Loop Tanks Monitor**](https://github.com/martinpihrt/OSPy-plugins/wiki/Plugin-current-loop-tanks-monitor) | `1.1.1` | Monitors up to four water tanks through an ADS1115 and 4-20 mA pressure sensors. |
| [**Database Connector**](https://github.com/martinpihrt/OSPy-plugins/wiki/Plugin-database-connector) | `1.1.3` | Provides shared MySQL access, backup and durable queued writes for OSPy plug-ins. |
| [**Direct 16 Relay Outputs**](https://github.com/martinpihrt/OSPy-plugins/wiki/Plugin-relay-16) | `1.0.0` | Controls up to 16 direct Raspberry Pi GPIO relay outputs with configurable trigger polarity. |
| [**Door Opening**](https://github.com/martinpihrt/OSPy-plugins/wiki/Plugin-door-opening) | `1.0.0` | Activates a selected OSPy station for a bounded door or gate opening interval. |
| [**E-mail Notifications**](https://github.com/martinpihrt/OSPy-plugins/wiki/Plugin-email-notifications) | `1.0.1` | Sends OSPy event notifications through a STARTTLS SMTP server with an optional retry queue. |
| [**E-mail Notifications SSL**](https://github.com/martinpihrt/OSPy-plugins/wiki/Plugin-email-notifications-ssl) | `1.1.6` | Sends OSPy event and login notifications through SMTP over SSL with an optional retry queue. |
| [**E-mail Reader**](https://github.com/martinpihrt/OSPy-plugins/wiki/Plugin-email-reader) | `1.0.0` | Reads authenticated IMAP commands and controls OSPy programs, stations and system functions. |
| [**Energy Meter**](https://github.com/martinpihrt/OSPy-plugins/wiki/Plugin-energy-meter) | `1.0.7` | Monitors Shelly three-phase electricity meters and stores import, export, tariff, cost and solar calculations. |
| [**Home Assistant**](https://github.com/martinpihrt/OSPy-plugins/wiki/Plugin-mqtt-home-assistant) | `1.0.1` | Publishes OSPy devices, controls and sensor values through Home Assistant MQTT Discovery. |
| [**IP Cam**](https://github.com/martinpihrt/OSPy-plugins/wiki/Plugin-ip-cam) | `1.0.0` | Downloads, caches and proxies JPEG, GIF and MJPEG images from IP cameras. |
| [**IP Scanner**](https://github.com/martinpihrt/OSPy-plugins/wiki/Plugin-ip-scanner) | `1.0.0` | Scans the local network for devices, names, MAC addresses and common web services. |
| [**Irrigation Safety**](https://github.com/martinpihrt/OSPy-plugins/wiki/Plugin-irrigation-safety) | `1.0.0` | Monitors irrigation flow, pressure and tank level, learns station flow ranges and can stop outputs and disable the scheduler when a confirmed fault occurs. |
| [**Label Maker**](https://github.com/martinpihrt/OSPy-plugins/wiki/Plugin-labelmaker) | `1.0.0` | Generates EAN13 barcodes and configurable QR code images. |
| [**LCD Display**](https://github.com/martinpihrt/OSPy-plugins/wiki/Plugin-lcd-display) | `1.0.2` | Displays OSPy status information on a 16x2 HD44780 LCD through a PCF8574 I2C expander. |
| [**Modbus Stations**](https://github.com/martinpihrt/OSPy-plugins/wiki/Plugin-modbus-stations) | `1.0.0` | Controls OSPy station outputs through Modbus RTU serial relay boards. |
| [**Monthly Water Level**](https://github.com/martinpihrt/OSPy-plugins/wiki/Plugin-monthly-water-level) | `1.0.1` | Applies a configurable irrigation percentage adjustment for each calendar month. |
| [**MQTT**](https://github.com/martinpihrt/OSPy-plugins/wiki/Plugin-mqtt) | `1.0.1` | Shared MQTT client, status publishing and remote OSPy control. |
| [**Network Ping Monitor**](https://github.com/martinpihrt/OSPy-plugins/wiki/Plugin-network-ping-monitor) | `1.0.2` | Monitors three network targets through ICMP and optionally logs availability and latency. |
| [**OSPy package Backup**](https://github.com/martinpihrt/OSPy-plugins/wiki/Plugin-ospy-backup) | `1.0.5` | Creates downloadable ZIP archives of installed plug-in data directories. |
| [**Photovoltaic Boiler**](https://github.com/martinpihrt/OSPy-plugins/wiki/Plugin-photovoltaic-boiler) | `1.0.0` | Controls boiler heating between photovoltaic surplus and the public grid using configured temperature sources. |
| [**Ping Monitor**](https://github.com/martinpihrt/OSPy-plugins/wiki/Plugin-ping-monitor) | `1.0.0` | Monitors host reachability, logs outages and can notify or restart a device after repeated failures. |
| [**Pool Heating**](https://github.com/martinpihrt/OSPy-plugins/wiki/Plugin-pool-heating) | `1.0.0` | Controls a pool circulation pump from pool and solar collector temperatures. |
| [**Pressure Monitor**](https://github.com/martinpihrt/OSPy-plugins/wiki/Plugin-pressure-monitor) | `1.1.1` | Checks binary pipe pressure while the master station runs and can stop irrigation when pressure is missing. |
| [**Pressurizer**](https://github.com/martinpihrt/OSPy-plugins/wiki/Plugin-pressurizer) | `1.0.0` | Pre-runs the master pump to build pressure before selected irrigation stations start. |
| [**Proto**](https://github.com/martinpihrt/OSPy-plugins/wiki/Plugin-proto) | `1.0.0` | Provides a minimal working example and starting point for developing OSPy plug-ins. |
| [**Pulse Output Test**](https://github.com/martinpihrt/OSPy-plugins/wiki/Plugin-pulse) | `1.0.0` | Pulses a selected OSPy station at 1 Hz for a bounded valve-location test. |
| [**Real Time and NTP time**](https://github.com/martinpihrt/OSPy-plugins/wiki/Plugin-real-time) | `1.0.1` | Synchronizes system time with NTP and supported I2C real-time clocks. |
| [**Relay Test**](https://github.com/martinpihrt/OSPy-plugins/wiki/Plugin-relay) | `1.0.0` | Runs a bounded test of the OSPy relay output. |
| [**Remote FTP Control**](https://github.com/martinpihrt/OSPy-plugins/wiki/Plugin-remote-ftp-control) | `1.0.0` | Exchanges command and status files through FTP for legacy remote control of OSPy. |
| [**Remote Notifications**](https://github.com/martinpihrt/OSPy-plugins/wiki/Plugin-remote-notifications) | `1.0.0` | Sends OSPy status and event notifications to a configured remote PHP and SQL web service. |
| [**RS485 Communication**](https://github.com/martinpihrt/OSPy-plugins/wiki/Plugin-rs485-communication) | `1.0.3` | Provides a central RS485 worker and FIFO rs485_queue for OSPy plug-ins, with Waveshare CH343G auto-detection, status monitoring and adapter testing. |
| [**Shelly Cloud Integration**](https://github.com/martinpihrt/OSPy-plugins/wiki/Plugin-shelly-cloud-integrator) | `1.0.8` | Loads and caches configured Shelly device states from the Shelly Cloud API for OSPy and other plug-ins. |
| [**Signaling Examples**](https://github.com/martinpihrt/OSPy-plugins/wiki/Plugin-signaling-examples) | `1.0.0` | Demonstrates OSPy and plug-in signal subscriptions and records received events. |
| [**SMS Modem**](https://github.com/martinpihrt/OSPy-plugins/wiki/Plugin-sms-adj) | `1.0.0` | Receives authorized SMS commands through a Gammu-compatible modem and returns OSPy status by SMS. |
| [**Speed Monitor**](https://github.com/martinpihrt/OSPy-plugins/wiki/Plugin-speed-monitor) | `1.0.0` | Measures and logs Internet ping, download and upload performance at scheduled intervals. |
| [**System Debug Information**](https://github.com/martinpihrt/OSPy-plugins/wiki/Plugin-system-debug) | `1.0.1` | Displays, downloads and clears the OSPy technical debug log. |
| [**System Information**](https://github.com/martinpihrt/OSPy-plugins/wiki/Plugin-system-info) | `1.0.1` | Displays operating-system, hardware, network, process, storage, USB, serial and optional I2C information. |
| [**System Update**](https://github.com/martinpihrt/OSPy-plugins/wiki/Plugin-system-update) | `1.2.8` | Checks, installs and safely rolls back OSPy updates from stable or beta Git branches with backup and watchdog protection. |
| [**System Watchdog**](https://github.com/martinpihrt/OSPy-plugins/wiki/Plugin-system-watchdog) | `1.0.0` | Configures and monitors the Raspberry Pi hardware watchdog to recover from system lockups. |
| [**Telegram Bot**](https://github.com/martinpihrt/OSPy-plugins/wiki/Plugin-telegram-bot) | `1.0.1` | Sends Telegram notifications and accepts a limited set of OSPy control commands from subscribed chats. |
| [**Temperature Switch**](https://github.com/martinpihrt/OSPy-plugins/wiki/Plugin-temperature-switch) | `1.0.0` | Starts and stops OSPy programs from configured temperature sources and hysteresis limits. |
| [**Thermostat**](https://github.com/martinpihrt/OSPy-plugins/wiki/Plugin-thermostat) | `1.1.3` | Controls up to 20 OSPy programs from temperature sources, hysteresis limits, operating windows and a heating-water condition. |
| [**UPS Monitor**](https://github.com/martinpihrt/OSPy-plugins/wiki/Plugin-ups-adj) | `1.0.5` | Monitors mains power and can notify, shut down OSPy and switch off a UPS after a sustained outage. |
| [**Usage Statistics**](https://github.com/martinpihrt/OSPy-plugins/wiki/Plugin-usage-statistics) | `1.0.1` | Downloads and displays anonymized public OSPy usage statistics. |
| [**Venetian Blind**](https://github.com/martinpihrt/OSPy-plugins/wiki/Plugin-venetian-blind) | `1.2.8` | Controls configured Shelly or compatible blinds, including tilt positions, automation rules and mobile actions. |
| [**Voice Notification**](https://github.com/martinpihrt/OSPy-plugins/wiki/Plugin-voice-notification) | `1.0.0` | Plays scheduled voice announcements before configured OSPy program and station events. |
| [**Voice Station**](https://github.com/martinpihrt/OSPy-plugins/wiki/Plugin-voice-station) | `1.0.0` | Queues and plays audio when station outputs change, regardless of what triggered the station. |
| [**Voltage and Temperature Monitor**](https://github.com/martinpihrt/OSPy-plugins/wiki/Plugin-volt-temp-da) | `1.0.0` | Measures and logs voltages or LM35 temperatures through a PCF8591 I2C converter. |
| [**Water Consumption Counter**](https://github.com/martinpihrt/OSPy-plugins/wiki/Plugin-water-consumption-counter) | `1.2.7` | Estimates and reports water consumption from configured station flow rates and master-station runtime. |
| [**Water Meter**](https://github.com/martinpihrt/OSPy-plugins/wiki/Plugin-water-meter) | `1.2.1` | Measures pulse-output water meters through a PCF8583 counter with live flow, history, CSV and optional SQL logging. |
| [**Water Tank Monitor**](https://github.com/martinpihrt/OSPy-plugins/wiki/Plugin-tank-monitor) | `1.1.1` | Measures ultrasonic tank level and volume, blocks irrigation on low water and exposes tank provider actions. |
| [**Weather Dashboard**](https://github.com/martinpihrt/OSPy-plugins/wiki/Plugin-weather-dashboard) | `1.0.2` | Displays selected OSPy sensor and plug-in values as configurable gauges or text. |
| [**Weather Stations**](https://github.com/martinpihrt/OSPy-plugins/wiki/Plugin-weather-stations) | `1.0.0` | Displays selected OSPy sensor and plug-in values as configurable gauges or text. |
| [**Weather-based Rain Delay**](https://github.com/martinpihrt/OSPy-plugins/wiki/Plugin-weather-based-rain-delay) | `1.0.0` | Sets OSPy rain delay from measured or Netatmo rainfall and configured weather thresholds. |
| [**Weather-based Water Level**](https://github.com/martinpihrt/OSPy-plugins/wiki/Plugin-weather-based-water-level) | `1.1.2` | Calculates hourly OSPy water-level adjustment from weather balance, Zimmerman or evapotranspiration methods. |
| [**Weather-based Water Level Netatmo**](https://github.com/martinpihrt/OSPy-plugins/wiki/Plugin-weather-based-water-level-netatmo) | `1.0.0` | Adjusts OSPy water level using rainfall history from a configured Netatmo rain module. |
| [**Webcam Monitor**](https://github.com/martinpihrt/OSPy-plugins/wiki/Plugin-webcam) | `1.0.0` | Captures and serves snapshots from a Linux USB webcam using fswebcam. |
| [**Wind Speed Monitor**](https://github.com/martinpihrt/OSPy-plugins/wiki/Plugin-wind-monitor) | `1.2.3` | Measures wind through PCF8583 or Modbus sensors and can log, notify or run safety actions. |
<!-- plugin-table:end -->
