Sunrise and Sunset Readme
====

Only for Python 3

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
