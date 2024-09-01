Sunrise and Sunset Readme
====

Only for Python 3+

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
  The help for the plugin contains a list of known cities, from which we can choose our position. If the city you are looking for is not in the list, we will use the box below and add our location. Other necessary data such as location, region... will be read from the available location.

* Custom Location:
  Somewhere on earth (own name). Example: Pilsen

* Custom region:
  The custom label serves for our better location orientation.

* Custom Timezone/name:
  UTC (Coordinated Universal Time). As the Earths rotation slows slightly, GMT is gradually lagging behind UTC. In order to be used in practical life, which is associated with the rotation of the Earth, UTC is maintained within ± 0.9 seconds of UT1; if this deviation is exceeded, the so-called leap second is added or (theoretically) removed at midnight on the next 30 June or 31 December, so that this day ends at 23.59: 60, resp. 23.59: 58 (as opposed to the usual 23.59: 59). This occurs on average once a year to a year and a half. As the Earth's rotation slows down, leap seconds are always added, but theoretically the possibility of taking a leap second is also considered. The International Earth Rotation and Reference Systems Service decides whether to use the leap second in the relevant term according to the Earth's rotation measurements.
  Example: UTC or Europe/Prague...

Note: custom location and custom region can be anything you like.

* Custom Latitude and longitude:
  Example city Pilsen 49°44′29",13°22′57"

* Show in footer:  
  Show data from plugin in footer on home page.

* Status:  
  Status window from the plugin.


Script injection
-----------
Plugin adds display of sunrise and sunset times in the homepage schedule (javascript injection).
https://github.com/martinpihrt/OSPy-plugins/tree/master/plugins/sunrise_and_sunset/static/images/sun_home.png