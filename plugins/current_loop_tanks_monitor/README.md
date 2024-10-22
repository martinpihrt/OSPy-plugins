Current Loop Tanks Monitor Readme
====

Tested in Python 3+

This plug-in module measures the water level in 4 tanks. A differential pressure sensor with a 4-20mA/24V current loop (e.g. TL-136) is used for the measurement. If the water level is low, this plug-in stops the irrigation system (stops the running stations in the scheduler) and sends an error e-mail.


Plugin setup
-----------
* Check Use measuring the water level in the tanks:    
  If checked measures the water level in the tanks is active.  

* Address of the converter on the bus:  
  Address selection  
  Adr pin connecting to:
  GND = 0x48  
  VDD = 0x49  
  SDA = 0x4A
  SCL = 0x4B

* The voltage for the minimum water level in the tank 1-4:  
  Enter the voltage from the sensor for the minimum water level in the tank.    

* The voltage for the maximum water level in the tank 1-4:  
  Enter the voltage from the sensor for the maximum water level in the tank.  

* The water level for the minimum water level in the tank 1-4 (for event):  
  Enter the level for the minimum water level in the tank.   

* Stop stations if minimum water level in tank 1-4:  
  Stoping these stations if is minimum water level in the tank. Selector for stop stations in scheduler.

* Cylinder diameter for volume calculation tank 1-4:  
  Enter the diameter for volume calculation.

* Display as liters or m3 tank 1-4:  
  Show measured water as liters or m3.    

* Use averaging for samples tank 1-4:
  If checked, averaging of measured values will be performed (this option affects the speed of response to the measured value).

* Number of samples for average tank 1-4:  
  Enter the number count for samples.
  
* Send an E-mail with an error that there is minimum water in the tank 1-4:  
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

* Enable local logging:  
  Enable logging and graphing.

* Check Enable SQL logging:  
  If checked enabled logging save measure value to SQL database. This option requires the Database Connector extension to be installed and configured. The button will delete the tankmonitor table from the database, thus deleting all saved data from this extension! This promotion is non-refundable!  

* Maximum number of log records:  
  Maximum number of log records (only for csv file).

* Interval for logging:  
  Logging interval (minimum 1 minute).

* Select filter for graph history  
  From - To selector (date time)

* Status:  
  Status window from the plugin.  

Visit [Martin Pihrt's blog](https://pihrt.com/elektronika/482-mereni-vysky-tl136). for more information.
