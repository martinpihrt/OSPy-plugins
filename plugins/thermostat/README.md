Thermostat Readme
====

Tested in Python 3+

The thermostat plugin checks selected temperature sources and starts or stops selected OSPy programs when the configured temperature limits are reached.

Each thermostat has a low temperature, a high temperature and one selected program. The low and high limits create hysteresis. For example, low 22.4 C and high 22.6 C means that no action is repeated while the temperature stays between these values.

Temperature sources
-----------
* Air Temperature DS probes
* OSPy sensors
* Shelly Cloud temperature values

Plugin setup
-----------
* Use thermostat:
  Enable or disable the whole plugin.

* Show in footer:
  Show a short thermostat status in the OSPy home page footer.

* Check interval:
  How often the temperatures are checked.

* Thermostat enabled:
  Enable or disable one thermostat zone.

* Temperature source:
  Select where the temperature is read from.

* Channel:
  Select a DS probe, OSPy sensor or Shelly device.

* Shelly temperature:
  Select which Shelly temperature value is used. This option is shown only for the Shelly Cloud source and is useful for Shelly devices with more temperature probes. For example, Temperature 3 means the third temperature value reported by the selected Shelly device. DS probes and OSPy sensors do not use this option.

* Program:
  Select the OSPy program controlled by this thermostat.

* Low temperature / Low action:
  When the temperature is equal or lower than the low value, the selected low action is executed once.

* High temperature / High action:
  When the temperature is equal or higher than the high value, the selected high action is executed once.

Note
-----------
The plugin controls OSPy programs only. If you need to control a relay by URL, use an OSPy program together with the CLI Control plugin.
