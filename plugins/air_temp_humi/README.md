Air Temperature and Humidity Monitor Readme
====

Tested in Python 3+

This plugin needs DHT11 (22) probe connected to GPIO 10 (pin 19 MOSI).   
This plugin allows you to connect 1-6 DS18B20 sensors connected to the external hardware board via an I2C bus (address 0x03). 
Visit [Martin Pihrt's blog](https://pihrt.com/clanky/moje-raspberry-pi-plugin-ospy-mereni-teploty-pomoci-ds18b20). for more information for HW.

The plug-in includes an OSPy `plugin.json` manifest, registers its sensor worker
with the shared plug-in runtime, uses the common stop signal, and implements
`health()`. Diagnostics evaluates only the configured DHT and DS18B20 sensor
types and reports worker state, enabled probes, latest successful sample, and
the latest sensor error.

Plugin setup
-----------

* Check Enabled:  
  If checked enabled plugin is enabled.

* Check Enable local logging and show graph:  
  If checked enabled logging save measure value to logfile (format .csv for Excel) and logfile for graph.

* Check Enable SQL logging:  
  If checked enabled logging save measure value to SQL database. This option requires the Database Connector extension to be installed and configured. The button will delete the airtemp table from the database, thus deleting all saved data from this extension! This promotion is non-refundable!

* Maximum number of log records:  
  Type maximum records in log file. 0 is unlimited.  

* Interval for logging:  
  Type interval for logging in minutes (minimum is 1).

* Label for sensor:  
  Type label for Your probe.

* Check Allow regulation:  
  If checked "Allow regulation", now is output regulation enabled.

* Hysteresis:  
  Number value for hysteresis in regulation loop.

* Humidity for output ON:  
  Humidity value for output switched to on.

* Maximum run time in activate:  
  Maximum duration when activating the output (in minutes and seconds). After this time, the output will turn off regardless of other events (conditions).  

* Humidity for output OFF:  
  Humidity value for output switched to off.

* Select Output:  
  Select station for output.

* Check Enable DS18B20:  
  If checked enabled DS18B20, I2C bus is in plugin enabled.

* DS18B20 error timeout:  
  Time in seconds for keeping the last valid DS18B20 value when an I2C read returns an error value such as -127. During this time the plugin does not overwrite the displayed/logged value with the error value. Use 0 to keep the last valid value without timeout.

* DS18B20 sensors:  
  Enable only the connected DS18B20 sensors (DS1-DS6) and set a label for each used sensor. Disabled sensors are hidden from the graph and log view.
  
* Label for sensor DS 1-6:  
  Type label for Your probe Dallas DS18B20.

* Status:  
  Status window from the plugin.

* Graph
  To use the graph it is necessary to enable saving of measured data (from temperature sensors). When using for the first time, name the sensors first and then delete all records (using the button). 

* Select filter for graph history  
  Without limits  
  Day filter  
  Month filter  
  Year filter

Visit [Martin Pihrt's blog](https://pihrt.com/clanky/moje-raspberry-pi-plugin-ospy-mereni-teploty-pomoci-ds18b20). for more information HW board with DS18B20 probe.
