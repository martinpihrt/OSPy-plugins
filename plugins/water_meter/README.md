Water Meter Readme
====

This plugin needs an enabled I2C bus and connected counter PCF8583 on I2C address 0x50 or 0x51.  
This plugin measures the amount of water flowing per sec, min, hour and the total amount of water.

Plugin setup
-----------
* Check Use Water Meter:  
  If checked use water meter plugin is enabled.  

* Check I2C address 0x50:  
  If checked address is 0x51.  

* Number of pulses per liter:
  Type number of pulses per liter from your sensor.

* Water meter state:
  Show actual liter per second

* Status:
  Status window from the plugin.  

The hardware should be connected as follows:
<a href="/plugins/water_meter/static/images/schematics.png"><img src="/plugins/water_meter/static/images/schematics.png" width="100%"></a>

Visit [Martin Pihrt's blog](http://pihrt.com/elektronika/298-moje-raspberry-pi-plugin-prutokomer). for more information.
