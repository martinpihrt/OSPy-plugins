MQTT Readme
====

Tested in Python 3+

* MQTT client
This MQTT plugin adds an MQTT client to the OSPy daemon for other plugins to use to publish information and or receive commands over MQTT. On this page, the shared client is configured. Having a shared MQTT client simplifies configuration and lowers overhead on the OSPy process, network and broker. 
This plugin needs paho-mqtt. If not installed paho-mqtt, plugin installs paho-mqtt in to the system himself. On first use (if run installation paho-mqtt) please wait for status. We can use a public Broker server to test'): http://www.hivemq.com/demos/websocket-client/.

* MQTT secondary
The MQTT plugin allows multiple secondary OSPy controlers to be running with the control OSPy system running. This means that one OSPy system can act as the control driver for secondary systems that also use OSPy and have the mqtt_secondary plugin installed. The control OSPy sends a list containing the on/off states of all stations. The secondary system receives the list and checks whether it is necessary to switch on one of its stations or switch it off and make the necessary changes. All irrigation plans are set on the main system and it records all running stations as if they were on the OSPy control system itself. There is no feedback from the secondary  OSPy, so the control system assumes that all stations are working as they should. If enabled logging in secondary OSPy, stations running on this secondary OSPy are also stored in the log. This provides a way to check if the station on the secondary is working properly. Requirements: This plugin requires the main OSPy control system, which has the basic mqtt plugin and the mqtt_zones plugin installed. Each secondary OSPy system must have the basic mqtt plugin installed. You must this OSPy switch to manual mode! If you change settings you must restarting OSPy! 

Plugin setup (MQTT client)
-----------

* MQTT Broker Host:  
  Type host for MQTT Broker.

* MQTT Broker Port:  
  Type Port for MQTT Broker.

* MQTT Broker Username:  
  Type User name for MQTT Broker.

* MQTT Broker Password:  
  Type Password for MQTT Broker.

* MQTT Publish up/down topic:  
  Type Publish for up/down MQTT topic. 

Plugin setup (MQTT secondary)
-----------

* Use MQTT secondary:  
  Required to receive secondary MQTT messages.

* Zone topic:  
  The topic to subscribe to for control commands.

* First station number:  
  The number from the control OSPy of this secondary OSPy first station.

* Station count:  
  The number of station this secondary uses.


Visit [Martin Pihrt's blog](http://www.pihrt.com). for more information.

Example of settings for two OSPy systems
-----------
* OSPy control system
There are a total of 8 physical stations on the control OSPy system. We want to control another secondary OSPy system, which also has 8 physical stations. On the control OSPy system, set a total of 16 stations in the settings tab. The scheduler will control all 16 stations through the set programs. Run the "MQTT" plugin on the control OSPy system and set it (server, user, password, port) for connection to MQTT server (message broker). MQTT secondary will not be used on the control OSPy system! Next, we will run the "MQTT Zone Broadcaster" plugin on the control system. In the plugin settings, fill in the topic to which the station statuses will be sent on the MQTT server. If we have everything set up correctly, then when switching stations on and off on the control system, the states of the stations are sent to the MQTT server. 
Example of outgoing message:<br>
[{"status": "off", "reason": "system_off", "station": 0, "name": "Th\u016fje"}, {"status": "off", "reason": "system_off", "station": 1, "name": "Bor\u016fvky"}, {"status": "off", "reason": "system_off", "station": 2, "name": "Lavi\u010dka bok"}, {"status": "off", "reason": "system_off", "station": 3, "name": "Jalovec a krm\u00edtko"}, {"status": "off", "reason": "system_off", "station": 4, "name": "Z\u00e1hon u baz\u00e9nu "}, {"status": "off", "reason": "system_off", "station": 5, "name": "Vchod a ryb\u00edz"}, {"status": "off", "reason": "system_off", "station": 6, "name": "Filtrace baz\u00e9n"}, {"status": "off", "reason": "system_off", "station": 7, "name": "UV lampa"}, {"status": "off", "reason": "system_off", "station": 8, "name": "Hadice"}, {"status": "off", "reason": "system_off", "station": 9, "name": "\u010cerpadlo"}, {"status": "on", "reason": "program", "station": 10, "name": "Ventil\u00e1tor sklep"}, {"status": "on", "reason": "program", "station": 11, "name": "test"}]

* OSPy secondary system
There are a total of 8 physical stations. On the secondary OSPy system, set a total of 8 stations in the settings tab. Run the "MQTT" plugin on the control OSPy system and set it (server, user, password, port) for connection to MQTT server (message broker). MQTT secondary will be used on the secondary OSPy system! Fill in the Zone topic to receive messages with station statuses. With the control system we want to control this secondary system from station 1 from station 9. So we fill in the First station number to the number 9. Next, fill in the number of controlled stations from the control system. the control system will control stations 9-16. So we enter Station count to the number 8. we switch the secondary ospy system to manual control on the main screen! We can also use a plugin for sending emails from the slave system (as a feedback check of the device operation). Before the first use, we will restart the OSPy system!
