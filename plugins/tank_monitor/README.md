Tank Monitor Readme
====

This plugin measures the water level in the tank. If the water level falls below the specified limit above ground will stop watering, stop the scheduler and sent an E-mail with an error message.  


Plugin setup
-----------
* Check Use ultrasonic measuring the water level in the tank:    
  If checked measures the water level in the tank is active.  

* The distance from the sensor to the minimum water level in the tank:  
  Enter the distance from the sensor to the minimum water level in the tank (the tank bottom).  

* The distance from the sensor to the maximum water level in the tank:  
  Enter the distance from the sensor to the maximu water level in the tank (maximum to sensor - 2cm).  

* The water level from the bottom to the minimum water level in the tank:  
  Enter the level for the minimum water level in the tank. If it falls below this level will stop watering, stop the scheduler and send an E-mail (For this function required E-mail plugin).  

* Stop scheduller if is minimum water in the tank:
  Disabling the scheduler if is minimum water level in tank

* Cylinder diameter for volume calculation:
  Enter the diameter for volume calculation.

* Display as liters or m3:
  Show measured water as liters or m3.
  
* Send an E-mail with an error that there is minimum water in the tank:
  For this function required E-mail plugin.

* Send an E-mail with an error if sonic probe has fault: (and stop scheduler!)
  For this function required E-mail plugin.

* Regulate the maximum water level:
  If checked, regulation have the maximal water level active.

* Maximum maintained water level:
  If the measured water level exceeds this set value, the output is activated.    

* Minimum maintained water level:
  If the measured water level falls below this set value, the output is deactivated.   

* Select Output for regulation:
  Select Output for regulation zones.

* Enable logging:
  Enable logging and graphing.

* Maximum number of log records:
  Maximum number of log records (only for csv file).

* Interval for logging:
  Logging interval (minimum 1 minute).

* Select filter for graph history
  Without limits
  Day filter
  Month filter
  Year filter

* Status:  
  Status window from the plugin.  

The hardware should be connected as follows:
<a href="/plugins/tank_monitor/static/images/schematics.png"><img src="/plugins/tank_monitor/static/images/schematics.png" width="100%"></a>

Visit [Martin Pihrt's blog](http://pihrt.com/elektronika/339-moje-raspberry-pi-plugin-ospy-vlhkost-pudy-a-mozstvi-vody-v-tankua). for more information.
