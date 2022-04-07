Tank Monitor Readme
====

Tested in Python 3 and Python 2

This plugin measures the water level in the tank. If water level is small, this plugin stop irigation system (stop runing stations in scheduler) and sends E-mail with error Safety for master station pump if no water.


Plugin setup
-----------
* Check Use ultrasonic measuring the water level in the tank:    
  If checked measures the water level in the tank is active.  

* The distance from the sensor to the minimum water level in the tank:  
  Enter the distance from the sensor to the minimum water level in the tank (the tank bottom).  

* The distance from the sensor to the maximum water level in the tank:  
  Enter the distance from the sensor to the maximu water level in the tank (maximum to sensor - 2cm).  

* The water level from the bottom to the minimum water level in the tank:  
  Enter the level for the minimum water level in the tank.   

* Stop stations if minimum water level:  
  Stoping these stations if is minimum water level in the tank. Selector for stop stations in scheduler.

* Stop stations if sonic probe has fault:  
  If the level sensor fails, the above selected stations in the scheduler will stop.

* Cylinder diameter for volume calculation:  
  Enter the diameter for volume calculation.

* Display as liters or m3:  
  Show measured water as liters or m3.
  
* Send an E-mail with an error that there is minimum water in the tank:  
  For this function required E-mail plugin.

* Send an E-mail with an error if sonic probe has fault:   
  For this function required E-mail plugin.

* Regulate the maximum water level:  
  If checked, regulation have the maximal water level active.

* Maximum maintained water level:  
  If the measured water level exceeds this set value, the output is activated.  

* Maximum run time in activate:  
  Maximum duration when activating the output (in minutes and seconds). After this time, the output will turn off regardless of other events (conditions).    

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
