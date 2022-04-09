Temperature Switch Readme
====

Tested in Python 3 and Python 2

This plugin needs enabled and corect setup  the "Air Temperature and Humidity Monitor".
This plugin allows regulation from DS18B20 sensors connected to the external hardware board via an I2C bus (address 0x03). 
Visit [Martin Pihrt's blog](https://pihrt.com/elektronika/380-moje-raspberry-pi-plugin-ospy-mereni-teploty-pomoci-ds18b20). for more information for HW.

Plugin setup
-----------

* Check Enable Control A (B, C):  
  If checked Enable Control A (B, C) control for regulation A (B, C) is enabled.

* Probe input for ON: 
  Select input temperature probe for measuring.

* Temperature for output ON:  
  Temperature value for output xx switched to on.

* Maximum run time in activate:  
  Maximum duration when activating the output (in minutes and seconds). After this time, the output will turn off regardless of other events (conditions).  

* Probe input for OFF:  
  Select input temperature probe for measuring.

* Temperature for output OFF:  
  Temperature value for output xx switched to off.

* Select Output:  
  Select output for contol.

* Status:  
  Status window from the plugin.

Visit [Martin Pihrt's blog](https://pihrt.com/elektronika/380-moje-raspberry-pi-plugin-ospy-mereni-teploty-pomoci-ds18b20). for more information HW board with DS18B20 probe.
