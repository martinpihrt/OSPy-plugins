MQTT Run-once Readme
====

This MQTT Run-once plugin Relies on the base MQTT plugin, allows runonce programs to be set over MQTT. The received message is a sheet that contains: station number, time in seconds. 

Plugin setup
-----------

* Use MQTT Zones:  
If checked use button plugin is enabled.

* MQTT Scheduling topic:  
Type the topic subscribe to for run once commands.

* Status:  
Status window from the plugin.


MQTT data example
-----------

* Sending message in MQTT as list:  
  Station 1 -> OFF, 2 -> OFF, 3 -> ON 100 second, 4 -> ON 30 second...  
```bash
[0,0,100,30]    
``` 

* Sending message in MQTT as dict:  
  Station 1 -> OFF, 2 -> OFF, 3 -> ON 100 second, 4 -> ON 30 second...  
```bash
{"station name 1": 0, "station name 2": 0, "station name 3": 100, "station name 4": 30}  
```  
