Tank Monitor Readme
====

This plugin measures the water level in the tank. If the water level falls below the specified limit above ground will stop watering, stop the scheduler and sent an email with an error message.  


Plugin setup
-----------
* Check Use ultrasonic measuring the water level in the tank:    
  if checked measures the water level in the tank is active.  

* The distance from the sensor to the minimum water level in the tank:  
  Enter the distance from the sensor to the minimum water level in the tank (the tank bottom).  

* The distance from the sensor to the maximum water level in the tank:  
  Enter the distance from the sensor to the maximu water level in the tank (maximum to sensor - 2cm).  

* The water level from the bottom to the minimum water level in the tank:  
  Enter the level for the minimum water level in the tank. If it falls below this level will stop watering, stop the scheduler and send an email (For this function required email plugin).  

* Cylinder diameter for volume calculation:
  Enter the diameter for volume calculation.

* Enable logging:
  Enable logging and graphing.

* Maximum number of log records:
  Maximum number of log records (only for csv file).

* Interval for logging:
  Logging interval (minimum 1 minute).

* Status:  
  Status window from the plugin.  

The hardware should be connected as follows:
<a href="/plugins/tank_monitor/static/images/schematics.png"><img src="/plugins/tank_monitor/static/images/schematics.png" width="100%"></a>

Visit [Martin Pihrt's blog](http://pihrt.com/elektronika/339-moje-raspberry-pi-plugin-ospy-vlhkost-pudy-a-mozstvi-vody-v-tankua). for more information.
