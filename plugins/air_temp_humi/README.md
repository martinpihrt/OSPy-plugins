Air Temperature and Humidity Monitor Readme
====

This plugin needs DHT11 (22) probe connected to GPIO 10 (pin 19 MOSI).   
This plugin allows you to connect 1-6 DS18B20 sensors connected to the external hardware board via an I2C bus (address 0x03). 
Visit [Martin Pihrt's blog](https://pihrt.com/elektronika/380-moje-raspberry-pi-plugin-ospy-mereni-teploty-pomoci-ds18b20). for more information for HW.

Plugin setup
-----------

* Check Enabled:  
  If checked enabled plugin is enabled.

* Check Enable logging and show graph:  
  If checked enabled logging save measure value to logfile (format .csv for Excel) and logfile for graph.

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

* Used DS18B20:  
  Value count for connected DS18B20 devices (1-6).
  
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

Visit [Martin Pihrt's blog](https://pihrt.com/elektronika/380-moje-raspberry-pi-plugin-ospy-mereni-teploty-pomoci-ds18b20). for more information HW board with DS18B20 probe.
