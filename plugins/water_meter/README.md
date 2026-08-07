Water Meter Readme
====

Tested in Python 3+

This plugin needs an enabled I2C bus and connected counter PCF8583 on I2C address 0x50 or 0x51.  
This plugin measures the amount of water flowing per sec, min, hour and the total amount of water.

Addresses `0x50` and `0x51` are alternatives; the plug-in occupies only the address selected in its settings. OSPy can install and run Water Meter beside another selectable-address plug-in when each receives a different address. If the preferred address is occupied during activation, the plug-in selects the free alternative. The settings page refuses an address currently used by another enabled plug-in and keeps the preceding selection.

The plug-in includes a manifest declaring its SMBus and I2C requirements, uses the shared OSPy worker lifecycle, closes the I2C handle during errors and shutdown, and reports counter availability, flow and totals through the Diagnostics health interface.

Plugin setup
-----------
* Check Use Water Meter:  
  If checked use water meter plugin is enabled.  

* Select the I2C address: Clear the checkbox for `0x50` or select it for `0x51`. The selected address must not already be used by another enabled plug-in.

* Number of pulses per liter:
  Type number of pulses per liter from your sensor.

* Water meter state:
  Show actual liter per second

* Status:
  Status window from the plugin.  

The hardware should be connected as follows:
<a href="/plugins/water_meter/static/images/schematics.png"><img src="/plugins/water_meter/static/images/schematics.png" width="100%"></a>

Visit [Martin Pihrt's blog](https://pihrt.com/clanky/moje-raspberry-pi-plugin-prutokomer). for more information.
