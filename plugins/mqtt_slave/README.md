MQTT Slave Readme
====

This MQTT Relies on the base MQTT plugin.
Allows this OSPy system to be controlled by another (master) OSPy system over MQTT.    

Plugin setup
-----------

* Use MQTT Zones:  
If checked use button plugin is enabled.

* Zone topic:  
The topic to subscribe to for control commands.

* First station number:  
The number from the master of this slave's first station.

* Station count:  
The number of station this slave uses.

* Status:  
Status window from the plugin.

-----------

The mqtt_slave plugin allows multiple systems running OSPy to be controlled through a single user interface over MQTT.

That means a single OSPy system can act as a master controller for one or more remote (slave) systems which are also running OSPy and have the the mqtt_slave plugin installed.

When this plugin system is running, the master OSPy broadcasts a list containing the on/off states of all stations.

When a slave receives the list it checks to see if any of it's  stations need to be switched on or off and makes the necessary changes.

Each slave can have a master station configured to work with its local stations.

All irrigation schedules are set up on the master and it logs all station runs as if they are on the master itself. 

There is no feedback from the slave(s) so the master "assumes" that all stations are operating as expected. 

If logging is enabled on the slave, station runs on that slave will be logged. This provides a way to check that the stations on the slave have been operating properly.

# Requirements

* This plugin requires a master OSPy system which has the base mqtt plugin and the mqtt_zones plugin installed.
* Each slave OSPy system must have the base mqtt plugin and the mqtt_slave plugin installed.
* An MQTT broker such as mosquitto is also required to be accessible by each OSPy device. 
* This broker can be on a different part of the local network, on a remote network, or installed on one of the OSPy systems such as the master OSPy.

# Setting up and using the mqtt_slave plugin

## Master set up

Instal eclipse paho if not already on the Pi
Install the base mqtt plugin and the mqtt_zones plugins

### Configure MQTT plugin

MQTT Broker Host This will be the URL of the MQTT broker or localhost if the broker is running on the OSPy master
MQTT Broker Port: Default is 1883 but may be different depending on your MQTT broker
MQTT Broker Username: Default is mosquitto but depends on your setup
MQTT Broker Password: Depends on your setup. Use pass as default
MQTT Publish up/down topic Can be left blank
MQTT Client ID A unique name for each OSPy system. Default is OSPy but can be changed on Options page > System name

Configure the base mqtt_zones plugin (MQTT ZONE BROADCASTER on the plugins menu):
Zone topic: Can be anything you like for example OSPy_zones. This same is also to be used on each slave

Configure number of stations:
Adjust the number of stations the master shows to be equal to or greater than the total number of stations used by the master and all slaves combined.
This can be done under Options > Station handling > Extension boards: Each increase in the number of extension boards adds 8 stations to the master UI.

Create irrigation programs for all stations.

## Slave set up

Instal eclipse paho if not already on the Pi
Install the base mqtt plugin and the mqtt_slave plugins
Change the system name to a name that will be unique among the OSPys in your setup. Do this on the OSPy Options page.

### Configure the base mqtt plugin:

MQTT Broker Host This will be the URL of the MQTT broker or localhost if the broker is running on this OSPy.
MQTT Broker Port: Default is 1883 but may be different depending on your MQTT broker
MQTT Broker Username: Default is mosquitto but depends on your setup
MQTT Broker Password: Depends on your setup. Use pass as default
MQTT Publish up/down topic Can be left blank
MQTT Client ID A unique name for each OSPy system. Default is OSPy but should be changed on Options page > System name:

### Configure the mqtt_slave plugin:

Zone topic: This must be the same topic you entered on the master on the MQTT Zones Plugin setup page.
First station number: This will be the station number the master is using for the first station on this slave.
This will determine which irrigation schedules will correspond to the stations on this slave.
Station count: How many asctive stations does this slave have including the master station if used.
On the OSPy home screen set the mode to Manual. The slave will only react to signals from the master when it is in manual mode.
Enable logging if desired. Do this on the Options page > Logging Be sure the Enable logging box is filled.

## Test your setup:
With your master and at least one slave set up and running, You can switch the master to manual and you can test individual stations.
