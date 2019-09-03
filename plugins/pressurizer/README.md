Pressurizer Readme
====

This plugin allows the main station (master pump) to be activated for a certain time before the station starts. 
This is to ensure that there is pressure in the pipeline before the valves are opened. 
This plugin requires setting master station to enabled. Setup this in options! And also enable the relay as master station in options.
Some valves require some switching pressure. The set "Run time" of the main station must not be longer than the set time before switching on the stations.


  Example: "Pre station run time" = 10 sec, "Run time" = max 10 seconds!  

Plugin setup
-----------

* Enable:  
  If the check box is marked, the master pump is activated before turning on the stations.

* Pre station run time:  
  How many seconds before turning on station has turning on master station (1 - 59 sec).

* Run time:  
  For what time will turn on the master station (1 - 59 sec).  

* Activated relay:
  If the check box is marked, the relay is activated before turning on the stations.
  
* Status:  
  Status window from the plugin.

Visit [Martin Pihrt blog](https://pihrt.com). for more information.  
