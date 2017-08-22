Tank and Humidity Monitor Readme
====

This plugin measures the water level in the tank and soil moisture for the station. If the water level falls below the specified limit above ground will stop watering, stop the scheduler and sent an email with an error message.  


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
Default value is: Bot 33, Top 2, Minimum 6 cm.  
* Use measuring frequenci probe 1-8:  
  If checked to measure soil moisture (frequency) of the probe 1-8 for station 1-8.  
* Frequenci from sensor for 0% humidity:  
  Enter the frequency at 0% humidity from sensor frequency (moisture) apply to all 8 sensors.  
* Frequenci from sensor for 100% humidity:  
  Enter the frequency for 100% of the moisture sensor frequency (moisture) apply to all 8 sensors.  
Based on soil moisture varies run time station in the range of 0% humidity = 100% uptime, 100% humidity = 0% uptime station (watch this plugin is affected and the rest of plugins! Weather-based Water Level, Weather-based Rain Delay, Monthly Water Level).  
* Status:  
  Status window from the plugin.  

The hardware should be connected as follows:
<a href="/plugins/tank_humi_monitor/static/images/schematics.png"><img src="/plugins/tank_humi_monitor/static/images/schematics.png" width="100%"></a>

Visit [Martin Pihrt's blog](http://pihrt.com/elektronika/339-moje-raspberry-pi-plugin-ospy-vlhkost-pudy-a-mozstvi-vody-v-tankua). for more information.
