CHMI Readme
====

Tested in Python 3+

When is enabled extension retrieves data from the meteorological radar of the Czech Hydrometeorological Institute. The interactive map of the Czech Republic is based on an ESP32 microcontroller and contains 72 WS2812 RGB LEDs on the front - each for one district city. It is thus possible, for example, to display current warnings in given locations, or other dates. Different sensors can be connected and all usable pins are brought out on solder pads for possible connection of different sensors and devices. The board is equipped with a USB programming converter, so all you need to program it is a cable with a USB-C connector and, for example, the Arduino IDE. https://www.laskakit.cz/laskakit-interaktivni-mapa-cr-ws2812b/.
The extension allows you to set a rain delay when rain is detected at a set position on the map. The location coordinates are obtained from the OSPy settings from the weather/location menu. For proper function, you need to enter your location in the settings (for example, Prague).

Plugin setup
-----------
* Check Use CHMI:  
  If checked use CHMI plugin is enabled.

* Map IP address:
  IP address for laskakit map or other diy maps.

* Meteo map:
  A downloaded map from the Meteo Institute is displayed here.

* Use a rain delay:
  If the box is checked, a rain delay will be set if rain is detected. The location coordinates are obtained from the OSPy settings from the weather/location menu. For proper function, you need to enter your location in the settings (for example, Prague). Warning: you have to enable "Use Weather" and "Storm Glass API key". If you don't use a key, enter anything.

* Delay time:
  Delay time in hours.

* Intensity threshold:
  Intensity threshold for activate rain delay in my location. The detection logic is of the "or" type. This means that when the red color exceeds the value 50, or the green value 100, or the blue value 200, for example, rain is detected. 

* Enable logging:
  When an event is triggered in my location, the rgb value and the date and time when the event occurred are saved in the log.

* Maximum number of log records:
  0 = unlimited.     
 
* Status:  
  Status window from the plugin.