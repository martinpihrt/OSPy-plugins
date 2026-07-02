CHMI Readme
====

Tested in Python 3+

When enabled, the extension retrieves radar data from the selected meteorological service. The CHMI source uses Czech Hydrometeorological Institute PNG radar images. The SHMU source uses Slovak Hydrometeorological Institute OpenData HDF radar composites.

The SHMU source requires the h5py and numpy Python libraries. If they are missing, the settings page shows an install button and writes the installation progress to the status window. On Raspberry Pi OS the plugin installs the system packages `python3-h5py`, `python3-numpy`, and `python3-pillow`. After installation, set your location coordinates in the OSPy options so rain detection works correctly.

The interactive map of the Czech Republic is based on an ESP32 microcontroller and contains 72 WS2812 RGB LEDs on the front - each for one district city. It is thus possible, for example, to display current warnings in given locations, or other dates. Different sensors can be connected and all usable pins are brought out on solder pads for possible connection of different sensors and devices. The board is equipped with a USB programming converter, so all you need to program it is a cable with a USB-C connector and, for example, the Arduino IDE. https://www.laskakit.cz/laskakit-interaktivni-mapa-cr-ws2812b/.
The extension allows you to set a rain delay when rain is detected at a set position on the map. The location coordinates are obtained from the OSPy settings from the weather/location menu. For proper function, you need to enter your location in the settings (for example, Prague).

Radar PNG images are downloaded from the CHMI open data endpoint:
https://opendata.chmi.cz/meteorology/weather/radar/composite/maxz/png_masked/

Radar HDF files are downloaded from the SHMU open data endpoint:
https://opendata.shmu.sk/meteorology/weather/radar/composite/skcomp/zmax/

Plugin setup
-----------
* Radar data source:
  Select CHMI Czech Republic or SHMU Slovakia.

* SHMU radar libraries:
  This row is visible only when the SHMU dependencies are missing. Click "Install libraries" to install the required Python libraries. The status window shows progress and the final result.

* Use radar:
  If checked, the radar plugin is enabled.

* Send to HW map:
  If checked, detected rainy cities are sent to the external hardware map.

* Animate radar map:
  If checked, recent radar images from the last hour and available forecast frames are kept in RAM and animated on the settings page. Animation frames are not written to the SD card. The time slider below the map can be used to move through the animation manually. The timeline uses green frames for radar history and yellow frames for forecast data. Forecast frames are loaded from the CHMI forecast archive when available and cover approximately +10 to +60 minutes. The current location from the OSPy weather settings is drawn directly into the animation map. The static map remains available when animation data is not ready yet.

* Show on home page:
  If checked, a small animated CHMI radar widget is injected into the OSPy home page. The widget is shown only when CHMI is enabled and animation frames are available. Clicking the widget opens the CHMI plugin settings page.

* Map IP address:
  IP address for laskakit map or other diy maps.

* Meteo map:
  A downloaded map from the Meteo Institute is displayed here.

* Use a rain delay:
  If the box is checked, a rain delay will be set if rain is detected. The location coordinates are obtained from the OSPy settings from the weather/location menu. For proper function, you need to enter your location in the settings (for example, Prague). Warning: you have to enable "Use Weather" and "Storm Glass API key". If you don't use a key, enter anything.

* Delay time:
  Delay time in hours.

* Intensity threshold:
  Intensity threshold for activate rain delay in my location. Each RGB channel can be enabled or disabled. Enabled channels use "or" logic. This means that when enabled red exceeds the value 50, or enabled green 100, or enabled blue 200, for example, the pixel is marked as rainy. Disabled channels are ignored completely.

* Detection radius:
  Pixel radius around my location used for rain detection. The default value is 6 px. Instead of checking only one pixel, the plugin checks a circular area around the configured location.

* Minimum rainy pixels:
  Minimum percentage of pixels in the detection area that must exceed the intensity threshold before rain delay is activated. The default value is 10 %. This helps ignore random noise or a single bad radar pixel.

* Enable logging:
  When an event is triggered in my location, the rgb value and the date and time when the event occurred are saved in the log.

* Maximum number of log records:
  0 = unlimited.     
 
* Status:  
  Status window from the plugin. The status is refreshed automatically while the settings page is open.

* Download now:
  Starts a new radar data download without waiting for the next scheduled update.
