Pressurizer Readme
====

Tested in Python 3+

This plugin allows the main station (master pump) to be activated for a certain time before the station starts. 
This is to ensure that there is pressure in the pipeline before the valves are opened. 
This plugin requires setting master station to enabled. Setup this in options! And also enable the relay as master station in options.
Some valves require some switching pressure. The set "Run time" of the main station must not be longer than the set time before switching on the stations.


  Example: "Pre station run time" = 10 sec, "Run time" = max 10 seconds!

Plugin setup
-----------

* Enable:  
  If the check box is marked, the master pump is activated before turning on the stations.

* Ignore manual mode:  
  If the check box is marked, the master pump is activated before turning on the stations in manual mode (ignore manual).

* Ignore rain:  
  If the check box is marked, the master pump is activated before turning on the stations if rain is detected (ignore rain).

* Ignore rain delay:  
  If the check box is marked, the master pump is activated before turning on the stations if rain delay is detected (ignore rain delay).

* Use these stations:  
  These marked stations will be used and the pressurizer will respond to them.

* Pre station run time:  
  How many seconds before turning on station has turning on master station (1 - 999 sec).

* Run time:  
  For what time will turn on the master station (1 - 999 sec). 

* Wait after activation:
  How long after the relay is activated wait for another stations (in order not to activate the pressurizer before each switch is stations on) 0-999 min, 0-59 sec.
  All values should be positive and seconds should not exceed 59.

* Activated relay:
  If the check box is marked, the relay is activated before turning on the stations.
  
* Status:  
  Status window from the plugin.

Visit [Martin Pihrt blog](https://pihrt.com). for more information.  
