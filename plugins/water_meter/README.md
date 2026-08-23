Water Meter Readme
====

The Water Meter plug-in measures a pulse-output water meter through a PCF8583 I2C counter. It performs uninterrupted one-second measurements and reports current flow in liters per second, the equivalent liters per minute, consumption in the current minute and hour, and total consumption.

Version 1.2.1 adds the explicit `reset_total_consumption` provider action. Automation Rules can use it to reset accumulated total consumption together with the current-minute and current-hour counters through OSPy's validated provider-action interface. The action accepts no parameters, targets only the main Water Meter resource and is never run unless an enabled live rule selects it while Automation Rules control actions are enabled. Version 1.2.0 implements the read-only `ospy.provider.v1` contract. Automation consumers can read cached flow and accumulated volumes without causing another PCF8583 access or changing the existing measurement loop.

Addresses `0x50` and `0x51` are alternatives; the plug-in occupies only the address selected in its settings. OSPy can install and run Water Meter beside another selectable-address plug-in when each receives a different address. If the preferred address is occupied during activation, the plug-in selects the free alternative. The settings page refuses an address currently used by another enabled plug-in, keeps the preceding settings and displays the conflict in a red status bar without leaving the page.

Overview and settings are separate pages. The overview refreshes live values every second, includes activity and counter information, and shows a selectable history graph when local or SQL logging is enabled. The measurement log can be viewed and downloaded as CSV.

Logging
----

Local JSON logging and optional SQL logging through the Database Connector plug-in can be enabled independently. Select which source supplies the graph, measurement log and CSV download. Configure the logging interval in seconds, optionally omit samples whose flow is zero, and set the maximum number of records. A maximum of `0` keeps unlimited history; a positive limit is applied independently to the local file and SQL table.

Home display
----

Enable **Show on Home** to add a live Water flow value to the OSPy Home footer/header area. It is updated after every one-second measurement in the format `0.250 l/s (15.000 l/min)` and opens the Water Meter overview when selected. The item is removed when the option is disabled or during plug-in shutdown.

Setup
----

* Enable **Use Water Meter**.
* Select I2C address `0x50` or `0x51`; it must differ from an address already used by another enabled plug-in.
* Enter the sensor calibration as pulses per liter. Decimal values accept a point or comma.
* Choose local and/or SQL logging, the display source, interval, record limit and zero-flow behavior when history is required.

The mobile API provides a status summary, live cards for `l/s`, `l/min`, current-minute, current-hour and total consumption, and bounded/downsampled flow history from the selected local or SQL source. The manifest declares SMBus and I2C requirements plus the optional Database Connector dependency and mobile API v1. The plug-in uses the shared OSPy worker lifecycle, closes the I2C handle during errors and shutdown, removes its Home value during shutdown, and reports counter availability, live flow and totals through the Diagnostics health interface.

The PCF8583 count is read explicitly from registers `0x01–0x03`. If setup or a measurement fails, the plug-in closes the bus, retries initialization automatically and shows the current I2C error on the overview instead of silently remaining at zero. Saving settings requests a safe counter reinitialization in the worker thread.
