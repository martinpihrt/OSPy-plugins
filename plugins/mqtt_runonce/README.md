MQTT Run-once Readme
====

Tested in Python 3+

This MQTT plugin adds an MQTT client to the OSPy daemon for other plugins to use to publish information and or receive commands over MQTT. This plugin needs paho-mqtt. If not installed paho-mqtt, plugin installs paho-mqtt in to the system himself. On first use (if run installation paho-mqtt) please wait for status. We can use a public Broker server to test'): http://www.hivemq.com/demos/websocket-client/.

This MQTT Run-once plugin allows runonce programs to be set over MQTT. The received message is a sheet that contains: station number, time in seconds. 

Plugin setup
-----------

* Use MQTT Zones:  
  If checked use button plugin is enabled.  

* MQTT Scheduling topic:  
  Type the topic subscribe to for run once commands.  

* MQTT Broker Host:  
  Type host for MQTT Broker.

* MQTT Broker Port:  
  Type Port for MQTT Broker.

* MQTT Broker Username:  
  Type User name for MQTT Broker.

* MQTT Broker Password:  
  Type Password for MQTT Broker.

* MQTT Publish Ready/Exit topic:  
  Type Publish for Ready/Exit MQTT topic.

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
