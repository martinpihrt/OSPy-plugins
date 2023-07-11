CHMI Readme
====

When is enabled extension retrieves data from the meteorological radar of the Czech Hydrometeorological Institute. The interactive map of the Czech Republic is based on an ESP32 microcontroller and contains 72 WS2812 RGB LEDs on the front - each for one district city. It is thus possible, for example, to display current warnings in given locations, or other dates. Different sensors can be connected and all usable pins are brought out on solder pads for possible connection of different sensors and devices. The board is equipped with a USB programming converter, so all you need to program it is a cable with a USB-C connector and, for example, the Arduino IDE. https://www.laskakit.cz/laskakit-interaktivni-mapa-cr-ws2812b/

Plugin setup
-----------
* Check Use CHMI:  
  If checked use CHMI plugin is enabled.

* Map IP address:
  IP address for laskakit map or other diy maps.

* Meteo map:
  A downloaded map from the Meteo Institute is displayed here.  
 
* Status:  
  Status window from the plugin.