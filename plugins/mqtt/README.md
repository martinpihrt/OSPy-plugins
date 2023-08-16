MQTT Readme
====

Tested in Python 3+

If you change settings you must restarting OSPy!

MQTT core
-----------

This MQTT plugin adds an MQTT client to the OSPy daemon for other plugins to use to publish information and or receive commands over MQTT. On this page, the shared client is configured. Having a shared MQTT client simplifies configuration and lowers overhead on the OSPy process, network and broker. 
This plugin needs paho-mqtt. If not installed paho-mqtt, plugin installs paho-mqtt in to the system himself. On first use (if run installation paho-mqtt) please wait for status. We can use a public Broker server to test'): http://www.hivemq.com/demos/websocket-client/.

MQTT manual control
-----------

The MQTT plugin allows multiple secondary OSPy controlers to be running with the control OSPy system running. This means that one OSPy system can act as the control driver for secondary systems that also use OSPy and have the mqtt plugin installed. The control OSPy sends a list containing the on/off states of all stations. The secondary system receives the list and checks whether it is necessary to switch on one of its stations or switch it off and make the necessary changes. All irrigation plans are set on the main system and it records all running stations as if they were on the OSPy control system itself. There is no feedback from the secondary  OSPy, so the control system assumes that all stations are working as they should. If enabled logging in secondary OSPy, stations running on this secondary OSPy are also stored in the log. This provides a way to check if the station on the secondary is working properly. You must this OSPy switch to manual mode! MQTT core is required for this feature.

MQTT zones state
-----------

Status of all stations will be sent to the given topic. MQTT core is required for this feature. Example: [{"station": 0, "status": "off", "name": "Station 01", "reason": ""}, {"station": 1, "status": "off", "name": "Station 02", "reason": ""}, {"station": 2, "status": "off", "name": "Station 03", "reason": ""}, {"station": 3, "status": "off", "name": "Station 04", "reason": ""}, {"station": 4, "status": "off", "name": "Station 05", "reason": ""}, {"station": 5, "status": "off", "name": "Station 06", "reason": ""}, {"station": 6, "status": "off", "name": "Station 07", "reason": ""}, {"station": 7, "status": "off", "name": "Station 08", "reason": ""}]

MQTT run-once
-----------

will be received from the given topic for commands to start stations. MQTT core is required for this feature. The received message is a sheet that contains list or dict (station number, time in seconds.) Note: the list or dict must be as long as the number of stations. Otherwise, the processing will not take place! We can use a dictionary or list for control. The list is simpler than the dictionary (we do not have to change it in the commands every time we change the name of a station. You must this OSPy switch to scheduler mode! If you change settings you must restarting OSPy! 

MQTT get values
-----------

The status of the system settings will be sent to the given topic (cpu temperature, manual mode, scheduler enabled...) This list is sent whenever there is a change in the system. Example: {"cpu_temp": "47.1", "temp_unit": "C", "manual_mode": true, "scheduler_enabled": true, "system_name": "Test VIP2", "output_count": 8, "rain_sensed": false, "rain_block": 0, "level_adjustment": 1.0, "ospy_version": "3.0.58", "release_date": "2023-08-13", "uptime": "3. day 05:38"}

Plugin setup (MQTT core)
-----------

* Use MQTT core:
  Required to receive and send MQTT messages. This MQTT core is always required for all options below.

* Broker Host:  
  Type host for MQTT Broker. For test use: http://www.hivemq.com/demos/websocket-client/.

* Broker Port:  
  Type Port for MQTT Broker. Range for port is 80 to 65635.

* Broker Username:  
  Type User name for MQTT Broker.

* Broker Password:  
  Type Password for MQTT Broker.

* Up/down topic:  
  Type Publish for up/down topic. 

Plugin setup (MQTT manual control)
-----------

* Use manual control:  
  After checking the box, station control commands (on/off) will be received from the given topic. This OSPy will be controlled by another device. Warning: only works if OSPy is in manual mode! MQTT core is required for this feature.

* Control topic:  
  The topic to subscribe to for control commands.

* First station number:  
  The number from the control OSPy of this secondary OSPy first station.

* Station count:  
  The number of station this secondary uses.

Plugin setup (MQTT zones state)
-----------

* Use zones:  
  When the box is checked, the statuses of all stations will be sent to the given topic. MQTT core is required for this feature.

* Zones topic:  
  The topic to broadcast from zones.

Plugin setup (MQTT run-once)
-----------

* Use run-once:  
  When the box is checked, will be received from the given topic for commands to start stations. MQTT core is required for this feature.

* Run-once topic:  
  The topic to broadcast from zones.   


Example of settings for two OSPy systems (main OSPy and more secondary OSPy)
-----------
* OSPy control system
There are a total of 8 physical stations on the control OSPy system. We want to control another secondary OSPy system, which also has 8 physical stations. On the control OSPy system, set a total of 16 stations in the settings tab. The scheduler will control all 16 stations through the set programs. Run the "MQTT" plugin on the control OSPy system and set it (server, user, password, port) for connection to MQTT server (message broker). Manual MQTT control will not be used on the OSPy controller! Next, check "MQTT Use zones" for sharing stations status.

Example of outgoing message (main OSPy): [{"station": 0, "status": "off", "name": "Station 01", "reason": ""}, {"station": 1, "status": "off", "name": "Station 02", "reason": ""}, {"station": 2, "status": "off", "name": "Station 03", "reason": ""}, {"station": 3, "status": "off", "name": "Station 04", "reason": ""}, {"station": 4, "status": "off", "name": "Station 05", "reason": ""}, {"station": 5, "status": "off", "name": "Station 06", "reason": ""}, {"station": 6, "status": "off", "name": "Station 07", "reason": ""}, {"station": 7, "status": "off", "name": "Station 08", "reason": ""}]

* OSPy secondary system
There are a total of 8 physical stations. On the secondary OSPy system, set a total of 8 stations in the settings tab. Run the "MQTT" plugin on the control OSPy system and set it (server, user, password, port) for connection to MQTT server (message broker). MQTT manual control will be used on the secondary OSPy system! Fill in the Zones topic to receive messages with station statuses. With the control system we want to control this secondary system from station 1 from station 9. So we fill in the First station number to the number 9. Next, fill in the number of controlled stations from the control system. the control system will control stations 9-16. So we enter Station count to the number 8. we switch the secondary ospy system to manual control on the main screen! We can also use a plugin for sending emails from the slave system (as a feedback check of the device operation). Before the first use, we will restart the OSPy system!

More information can be found in the help directly in the plugin (help button)
