Air Temperature and Humidity Monitor Readme
====

This plugin needs DHT11 sensor connected to GPIO 10 (pin 19 MOSI).
Range for Humidity: 20 - 90 % Relative Humidity  
Range for Temperature: 0 - 50 Celsius    
This plugin allows you to connect 1-6 DS18B20 sensors connected to the external hardware board via an I2C bus (address 0x03). 
Visit [Martin Pihrt's blog](https://pihrt.com/elektronika/380-moje-raspberry-pi-plugin-ospy-mereni-teploty-pomoci-ds18b20). for more information for HW.

Plugin setup
-----------

* Check Enabled:  
  If checked enabled plugin is enabled.

* Check Enable logging:  
  If checked enabled logging save measure value to logfile (format .csv for Excel).

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

* Humidity for output OFF:  
  Humidity value for output switched to off.

* Select Output:  
  Select station for output.

* Check Enable DS18B20:  
  If checked enabled DS18B20, I2C bus is in plugin enabled.

* Used DS18B20:  
  Value count for connected DS18B20 devices (1-6).

* Status:  
  Status window from the plugin.


The hardware should be connected as follows (without separate I2C Bus):
<a href="/plugins/air_temp_humi/static/images/schematics.png"><img src="/plugins/air_temp_humi/static/images/schematics.png" width="100%"></a>

Visit [Martin Pihrt's blog](http://www.pihrt.com). for more information.
