MQTT Home Assistant Readme
====

Tested in Python 3+


The MQTT HASS plugin implements MQTT Discovery for Home Assistant (HASS), including reporting and control of selected OSPy system settings, stations, programs, and sensor values over MQTT. MQTT Discovery enables automatic device and entity enrollment from the HASS user interface configuration panel, including plug-and-play availability detection, status, and control.

Available devices and entities
----

This plugin can expose:

* System controls: rain delay, water level adjustment, scheduler enable switch, manual operation switch, and rain sensor state.
* Stations: one switch entity for each enabled OSPy station.
* Programs: one button entity for each OSPy program.
* Stop buttons for stopping all stations from Home Assistant.
* Temperature and humidity extension values: DHT temperature, DHT humidity, and DS1 to DS6 temperature sensors from the air temperature and humidity plugin.
* DS18B20 error filtering: DS error values such as -127 can be sent or suppressed before publishing to Home Assistant.
* Water tank extension values: tank level percentage and tank volume from the ultrasonic tank monitor plugin.
* Current loop tank extension values: level percentage and volume for each enabled current loop tank.
* Availability status so Home Assistant can show unavailable entities when a station, sensor, or optional plugin is disabled or not responding.
