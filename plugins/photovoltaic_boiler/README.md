Photovoltaic Boiler Readme
====

Tested in Python 3+

This plugin needs enabled and corect setup the Air Temperature and Humidity Monitor. Reading temperature using from DS18B20 sensors connected to the external hardware board'). Or it is possible to use temperature measurement from OSPy sensors (LAN/Wi-Fi, radio...) Allows boiler heating regulation. Example: for heating boiler with photovoltaic solar panel. During the day, when the solar power plant has excess electricity, we heat the boiler from the solar power plant. In the evening hours, for example, from 8 p.m. to 11 p.m., and if the boiler temperature is lower than set, we switch the station (contactor) to the public network. The contactor has a changeover contact that connects the boiler either to the solar power plant or to the public grid. The boiler has its own thermostat with a set temperature to regulate the water temperature. This extension only switches between the public grid and PV if there was no solar heating.

Plugin setup
-----------

* Check Enable Control:  
  If checked Enable Control, control for regulation is enabled.  

* Sensors or plugin:  
  Select the temperature probes from sensors or from plugin air temperature.  

* Probe input for boiler: 
  Select the temperature sensor (its name) you want to use.

* Start Time for activating (hh:mm):
  If the boiler temperature is lower than set in this extension and the current time is greater than the start time, the output will be switched.

* Stop Time for activating (hh:mm): 
  If the boiler temperature is lower than set in this extension and the current time is less than the stop time, the output will be active.

* Temperature for ON output:
  Temperature for switch ON (boiler output).

* Select Output:  
  Select the output you want to control with regulation.  

* Show in footer:  
  Show data from plugin in footer on home page.  

* Status:  
  Status window from the plugin.

Visit [Martin Pihrt's blog](https://pihrt.com/elektronika/380-moje-raspberry-pi-plugin-ospy-mereni-teploty-pomoci-ds18b20). for more information HW board with DS18B20 probe.
