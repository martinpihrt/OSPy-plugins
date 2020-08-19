MQTT Run-once Readme
====

!!! NOT READY FOR USE!!!

This MQTT Run-once plugin Relies on the base MQTT plugin, allows runonce programs to be set over MQTT. The received message is a sheet that contains: station number, time in minutes and time in seconds. 

Plugin setup
-----------

* Use MQTT Zones:  
If checked use button plugin is enabled.

* MQTT Scheduling topic:  
Type the topic subscribe to for run once commands.

* Status:  
Status window from the plugin.

Visit [Martin Pihrt's blog](http://www.pihrt.com). for more information.

MQTT data example
-----------

Command for run-now station 1 for 5 minutes and 20 seconds:
```bash
[{0,5,20}]
```

Command for run-now station 1 and 3 for 5 minutes and 20 seconds (6 minutes and 10 seconds):
```bash
[{0,5,20},{2,6,10}]
```
