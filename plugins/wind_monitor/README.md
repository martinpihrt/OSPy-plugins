Wind Speed Monitor Readme
====

This plugin checked wind speed, if station is switched on and actual wind speed is > wind speed value in options, switches off all station  and sends email with error.  
This plugin needs an enabled I2C bus and connected counter PCF8583 on I2C address 0x50 (0x51).  
Prevent safety for fault watering.  


Plugin setup
-----------
* Check Use wind monitor:  
  If checked use wind monitor plugin is enabled.    

* Check I2C address 0x50:  
  If checked address is 0x51.

* Check Send email with error:  
  If checked send email with error e-mail notification plugin sends e-mail with error.  
  For this function required e-mail notification plugin with all setup in plugin.  

* Number of pulses:  
  Type number of pulses per rotation from your rotation sensor.  

* Number of wind speed per rotation:  
  Type number of wind speed per rotation in meter per second.

* Max wind speed:  
  Type maximum wind speed to deactivate all stations (meter per second).   

* Wind speed state:  
  Show actual wind speed in meter per second.

* Status:  
  Status window from the plugin.  

The hardware should be connected as follows:
<a href="/plugins/wind_monitor/static/images/schematics.png"><img src="/plugins/wind_monitor/static/images/schematics.png" width="100%"></a>

Visit [Martin Pihrt's blog](http://pihrt.com/elektronika/298-moje-raspberry-pi-plugin-prutokomer). for more information.
