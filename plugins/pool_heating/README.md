Pool Heating Readme
====

Tested in Python 3+

This plugin needs enabled and corect setup the "Air Temperature and Humidity Monitor". Allows pool heating regulation. Reading temperature using from DS18B20 sensors connected to the external hardware board via an I2C bus (address 0x03). Or it is possible to use temperature measurement from OSPy sensors (LAN / Wi-Fi, radio...)
Example: for heating a swimming pool with a solar panel. If the temperature difference (solar panel and pool water) is higher, the output (filter pump) is switched on. If the temperature difference from the solar panel is lower than the set temperature, the output (filter pump) is switched off.
Visit [Martin Pihrt's blog](https://pihrt.com/elektronika/380-moje-raspberry-pi-plugin-ospy-mereni-teploty-pomoci-ds18b20). for more information for HW.

Plugin setup
-----------

* Check Enable Control:  
  If checked Enable Control, control for regulation is enabled.  

* Sensors or plugin:  
  Select the temperature probes from sensors or from plugin air temperature.  

* Probe input from swimming pool: 
  Select the temperature sensor (its name) you want to use.

* Probe input from Solar:  
  Temperature value for output xx switched to on.

* Probe input for OFF:  
  Select the temperature sensor (its name) you want to use.

* Temperature difference for ON:  
  Temperature difference for switch ON (filtration pump).

* Maximum run time in activate:  
  Maximum duration when activating the output (in minutes and seconds). After this time, the output will turn off regardless of other events (conditions).  

* Temperature difference for OFF:
  Temperature difference for switch OFF (filtration pump).  

* Select Output:  
  Select the output you want to control with regulation.  

* Enable Safety:  
  If the box is checked, safety will be enabled. 

* Temperature safety difference:  
  Temperature difference for safety shutdown of automation.  

* Maximum run time for safety check:  
  Simply put, if the temperature is higher and it takes xxmin then it means that the pump is not running or that it is idling (no water). A fault e-mail is sent and the station is switched off permanently.  

* Check Send E-mail with error:  
  If checked send e-mail with error e-mail notification plugin sends e-mail with error.    
  For this function required e-mail notification plugin with all setup in plugin.  

* E-mail subject:
  Type E-mail subject for send E-mail.  

* Show in footer:  
  Show data from plugin in footer on home page.  

* Status:  
  Status window from the plugin.

Visit [Martin Pihrt's blog](https://pihrt.com/elektronika/380-moje-raspberry-pi-plugin-ospy-mereni-teploty-pomoci-ds18b20). for more information HW board with DS18B20 probe.
