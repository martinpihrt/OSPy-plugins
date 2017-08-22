Voltage and Temperature Monitor Readme
====

This plugin needs an enabled I2C bus and connected I2C A/D converter PCF8591 on I2C address 0x48.
For measuring temperature use temp probe LM35D (0-100 &deg;C) on AD0-3 converter.  

Plugin setup
-----------

* Check Enabled:  
  If checked enabled plugin is enabled.

* Check Enable logging:  
  If checked enabled logging save measure value to logfile (format .csv for Excel).

* Maximum number of log records:  
  Type maximum records in log file. 0 is unlimited.  

* I/O Voltage:  
  Type power supply for PCF8591 range 0.0 - 15.0 V.  
  Watch the I2C bus and eventual separation I2C bus!  
  (default is 5.0V)

* Interval for logging:  
  Type interval for logging in minutes (minimum is 1).

* Label for input 1 - 4:  
  Type label for Your probe.

* Check Measure as temperature: 
  If checked value is temperature.  
  On the AD input is connect LM 35D (DZ) temperature sensor.

* Status:  
  Status window from the plugin.

* DA output value:  
  Type value for DA output.  
  Range is 0-255 = 0 - I/O Voltage  



The hardware should be connected as follows (without separate I2C Bus):
<a href="/plugins/volt_temp_da/static/images/schematics.png"><img src="/plugins/volt_temp_da/static/images/schematics.png" width="100%"></a>

The hardware should be connected as follows (with separate I2C Bus for higher voltage):
<a href="/plugins/volt_temp_da/static/images/schematics2.png"><img src="/plugins/volt_temp_da/static/images/schematics2.png" width="100%"></a>


Visit [Martin Pihrt's blog](http://www.pihrt.com/elektronika/289-pcf-8591-4xad-1xda-na-i2c-arduino-raspberry-pi). for more information.