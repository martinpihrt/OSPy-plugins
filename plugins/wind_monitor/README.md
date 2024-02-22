Wind Speed Monitor Readme
====

Tested in Python 3+

This plugin checked wind speed, if station is switched on and actual wind speed is > wind speed value in options, switches off all selected stations in scheduler and sends E-mail with error. Preventing for fault watering while wind.
This plugin needs an enabled I2C bus and connected counter PCF8583 on I2C address 0x50 or 0x51.
1m/s = 3,6 km/h or 1m/s = 2,237 mile/h.
Measurement cycle:  
  the counter is cleared, 10 seconds are waited, from the counter read the number of pulses in 10 seconds.  
Formula for calculation:  
  pulse = number of measured pulses from the counter/10. Result in m/s = (pulse/(set number of pulses per revolution * 1.0)) * set wind speed in m/s.
Rounding to 2 places:  
  result in m/s = round (result in m/s * 1.0, 2). If we want the result in km/h to 2 decimal places: result in km/h = round (result in m/s * 3.6, 2).
Current value measurement:  
  the current wind value is measured continuously (the records in counter), but the result is processed and displayed after 10 seconds.
Maximal speed measurement:  
  if the current speed is higher than the previous maximal speed, save to log (if enabled log) is performed and the new maximal wind speed is saved.
Switching off the station in case of exceeding the maximum set speed: 
  wind in m/s maximal setup speed -> stop station.
Error message at maximal wind speed:  
  if the wind has a speed higher than 150 km/h (42 m/sec), measurement is not guaranteed an error is displayed.
Measurement accuracy very much depends on the setting of the following parameters (Number of pulses/sec, wind speed per rotation m/sec).


Plugin setup
-----------
* Check Use wind monitor:  
  If checked use wind monitor plugin is enabled.  

* I2C address 0x50:  
  If checked I2C address is 0x51.    

* Check Send E-mail if error:  
  If checked E-mail notification plugin sends E-mail with error.  
  For this function required E-mail notification plugin with all setup in plugin.  

* Stoping stations:  
  Stoping selected stations in scheduler if stations has run.  

* Stoping this stations:  
  Selector for used stations. If wind speed is bigger stop this selected stations.  

* Number of pulses:  
  Type number of pulses per rotation from your rotation sensor.  

* Number of wind speed per rotation:  
  Type number of wind speed per rotation in meter per second.

* Max wind speed:  
  Type maximum wind speed to deactivate all stations (meter per second).   

* Wind speed state:  
  Show actual wind speed in meter per second.

* Enable local logging:  
  Enable logging and graphing.

* Check Enable SQL logging:  
  If checked enabled logging save measure value to SQL database. This option requires the Database Connector extension to be installed and configured. The button will delete the windmonitor table from the database, thus deleting all saved data from this extension! This promotion is non-refundable!  

* Save to log if maximal speed change:  
  If the wind speed changes above the stored maximum and there is no time for save log to file, log this value immediately.

* Maximum number of log records:  
  Maximum number of log records (only for csv file).

* Interval for logging:  
  Logging interval (minimum 1 minute).

* Display in km/h:  
  the measured data will be displayed in km/h.

* Run the program when exceeded
  When the set speed is exceeded, start the selected program and close the window blinds, for example.

* Running program:  
  Select the program will be run after event.   

* Maximum wind speed for starting the program in m/s
  If this set speed is exceeded, another condition will be activated.

* Number of event repetitions for the action
  If the maximum wind speed is repeatedly exceeded in a given time period (it is set in the box below), the program will be started.

* Repeatedly exceeded in these interval
  In this time period, the number of set exceeded events (time in minutes) is measured.

* Ignore other events for a while
  If the program has been started, the next possible start will be triggered by an event only after this set time (in hours).  

* Select filter for graph history  
  Without limits  
  Day filter  
  Month filter  
  Year filter    

* Status:  
  Status window from the plugin.  

The hardware should be connected as follows:  
<a href="/plugins/wind_monitor/static/images/schematics.png"><img src="/plugins/wind_monitor/static/images/schematics.png" width="100%"></a>

Visit [Martin Pihrt's blog](http://pihrt.com/elektronika/298-moje-raspberry-pi-plugin-prutokomer). for more information.
