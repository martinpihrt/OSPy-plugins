Sunrise and Sunset Readme
====

Only for Python 3+

The plug-in includes a `plugin.json` manifest and reports its worker, Astral
availability, location, sunrise, sunset, scheduled programs, dependency
installation and calculation errors through the OSPy system health interface.
The mobile interface provides today's astronomical values and a fixed 24-hour timeline with night before sunrise and after sunset; it does not expose irrelevant history-range controls.

From version 1.0.5 the plug-in is also the astronomical provider for native OSPy sunrise and sunset program types. It exposes a read-only availability check and the calculated dawn, sunrise, noon, sunset and dusk values for a requested date. OSPy keeps calendar filtering, offsets, allowed time windows and irrigation scheduling in the core; this plug-in remains responsible for Astral, location and timezone calculation. The older plug-in option for launching an existing program remains available and is not removed.

If the plug-in is disabled, Astral is unavailable or no valid location can be resolved, the provider returns no guessed time. OSPy therefore retains the saved solar program but does not generate its automatic occurrence until the provider recovers. Manual program control and non-solar programs are unaffected.

When the OSPy weather location is used, the displayed Astral region comes from the location detected by OSPy. Older installations use the detected country code until the weather location is looked up again.

## Mobile application

Open Plug-ins and expand Astro Sunrise and Sunset operating data in the OSPy mobile application. The native 24-hour timeline always represents the current day, uses gray bands before sunrise and after sunset, marks sunrise, sunset and the current time, and therefore does not offer history-range buttons. The astronomical metrics and timeline refresh automatically while the panel remains expanded.

This extension requires the Astral Python package. If Astral is missing, the status page shows an Install libraries button and writes the installation progress to the status log. On Raspberry Pi OS install it with:

```
sudo apt install python3-astral
```

This extension allows you to run a specific program depending on sunrise or sunset. This extension calculate the following astronomical data.

* Dawn
  The time in the morning when the sun is a specific number of degrees below the horizon.
* Sunrise
  The time in the morning when the top of the sun breaks the horizon (asuming a location with no obscuring features.)
* Noon
  The time when the sun is at highest point directly above the observer.
* Sunset
  The time in the evening when the sun is about to disappear below the horizon (asuming a location with no obscuring features.)
* Dusk
  The time in the evening when the sun is a specific number of degrees below the horizon.
* Moon Phase
  The moon phase method returns an number describing the phase, where the value is between 0 and 27.99. The following lists the mapping of various values to the description of the phase of the moon.

More information can be found after installing the plugin in the plugin help. 

In terms of economy and good usability of moisture, early morning watering is optimal. We can also spray the leaves, because they will dry out before the sun can burn them. Plants should not be sprayed at all at noon: water droplets act like small optical lenses on the leaves, in which the sun's rays concentrate and cause burns on the leaves. In addition, it is uneconomical, because part of the water evaporates already in the air and another part immediately upon impact with the hot ground. If the plants wither during the day, we will help them with moisture directly to the roots. In the evening it should be watered only to the roots. The sprinkled leaves do not have time to dry and there is a risk of fungal diseases. Otherwise, evening watering is advantageous because the water absorbs well into the soil overnight and the plants have it in store for the next hot day. 


Plugin setup
-----------

* Use astro plugin:  
  If the box is checked, the plugin checks Sunrise and Sunset updates every hour.

* City Location:
  Select a city from the Astral list to use its built-in location. Leave the city unselected to use the coordinates from OSPy weather settings and the time zone configured on the OSPy host. Weather and location must be enabled in OSPy. The plug-in no longer stores a separate manual location.

* Show in footer:  
  Show data from plugin in footer on home page.

* Status:  
  Status window from the plugin.


Script injection
-----------
Plugin adds display of sunrise and sunset times in the homepage schedule (javascript injection).
https://github.com/martinpihrt/OSPy-plugins/tree/master/plugins/sunrise_and_sunset/static/images/sun_home.png
