Thermostat Readme
====

Tested in Python 3+

The plug-in includes a `plugin.json` manifest and reports its worker, enabled thermostats, current temperatures, unavailable sources or setup errors, active program actions, latest cycle and errors through the OSPy system health interface.

The thermostat plugin checks selected temperature sources and starts or stops selected OSPy programs when the configured temperature limits are reached.

Up to 20 thermostats can be created, edited and deleted as independent cards. Existing settings from the earlier three-slot version are retained automatically.

Each thermostat has a low temperature, a high temperature and one selected program. The low and high limits create hysteresis. For example, low 22.4 C and high 22.6 C means that no action is repeated while the temperature stays between these values.

Each enabled thermostat must use a different OSPy program. This prevents one thermostat from stopping a program controlled by another thermostat.

Temperature sources
-----------
* Air Temperature DS probes
* OSPy sensors
* Shelly Cloud temperature values

Plugin setup
-----------
* Use thermostat:
  Enable or disable the whole plugin. Disabling the plugin stops programs assigned to enabled thermostats.

* Show in footer:
  Show a short thermostat status in the OSPy home page footer.

* Check interval:
  How often the temperatures are checked. Operating time boundaries are handled independently of this interval.

* Add thermostat / Save thermostat / Delete:
  Create, edit or delete thermostat cards. Deleting an enabled thermostat stops its selected program.

* Thermostat enabled:
  Enable or disable one thermostat. Disabling an active thermostat stops its selected program.

* Temperature source:
  Select where the temperature is read from.

* Channel:
  Select a DS probe, OSPy sensor or Shelly device.

* Shelly temperature:
  Select which Shelly temperature value is used. This option is shown only for the Shelly Cloud source and is useful for Shelly devices with more temperature probes. For example, Temperature 3 means the third temperature value reported by the selected Shelly device. DS probes and OSPy sensors do not use this option.

* Program:
  Select the OSPy program controlled by this thermostat. One program can be assigned to only one enabled thermostat.

* Low temperature / Low action:
  When the temperature is equal or lower than the low value, the selected low action is executed once.

* High temperature / High action:
  When the temperature is equal or higher than the high value, the selected high action is executed once.

* Limit operating time:
  Leave disabled for continuous operation. Enable it to run the thermostat only from the selected start time up to, but not including, the selected end time. Overnight windows such as 22:00 to 06:00 are supported. The selected program is stopped when the operating window ends.

Note
-----------
The plugin controls OSPy programs only. If you need to control a relay by URL, use an OSPy program together with the CLI Control plugin.
