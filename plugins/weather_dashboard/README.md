Weather Dashboard Readme
====

Tested in Python 3+

This plugin displays selected values from other OSPy plugins and OSPy sensors on one dashboard.
Each value is configured as one gauge. The dashboard can show gauges as round canvas meters or as simple text values.


Plugin setup
-----------
* Dashboard mode:  
  Select Canvas mode for round meters or Text mode for simple text values.

* Canvas size:  
  The number determines the size of the round meter in canvas mode.

* Text font:  
  The number determines the font size in text mode.

* Add Gauge:  
  Adds a new gauge with default settings.

* Delete:  
  Removes the selected gauge from the dashboard.

* Enabled:  
  If checked, this gauge is shown on the dashboard. If unchecked, the gauge is saved but hidden.

* Name:  
  Name displayed on the canvas meter or before the text value.

* Unit:  
  Unit displayed after the value, for example C, %, cm, l, V, or km/h.

* Source:  
  Select where the value is read from. Available sources are loaded from the plugin source registry.

* Channel:  
  Select the input channel for the selected source. The list changes automatically after changing Source.

* Value type:  
  Select which value from the selected source is displayed. The list changes automatically after changing Source.

* Ticks:  
  Comma separated scale labels for the canvas meter, for example 0,25,50,75,100.

* Min:  
  Minimum value of the canvas meter scale.

* Max:  
  Maximum value of the canvas meter scale.

* Red color from to:  
  Red color on the canvas meter scale according to the value from to.

* Blue color from to:  
  Blue color on the canvas meter scale according to the value from to.

* Green color from to:  
  Green color on the canvas meter scale according to the value from to.


Available sources
-----------
* Air Temperature:  
  Reads DS18B20 probes from the Air Temperature and Humidity Monitor plugin.

* Tank Monitor:  
  Reads percent and volume values from the Water Tank Monitor plugin.

* Current Loop:  
  Reads percent, cm, liter, and voltage values from the Current Loop Tanks Monitor plugin.

* Wind Monitor:  
  Reads wind speed from the Wind Speed Monitor plugin.

* OSPy Sensor:  
  Reads values from configured OSPy sensors.


Using the dashboard
-----------
After changing settings press Submit to save all gauges.
Open the dashboard page to view the configured values.
Values are refreshed automatically.
